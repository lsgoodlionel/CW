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

EXPORT_VERSION = 8
# 1-7 见历史;8:用户/角色/权限
SUPPORTED_VERSIONS = {1, 2, 3, 4, 5, 6, 7, 8}


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
    subs = db.scalars(select(models.SubAccount).order_by(models.SubAccount.code)).all()
    acc_code = {a.id: a.code for a in accounts}

    payload = {
        "version": EXPORT_VERSION,
        "exported_at": datetime.now().isoformat(),
        "company": _company_dict(company),
        "accounts": [
            {"code": a.code, "name": a.name, "category": a.category,
             "direction": a.direction, "is_active": a.is_active}
            for a in accounts
        ],
        "sub_accounts": [
            {"account_code": acc_code.get(s.account_id, ""), "code": s.code,
             "name": s.name, "note": s.note, "is_active": s.is_active,
             "sort_no": s.sort_no}
            for s in subs
        ],
        "customers": [
            {"ref": c.id, "party_type": c.party_type, "name": c.name,
             "short_name": c.short_name,
             "tax_number": c.tax_number, "address": c.address, "phone": c.phone,
             "bank_name": c.bank_name, "bank_account": c.bank_account,
             "contact_person": c.contact_person, "contact_phone": c.contact_phone,
             "email": c.email, "note": c.note, "is_active": c.is_active}
            for c in customers
        ],
        "org_units": [
            {"ref": u.id, "parent_ref": u.parent_id, "name": u.name,
             "sort_no": u.sort_no, "note": u.note}
            for u in db.scalars(select(models.OrgUnit).order_by(models.OrgUnit.id)).all()
        ],
        "employees": [
            {"ref": e.id, "employee_no": e.employee_no, "name": e.name, "gender": e.gender,
             "phone": e.phone, "id_number": e.id_number, "email": e.email,
             "hire_date": e.hire_date, "equity_ratio": str(e.equity_ratio),
             "status": e.status, "note": e.note,
             "positions": [
                 {"org_unit_ref": p.org_unit_id, "role_type": p.role_type,
                  "position": p.position} for p in e.positions
             ]}
            for e in db.scalars(select(models.Employee).order_by(models.Employee.id)
                                .options(selectinload(models.Employee.positions))).all()
        ],
        "links": [
            {"source_ref": link.source_id, "target_ref": link.target_id,
             "relation_type": link.relation_type, "note": link.note}
            for link in links
        ],
        "workflow_definitions": [
            {"ref": d.id, "name": d.name, "biz_type": d.biz_type, "note": d.note,
             "is_active": d.is_active,
             "steps": [{"step_no": s.step_no, "name": s.name,
                        "approver_type": s.approver_type,
                        "approver_employee_ref": s.approver_employee_id,
                        "approver_role": s.approver_role} for s in d.steps]}
            for d in db.scalars(select(models.WorkflowDefinition)
                                .options(selectinload(models.WorkflowDefinition.steps))).all()
        ],
        "workflow_instances": [
            {"ref": ins.id, "definition_ref": ins.definition_id, "biz_type": ins.biz_type,
             "biz_id": ins.biz_id, "title": ins.title,
             "applicant_ref": ins.applicant_employee_id, "status": ins.status,
             "current_step_no": ins.current_step_no,
             "created_at": ins.created_at.isoformat() if ins.created_at else None,
             "tasks": [{"step_no": t.step_no, "step_name": t.step_name,
                        "approver_ref": t.approver_employee_id, "result": t.result,
                        "comment": t.comment,
                        "acted_at": t.acted_at.isoformat() if t.acted_at else None}
                       for t in ins.tasks]}
            for ins in db.scalars(select(models.WorkflowInstance)
                                  .options(selectinload(models.WorkflowInstance.tasks))).all()
        ],
        "expense_claims": [
            {"claim_no": c.claim_no, "applicant_ref": c.applicant_employee_id,
             "org_unit_ref": c.org_unit_id, "reason": c.reason,
             "total_amount": str(c.total_amount), "status": c.status,
             "workflow_instance_ref": c.workflow_instance_id,
             "voucher_ref": c.voucher_id, "note": c.note,
             "created_at": c.created_at.isoformat() if c.created_at else None,
             "items": [{"category": it.category, "account_code": acc_code.get(it.account_id, ""),
                        "sub_account": it.sub_account, "amount": str(it.amount),
                        "note": it.note} for it in c.items]}
            for c in db.scalars(select(models.ExpenseClaim)
                                .options(selectinload(models.ExpenseClaim.items))).all()
        ],
        "roles": [
            {"name": r.name, "note": r.note, "is_system": r.is_system,
             "perms": [p.perm for p in r.permissions]}
            for r in db.scalars(select(models.Role)
                                .options(selectinload(models.Role.permissions))).all()
        ],
        "users": [
            {"username": u.username, "password_hash": u.password_hash,
             "display_name": u.display_name, "employee_ref": u.employee_id,
             "is_super_admin": u.is_super_admin, "is_active": u.is_active,
             "role_names": [r.name for r in u.roles]}
            for u in db.scalars(select(models.User)).all()
        ],
        "operation_logs": [
            {"created_at": lg.created_at.isoformat() if lg.created_at else None,
             "action_type": lg.action_type, "action": lg.action, "method": lg.method,
             "path": lg.path, "entity_id": lg.entity_id, "summary": lg.summary,
             "operator": lg.operator, "detail": lg.detail, "status_code": lg.status_code,
             "duration_ms": lg.duration_ms, "ip": lg.ip}
            for lg in db.scalars(
                select(models.OperationLog).order_by(models.OperationLog.id)).all()
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
    db.execute(delete(models.SubAccount))
    db.execute(delete(models.Account))
    db.execute(delete(models.Customer))
    db.execute(delete(models.ExpenseItem))
    db.execute(delete(models.ExpenseClaim))
    db.execute(delete(models.WorkflowTask))
    db.execute(delete(models.WorkflowInstance))
    db.execute(delete(models.WorkflowStep))
    db.execute(delete(models.WorkflowDefinition))
    db.execute(delete(models.EmployeePosition))
    db.execute(delete(models.Employee))
    db.execute(delete(models.OrgUnit))
    db.execute(delete(models.OperationLog))
    db.execute(delete(models.UserRole))
    db.execute(delete(models.RolePermission))
    db.execute(delete(models.User))
    db.execute(delete(models.Role))

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

    # 3c. 二级科目(按一级编码归属;记录 (账户id,名称)→二级 用于分录回链)
    sub_lookup: dict[tuple[int, str], models.SubAccount] = {}
    for s in payload.get("sub_accounts", []):
        acc = code_to_account.get(s.get("account_code"))
        if acc is None:
            continue
        sub = models.SubAccount(
            account_id=acc.id, code=s["code"], name=s["name"],
            note=s.get("note", ""), is_active=s.get("is_active", True),
            sort_no=s.get("sort_no", 0),
        )
        db.add(sub)
        sub_lookup[(acc.id, s["name"])] = sub
    db.flush()

    # 3d. 组织架构(两遍:先建单元,再回填 parent)+ 员工
    ref_to_unit: dict[int, models.OrgUnit] = {}
    for u in payload.get("org_units", []):
        unit = models.OrgUnit(name=u["name"], sort_no=u.get("sort_no", 0),
                              note=u.get("note", ""))
        db.add(unit)
        if u.get("ref") is not None:
            ref_to_unit[u["ref"]] = unit
    db.flush()
    for u in payload.get("org_units", []):
        unit = ref_to_unit.get(u.get("ref"))
        parent = ref_to_unit.get(u.get("parent_ref"))
        if unit is not None and parent is not None:
            unit.parent_id = parent.id
    ref_to_emp: dict[int, models.Employee] = {}
    for e in payload.get("employees", []):
        positions = e.get("positions")
        # 兼容旧格式(v4 早期无 positions,单部门字段)
        legacy_unit = ref_to_unit.get(e.get("org_unit_ref"))
        data = {k: v for k, v in e.items()
                if k not in ("ref", "positions", "org_unit_ref", "role_type", "position")}
        data["equity_ratio"] = Decimal(str(data.get("equity_ratio", "0")))
        emp = models.Employee(**data)
        if positions:
            for i, p in enumerate(positions, start=1):
                u = ref_to_unit.get(p.get("org_unit_ref"))
                emp.positions.append(models.EmployeePosition(
                    org_unit_id=u.id if u else None,
                    role_type=p.get("role_type", "staff"),
                    position=p.get("position", ""), sort_no=i))
        elif legacy_unit or e.get("role_type") or e.get("position"):
            emp.positions.append(models.EmployeePosition(
                org_unit_id=legacy_unit.id if legacy_unit else None,
                role_type=e.get("role_type", "staff"),
                position=e.get("position", ""), sort_no=1))
        db.add(emp)
        if e.get("ref") is not None:
            ref_to_emp[e["ref"]] = emp
    db.flush()

    # 3f. 审批流程(定义 + 步骤 + 实例 + 任务;员工按 ref 映射)
    ref_to_def: dict[int, models.WorkflowDefinition] = {}
    for wd in payload.get("workflow_definitions", []):
        d = models.WorkflowDefinition(
            name=wd["name"], biz_type=wd.get("biz_type", "general"),
            note=wd.get("note", ""), is_active=wd.get("is_active", True))
        for s in wd.get("steps", []):
            ap = ref_to_emp.get(s.get("approver_employee_ref"))
            d.steps.append(models.WorkflowStep(
                step_no=s.get("step_no", 1), name=s.get("name", ""),
                approver_type=s.get("approver_type", "employee"),
                approver_employee_id=ap.id if ap else None,
                approver_role=s.get("approver_role", "")))
        db.add(d)
        if wd.get("ref") is not None:
            ref_to_def[wd["ref"]] = d
    db.flush()
    ref_to_instance: dict[int, models.WorkflowInstance] = {}
    for wi in payload.get("workflow_instances", []):
        d = ref_to_def.get(wi.get("definition_ref"))
        if d is None:
            continue
        app_emp = ref_to_emp.get(wi.get("applicant_ref"))
        ts = wi.get("created_at")
        inst = models.WorkflowInstance(
            definition_id=d.id, biz_type=wi.get("biz_type", "general"),
            biz_id=wi.get("biz_id"), title=wi.get("title", ""),
            applicant_employee_id=app_emp.id if app_emp else None,
            status=wi.get("status", "pending"),
            current_step_no=wi.get("current_step_no", 1),
            created_at=datetime.fromisoformat(ts) if ts else None)
        for t in wi.get("tasks", []):
            ap = ref_to_emp.get(t.get("approver_ref"))
            at = t.get("acted_at")
            inst.tasks.append(models.WorkflowTask(
                step_no=t.get("step_no", 1), step_name=t.get("step_name", ""),
                approver_employee_id=ap.id if ap else None,
                result=t.get("result", "pending"), comment=t.get("comment", ""),
                acted_at=datetime.fromisoformat(at) if at else None))
        db.add(inst)
        if wi.get("ref") is not None:
            ref_to_instance[wi["ref"]] = inst
    db.flush()

    # 3e. 角色 + 用户(用户按 role_name/employee_ref 映射)
    name_to_role: dict[str, models.Role] = {}
    for r in payload.get("roles", []):
        role = models.Role(name=r["name"], note=r.get("note", ""),
                           is_system=r.get("is_system", False))
        for p in r.get("perms", []):
            role.permissions.append(models.RolePermission(perm=p))
        db.add(role)
        name_to_role[r["name"]] = role
    db.flush()
    for u in payload.get("users", []):
        emp = ref_to_emp.get(u.get("employee_ref"))
        user = models.User(
            username=u["username"], password_hash=u.get("password_hash", ""),
            display_name=u.get("display_name", ""),
            employee_id=emp.id if emp else None,
            is_super_admin=u.get("is_super_admin", False),
            is_active=u.get("is_active", True))
        db.add(user)
        db.flush()
        for rn in u.get("role_names", []):
            role = name_to_role.get(rn)
            if role:
                db.add(models.UserRole(user_id=user.id, role_id=role.id))
    db.flush()

    # 3f. 操作日志(审计流水)
    for lg in payload.get("operation_logs", []):
        ts = lg.get("created_at")
        db.add(models.OperationLog(
            created_at=datetime.fromisoformat(ts) if ts else None,
            action_type=lg.get("action_type", "other"), action=lg.get("action", ""),
            method=lg.get("method", ""), path=lg.get("path", ""),
            entity_id=lg.get("entity_id", ""), summary=lg.get("summary", ""),
            operator=lg.get("operator", ""),
            detail=lg.get("detail", ""), status_code=lg.get("status_code", 0),
            duration_ms=lg.get("duration_ms", 0), ip=lg.get("ip", "")))
    db.flush()

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
            sub_name = e.get("sub_account", "")
            sub = sub_lookup.get((acc.id, sub_name)) if sub_name else None
            voucher.entries.append(models.VoucherEntry(
                line_no=e.get("line_no", 1), summary=e.get("summary", ""),
                account=acc, sub_account=sub_name,
                sub_account_id=sub.id if sub else None,
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

    # 5. 费用报销单(引用员工/部门/科目/流程实例/凭证,均按 ref 映射)
    for c in payload.get("expense_claims", []):
        app_emp = ref_to_emp.get(c.get("applicant_ref"))
        unit = ref_to_unit.get(c.get("org_unit_ref"))
        inst = ref_to_instance.get(c.get("workflow_instance_ref"))
        vch = ref_to_voucher.get(c.get("voucher_ref"))
        ts = c.get("created_at")
        claim = models.ExpenseClaim(
            claim_no=c.get("claim_no", ""),
            applicant_employee_id=app_emp.id if app_emp else None,
            org_unit_id=unit.id if unit else None, reason=c.get("reason", ""),
            total_amount=Decimal(str(c.get("total_amount", "0"))),
            status=c.get("status", "draft"),
            workflow_instance_id=inst.id if inst else None,
            voucher_id=vch.id if vch else None, note=c.get("note", ""),
            created_at=datetime.fromisoformat(ts) if ts else None)
        for it in c.get("items", []):
            acc = code_to_account.get(it.get("account_code"))
            claim.items.append(models.ExpenseItem(
                category=it.get("category", ""),
                account_id=acc.id if acc else None,
                sub_account=it.get("sub_account", ""),
                amount=Decimal(str(it.get("amount", "0"))), note=it.get("note", "")))
        db.add(claim)

    db.commit()
    return {
        "accounts": len(code_to_account),
        "customers": len(ref_to_customer),
        "vouchers": voucher_count,
        "attachments": attachment_count,
        "links": link_count,
    }
