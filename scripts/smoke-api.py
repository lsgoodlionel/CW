"""对运行中的后端做 API 冒烟检查(仅用标准库,CI 与本地通用)。

覆盖完整应用栈:鉴权中间件、操作日志中间件、数据库、Excel/PDF 导出与备份往返。
用法:python scripts/smoke-api.py [base_url] [username] [password]
默认 http://127.0.0.1:8000 admin admin123;任一步失败即以非零退出。
"""
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import date

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
USER = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin123"
failures: list[str] = []
token = ""


def call(method, path, body=None, headers=None, raw=False):
    """发起请求,返回 (状态码, 响应体);JSON 自动解析,raw=True 时返回字节。"""
    h = {"Authorization": f"Bearer {token}"} if token else {}
    h.update(headers or {})
    data = body
    if isinstance(body, (dict, list)):
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            content = r.read()
            return r.status, content if raw else _json(content)
    except urllib.error.HTTPError as e:
        return e.code, _json(e.read())


def _json(content):
    try:
        return json.loads(content)
    except ValueError:
        return content


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def wait_ready():
    for _ in range(60):
        try:
            if call("GET", "/api/health")[0] == 200:
                return True
        except OSError:
            pass
        time.sleep(1)
    return False


def multipart(field, filename, content: bytes):
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; "
            f"filename=\"{filename}\"\r\nContent-Type: application/zip\r\n\r\n").encode()
    body += content + f"\r\n--{boundary}--\r\n".encode()
    return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def main():
    global token
    check("服务就绪 /api/health", wait_ready())
    if failures:
        return

    status, _ = call("GET", "/api/accounts")
    check("未登录访问被拒绝(401)", status == 401, status)

    status, res = call("POST", "/api/auth/login", {"username": USER, "password": PASSWORD})
    token = res.get("token", "") if isinstance(res, dict) else ""
    check("登录获得令牌", status == 200 and bool(token), status)
    if not token:
        return

    status, me = call("GET", "/api/auth/me")
    check("当前用户", status == 200 and me.get("username") == USER, status)

    status, about = call("GET", "/api/about")
    check("关于系统返回版本", status == 200 and bool(about.get("version")), status)

    status, accounts = call("GET", "/api/accounts")
    check("预置科目 81 个", status == 200 and len(accounts) == 81,
          f"{status} {len(accounts) if isinstance(accounts, list) else accounts}")

    by_code = {a["code"]: a["id"] for a in accounts} if isinstance(accounts, list) else {}
    today = date.today()
    voucher = {
        "voucher_date": today.isoformat(), "note": "冒烟测试凭证", "status": "posted",
        "entries": [
            {"summary": "支付办公费", "account_id": by_code.get("6602"), "debit": "100.00", "credit": "0"},
            {"summary": "支付办公费", "account_id": by_code.get("1002"), "debit": "0", "credit": "100.00"},
        ],
    }
    status, v = call("POST", "/api/vouchers", voucher)
    check("新建凭证", status == 201 and isinstance(v, dict) and v.get("id"), f"{status} {v}")

    status, page = call("GET", "/api/vouchers")
    before = page.get("total") if isinstance(page, dict) else None
    check("凭证列表", status == 200 and isinstance(before, int) and before >= 1, status)

    status, dash = call("GET", f"/api/reports/dashboard?period_type=month&ref_date={today.isoformat()}")
    check("仪表盘", status == 200, status)

    q = f"report_type=month&year={today.year}&month={today.month}"
    status, _ = call("GET", f"/api/reports/official?{q}")
    check("官方财务报表", status == 200, status)
    status, xls = call("GET", f"/api/reports/export-excel?{q}", raw=True)
    check("财务报表导出 .xls", status == 200 and isinstance(xls, bytes) and len(xls) > 1000, status)
    status, ledger = call("GET", f"/api/ledgers/export-excel?ledger_type=all&{q}", raw=True)
    check("会计账簿导出 Excel", status == 200 and isinstance(ledger, bytes) and ledger[:2] == b"PK", status)
    status, pdf = call("GET", f"/api/logs/export-pdf?year={today.year}", raw=True)
    check("操作日志导出 PDF", status == 200 and isinstance(pdf, bytes) and pdf[:4] == b"%PDF", status)

    status, backup = call("GET", "/api/data/export", raw=True)
    check("导出备份 zip", status == 200 and isinstance(backup, bytes) and backup[:2] == b"PK", status)
    if isinstance(backup, bytes) and backup[:2] == b"PK":
        body, headers = multipart("file", "backup.zip", backup)
        status, res = call("POST", "/api/data/import", body, headers)
        check("导入备份恢复", status == 200 and isinstance(res, dict) and res.get("success"),
              f"{status} {res}")
        # 整站恢复会按备份重建账号(PostgreSQL 下用户 id 变化),原令牌失效属预期;与前端一致,重新登录
        token = ""
        status, res = call("POST", "/api/auth/login", {"username": USER, "password": PASSWORD})
        token = res.get("token", "") if isinstance(res, dict) else ""
        check("恢复后可用备份中的账号重新登录", status == 200 and bool(token), status)
        status, accounts2 = call("GET", "/api/accounts")
        check("恢复后科目仍为 81 个", status == 200 and len(accounts2) == 81, status)
        status, page2 = call("GET", "/api/vouchers")
        total = page2.get("total") if isinstance(page2, dict) else None
        check("恢复后凭证数与导出前一致", status == 200 and total == before,
              f"{status} total={total} before={before}")


if __name__ == "__main__":
    main()
    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    sys.exit(1 if failures else 0)
