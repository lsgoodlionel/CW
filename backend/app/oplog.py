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
    (r"POST", r"^/api/vouchers/(\d+)/reverse$", "voucher", "生成红字冲销(凭证#{id})"),
    (r"POST", r"^/api/vouchers/(\d+)/links$", "voucher", "添加凭证关联(凭证#{id})"),
    (r"DELETE", r"^/api/vouchers/links/(\d+)$", "voucher", "删除凭证关联 #{id}"),
    (r"PATCH", r"^/api/attachments/(\d+)$", "attachment", "修改附件类型 #{id}"),
    (r"POST", r"^/api/vouchers$", "voucher", "新建凭证"),
    (r"PUT", r"^/api/vouchers/(\d+)$", "voucher", "修改凭证 #{id}"),
    (r"DELETE", r"^/api/vouchers/(\d+)$", "voucher", "删除凭证 #{id}"),
    (r"POST", r"^/api/customers$", "customer", "新增往来单位"),
    (r"PUT", r"^/api/customers/(\d+)$", "customer", "修改往来单位 #{id}"),
    (r"DELETE", r"^/api/customers/(\d+)$", "customer", "删除/停用往来单位 #{id}"),
    (r"POST", r"^/api/personnel/org-units$", "personnel", "新增部门"),
    (r"PUT", r"^/api/personnel/org-units/(\d+)$", "personnel", "修改部门 #{id}"),
    (r"DELETE", r"^/api/personnel/org-units/(\d+)$", "personnel", "删除部门 #{id}"),
    (r"POST", r"^/api/personnel/org-units/(\d+)/members$", "personnel", "部门#{id}添加成员"),
    (r"POST", r"^/api/workflow/definitions$", "workflow", "新增审批流程"),
    (r"PUT", r"^/api/workflow/definitions/(\d+)$", "workflow", "修改审批流程 #{id}"),
    (r"DELETE", r"^/api/workflow/definitions/(\d+)$", "workflow", "删除审批流程 #{id}"),
    (r"POST", r"^/api/workflow/instances$", "workflow", "发起审批"),
    (r"POST", r"^/api/expense/claims$", "expense", "新建报销单"),
    (r"PUT", r"^/api/expense/claims/(\d+)$", "expense", "修改报销单 #{id}"),
    (r"DELETE", r"^/api/expense/claims/(\d+)$", "expense", "删除报销单 #{id}"),
    (r"POST", r"^/api/expense/claims/(\d+)/submit$", "expense", "提交报销单 #{id}"),
    (r"POST", r"^/api/expense/claims/(\d+)/make-voucher$", "expense", "报销单生成凭证 #{id}"),
    (r"POST", r"^/api/workflow/tasks/(\d+)/approve$", "workflow", "审批通过 #{id}"),
    (r"POST", r"^/api/workflow/tasks/(\d+)/reject$", "workflow", "审批驳回 #{id}"),
    (r"POST", r"^/api/personnel/employees$", "personnel", "新增员工"),
    (r"PUT", r"^/api/personnel/employees/(\d+)$", "personnel", "修改员工 #{id}"),
    (r"DELETE", r"^/api/personnel/employees/(\d+)$", "personnel", "删除员工 #{id}"),
    (r"POST", r"^/api/accounts/subaccounts/import$", "account", "批量导入二级科目"),
    (r"GET", r"^/api/accounts/export-excel$", "account", "导出会计科目表 Excel"),
    (r"POST", r"^/api/accounts/(\d+)/subaccounts$", "account", "新增二级科目(一级#{id})"),
    (r"PUT", r"^/api/accounts/subaccounts/(\d+)$", "account", "修改二级科目 #{id}"),
    (r"DELETE", r"^/api/accounts/subaccounts/(\d+)$", "account", "停用/删除二级科目 #{id}"),
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
    "customer": "往来单位", "personnel": "人员", "workflow": "审批流程",
    "expense": "费用报销", "company": "企业信息", "report": "报表",
    "ledger": "账簿", "data": "数据", "other": "其他",
}


def classify(method: str, path: str) -> tuple[str, str, str] | None:
    """返回 (action_type, action_label, entity_id);不需记录则返回 None。"""
    for m_re, p_re, atype, label in _RULES:
        if re.fullmatch(m_re, method) and (match := re.fullmatch(p_re, path)):
            entity_id = match.group(1) if match.groups() else ""
            return atype, label.format(id=entity_id), entity_id
    return None


# 路径 → (模型名, 固定id或None) 用于抓取「修改前」快照
_ENTITY_RULES: list[tuple[str, str, int | None]] = [
    (r"^/api/vouchers/(\d+)$", "Voucher", None),
    (r"^/api/accounts/subaccounts/(\d+)$", "SubAccount", None),
    (r"^/api/accounts/(\d+)$", "Account", None),
    (r"^/api/customers/(\d+)$", "Customer", None),
    (r"^/api/personnel/employees/(\d+)$", "Employee", None),
    (r"^/api/personnel/org-units/(\d+)$", "OrgUnit", None),
    (r"^/api/company$", "CompanyInfo", 1),
]
_REDACT = ("password", "token", "secret")
_MAX_DETAIL = 4000


def _jsonable(value):
    from decimal import Decimal
    from datetime import date, datetime
    if isinstance(value, (Decimal,)):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _snapshot(obj) -> dict:
    """取 ORM 对象的列值快照(排除时间戳,脱敏)。"""
    from sqlalchemy import inspect as sa_inspect
    out = {}
    for col in sa_inspect(obj).mapper.column_attrs:
        k = col.key
        if k in ("created_at", "updated_at"):
            continue
        if any(s in k.lower() for s in _REDACT):
            out[k] = "***"
            continue
        out[k] = _jsonable(getattr(obj, k))
    return out


def _model_for(path: str):
    for pattern, model_name, fixed_id in _ENTITY_RULES:
        m = re.fullmatch(pattern, path)
        if m:
            obj_id = fixed_id if fixed_id is not None else int(m.group(1))
            return getattr(models, model_name), obj_id
    return None, None


def _before_snapshot(method: str, path: str) -> dict | None:
    """更新/删除前抓取实体快照。"""
    if method not in ("PUT", "PATCH", "DELETE"):
        return None
    model, obj_id = _model_for(path)
    if model is None:
        return None
    try:
        db = SessionLocal()
        obj = db.get(model, obj_id)
        snap = _snapshot(obj) if obj is not None else None
        db.close()
        return snap
    except Exception:
        return None


async def _parse_body(request: Request, method: str) -> tuple[str, dict | None]:
    """解析 JSON 请求体,返回 (摘要, 提交内容 dict)。"""
    if method not in ("POST", "PUT", "PATCH"):
        return "", None
    if "application/json" not in request.headers.get("content-type", ""):
        return "", None
    try:
        raw = await request.body()
        if not raw or len(raw) > 200_000:
            return "", None
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return "", None
    if not isinstance(data, dict):
        return "", None
    summary = ""
    for key in ("note", "name", "voucher_no", "voucher_date"):
        if data.get(key):
            summary = f"{key}={data[key]}"[:180]
            break
    redacted = {k: ("***" if any(s in k.lower() for s in _REDACT) else v)
                for k, v in data.items()}
    return summary, redacted


def _build_detail(method: str, before: dict | None, submitted: dict | None) -> str:
    """组装变更详情:提交内容 + 修改前后差异。"""
    detail: dict = {}
    if method == "DELETE" and before:
        detail["删除前"] = before
    elif before is not None and submitted:
        # 更新:逐字段对比生成差异
        changes = {}
        for k, new_val in submitted.items():
            if k in before and before.get(k) != new_val:
                changes[k] = {"改前": before.get(k), "改后": new_val}
        if changes:
            detail["变更"] = changes
        detail["提交内容"] = submitted
    elif submitted:
        detail["提交内容"] = submitted
    if not detail:
        return ""
    try:
        return json.dumps(detail, ensure_ascii=False, default=str)[:_MAX_DETAIL]
    except (TypeError, ValueError):
        return ""


class OperationLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path
        rule = classify(method, path)

        summary, submitted = ("", None)
        before = None
        if rule is not None:
            summary, submitted = await _parse_body(request, method)
            before = _before_snapshot(method, path)

        start = time.perf_counter()
        response = await call_next(request)
        if rule is None:
            return response

        # 仅对成功的写操作记录详情(失败请求不产生变更)
        detail = ""
        if response.status_code < 400:
            detail = _build_detail(method, before, submitted)

        duration_ms = int((time.perf_counter() - start) * 1000)
        atype, label, entity_id = rule
        client = request.client.host if request.client else ""
        user = getattr(request.state, "user", None)
        operator = getattr(user, "username", "") if user else ""
        try:
            db = SessionLocal()
            db.add(models.OperationLog(
                action_type=atype, action=label, method=method, path=path,
                entity_id=entity_id, summary=summary, detail=detail, operator=operator,
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
