"""凭证附件完成度统计。

当前凭证的附件完成状态需要合并三类来源:本凭证、关联凭证、关联合同。
"""
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from . import models, schemas


def parse_required_attachment_kinds(raw: str | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for kind in raw.split(","):
        kind = kind.strip()
        if kind and kind in schemas.ATTACHMENT_KINDS and kind not in out:
            out.append(kind)
    return out


def dump_required_attachment_kinds(kinds: list[str]) -> str:
    return ",".join(kinds)


def missing_attachment_kinds(
    required: list[str], counts: dict[str, int]
) -> list[str]:
    return [kind for kind in required if counts.get(kind, 0) <= 0]


def count_missing_attachment_vouchers(db: Session) -> int:
    rows = db.execute(
        select(models.Voucher.id, models.Voucher.required_attachment_kinds)
        .where(models.Voucher.required_attachment_kinds != "")
    ).all()
    ids = [voucher_id for voucher_id, _ in rows]
    context = attachment_context(db, ids)
    missing_count = 0
    for voucher_id, raw_required in rows:
        required = parse_required_attachment_kinds(raw_required)
        if not required:
            continue
        kind_counts, _ = context.get(voucher_id, ({}, {}))
        if missing_attachment_kinds(required, kind_counts):
            missing_count += 1
    return missing_count


def _merge_kind_counts(*parts: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for part in parts:
        for kind, count in part.items():
            merged[kind] = merged.get(kind, 0) + count
    return merged


def attachment_context(
    db: Session, voucher_ids: list[int]
) -> dict[int, tuple[dict[str, int], dict[str, int]]]:
    if not voucher_ids:
        return {}
    idset = set(voucher_ids)
    self_counts: dict[int, dict[str, int]] = {vid: {} for vid in voucher_ids}
    source_counts: dict[int, dict[str, int]] = {
        vid: {"self": 0, "linked_voucher": 0, "linked_contract": 0}
        for vid in voucher_ids
    }

    self_rows = db.execute(
        select(models.Attachment.voucher_id, models.Attachment.kind, func.count(models.Attachment.id))
        .where(models.Attachment.voucher_id.in_(voucher_ids))
        .group_by(models.Attachment.voucher_id, models.Attachment.kind)
    ).all()
    for voucher_id, kind, count in self_rows:
        self_counts[voucher_id][kind] = self_counts[voucher_id].get(kind, 0) + count
        source_counts[voucher_id]["self"] += count

    linked_voucher_ids: dict[int, set[int]] = {vid: set() for vid in voucher_ids}
    link_rows = db.execute(
        select(models.VoucherLink.source_id, models.VoucherLink.target_id)
        .where(or_(models.VoucherLink.source_id.in_(voucher_ids),
                   models.VoucherLink.target_id.in_(voucher_ids)))
    ).all()
    for src, tgt in link_rows:
        if src in idset:
            linked_voucher_ids[src].add(tgt)
        if tgt in idset:
            linked_voucher_ids[tgt].add(src)

    linked_counts: dict[int, dict[str, int]] = {vid: {} for vid in voucher_ids}
    all_linked_ids = sorted({other for ids in linked_voucher_ids.values() for other in ids})
    if all_linked_ids:
        linked_rows = db.execute(
            select(models.Attachment.voucher_id, models.Attachment.kind, func.count(models.Attachment.id))
            .where(models.Attachment.voucher_id.in_(all_linked_ids))
            .group_by(models.Attachment.voucher_id, models.Attachment.kind)
        ).all()
        counts_by_linked: dict[int, dict[str, int]] = {}
        for voucher_id, kind, count in linked_rows:
            counts_by_linked.setdefault(voucher_id, {})[kind] = count
        for vid, others in linked_voucher_ids.items():
            for other in others:
                for kind, count in counts_by_linked.get(other, {}).items():
                    linked_counts[vid][kind] = linked_counts[vid].get(kind, 0) + count
                    source_counts[vid]["linked_voucher"] += count

    contract_ids: dict[int, set[int]] = {vid: set() for vid in voucher_ids}
    contract_rows = db.execute(
        select(models.ContractVoucherLink.voucher_id, models.ContractVoucherLink.contract_id)
        .where(models.ContractVoucherLink.voucher_id.in_(voucher_ids))
    ).all()
    for voucher_id, contract_id in contract_rows:
        contract_ids[voucher_id].add(contract_id)

    contract_counts: dict[int, dict[str, int]] = {vid: {} for vid in voucher_ids}
    all_contract_ids = sorted({cid for ids in contract_ids.values() for cid in ids})
    if all_contract_ids:
        contract_att_rows = db.execute(
            select(models.Attachment.contract_id, models.Attachment.kind, func.count(models.Attachment.id))
            .where(models.Attachment.contract_id.in_(all_contract_ids))
            .group_by(models.Attachment.contract_id, models.Attachment.kind)
        ).all()
        counts_by_contract: dict[int, dict[str, int]] = {}
        for contract_id, kind, count in contract_att_rows:
            counts_by_contract.setdefault(contract_id, {})[kind] = count
        for vid, contracts in contract_ids.items():
            for contract_id in contracts:
                for kind, count in counts_by_contract.get(contract_id, {}).items():
                    contract_counts[vid][kind] = contract_counts[vid].get(kind, 0) + count
                    source_counts[vid]["linked_contract"] += count

    return {
        vid: (_merge_kind_counts(self_counts[vid], linked_counts[vid], contract_counts[vid]),
              {k: v for k, v in source_counts[vid].items() if v > 0})
        for vid in voucher_ids
    }
