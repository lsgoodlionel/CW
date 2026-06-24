"""附件 API:上传(发票/回单)、下载、删除。文件存本地卷,元数据入库。"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings
from .. import models, schemas

router = APIRouter(prefix="/api", tags=["attachments"])

ALLOWED_KINDS = {"invoice", "receipt", "other"}


def _upload_root() -> Path:
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.post(
    "/vouchers/{voucher_id}/attachments",
    response_model=schemas.AttachmentOut, status_code=201,
)
async def upload_attachment(
    voucher_id: int,
    kind: str = Form("other"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    voucher = db.get(models.Voucher, voucher_id)
    if voucher is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if kind not in ALLOWED_KINDS:
        raise HTTPException(status_code=400, detail=f"kind 必须是 {ALLOWED_KINDS} 之一")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="文件超过大小上限")
    if not content:
        raise HTTPException(status_code=400, detail="空文件")

    suffix = Path(file.filename or "").suffix
    sub_dir = _upload_root() / str(voucher_id)
    sub_dir.mkdir(parents=True, exist_ok=True)
    stored = sub_dir / f"{uuid.uuid4().hex}{suffix}"
    stored.write_bytes(content)

    attachment = models.Attachment(
        voucher_id=voucher_id,
        kind=kind,
        original_name=file.filename or stored.name,
        stored_path=str(stored),
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db)):
    attachment = db.get(models.Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    path = Path(attachment.stored_path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="文件已丢失")
    return FileResponse(
        path, media_type=attachment.mime_type, filename=attachment.original_name
    )


@router.get("/attachments/{attachment_id}/preview")
def preview_attachment(attachment_id: int, db: Session = Depends(get_db)):
    """在线预览:以 inline 方式返回,浏览器直接渲染图片/PDF。"""
    attachment = db.get(models.Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    path = Path(attachment.stored_path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="文件已丢失")
    return FileResponse(
        path,
        media_type=attachment.mime_type or "application/octet-stream",
        content_disposition_type="inline",
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    attachment = db.get(models.Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    path = Path(attachment.stored_path)
    if path.exists():
        path.unlink(missing_ok=True)
    db.delete(attachment)
    db.commit()
