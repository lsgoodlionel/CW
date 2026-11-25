#!/usr/bin/env python3
"""Before a Compose upgrade, verify the configured password against the live DB.

Only status labels are printed. Passwords stay in process memory and Docker exec stdin.
"""
import json
import secrets
import subprocess
import sys
from urllib.parse import unquote, urlsplit


def run(args, *, input_text=None):
    return subprocess.run(args, input=input_text, text=True, capture_output=True)


def fail(message):
    print(f"[数据库预检] {message}", file=sys.stderr)
    return 1


def main():
    config = run(["docker", "compose", "config", "--format", "json"])
    if config.returncode:
        return fail("无法解析 Compose 配置；未更改容器。")
    try:
        services = json.loads(config.stdout)["services"]
        db_env = services["db"]["environment"]
        backend_env = services["backend"]["environment"]
        user, password, database = (db_env[key] for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"))
        url = urlsplit(backend_env["DATABASE_URL"])
        if (unquote(url.username or ""), unquote(url.password or ""), url.path.lstrip("/")) != (user, password, database):
            return fail("后端连接配置与数据库服务配置不一致；未更改容器。")
    except (KeyError, TypeError, ValueError):
        return fail("数据库连接配置不完整；未更改容器。")

    db = run(["docker", "compose", "ps", "-q", "db"])
    if db.returncode:
        return fail("无法查询数据库容器；未更改容器。")
    cid = db.stdout.strip()
    if not cid:
        print("[数据库预检] 首次安装，数据库容器尚不存在；跳过现有账户检查。")
        return 0
    inspected = run(["docker", "inspect", cid])
    if inspected.returncode:
        return fail("无法检查数据库容器；未更改容器。")
    try:
        info = json.loads(inspected.stdout)[0]
        addresses = [n.get("IPAddress") for n in info["NetworkSettings"]["Networks"].values() if n.get("IPAddress")]
        if not addresses:
            return fail("数据库容器没有可用的网桥地址；未更改容器。")
        actual_env = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
    except (KeyError, IndexError, TypeError, ValueError):
        return fail("无法读取数据库容器状态；未更改容器。")
    if actual_env.get("POSTGRES_PASSWORD") != password:
        print("[数据库预检] 运行中数据库容器的初始化密码环境与当前配置不同；以实际账户认证结果为准。")

    # The local socket and 127.0.0.1 can be trusted by pg_hba.conf. Connect to
    # the bridge address and reject a false positive if even a wrong password works.
    command = ('IFS= read -r pw; export PGPASSWORD="$pw"; '
               'psql -X -h "$3" -U "$1" -d "$2" -Atqc "SELECT 1" >/dev/null 2>&1')
    def authenticates(candidate):
        result = run(["docker", "exec", "-i", cid, "sh", "-c", command, "sh", user, database, addresses[0]],
                     input_text=candidate + "\n")
        return result.returncode == 0

    if not authenticates(password):
        return fail("当前配置的数据库密码认证失败。停止升级；先核对现有账户与 .env，勿重建数据卷。")
    if authenticates(secrets.token_hex(32)):
        return fail("数据库连接未验证密码，无法确认凭据一致；停止升级。")
    print("[数据库预检] 当前配置密码通过数据库网桥认证。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
