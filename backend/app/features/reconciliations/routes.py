"""Reconciliation routes (R1, docs/05).

Snapshot expected từ ledger/movements so với read model.
Sai lệch tạo exception để xử lý — KHÔNG tự vá (auto_fixed luôn False/None).
"""
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.api.observability import record_reconciliation_result
from app.api.pagination import (
    KeysetSpec,
    apply_keyset,
    build_cursor_payload,
    clamp_limit,
    coerce_timestamp,
    decode_cursor,
    encode_cursor,
)
from app.api.routes.auth_utils import (
    get_accessible_cashbox_ids,
    get_accessible_location_ids,
    require_any_capability,
)
from app.database import get_db
from app.models.cash_sim import CashEntry, CashJournal, CashRequest
from app.models.inventory import Balance, Movement
from app.models.reconciliation import ReconciliationException, ReconciliationRun
from app.services import idempotency

router = APIRouter()

_RECON_CAPS = ("cash:reconcile", "audit:view", "approval:view_inbox")
_SUBJECT_CASH = "cash_ledger"
_SUBJECT_INV = "inventory_ledger"


def _require_key(request: Request) -> str:
    key = request.headers.get("idempotency-key")
    if not key or not key.strip():
        raise AppError(
            400, "IDEMPOTENCY_KEY_REQUIRED",
            "Header Idempotency-Key là bắt buộc với mọi thao tác ghi (docs/06)",
        )
    return key.strip()


@router.post("/reconciliations", status_code=201)
async def run_reconciliation(
    payload: dict,
    request: Request,
    user=Depends(require_any_capability("cash:reconcile")),
    db: AsyncSession = Depends(get_db),
):
    scope = str(payload.get("scope", "cash")).lower()
    if scope not in ("cash", "inventory"):
        raise AppError(422, "INVALID_SCOPE", f"scope phải là cash|inventory, nhận {scope!r}")
    key = _require_key(request)
    cached = idempotency.check(key, idempotency.payload_hash(payload))
    if cached is not None:
        return cached[1]

    run = ReconciliationRun(
        id=uuid.uuid4(), scope=scope, status="running", auto_fixed=False
    )
    db.add(run)
    await db.flush()

    exceptions: list[dict] = []
    if scope == "cash":
        # S6/B2 — sổ quỹ theo két: chỉ đối soát các journal thuộc két user
        # được phép, nếu không user giới hạn sẽ thấy exception của chi
        # nhánh khác (rò dữ liệu tài chính ngoài scope).
        allowed_cashbox_ids = await get_accessible_cashbox_ids(db, user)
        journals_stmt = select(CashJournal)
        if allowed_cashbox_ids is not None:
            journals_stmt = journals_stmt.where(
                CashJournal.request_id.in_(
                    select(CashRequest.id).where(
                        CashRequest.cashbox_id.in_(allowed_cashbox_ids)
                    )
                )
            )
        journals = (await db.execute(journals_stmt)).scalars().all()
        # Look up cashbox_id per journal (request -> cashbox).
        cashbox_by_journal: dict[str, uuid.UUID] = {}
        if journals:
            journal_ids = [str(j.id) for j in journals]
            req_rows = (
                await db.execute(
                    select(CashJournal.id, CashRequest.cashbox_id).join(
                        CashRequest, CashJournal.request_id == CashRequest.id
                    ).where(CashJournal.id.in_(journal_ids))
                )
            ).all()
            cashbox_by_journal = {str(jid): cbid for jid, cbid in req_rows}
        for j in journals:
            entries = (
                await db.execute(select(CashEntry).where(CashEntry.journal_id == j.id))
            ).scalars().all()
            dr = sum(float(e.debit) for e in entries)
            cr = sum(float(e.credit) for e in entries)
            if abs(dr - cr) > 1e-9:
                exceptions.append(
                    {
                        "subject": f"journal:{j.id}",
                        "expected": {"debit": dr, "credit": dr},
                        "actual": {"debit": dr, "credit": cr},
                        "_cashbox_id": cashbox_by_journal.get(str(j.id)),
                    }
                )
    else:
        allowed_location_ids = await get_accessible_location_ids(db, user)
        moves_stmt = select(Movement)
        if allowed_location_ids is not None:
            moves_stmt = moves_stmt.where(Movement.location_id.in_(allowed_location_ids))
        moves = (await db.execute(moves_stmt)).scalars().all()
        sums: dict[tuple, float] = {}
        for m in moves:
            k = (str(m.location_id), str(m.item_id))
            sums[k] = sums.get(k, 0.0) + float(m.quantity_signed)
        bals_stmt = select(Balance)
        if allowed_location_ids is not None:
            bals_stmt = bals_stmt.where(Balance.location_id.in_(allowed_location_ids))
        bals = (await db.execute(bals_stmt)).scalars().all()
        bal_map = {(str(b.location_id), str(b.item_id)): float(b.quantity) for b in bals}
        for k in sums.keys() | bal_map.keys():
            expected = sums.get(k, 0.0)
            actual = bal_map.get(k)
            if actual is None or abs(expected - actual) > 1e-6:
                exceptions.append(
                    {
                        "subject": f"balance:{k[0]}:{k[1]}",
                        "expected": {"quantity": expected},
                        "actual": {"quantity": actual},
                        "_location_id": k[0],
                    }
                )

    for e in exceptions:
        db.add(
            ReconciliationException(
                id=uuid.uuid4(),
                run_id=run.id,
                subject=e["subject"],
                expected_json=e["expected"],
                actual_json=e["actual"],
                cashbox_id=e.get("_cashbox_id"),
                location_id=e.get("_location_id"),
            )
        )
    run.status = "exception" if exceptions else "matched"
    await db.commit()
    record_reconciliation_result(scope, run.status)
    await db.refresh(run)
    body = {
        "id": str(run.id),
        "scope": run.scope,
        "status": run.status,
        "auto_fixed": False,
        "exceptions": [
            {"subject": e["subject"], "expected": e["expected"], "actual": e["actual"]}
            for e in exceptions
        ],
    }
    idempotency.remember(db, key, idempotency.payload_hash(payload), 201, body)
    return body


@router.get("/reconciliations")
async def list_reconciliations(
    user=Depends(require_any_capability(*_RECON_CAPS)),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    cursor: str | None = None,
):
    """Danh sách runs + exceptions (màn Báo cáo đọc ở đây)."""
    limit = clamp_limit(limit)
    spec = KeysetSpec(
        columns=(ReconciliationRun.created_at, ReconciliationRun.id),
        descending=(True, False),
        keys=("created_at", "id"),
        attrs=("created_at", "id"),
        coerce=(coerce_timestamp, lambda raw: uuid.UUID(str(raw))),
    )
    stmt = select(ReconciliationRun).order_by(
        ReconciliationRun.created_at.desc(), ReconciliationRun.id
    )
    stmt = apply_keyset(stmt, spec, decode_cursor(cursor))
    runs = (
        await db.execute(
            stmt.limit(limit + 1)
        )
    ).scalars().all()
    page, next_cursor = runs[:limit], None
    if len(runs) > limit:
        next_cursor = encode_cursor(build_cursor_payload(spec, page[-1]))
    out = []
    for r in page:
        excs = (
            await db.execute(
                select(ReconciliationException).where(ReconciliationException.run_id == r.id)
            )
        ).scalars().all()
        out.append(
            {
                "id": str(r.id),
                "scope": r.scope,
                "status": r.status,
                "auto_fixed": r.auto_fixed,
                "exceptions": [
                    {
                        "subject": e.subject,
                        "expected": e.expected_json,
                        "actual": e.actual_json,
                    }
                    for e in excs
                ],
            }
        )
    return {"runs": out, "next_cursor": next_cursor, "limit": limit}
