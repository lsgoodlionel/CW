"""诊断模块验证(不触网:monkeypatch 上传函数)。"""
import io
import time
import zipfile

from app import diag
from app.config import settings


def run():
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    # 关闭态:无 token → enabled False,report 均为安全 no-op
    settings.paper_repo_token = ""
    check("无token时禁用", diag.enabled() is False)
    check("禁用时手动上传返回None", diag.report_manual("x") is None)
    try:
        diag.report_exception(ValueError("boom"))   # 不应抛出
        check("禁用时出错上报不抛出", True)
    except Exception:
        check("禁用时出错上报不抛出", False)

    # 环形缓冲
    diag.install_log_capture()
    import logging
    logging.getLogger("cw.test").error("测试错误行-ABC")
    check("环形缓冲记录日志", any("测试错误行-ABC" in ln for ln in diag.recent_lines()))

    # 打包内容
    zbytes = diag._build_zip({"app": "CW", "signature": "s1"}, "TRACE-XYZ")
    zf = zipfile.ZipFile(io.BytesIO(zbytes))
    names = set(zf.namelist())
    check("zip含三文件", {"meta.json", "traceback.txt", "recent.log"} <= names)
    check("zip含traceback", b"TRACE-XYZ" in zf.read("traceback.txt"))

    # 启用态:monkeypatch _upload 记录调用,不触网
    calls = []
    orig_upload = diag._upload
    diag._upload = lambda path, content, message: (calls.append((path, content)), 201)[1]
    settings.paper_repo_token = "fake-token"
    settings.log_app_slug = "CW"
    settings.error_report_cooldown = 600
    try:
        check("有token时启用", diag.enabled() is True)
        path = diag.report_manual("手动测试")
        check("手动上传路径正确", path is not None and path.startswith("CW/logs/") and path.endswith("_manual.zip"))
        check("手动上传已调用_upload", len(calls) == 1)
        up_zip = zipfile.ZipFile(io.BytesIO(calls[0][1]))
        check("上传内容为合法zip", "meta.json" in up_zip.namelist())

        # 出错上报 + 节流去重:同签名两次仅上传一次
        diag._last_upload.clear()
        calls.clear()

        def _boom():
            raise ValueError("同一处错误")
        for _ in range(2):
            try:
                _boom()
            except ValueError as e:
                diag.report_exception(e, {"path": "/x"})
        time.sleep(0.6)                       # 等后台线程完成
        check("同类错误节流仅上传一次", len(calls) == 1)
    finally:
        diag._upload = orig_upload
        settings.paper_repo_token = ""

    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
