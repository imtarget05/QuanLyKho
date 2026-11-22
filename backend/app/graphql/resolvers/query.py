"""Query resolvers for GraphQL banking & inventory domain."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.graphql.context import get_loader
from app.graphql.loaders import account_to_dict
from app.models.audit import AuditEntry
from app.models.ledger import GeneralLedgerEntry, GLAccountBalance
from app.models.outbox import OutboxEventRecord
from app.models.saga import SagaInstance


async def _saga_to_dict(saga: SagaInstance) -> dict[str, Any]:
    return {
        "id": str(saga.id),
        "sagaName": saga.saga_name,
        "sagaType": saga.saga_type,
        "status": saga.status,
        "currentStep": saga.current_step,
        "errorMessage": saga.error_message,
        "createdAt": saga.created_at,
        "updatedAt": saga.updated_at,
        "steps": [],
    }


# ---------------------------------------------------------------------------
# Query: account
# ---------------------------------------------------------------------------
async def resolve_account(_, info, id: UUID) -> dict[str, Any] | None:
    """Lấy thông tin tài khoản theo ID (mã GLAccountBalance)."""
    loader = get_loader(info, "account")
    if loader is not None:
        return await loader.load(str(id))

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(GLAccountBalance).where(GLAccountBalance.account_code == str(id))
        )
        bal = res.scalars().first()
        return None if bal is None else account_to_dict(bal)


# ---------------------------------------------------------------------------
# Query: accounts
# ---------------------------------------------------------------------------
async def resolve_accounts(
    _, info, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(GLAccountBalance).offset(offset).limit(limit)
        )
        bals = res.scalars().all()
        rows = [account_to_dict(b) for b in bals]
        # Nạp sẵn cache để field con (vd. `ledgerEntries`) không query lại account.
        loader = get_loader(info, "account")
        if loader is not None:
            for row in rows:
                loader.prime(row["code"], row)
        return rows


# ---------------------------------------------------------------------------
# Query: balance
# ---------------------------------------------------------------------------
async def resolve_balance(_, info, accountId: UUID) -> dict[str, Any] | None:
    """Lấy số dô multi-tier của tài khoản."""
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(GLAccountBalance).where(
                GLAccountBalance.account_code == str(accountId)
            )
        )
        bal = res.scalars().first()
        if bal is None:
            return None
        return {
            "accountId": str(bal.account_code),
            "accountCode": bal.account_code,
            "ledgerBalance": Decimal(bal.ledger_balance),
            "availableBalance": Decimal(bal.available_balance),
            "holdBalance": Decimal(bal.hold_balance),
            "memoBalance": Decimal(0),
            "version": bal.version,
            "updatedAt": bal.updated_at,
        }


# ---------------------------------------------------------------------------
# Query: ledgerEntry / ledgerEntries
# ---------------------------------------------------------------------------
async def resolve_ledger_entry(_, info, id: UUID) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(GeneralLedgerEntry).where(GeneralLedgerEntry.id == id)
        )
        entry = res.scalars().first()
        if entry is None:
            return None
        return {
            "id": str(entry.id),
            "journalId": str(entry.journal_id),
            "accountCode": entry.account_code,
            "debit": Decimal(entry.debit),
            "credit": Decimal(entry.credit),
            "postedAt": None,
        }


async def resolve_ledger_entries(
    _, info, accountCode: str | None = None, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = select(GeneralLedgerEntry)
        if accountCode:
            stmt = stmt.where(GeneralLedgerEntry.account_code == accountCode)
        stmt = stmt.offset(offset).limit(limit)
        res = await session.execute(stmt)
        entries = res.scalars().all()
        return [
            {
                "id": str(e.id),
                "journalId": str(e.journal_id),
                "accountCode": e.account_code,
                "debit": Decimal(e.debit),
                "credit": Decimal(e.credit),
                "postedAt": None,
            }
            for e in entries
        ]

# ---------------------------------------------------------------------------
# Query: saga / sagas
# ---------------------------------------------------------------------------
async def resolve_saga(_, info, id: UUID) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(SagaInstance).where(SagaInstance.id == id)
        )
        saga = res.scalars().first()
        if saga is None:
            return None
        return _saga_to_dict(saga)


async def resolve_sagas(
    _, info, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(SagaInstance).offset(offset).limit(limit)
        )
        sagas = res.scalars().all()
        return [_saga_to_dict(s) for s in sagas]


# ---------------------------------------------------------------------------
# Query: auditEntry / auditTrail
# ---------------------------------------------------------------------------
async def resolve_audit_entry(_, info, id: str) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(AuditEntry).where(AuditEntry.id == int(id))
        )
        entry = res.scalars().first()
        if entry is None:
            return None
        return entry.to_dict()


def _audit_entry_to_graphql(record) -> dict[str, Any]:
    """Đổi bản ghi ORM (snake_case) sang field camelCase của schema GraphQL."""
    data = record.to_dict()
    return {
        "id": data["id"],
        "eventId": data["event_id"],
        "actorId": data["actor_id"],
        "action": data["action"],
        "entityType": data["entity_type"],
        "entityId": data["entity_id"],
        "statePayload": data["state_payload"],
        "payloadHash": data["payload_hash"],
        "prevHash": data["prev_hash"],
        "currentHash": data["current_hash"],
        "timestamp": data["timestamp"],
    }


async def resolve_audit_trail(
    _, info, entityType: str | None = None, entityId: str | None = None,
    limit: int = 50, offset: int = 0,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        query = select(AuditEntry)
        count_query = select(func.count(AuditEntry.id))
        if entityType:
            query = query.where(AuditEntry.entity_type == entityType)
            count_query = count_query.where(AuditEntry.entity_type == entityType)
        if entityId:
            query = query.where(AuditEntry.entity_id == entityId)
            count_query = count_query.where(AuditEntry.entity_id == entityId)
        query = query.order_by(AuditEntry.id.desc()).offset(offset).limit(limit)
        records_res = await session.execute(query)
        records = list(records_res.scalars().all())
        count_res = await session.execute(count_query)
        total_count = count_res.scalar() or 0
        return {
            "entries": [_audit_entry_to_graphql(r) for r in records],
            "totalCount": total_count,
            "hasMore": (offset + limit) < total_count,
        }


# ---------------------------------------------------------------------------
# Query: outboxEvent / outboxEvents
# ---------------------------------------------------------------------------
async def resolve_outbox_event(_, info, id: UUID) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(OutboxEventRecord).where(OutboxEventRecord.id == id)
        )
        ev = res.scalars().first()
        if ev is None:
            return None
        return {
            "id": ev.id,
            "topic": ev.topic,
            "eventType": ev.event_type,
            "aggregateId": ev.aggregate_id,
            "payload": ev.payload,
            "traceId": ev.trace_id,
            "status": ev.status,
            "attempts": ev.attempts,
            "createdAt": ev.created_at,
            "publishedAt": ev.published_at,
        }


async def resolve_outbox_events(
    _, info, topic: str | None = None, status: str | None = None,
    limit: int = 50, offset: int = 0,
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = select(OutboxEventRecord).offset(offset).limit(limit)
        if topic:
            stmt = stmt.where(OutboxEventRecord.topic == topic)
        if status:
            stmt = stmt.where(OutboxEventRecord.status == status)
        res = await session.execute(stmt)
        events = res.scalars().all()
        return [
            {
                "id": e.id,
                "topic": e.topic,
                "eventType": e.event_type,
                "aggregateId": e.aggregate_id,
                "payload": e.payload,
                "traceId": e.trace_id,
                "status": e.status,
                "attempts": e.attempts,
                "createdAt": e.created_at,
                "publishedAt": e.published_at,
            }
            for e in events
        ]


# ---------------------------------------------------------------------------
# Query: verifyAuditChain
# ---------------------------------------------------------------------------
async def resolve_verify_audit_chain(_, info, subject: str | None = None) -> bool:
    from app.services.audit_chain import verify_chain

    async with AsyncSessionLocal() as session:
        subj = subject or "global"
        return await verify_chain(session, subj)


# ---------------------------------------------------------------------------
# Query: health
# ---------------------------------------------------------------------------
async def resolve_health(_, info) -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "quanlykho-graphql",
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Query resolver map (Ariadne snake_case fallback)
# ---------------------------------------------------------------------------
query_resolvers = {
    "account": resolve_account,
    "accounts": resolve_accounts,
    "balance": resolve_balance,
    "ledgerEntry": resolve_ledger_entry,
    "ledgerEntries": resolve_ledger_entries,
    "saga": resolve_saga,
    "sagas": resolve_sagas,
    "auditEntry": resolve_audit_entry,
    "auditTrail": resolve_audit_trail,
    "outboxEvent": resolve_outbox_event,
    "outboxEvents": resolve_outbox_events,
    "verifyAuditChain": resolve_verify_audit_chain,
    "health": resolve_health,
}