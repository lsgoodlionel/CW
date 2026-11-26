#!/usr/bin/env python3
"""Install a paper-only GitHub token from the server terminal, never stdout/argv.

Run as root on the deployed host. The token is read without echo, checked against
the private paper repository, written only to the root-readable .env, and tested
with one manual diagnostic upload. Failed validation restores the prior .env.
"""
import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

APP_DIR = Path(os.environ.get("APP_DIR", "/opt/cw"))
ENV_FILE = APP_DIR / ".env"
REPO = "lsgoodlionel/paper"


def run(args, *, env=None):
    return subprocess.run(args, cwd=APP_DIR, env=env, capture_output=True, text=True)


def fail(message):
    print(f"[诊断配置] {message}", file=sys.stderr)
    return 1


def health_ok():
    response = run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5",
                    "http://127.0.0.1:18080/api/health"])
    return response.stdout == "200"


def wait_health():
    for _ in range(24):
        if health_ok():
            return True
        time.sleep(5)
    return False


def recreate_backend(image_ref):
    env = os.environ.copy()
    env["BACKEND_IMAGE"] = image_ref
    return run(["docker", "compose", "up", "-d", "--no-deps", "--force-recreate", "--no-build",
                "--pull", "never", "backend"], env=env).returncode == 0


def main():
    if os.geteuid() != 0 or not sys.stdin.isatty():
        return fail("请在服务器交互终端用 sudo 执行；令牌不得通过命令参数或聊天传递。")
    if not ENV_FILE.is_file() or not health_ok():
        return fail("部署配置不存在或服务未健康；未更改配置。")
    config = run(["docker", "compose", "config", "--format", "json"])
    if config.returncode:
        return fail("Compose 配置不可读取；未更改配置。")
    try:
        service_env = json.loads(config.stdout)["services"]["backend"]["environment"]
    except (KeyError, ValueError, TypeError):
        return fail("诊断服务配置不完整；未更改配置。")
    if service_env.get("PAPER_REPO") != REPO:
        return fail("目标仓库不是预期的 paper；未更改配置。")

    rows = ENV_FILE.read_text().splitlines(keepends=True)
    positions = [i for i, row in enumerate(rows) if row.startswith("PAPER_REPO_TOKEN=")]
    if len(positions) != 1:
        return fail(".env 中 PAPER_REPO_TOKEN 配置不唯一；未更改配置。")
    try:
        token = getpass.getpass("请输入仅授权 paper 仓库的细粒度 PAT（输入不回显）：")
    except (EOFError, KeyboardInterrupt):
        return fail("输入已取消；未更改配置。")
    if not token or not token.isascii() or any(c.isspace() for c in token) or "#" in token:
        return fail("令牌格式无效；未更改配置。")

    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}",
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "User-Agent": "CW-Diagnostics-Setup/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            valid_repo = json.load(response).get("full_name", "").lower() == REPO.lower()
    except Exception:
        return fail("GitHub 私有仓库读取验证失败；未更改配置。")
    if not valid_repo:
        return fail("令牌未授权预期仓库；未更改配置。")
    print("[诊断配置] 私有仓库读取验证通过。")

    previous = run(["docker", "compose", "ps", "-q", "backend"]).stdout.strip()
    inspected = run(["docker", "inspect", previous]) if previous else None
    if not inspected or inspected.returncode:
        return fail("后端容器不可检查；未更改配置。")
    image_ref = json.loads(inspected.stdout)[0]["Config"]["Image"]
    if not image_ref:
        return fail("后端镜像引用不可用；未更改配置。")

    backup = APP_DIR / "backups" / ("env-pre-diag-" + time.strftime("%Y%m%d-%H%M%S"))
    backup.parent.mkdir(exist_ok=True)
    shutil.copy2(ENV_FILE, backup)
    os.chmod(backup, 0o600)
    rows[positions[0]] = "PAPER_REPO_TOKEN=" + token + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".env.diag.", dir=APP_DIR)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.writelines(rows)
        os.chmod(temporary, 0o600)
        os.replace(temporary, ENV_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    del token

    def rollback():
        shutil.copy2(backup, ENV_FILE)
        os.chmod(ENV_FILE, 0o600)
        recreate_backend(image_ref)
        print("[诊断配置] 已恢复旧配置；健康=" + ("200" if wait_health() else "异常"))

    if not recreate_backend(image_ref) or not wait_health():
        rollback()
        return fail("后端重建或健康检查失败。")
    current = run(["docker", "compose", "ps", "-q", "backend"]).stdout.strip()
    if not current:
        rollback()
        return fail("后端容器未运行。")
    enabled = run(["docker", "exec", current, "python", "-c", "from app import diag; print(diag.enabled())"])
    if enabled.returncode or enabled.stdout.strip() != "True":
        rollback()
        return fail("诊断上传未启用。")
    uploaded = run(["docker", "exec", current, "python", "-c",
                    'from app import diag; print(bool(diag.report_manual("配置验证")))'])
    if uploaded.returncode or uploaded.stdout.strip() != "True":
        rollback()
        return fail("诊断测试上传失败；请确认令牌具有 Contents: Read and write 权限。")
    print("[诊断配置] 测试上传成功；自动上传已启用；健康=200。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
