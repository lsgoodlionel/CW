"""二级科目服务:编号生成、按名查找或自动新建、重命名同步凭证。"""
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session

from . import models


def next_code(db: Session, account: models.Account) -> str:
    """生成下一个二级编码:一级编码 + 2 位顺序号(不足两位补零,超出则递增位数)。"""
    existing = db.scalars(
        select(models.SubAccount.code).where(
            models.SubAccount.account_id == account.id)
    ).all()
    max_seq = 0
    prefix = account.code
    for code in existing:
        tail = code[len(prefix):]
        if tail.isdigit():
            max_seq = max(max_seq, int(tail))
    seq = max_seq + 1
    width = max(2, len(str(seq)))
    return f"{prefix}{seq:0{width}d}"


def next_sort(db: Session, account_id: int) -> int:
    cur = db.scalar(
        select(func.coalesce(func.max(models.SubAccount.sort_no), 0)).where(
            models.SubAccount.account_id == account_id)) or 0
    return cur + 1


def get_or_create(db: Session, account_id: int, name: str) -> models.SubAccount | None:
    """按(一级科目, 名称)查找二级;不存在则自动新建,编号延续。name 为空返回 None。"""
    name = (name or "").strip()
    if not name:
        return None
    sub = db.scalar(
        select(models.SubAccount).where(
            models.SubAccount.account_id == account_id,
            models.SubAccount.name == name)
    )
    if sub:
        return sub
    account = db.get(models.Account, account_id)
    if account is None:
        return None
    sub = models.SubAccount(
        account_id=account_id, code=next_code(db, account),
        name=name, sort_no=next_sort(db, account_id), is_active=True,
    )
    db.add(sub)
    db.flush()
    return sub


def rename_sync_vouchers(db: Session, sub: models.SubAccount, new_name: str) -> None:
    """重命名二级科目并同步更新引用它的凭证分录的明细科目名称。"""
    sub.name = new_name
    db.execute(
        update(models.VoucherEntry)
        .where(models.VoucherEntry.sub_account_id == sub.id)
        .values(sub_account=new_name)
    )
