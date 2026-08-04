"""附件 API:上传(发票/回单)、下载、删除。文件存本地卷,元数据入库。"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings
from .. import models, schemas, attach_svc

router = APIRouter(prefix="/api", tags=["attachments"])

ALLOWED_KINDS = attach_svc.ALLOWED_KINDS


async def read_upload(file: UploadFile, kind: str) -> bytes:
    """校验类型/大小并返回文件字节。"""
    if kind not in ALLOWED_KINDS:
        raise HTTPException(status_code=400, detail=f"kind 必须是 {ALLOWED_KINDS} 之一")
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="文件超过大小上限")
    if not content:
        raise HTTPException(status_code=400, detail="空文件")
    return content


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
    content = await read_upload(file, kind)
    stored = attach_svc.store_bytes(str(voucher_id), file.filename or "", content)
    attachment = attach_svc.make_attachment(
        kind=kind, original_name=file.filename or stored.name, stored_path=stored,
        mime_type=file.content_type or "", size_bytes=len(content),
        voucher_id=voucher_id)
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


@router.patch("/attachments/{attachment_id}", response_model=schemas.AttachmentOut)
def update_attachment_kind(
    attachment_id: int, kind: str = Form(...), db: Session = Depends(get_db)
):
    """变更已上传附件的类型。"""
    attachment = db.get(models.Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    if kind not in ALLOWED_KINDS:
        raise HTTPException(status_code=400, detail=f"kind 必须是 {ALLOWED_KINDS} 之一")
    attachment.kind = kind
    db.commit()
    db.refresh(attachment)
    return attachment


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
