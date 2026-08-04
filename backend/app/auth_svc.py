"""鉴权服务:密码哈希(PBKDF2)、令牌签名(HMAC)、权限目录与校验。均用标准库。"""
import base64
import hashlib
import hmac
import json
import os
import time

from .config import settings

_ITER = 120_000


# ---------- 密码 ----------
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, _ITER)
    return f"pbkdf2${_ITER}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, it, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), int(it))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ---------- 令牌(JWT 风格,HMAC-SHA256 签名)----------
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user_id: int) -> str:
    payload = {"uid": user_id, "exp": int(time.time()) + settings.token_ttl_hours * 3600}
    body = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def parse_token(token: str) -> int | None:
    try:
        body, sig = token.split(".")
        expect = _b64(hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(_unb64(body))
        if payload.get("exp", 0) < time.time():
            return None
        return int(payload["uid"])
    except (ValueError, KeyError, TypeError):
        return None


# ---------- 权限目录 ----------
MODULES = {
    "voucher": "记账凭证", "account": "会计科目", "customer": "往来单位",
    "personnel": "人员管理", "workflow": "流程设计", "approval": "审批中心",
    "expense_apply": "费用申请", "expense": "费用报销",
    "report": "财务报表", "ledger": "会计账簿", "company": "企业信息",
    "data": "数据备份", "logs": "操作日志", "user": "用户与权限",
}
ACTIONS = {"view": "查看", "create": "新建", "edit": "编辑", "delete": "删除", "approve": "审批"}

# 各模块适用的动作(用户与权限模块仅超管/被授权者可管理)
MODULE_ACTIONS = {m: list(ACTIONS) for m in MODULES}
for m in ("report", "ledger", "logs"):
    MODULE_ACTIONS[m] = ["view"]
MODULE_ACTIONS["data"] = ["view", "create"]
MODULE_ACTIONS["company"] = ["view", "edit"]
# 流程设计:仅设计流程定义(不含审批动作)
MODULE_ACTIONS["workflow"] = ["view", "create", "edit", "delete"]
# 审批中心:查看/审批(通过驳回)/管理(改派撤销=edit)/删除实例
MODULE_ACTIONS["approval"] = ["view", "approve", "edit", "delete"]


def catalog() -> list[dict]:
    return [{"module": m, "label": MODULES[m],
             "actions": [{"action": a, "label": ACTIONS[a]} for a in MODULE_ACTIONS[m]]}
            for m in MODULES]


# ---------- 路径 → 所需权限 ----------
_PREFIX_MODULE = [
    ("/api/users", "user"), ("/api/roles", "user"), ("/api/auth-presets", "user"),
    ("/api/vouchers", "voucher"), ("/api/attachments", "voucher"),
    ("/api/accounts", "account"), ("/api/customers", "customer"),
    ("/api/personnel", "personnel"), ("/api/workflow", "workflow"),
    ("/api/expense-apply", "expense_apply"), ("/api/expense", "expense"),
    ("/api/reports", "report"),
    ("/api/ledgers", "ledger"), ("/api/company", "company"),
    ("/api/data", "data"), ("/api/logs", "logs"),
]


def classify_perm(method: str, path: str) -> tuple[str, str] | None:
    """返回 (module, action);无法归类返回 None(仅需登录)。"""
    # 审批流程域细分:流程定义=流程设计(workflow);实例/待办=审批中心(approval)
    if path.startswith("/api/workflow"):
        # 元数据与就绪自检供多页面读取,仅需登录
        if path.startswith("/api/workflow/meta") or path.startswith("/api/workflow/approver-check"):
            return None
        if (path.startswith("/api/workflow/instances")
                or path.startswith("/api/workflow/tasks")
                or path.startswith("/api/workflow/my-tasks")):
            if path.endswith("/approve") or path.endswith("/reject"):
                return "approval", "approve"
            if method == "GET":
                return "approval", "view"
            if method == "DELETE":
                return "approval", "delete"
            # 发起/改派/撤销 等对实例的写操作归为「管理」
            return "approval", "edit"
        # 其余(/definitions 等)= 流程设计
        if method == "GET":
            return "workflow", "view"
        if method == "POST":
            return "workflow", "create"
        if method in ("PUT", "PATCH"):
            return "workflow", "edit"
        if method == "DELETE":
            return "workflow", "delete"
        return "workflow", "view"

    module = next((mod for pre, mod in _PREFIX_MODULE if path.startswith(pre)), None)
    if module is None:
        return None
    if path.endswith("/approve") or path.endswith("/reject") or path.endswith("/submit"):
        return module, "approve"
    if method == "GET":
        return module, "view"
    if method in ("POST",):
        return module, "create"
    if method in ("PUT", "PATCH"):
        return module, "edit"
    if method == "DELETE":
        return module, "delete"
    return module, "view"


def user_perms(user) -> set[str]:
    perms: set[str] = set()
    for role in user.roles:
        for rp in role.permissions:
            perms.add(rp.perm)
    # 展开 module:*
    out: set[str] = set()
    for p in perms:
        if p.endswith(":*"):
            mod = p.split(":")[0]
            out.update(f"{mod}:{a}" for a in MODULE_ACTIONS.get(mod, ACTIONS))
        else:
            out.add(p)
    return out


def user_has(user, module: str, action: str) -> bool:
    if getattr(user, "is_super_admin", False):
        return True
    return f"{module}:{action}" in user_perms(user)
