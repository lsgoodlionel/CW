"""整站数据一键导入/导出。

导出:打包为 zip —— `data.json`(企业信息/科目/凭证/分录/附件元数据)
     + `attachments/<stored_name>` 附件文件。
导入:读取 zip 快照,**整体替换**现有数据(事务保护)。
"""
import io
import json
import uuid
import zipfile
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..config import settings
from .. import models

router = APIRouter(prefix="/api/data", tags=["data"])

EXPORT_VERSION = 2
SUPPORTED_VERSIONS = {1, 2}  # 兼容早期备份(无客户/关联)


def _company_dict(c: models.CompanyInfo | None) -> dict:
    if c is None:
        return {}
    return {
        "name": c.name, "legal_person": c.legal_person, "accountant": c.accountant,
        "auditor": c.auditor, "bookkeeper": c.bookkeeper, "recorder": c.recorder,
    }


@router.get("/export")
def export_data(db: Session = Depends(get_db)):
    """导出整站数据为 zip 备份文件。"""
    company = db.get(models.CompanyInfo, 1)
    accounts = db.scalars(select(models.Account).order_by(models.Account.code)).all()
    account_code = {a.id: a.code for a in accounts}

    vouchers = db.scalars(
        select(models.Voucher).order_by(models.Voucher.id).options(
            selectinload(models.Voucher.entries),
            selectinload(models.Voucher.attachments),
        )
    ).all()

    customers = db.scalars(select(models.Customer).order_by(models.Customer.id)).all()
    links = db.scalars(select(models.VoucherLink)).all()

    payload = {
        "version": EXPORT_VERSION,
        "exported_at": datetime.now().isoformat(),
        "company": _company_dict(company),
        "accounts": [
            {"code": a.code, "name": a.name, "category": a.category,
             "direction": a.direction, "is_active": a.is_active}
            for a in accounts
        ],
        "customers": [
            {"ref": c.id, "name": c.name, "short_name": c.short_name,
             "tax_number": c.tax_number, "address": c.address, "phone": c.phone,
             "bank_name": c.bank_name, "bank_account": c.bank_account,
             "contact_person": c.contact_person, "contact_phone": c.contact_phone,
             "email": c.email, "note": c.note, "is_active": c.is_active}
            for c in customers
        ],
        "links": [
            {"source_ref": link.source_id, "target_ref": link.target_id,
             "relation_type": link.relation_type, "note": link.note}
            for link in links
        ],
        "vouchers": [],
    }

    # 收集附件文件名(zip 内路径)
    file_map: list[tuple[str, Path]] = []
    for v in vouchers:
        attachments = []
        for att in v.attachments:
            src = Path(att.stored_path)
            arc_name = f"attachments/{att.id}_{Path(att.stored_path).name}"
            attachments.append({
                "kind": att.kind, "original_name": att.original_name,
                "mime_type": att.mime_type, "size_bytes": att.size_bytes,
                "archive_name": arc_name,
            })
            if src.exists():
                file_map.append((arc_name, src))
        payload["vouchers"].append({
            "ref": v.id,
            "voucher_no": v.voucher_no,
            "voucher_date": v.voucher_date.isoformat(),
            "note": v.note, "status": v.status,
            "customer_ref": v.customer_id,
            "entries": [
                {"line_no": e.line_no, "summary": e.summary,
                 "account_code": account_code.get(e.account_id, ""),
                 "sub_account": e.sub_account,
                 "debit": str(e.debit), "credit": str(e.credit)}
                for e in v.entries
            ],
            "attachments": attachments,
        })

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", json.dumps(payload, ensure_ascii=False, indent=2))
        for arc_name, src in file_map:
            zf.write(src, arc_name)
    buffer.seek(0)

    filename = f"finance-backup-{datetime.now():%Y%m%d-%H%M%S}.zip"
    # 用 octet-stream 而非 application/zip,避免 Safari「下载后打开安全文件」自动解压成文件夹
    return StreamingResponse(
        buffer, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _find_member(zf: zipfile.ZipFile, target: str) -> str | None:
    """在 zip 中定位条目,容忍外层多套一层目录及 macOS 压缩噪声。

    例如手工压缩文件夹后,`data.json` 可能变成 `finance-backup-x/data.json`。
    """
    names = [n for n in zf.namelist() if "__MACOSX" not in n and not n.endswith("/")]
    if target in names:
        return target
    suffix = "/" + target
    candidates = [n for n in names if n.endswith(suffix)]
    if candidates:
        return min(candidates, key=len)  # 取层级最浅的
    return None


@router.post("/import")
async def import_data(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """从 zip 备份恢复整站数据(整体替换现有数据)。"""
    raw = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="不是有效的 zip 备份文件,请直接上传导出的 zip,勿先解压再压缩")

    data_member = _find_member(zf, "data.json")
    if data_member is None:
        raise HTTPException(
            status_code=400,
            detail="备份缺少 data.json。请上传导出得到的原始 zip(若被系统自动解压成文件夹,"
                   "请把文件夹里的文件直接打包,或重新导出)。",
        )
    try:
        payload = json.loads(zf.read(data_member).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="data.json 解析失败")

    if payload.get("version") not in SUPPORTED_VERSIONS:
        raise HTTPException(status_code=400, detail="备份版本不兼容")

    counts = _restore(db, zf, payload)
    return {"success": True, **counts}


def _restore(db: Session, zf: zipfile.ZipFile, payload: dict) -> dict:
    """在单个事务内清空并重建全部数据。附件文件落盘后再提交元数据。"""
    # 1. 清空(附件文件单独处理)
    db.execute(delete(models.VoucherLink))
    db.execute(delete(models.VoucherEntry))
    db.execute(delete(models.Attachment))
    db.execute(delete(models.Voucher))
    db.execute(delete(models.Account))
    db.execute(delete(models.Customer))

    # 2. 企业信息
    company = db.get(models.CompanyInfo, 1)
    if company is None:
        company = models.CompanyInfo(id=1)
        db.add(company)
    for key, value in (payload.get("company") or {}).items():
        if hasattr(company, key):
            setattr(company, key, value)

    # 3. 科目
    code_to_account: dict[str, models.Account] = {}
    for a in payload.get("accounts", []):
        acc = models.Account(
            code=a["code"], name=a["name"], category=a["category"],
            direction=a["direction"], is_active=a.get("is_active", True),
        )
        db.add(acc)
        code_to_account[a["code"]] = acc

    # 3b. 客户(记录旧 ref → 新对象映射)
    ref_to_customer: dict[int, models.Customer] = {}
    for c in payload.get("customers", []):
        fields = {k: v for k, v in c.items() if k != "ref"}
        customer = models.Customer(**fields)
        db.add(customer)
        if c.get("ref") is not None:
            ref_to_customer[c["ref"]] = customer
    db.flush()  # 取得科目/客户 id

    # 4. 凭证 + 分录 + 附件
    upload_root = Path(settings.upload_dir)
    voucher_count = attachment_count = 0
    ref_to_voucher: dict[int, models.Voucher] = {}
    for v in payload.get("vouchers", []):
        cust = ref_to_customer.get(v.get("customer_ref"))
        voucher = models.Voucher(
            voucher_no=v["voucher_no"],
            voucher_date=date.fromisoformat(v["voucher_date"]),
            note=v.get("note", ""), status=v.get("status", "posted"),
            customer_id=cust.id if cust else None,
            total_debit=Decimal("0"), total_credit=Decimal("0"),
        )
        total_debit = total_credit = Decimal("0")
        for e in v.get("entries", []):
            acc = code_to_account.get(e["account_code"])
            if acc is None:
                continue
            debit = Decimal(str(e.get("debit", "0")))
            credit = Decimal(str(e.get("credit", "0")))
            total_debit += debit
            total_credit += credit
            voucher.entries.append(models.VoucherEntry(
                line_no=e.get("line_no", 1), summary=e.get("summary", ""),
                account=acc, sub_account=e.get("sub_account", ""),
                debit=debit, credit=credit,
            ))
        voucher.total_debit = total_debit
        voucher.total_credit = total_credit
        db.add(voucher)
        db.flush()  # 取得 voucher.id 用于附件目录

        for att in v.get("attachments", []):
            arc = att.get("archive_name")
            if not arc:
                continue
            # 容忍外层多套一层目录:精确匹配不到时按文件名后缀定位
            member = arc if arc in zf.namelist() else _find_member(zf, arc)
            if member is None:
                continue
            sub_dir = upload_root / str(voucher.id)
            sub_dir.mkdir(parents=True, exist_ok=True)
            suffix = Path(att["original_name"]).suffix
            stored = sub_dir / f"{uuid.uuid4().hex}{suffix}"
            stored.write_bytes(zf.read(member))
            db.add(models.Attachment(
                voucher_id=voucher.id, kind=att.get("kind", "other"),
                original_name=att["original_name"], stored_path=str(stored),
                mime_type=att.get("mime_type", ""), size_bytes=att.get("size_bytes", 0),
            ))
            attachment_count += 1
        voucher_count += 1
        if v.get("ref") is not None:
            ref_to_voucher[v["ref"]] = voucher

    # 5. 凭证关联(按 ref 映射到新凭证)
    link_count = 0
    for link in payload.get("links", []):
        src = ref_to_voucher.get(link.get("source_ref"))
        tgt = ref_to_voucher.get(link.get("target_ref"))
        if src is None or tgt is None:
            continue
        db.add(models.VoucherLink(
            source_id=src.id, target_id=tgt.id,
            relation_type=link.get("relation_type", "other"),
            note=link.get("note", ""),
        ))
        link_count += 1

    db.commit()
    return {
        "accounts": len(code_to_account),
        "customers": len(ref_to_customer),
        "vouchers": voucher_count,
        "attachments": attachment_count,
        "links": link_count,
    }
