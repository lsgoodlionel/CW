"""附件存储服务:文件落本地卷、创建元数据行。被凭证/费用申请/费用报销共用。"""
import uuid
from pathlib import Path

from . import models
from .config import settings

# invoice 发票 / receipt 银行回单 / contract 合同 / tax_payment 完税证明 / other 其他
ALLOWED_KINDS = {"invoice", "receipt", "contract", "tax_payment", "other"}


def upload_root() -> Path:
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def store_bytes(owner_dir: str, original_name: str, content: bytes) -> Path:
    """把内容写入 upload_dir/<owner_dir>/<uuid><ext>,返回落地路径。"""
    sub_dir = upload_root() / owner_dir
    sub_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_name or "").suffix
    stored = sub_dir / f"{uuid.uuid4().hex}{suffix}"
    stored.write_bytes(content)
    return stored


def make_attachment(*, kind: str, original_name: str, stored_path: Path,
                    mime_type: str, size_bytes: int,
                    voucher_id: int | None = None,
                    expense_application_id: int | None = None,
                    expense_claim_id: int | None = None) -> models.Attachment:
    return models.Attachment(
        voucher_id=voucher_id,
        expense_application_id=expense_application_id,
        expense_claim_id=expense_claim_id,
        kind=kind if kind in ALLOWED_KINDS else "other",
        original_name=original_name, stored_path=str(stored_path),
        mime_type=mime_type or "application/octet-stream", size_bytes=size_bytes,
    )
