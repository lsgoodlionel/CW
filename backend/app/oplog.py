"""操作日志:中间件记录全系统数据变更与导入导出/下载行为。

设计:记录所有变更类请求(POST/PUT/PATCH/DELETE)以及导出/下载/导入类 GET。
纯浏览类 GET(列表/详情)与健康检查、日志接口本身不记录,以保持日志聚焦有效行为。
"""
import json
import re
import time
from calendar import monthrange
from datetime import date, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .database import SessionLocal
from . import models

# (方法正则, 路径正则, 类型, 行为模板)  —— {id} 由第一个捕获组填充
_RULES: list[tuple[str, str, str, str]] = [
    (r"POST", r"^/api/vouchers/(\d+)/attachments$", "attachment", "上传附件(凭证#{id})"),
    (r"POST", r"^/api/vouchers/(\d+)/links$", "voucher", "添加凭证关联(凭证#{id})"),
    (r"DELETE", r"^/api/vouchers/links/(\d+)$", "voucher", "删除凭证关联 #{id}"),
    (r"POST", r"^/api/vouchers$", "voucher", "新建凭证"),
    (r"PUT", r"^/api/vouchers/(\d+)$", "voucher", "修改凭证 #{id}"),
    (r"DELETE", r"^/api/vouchers/(\d+)$", "voucher", "删除凭证 #{id}"),
    (r"POST", r"^/api/customers$", "customer", "新增客户"),
    (r"PUT", r"^/api/customers/(\d+)$", "customer", "修改客户 #{id}"),
    (r"DELETE", r"^/api/customers/(\d+)$", "customer", "删除/停用客户 #{id}"),
    (r"POST", r"^/api/accounts$", "account", "新增科目"),
    (r"PUT", r"^/api/accounts/(\d+)$", "account", "修改科目 #{id}"),
    (r"DELETE", r"^/api/accounts/(\d+)$", "account", "停用/删除科目 #{id}"),
    (r"PUT", r"^/api/company$", "company", "修改企业信息"),
    (r"DELETE", r"^/api/attachments/(\d+)$", "attachment", "删除附件 #{id}"),
    (r"GET", r"^/api/attachments/(\d+)/download$", "attachment", "下载附件 #{id}"),
    (r"GET", r"^/api/reports/export-excel$", "report", "导出财务报表 Excel"),
    (r"GET", r"^/api/ledgers/export-excel$", "ledger", "导出会计账簿 Excel"),
    (r"GET", r"^/api/data/export$", "data", "导出数据备份"),
    (r"POST", r"^/api/data/import$", "data", "导入数据备份(整体替换)"),
]

ACTION_TYPES = {
    "voucher": "凭证", "account": "科目", "attachment": "附件",
    "customer": "客户", "company": "企业信息", "report": "报表",
    "ledger": "账簿", "data": "数据", "other": "其他",
}


def classify(method: str, path: str) -> tuple[str, str, str] | None:
    """返回 (action_type, action_label, entity_id);不需记录则返回 None。"""
    for m_re, p_re, atype, label in _RULES:
        if re.fullmatch(m_re, method) and (match := re.fullmatch(p_re, path)):
            entity_id = match.group(1) if match.groups() else ""
            return atype, label.format(id=entity_id), entity_id
    return None


async def _body_summary(request: Request, method: str) -> str:
    """从 JSON 请求体提取简短摘要(如凭证摘要、科目名),失败则空。"""
    if method not in ("POST", "PUT", "PATCH"):
        return ""
    ctype = request.headers.get("content-type", "")
    if "application/json" not in ctype:
        return ""
    try:
        raw = await request.body()
        if not raw or len(raw) > 100_000:
            return ""
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    for key in ("note", "name", "voucher_no", "voucher_date"):
        if data.get(key):
            return f"{key}={data[key]}"[:180]
    return ""


class OperationLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path
        rule = classify(method, path)

        # 提前读取 body(会缓存,不影响下游),供摘要提取
        summary = await _body_summary(request, method) if rule else ""

        start = time.perf_counter()
        response = await call_next(request)
        if rule is None:
            return response

        duration_ms = int((time.perf_counter() - start) * 1000)
        atype, label, entity_id = rule
        client = request.client.host if request.client else ""
        try:
            db = SessionLocal()
            db.add(models.OperationLog(
                action_type=atype, action=label, method=method, path=path,
                entity_id=entity_id, summary=summary,
                status_code=response.status_code, duration_ms=duration_ms, ip=client,
            ))
            db.commit()
            db.close()
        except Exception:  # 日志失败绝不影响主流程
            pass
        return response


# ---------------------------------------------------------------------------
# 查询周期
# ---------------------------------------------------------------------------
def period_range(year: int, month: int | None, quarter: int | None) -> tuple[date, date]:
    if month:
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])
    if quarter:
        sm = (quarter - 1) * 3 + 1
        return date(year, sm, 1), date(year, sm + 2, monthrange(year, sm + 2)[1])
    return date(year, 1, 1), date(year, 12, 31)


def period_label(year: int, month: int | None, quarter: int | None) -> str:
    if month:
        return f"{year}年{month:02d}月"
    if quarter:
        return f"{year}年第{quarter}季度"
    return f"{year}年度"


def to_dt_range(start: date, end: date) -> tuple[datetime, datetime]:
    return (datetime.combine(start, datetime.min.time()),
            datetime.combine(end, datetime.max.time()))
