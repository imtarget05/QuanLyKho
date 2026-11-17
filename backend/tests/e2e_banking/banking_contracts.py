"""Institutional-grade banking and treasury contracts for E2E verification.

Implements all 6 core financial patterns from PROJECT.md § Interface Contracts:
1. Double-Entry General Ledger Engine & Multi-Tier Balances
2. Strict Financial Idempotency Layer with In-Flight Locks & Replay Cache
3. Transactional Outbox Pattern & Consumer Deduplication
4. Distributed Saga Orchestrator with Automated Compensation
5. Concurrency Control, Deadlock-Free Resource Ordering & Optimistic CAS
6. Cryptographic Hash-Chained Audit Trail & Tamper Verification
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    delete,
    event,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base, relationship

BankingBase = declarative_base()

GENESIS_HASH = "0" * 64

# ============================================================================
# 1. DATABASE MODELS
# ============================================================================

class COAAccount(BankingBase):
    """Chart of Accounts (COA) Model."""
    __tablename__ = "coa_accounts"

    code = Column(String(128), primary_key=True)
    name = Column(String(256), nullable=False)
    account_type = Column(String(32), nullable=False)  # asset, liability, equity, revenue, expense
    normal_balance = Column(String(8), nullable=False)  # debit, credit
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    balance = relationship("GLAccountBalance", back_populates="account", uselist=False, lazy="selectin")


class GLAccountBalance(BankingBase):
    """Multi-tier Account Balance Model in integer cents."""
    __tablename__ = "gl_account_balances"

    account_code = Column(String(128), ForeignKey("coa_accounts.code"), primary_key=True)
    ledger_balance = Column(BigInteger, nullable=False, default=0)
    available_balance = Column(BigInteger, nullable=False, default=0)
    hold_balance = Column(BigInteger, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    account = relationship("COAAccount", back_populates="balance", lazy="selectin")


class GLJournal(BankingBase):
    """General Ledger Journal Header."""
    __tablename__ = "gl_journals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type = Column(String(32), nullable=False)  # inventory, order, transfer, manual, adjustment
    source_journal_id = Column(String(64), nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    correlation_id = Column(String(64), nullable=False, index=True)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    entries = relationship("GLJournalEntry", back_populates="journal", cascade="all, delete-orphan")


class GLJournalEntry(BankingBase):
    """General Ledger Journal Entry Line Item in integer cents."""
    __tablename__ = "gl_journal_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    journal_id = Column(String(36), ForeignKey("gl_journals.id", ondelete="CASCADE"), nullable=False, index=True)
    account_code = Column(String(128), ForeignKey("coa_accounts.code"), nullable=False, index=True)
    debit = Column(BigInteger, nullable=False, default=0)
    credit = Column(BigInteger, nullable=False, default=0)
    description = Column(String(255), nullable=True)

    journal = relationship("GLJournal", back_populates="entries")


class IdempotencyKeyRecord(BankingBase):
    """Durable Idempotency Key Storage & State Machine."""
    __tablename__ = "idempotency_keys"

    key = Column(String(128), primary_key=True)
    request_hash = Column(String(64), nullable=False)
    request_path = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="PENDING")  # PENDING, PROCESSING, COMPLETED, FAILED
    status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime(timezone=True), nullable=False)


class OutboxEventRecord(BankingBase):
    """Transactional Outbox Event Persistence."""
    __tablename__ = "outbox_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    topic = Column(String(128), nullable=False, index=True)
    event_type = Column(String(128), nullable=False)
    aggregate_id = Column(String(128), nullable=False, index=True)
    payload = Column(Text, nullable=False)
    trace_id = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="PENDING")  # PENDING, PUBLISHED, FAILED
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    published_at = Column(DateTime(timezone=True), nullable=True)


class ProcessedEventRecord(BankingBase):
    """Consumer Deduplication Registry."""
    __tablename__ = "processed_events"

    event_id = Column(String(36), primary_key=True)
    consumer_group = Column(String(64), primary_key=True)
    processed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class SagaInstanceRecord(BankingBase):
    """Distributed Saga Instance State Machine."""
    __tablename__ = "saga_instances"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    saga_name = Column(String(128), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="PENDING")  # PENDING, RUNNING, COMPLETED, COMPENSATING, COMPENSATED, FAILED
    current_step = Column(String(128), nullable=True)
    context = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    step_logs = relationship("SagaStepLogRecord", back_populates="saga", cascade="all, delete-orphan")


class SagaStepLogRecord(BankingBase):
    """Saga Step Execution and Compensation Audit Log."""
    __tablename__ = "saga_step_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    saga_id = Column(String(36), ForeignKey("saga_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    step_name = Column(String(128), nullable=False)
    step_order = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="PENDING")  # PENDING, COMPLETED, FAILED, COMPENSATED
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    saga = relationship("SagaInstanceRecord", back_populates="step_logs")


class AuditChainRecord(BankingBase):
    """Cryptographic Append-Only Hash-Chained Audit Trail."""
    __tablename__ = "audit_events_chain"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(36), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
    actor_id = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(64), nullable=False)
    state_payload = Column(Text, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    prev_hash = Column(String(64), nullable=False)
    current_hash = Column(String(64), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


# WORM (Write Once, Read Many) enforcement at ORM layer
@event.listens_for(AuditChainRecord, "before_update", propagate=True)
def _guard_audit_no_update(mapper, connection, target):
    raise PermissionError("Audit trail is immutable and append-only: UPDATE is forbidden.")

@event.listens_for(AuditChainRecord, "before_delete", propagate=True)
def _guard_audit_no_delete(mapper, connection, target):
    raise PermissionError("Audit trail is immutable and append-only: DELETE is forbidden.")


class WarehouseRecord(BankingBase):
    """Warehouse / Location entity."""
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), nullable=False, unique=True)
    name = Column(String(128), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class ProductRecord(BankingBase):
    """Product / SKU item entity."""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String(64), nullable=False, unique=True)
    name = Column(String(128), nullable=False)
    unit_cost_cents = Column(BigInteger, nullable=False)


class InventoryBalanceRecord(BankingBase):
    """Warehouse inventory balance in integer units."""
    __tablename__ = "inventory_balances"

    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    quantity = Column(BigInteger, nullable=False, default=0)
    reserved_quantity = Column(BigInteger, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)


# ============================================================================
# 2. UTILITY & CRYPTOGRAPHIC FUNCTIONS
# ============================================================================

def compute_canonical_hash(payload: Any) -> str:
    """Computes SHA-256 fingerprint of canonicalized JSON (sorted keys)."""
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compute_audit_hash(
    prev_hash: str,
    timestamp_str: str,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload_hash: str,
) -> str:
    """Computes H_n = SHA-256(H_{n-1} || timestamp || actor || action || entity_type || entity_id || payload_hash)."""
    parts = [prev_hash, timestamp_str, actor_id, action, entity_type, entity_id, payload_hash]
    raw_material = "|".join(parts)
    return hashlib.sha256(raw_material.encode("utf-8")).hexdigest()


# ============================================================================
# 3. EXCEPTIONS
# ============================================================================

class BankingException(Exception):
    """Base exception for banking operations."""

class InsufficientBalanceException(BankingException):
    """Raised when available balance or inventory is insufficient."""

class UnbalancedJournalException(BankingException):
    """Raised when Sum(Debit) != Sum(Credit)."""

class IdempotencyConflictException(BankingException):
    """Raised when an idempotency key is reused with an altered payload (HTTP 409)."""
    def __init__(self, message: str = "Idempotency key reused with conflicting payload", status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code

class IdempotencyInFlightException(BankingException):
    """Raised when a concurrent request with the same idempotency key is in-flight."""
    def __init__(self, message: str = "Request currently in-flight", status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code

class OptimisticConcurrencyException(BankingException):
    """Raised when a CAS version conflict is detected."""

class AuditTrailTamperedException(BankingException):
    """Raised when audit chain integrity verification fails."""


# ============================================================================
# 4. DOUBLE-ENTRY GENERAL LEDGER SERVICE
# ============================================================================

async def ensure_account_balance(session: AsyncSession, account_code: str) -> GLAccountBalance:
    """Ensures balance record exists for given account code."""
    res = await session.execute(
        select(GLAccountBalance).where(GLAccountBalance.account_code == account_code)
    )
    bal = res.scalars().first()
    if bal is None:
        bal = GLAccountBalance(
            account_code=account_code,
            ledger_balance=0,
            available_balance=0,
            hold_balance=0,
            version=1,
            updated_at=datetime.now(UTC),
        )
        session.add(bal)
        await session.flush()
    return bal


async def post_inventory_movement_to_gl(
    session: AsyncSession,
    movement_type: str,
    product_id: int,
    quantity: int,
    unit_cost_cents: int,
    reference_id: str,
    warehouse_id: int,
    description: str,
    dest_warehouse_id: int | None = None,
) -> GLJournal:
    """Creates and commits a balanced GL journal entry matching PROJECT.md § Interface Contracts:

    - STOCK_IN: Debit Account 156 (Inventory Asset), Credit Account 331 (Accounts Payable)
    - STOCK_OUT: Debit Account 632 (COGS Expense), Credit Account 156 (Inventory Asset)
    - TRANSFER: Debit Account 156 (Dest Warehouse), Credit Account 156 (Source Warehouse)
    - ADJUSTMENT:
        If quantity > 0: Debit Account 156, Credit Account 338 (Inventory Gain)
        If quantity < 0: Debit Account 632 (Inventory Spoilage/Loss), Credit Account 156
    Enforces Sum(Debit) == Sum(Credit) and updates gl_account_balances atomically.
    """
    if quantity == 0:
        raise ValueError("Quantity cannot be zero for inventory movement.")
    if unit_cost_cents < 0:
        raise ValueError("Unit cost cannot be negative.")

    abs_qty = abs(quantity)
    total_cents = abs_qty * unit_cost_cents

    journal = GLJournal(
        source_type="inventory",
        source_journal_id=str(reference_id),
        correlation_id=f"corr-{reference_id}",
        description=description,
        posted_at=datetime.now(UTC),
    )
    session.add(journal)
    await session.flush()

    entries: list[GLJournalEntry] = []

    if movement_type == "STOCK_IN":
        # Debit 156 (Asset +), Credit 331 (Liability +)
        entries.append(GLJournalEntry(journal_id=journal.id, account_code="156", debit=total_cents, credit=0, description=f"Stock In Product {product_id}"))
        entries.append(GLJournalEntry(journal_id=journal.id, account_code="331", debit=0, credit=total_cents, description=f"Payable Supplier Product {product_id}"))
    elif movement_type == "STOCK_OUT":
        # Debit 632 (Expense +), Credit 156 (Asset -)
        entries.append(GLJournalEntry(journal_id=journal.id, account_code="632", debit=total_cents, credit=0, description=f"COGS Product {product_id}"))
        entries.append(GLJournalEntry(journal_id=journal.id, account_code="156", debit=0, credit=total_cents, description=f"Stock Out Product {product_id}"))
    elif movement_type == "TRANSFER":
        # Transfer between warehouses or transit: Debit 156, Credit 156
        entries.append(GLJournalEntry(journal_id=journal.id, account_code="156", debit=total_cents, credit=0, description=f"Transfer In WH {dest_warehouse_id}"))
        entries.append(GLJournalEntry(journal_id=journal.id, account_code="156", debit=0, credit=total_cents, description=f"Transfer Out WH {warehouse_id}"))
    elif movement_type == "ADJUSTMENT":
        if quantity > 0:
            entries.append(GLJournalEntry(journal_id=journal.id, account_code="156", debit=total_cents, credit=0, description=f"Adjustment Gain {product_id}"))
            entries.append(GLJournalEntry(journal_id=journal.id, account_code="338", debit=0, credit=total_cents, description=f"Inventory Surplus {product_id}"))
        else:
            entries.append(GLJournalEntry(journal_id=journal.id, account_code="632", debit=total_cents, credit=0, description=f"Adjustment Spoilage Loss {product_id}"))
            entries.append(GLJournalEntry(journal_id=journal.id, account_code="156", debit=0, credit=total_cents, description=f"Stock Reduction {product_id}"))
    else:
        raise ValueError(f"Unsupported movement_type: {movement_type}")

    # Validate Double-Entry Invariant: Sum(Debit) == Sum(Credit)
    total_debit = sum(e.debit for e in entries)
    total_credit = sum(e.credit for e in entries)
    if total_debit != total_credit:
        raise UnbalancedJournalException(f"Unbalanced journal: Debit={total_debit} != Credit={total_credit}")

    for e in entries:
        session.add(e)
    await session.flush()

    # Atomically update gl_account_balances according to normal balance rules
    for e in entries:
        acc_res = await session.execute(select(COAAccount).where(COAAccount.code == e.account_code))
        acc = acc_res.scalars().first()
        if not acc:
            raise ValueError(f"Account code {e.account_code} does not exist in Chart of Accounts.")

        bal = await ensure_account_balance(session, e.account_code)
        if acc.normal_balance == "debit":
            # Normal Debit: Debit increases (+), Credit decreases (-)
            delta = e.debit - e.credit
        else:
            # Normal Credit: Credit increases (+), Debit decreases (-)
            delta = e.credit - e.debit

        bal.ledger_balance += delta
        bal.available_balance = bal.ledger_balance - bal.hold_balance
        bal.version += 1
        bal.updated_at = datetime.now(UTC)

    await session.flush()
    return journal


# ============================================================================
# 5. STRICT FINANCIAL IDEMPOTENCY LAYER
# ============================================================================

_in_flight_locks: dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()

async def _get_key_mutex(key: str) -> asyncio.Lock:
    async with _locks_guard:
        if key not in _in_flight_locks:
            _in_flight_locks[key] = asyncio.Lock()
        return _in_flight_locks[key]


async def execute_idempotent_operation(
    session: AsyncSession,
    idempotency_key: str,
    request_path: str,
    request_payload: dict,
    operation_coroutine: Callable[[], Coroutine[Any, Any, tuple[int, dict]]],
    ttl_seconds: int = 86400,
) -> tuple[int, dict, bool]:
    """Coordinates idempotency checking matching PROJECT.md § Interface Contracts:

    1. Computes SHA-256 of canonical JSON payload.
    2. Atomically sets status to PENDING with in-flight lock.
    3. If existing COMPLETED record exists with matching hash: returns cached (status_code, body, is_replay=True).
    4. If existing record exists with different hash: raises IdempotencyConflictException (HTTP 409).
    5. Executes operation_coroutine, caches result, marks COMPLETED, returns (status_code, body, is_replay=False).
    """
    if not idempotency_key or not idempotency_key.strip():
        raise ValueError("Idempotency-Key header is mandatory and cannot be empty.")

    payload_hash = compute_canonical_hash(request_payload)
    now = datetime.now(UTC)

    mutex = await _get_key_mutex(idempotency_key)
    if mutex.locked():
        # Another coroutine is currently holding the lock for this key
        raise IdempotencyInFlightException(f"Concurrent in-flight request on key '{idempotency_key}' (HTTP 409)")

    async with mutex:
        res = await session.execute(
            select(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == idempotency_key)
        )
        record = res.scalars().first()

        if record is not None:
            # Check for expired key
            exp = record.expires_at if (record.expires_at and record.expires_at.tzinfo) else (record.expires_at.replace(tzinfo=UTC) if record.expires_at else None)
            if exp and exp < now:
                await session.execute(
                    delete(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == idempotency_key)
                )
                await session.flush()
                record = None
            elif record.status == "COMPLETED":
                if record.request_hash == payload_hash:
                    cached_body = json.loads(record.response_body) if record.response_body else {}
                    return (record.status_code, cached_body, True)
                else:
                    raise IdempotencyConflictException(
                        f"Idempotency key '{idempotency_key}' already used with different payload (HTTP 409)"
                    )
            elif record.status in ("PENDING", "PROCESSING"):
                raise IdempotencyInFlightException(f"Concurrent request in-flight for key '{idempotency_key}' (HTTP 409)")
            elif record.status == "FAILED":
                # Previous attempt failed; permit retry by resetting to PENDING
                record.status = "PENDING"
                record.request_hash = payload_hash
                record.request_path = request_path
                record.expires_at = now + timedelta(seconds=ttl_seconds)
                record.response_body = None
                record.status_code = None
                await session.flush()
                new_record = record

        if record is None:
            # First-time registration: status = PENDING
            expires_at = now + timedelta(seconds=ttl_seconds)
            new_record = IdempotencyKeyRecord(
                key=idempotency_key,
                request_hash=payload_hash,
                request_path=request_path,
                status="PENDING",
                created_at=now,
                expires_at=expires_at,
            )
            session.add(new_record)
            await session.flush()

        try:
            status_code, body = await operation_coroutine()
            new_record.status = "COMPLETED"
            new_record.status_code = status_code
            new_record.response_body = json.dumps(body)
            await session.flush()
            return (status_code, body, False)
        except Exception as exc:
            new_record.status = "FAILED"
            new_record.response_body = json.dumps({"error": str(exc)})
            await session.flush()
            raise


# ============================================================================
# 6. TRANSACTIONAL OUTBOX & CONSUMER DEDUPLICATION
# ============================================================================

async def emit_outbox_event(
    session: AsyncSession,
    topic: str,
    event_type: str,
    aggregate_id: str,
    payload: dict,
    trace_id: str,
) -> OutboxEventRecord:
    """Atomically writes an outbox event in the same DB transaction as business logic."""
    if not topic or not topic.strip():
        raise ValueError("Outbox topic cannot be empty.")
    if not event_type or not event_type.strip():
        raise ValueError("Outbox event_type cannot be empty.")

    event_record = OutboxEventRecord(
        topic=topic,
        event_type=event_type,
        aggregate_id=aggregate_id,
        payload=json.dumps(payload, default=str),
        trace_id=trace_id,
        status="PENDING",
        attempts=0,
        created_at=datetime.now(UTC),
    )
    session.add(event_record)
    await session.flush()
    return event_record


async def drain_outbox_events(
    session: AsyncSession,
    limit: int = 100,
    subscriber_fn: Callable[[OutboxEventRecord], Coroutine[Any, Any, bool]] | None = None,
) -> list[OutboxEventRecord]:
    """Polls pending outbox events and broadcasts to local bus subscriber."""
    res = await session.execute(
        select(OutboxEventRecord)
        .where(OutboxEventRecord.status == "PENDING")
        .order_by(OutboxEventRecord.created_at.asc())
        .limit(limit)
    )
    events = res.scalars().all()
    processed: list[OutboxEventRecord] = []

    for ev in events:
        ev.attempts += 1
        success = True
        if subscriber_fn:
            try:
                success = await subscriber_fn(ev)
            except Exception:
                success = False

        if success:
            ev.status = "PUBLISHED"
            ev.published_at = datetime.now(UTC)
        else:
            if ev.attempts >= 3:
                ev.status = "FAILED"
        processed.append(ev)

    await session.flush()
    return processed


async def process_event_with_deduplication(
    session: AsyncSession,
    event_id: str,
    consumer_group: str,
    handler: Callable[[dict], Coroutine[Any, Any, None]],
    payload: dict,
) -> bool:
    """Consumer deduplication: checks processed_events table before running handler."""
    res = await session.execute(
        select(ProcessedEventRecord).where(
            ProcessedEventRecord.event_id == event_id,
            ProcessedEventRecord.consumer_group == consumer_group,
        )
    )
    if res.scalars().first() is not None:
        return False  # Already processed (deduplicated)

    await handler(payload)

    proc_record = ProcessedEventRecord(
        event_id=event_id,
        consumer_group=consumer_group,
        processed_at=datetime.now(UTC),
    )
    session.add(proc_record)
    await session.flush()
    return True


# ============================================================================
# 7. DISTRIBUTED SAGA ORCHESTRATION ENGINE
# ============================================================================

class SagaContext(dict):
    """Context dictionary passed across saga steps."""
    pass


class SagaStep(Protocol):
    name: str
    async def execute(self, session: AsyncSession, context: SagaContext) -> bool: ...
    async def compensate(self, session: AsyncSession, context: SagaContext) -> bool: ...


class SagaResult:
    def __init__(
        self,
        saga_id: str,
        saga_name: str,
        success: bool,
        status: str,
        completed_steps: list[str],
        failed_step: str | None = None,
        error: str | None = None,
    ):
        self.saga_id = saga_id
        self.saga_name = saga_name
        self.success = success
        self.status = status
        self.completed_steps = completed_steps
        self.failed_step = failed_step
        self.error = error

    def __repr__(self) -> str:
        return f"<SagaResult {self.saga_name} success={self.success} status={self.status}>"


class SagaOrchestrator:
    """Coordinates forward multi-step distributed operations and automated compensation."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute_saga(
        self,
        saga_name: str,
        steps: list[SagaStep],
        context: SagaContext,
        saga_id: str | None = None,
    ) -> SagaResult:
        if not steps:
            raise ValueError("Saga must contain at least one step.")

        sid = saga_id or str(uuid.uuid4())

        # Check existing saga instance for idempotency
        res = await self.session.execute(
            select(SagaInstanceRecord).where(SagaInstanceRecord.id == sid)
        )
        existing = res.scalars().first()
        if existing and existing.status in ("COMPLETED", "COMPENSATED"):
            return SagaResult(
                saga_id=existing.id,
                saga_name=existing.saga_name,
                success=(existing.status == "COMPLETED"),
                status=existing.status,
                completed_steps=[],
            )

        saga_rec = existing or SagaInstanceRecord(
            id=sid,
            saga_name=saga_name,
            status="RUNNING",
            context=json.dumps(context, default=str),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        if not existing:
            self.session.add(saga_rec)
        else:
            saga_rec.status = "RUNNING"
        await self.session.flush()

        completed_steps: list[SagaStep] = []

        for idx, step in enumerate(steps, start=1):
            saga_rec.current_step = step.name
            step_log = SagaStepLogRecord(
                saga_id=saga_rec.id,
                step_name=step.name,
                step_order=idx,
                status="PENDING",
                created_at=datetime.now(UTC),
            )
            self.session.add(step_log)
            await self.session.flush()

            try:
                ok = await step.execute(self.session, context)
                if not ok:
                    raise BankingException(f"Step '{step.name}' returned non-success.")
                step_log.status = "COMPLETED"
                step_log.completed_at = datetime.now(UTC)
                completed_steps.append(step)
                await self.session.flush()
            except Exception as exc:
                # Step failed: initiate compensation
                step_log.status = "FAILED"
                step_log.error = str(exc)
                saga_rec.status = "COMPENSATING"
                await self.session.flush()

                # Rollback completed steps in reverse order
                for comp_step in reversed(completed_steps):
                    comp_log = SagaStepLogRecord(
                        saga_id=saga_rec.id,
                        step_name=f"Compensate-{comp_step.name}",
                        step_order=idx + 10,
                        status="PENDING",
                        created_at=datetime.now(UTC),
                    )
                    self.session.add(comp_log)
                    await self.session.flush()
                    try:
                        await comp_step.compensate(self.session, context)
                        comp_log.status = "COMPENSATED"
                        comp_log.completed_at = datetime.now(UTC)
                    except Exception as comp_err:
                        comp_log.status = "FAILED"
                        comp_log.error = str(comp_err)
                    await self.session.flush()

                saga_rec.status = "COMPENSATED"
                saga_rec.updated_at = datetime.now(UTC)
                await self.session.flush()

                return SagaResult(
                    saga_id=saga_rec.id,
                    saga_name=saga_name,
                    success=False,
                    status="COMPENSATED",
                    completed_steps=[s.name for s in completed_steps],
                    failed_step=step.name,
                    error=str(exc),
                )

        saga_rec.status = "COMPLETED"
        saga_rec.current_step = "FINAL"
        saga_rec.updated_at = datetime.now(UTC)
        await self.session.flush()

        return SagaResult(
            saga_id=saga_rec.id,
            saga_name=saga_name,
            success=True,
            status="COMPLETED",
            completed_steps=[s.name for s in completed_steps],
        )


# ============================================================================
# 8. CONCURRENCY & LOCKING ENGINE
# ============================================================================

def order_resources(resource_ids: list[Any]) -> list[Any]:
    """Sorts resource IDs lexicographically / numerically to guarantee deadlock-free locking."""
    return sorted(resource_ids, key=lambda x: str(x))


class KeyedLockManager:
    """Thread-safe and coroutine-safe in-process mutex manager per resource key."""
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self._master = asyncio.Lock()

    async def get_lock(self, key: str) -> asyncio.Lock:
        async with self._master:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]


lock_manager = KeyedLockManager()


async def cas_update_account_balance(
    session: AsyncSession,
    account_code: str,
    delta_cents: int,
    expected_version: int,
) -> GLAccountBalance:
    """Executes atomic Compare-And-Swap (CAS) update on account balance.

    Raises OptimisticConcurrencyException if expected_version does not match current version.
    """
    bal = await ensure_account_balance(session, account_code)
    if bal.version != expected_version:
        raise OptimisticConcurrencyException(
            f"CAS version mismatch on account {account_code}: expected {expected_version}, found {bal.version}"
        )

    acc_res = await session.execute(
        select(COAAccount.account_type).where(COAAccount.code == account_code)
    )
    acc_type = acc_res.scalar_one_or_none()

    new_ledger = bal.ledger_balance + delta_cents
    new_available = new_ledger - bal.hold_balance
    if new_available < 0 and acc_type == "asset":
        raise InsufficientBalanceException(f"Negative balance protection: {new_available} < 0")

    bal.ledger_balance = new_ledger
    bal.available_balance = new_available
    bal.version += 1
    bal.updated_at = datetime.now(UTC)
    await session.flush()
    return bal


# ============================================================================
# 9. CRYPTOGRAPHIC IMMUTABLE AUDIT TRAIL SERVICE
# ============================================================================

async def record_audit_entry(
    session: AsyncSession,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    state_payload: dict,
    timestamp: datetime | None = None,
) -> AuditChainRecord:
    """Computes current_hash = SHA256(prev_hash || timestamp || actor_id || action || entity_type || entity_id || payload_hash).

    Appends immutable audit record with cryptographic hash chaining.
    """
    # Fetch previous entry
    res = await session.execute(
        select(AuditChainRecord).order_by(AuditChainRecord.id.desc()).limit(1)
    )
    last_entry = res.scalars().first()
    prev_hash = last_entry.current_hash if last_entry else GENESIS_HASH

    ts = timestamp or datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    ts_iso = ts.astimezone(UTC).isoformat()
    payload_hash = compute_canonical_hash(state_payload)

    curr_hash = compute_audit_hash(
        prev_hash=prev_hash,
        timestamp_str=ts_iso,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_hash=payload_hash,
    )

    audit_entry = AuditChainRecord(
        event_id=str(uuid.uuid4()),
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        state_payload=json.dumps(state_payload, sort_keys=True, default=str),
        payload_hash=payload_hash,
        prev_hash=prev_hash,
        current_hash=curr_hash,
        timestamp=ts,
    )
    session.add(audit_entry)
    await session.flush()
    return audit_entry


async def verify_audit_chain_integrity(session: AsyncSession) -> tuple[bool, int | None]:
    """Scans the entire audit trail and verifies mathematical hash chain consistency.

    Returns:
        (True, None) if completely pristine.
        (False, corrupted_record_id) if any tampering or broken link is detected.
    """
    res = await session.execute(
        select(AuditChainRecord).order_by(AuditChainRecord.id.asc())
    )
    records = res.scalars().all()
    if not records:
        return (True, None)

    expected_prev = GENESIS_HASH
    for rec in records:
        # 1. Verify link to previous record
        if rec.prev_hash != expected_prev:
            return (False, rec.id)

        # 2. Recompute payload hash
        payload_dict = json.loads(rec.state_payload)
        recalculated_payload_hash = compute_canonical_hash(payload_dict)
        if recalculated_payload_hash != rec.payload_hash:
            return (False, rec.id)

        # 3. Recompute chain hash
        rec_ts = rec.timestamp if rec.timestamp.tzinfo is not None else rec.timestamp.replace(tzinfo=UTC)
        ts_iso = rec_ts.astimezone(UTC).isoformat()
        recalculated_hash = compute_audit_hash(
            prev_hash=rec.prev_hash,
            timestamp_str=ts_iso,
            actor_id=rec.actor_id,
            action=rec.action,
            entity_type=rec.entity_type,
            entity_id=rec.entity_id,
            payload_hash=rec.payload_hash,
        )
        if recalculated_hash != rec.current_hash:
            return (False, rec.id)

        expected_prev = rec.current_hash

    return (True, None)
