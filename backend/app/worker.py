"""Durable background worker for jobs and the transactional outbox.

Jobs are leased from PostgreSQL with ``FOR UPDATE SKIP LOCKED``. A job's
domain side effects and terminal state are committed together, so a retry can
only run work that was rolled back. The outbox is dispatched in a separate
transaction after the originating business transaction has committed.
"""

import asyncio
import logging
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from opentelemetry import metrics, trace
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityEvent, Job, OutboxEvent
from app.models.cash_sim import CashEntry, CashJournal, CashRequest
from app.models.inventory import Balance, InventoryRequest, Movement, StockLevel
from app.models.reconciliation import ReconciliationException, ReconciliationRun

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = int(os.environ.get("WORKER_POLL_INTERVAL", "5"))
LEASE_SECONDS = int(os.environ.get("WORKER_LEASE_SECONDS", "60"))
MAX_RETRY = int(os.environ.get("WORKER_MAX_RETRY", "5"))
WORKER_ID = os.environ.get("WORKER_ID", socket.gethostname())
OUTBOX_BATCH_SIZE = 50
_worker_meter = metrics.get_meter("bankops.worker")
_worker_poll_results = _worker_meter.create_counter(
    "quanlykho_worker_polls_total",
    description="Worker poll loop outcomes.",
)
_worker_job_results = _worker_meter.create_counter(
    "quanlykho_worker_jobs_total",
    description="Leased background job outcomes.",
)
_worker_outbox_dispatched = _worker_meter.create_counter(
    "quanlykho_worker_outbox_dispatched_total",
    description="Outbox events materialized by the worker.",
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _claimable_job_condition(now: datetime):
    """Return queued jobs due now plus abandoned, expired leases."""
    return or_(
        and_(
            Job.status == "queued",
            or_(Job.next_attempt.is_(None), Job.next_attempt <= now),
        ),
        and_(
            Job.status == "running",
            Job.lease_until.is_not(None),
            Job.lease_until <= now,
        ),
    )


async def claim_job(session: AsyncSession) -> Job | None:
    """Atomically lease one due job without blocking other worker processes."""
    now = _utcnow()
    statement = (
        select(Job)
        .where(_claimable_job_condition(now))
        .order_by(Job.next_attempt.asc().nullsfirst(), Job.created_at, Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = (await session.execute(statement)).scalar_one_or_none()
    if job is None:
        return None

    job.status = "running"
    job.lease_owner = WORKER_ID
    job.lease_token = uuid.uuid4().hex
    job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    job.heartbeat_at = now
    job.next_attempt = None
    # Handle both ORM model (has column) and test mocks (may not have attribute)
    if getattr(job, "retry_count", None) is None:
        job.retry_count = 0
    await session.commit()
    logger.info(
        "Claimed job %s type=%s lease=%ss",
        job.id,
        job.type,
        LEASE_SECONDS,
    )
    return job


async def _load_owned_job(
    session: AsyncSession, job_id: object, lease_token: str
) -> Job | None:
    """Lock the job before executing so an expired lease cannot double-run it."""
    now = _utcnow()
    statement = (
        select(Job)
        .where(
            Job.id == job_id,
            Job.status == "running",
            Job.lease_token == lease_token,
            Job.lease_until > now,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.execute(statement)).scalar_one_or_none()


def _reconciliation_scope(job_type: str) -> str | None:
    """Translate the explicitly supported reconciliation job names to scope."""
    scopes = {
        "reconciliation": "all",
        "reconciliation:all": "all",
        "reconciliation:cash": "cash",
        "reconciliation:inventory": "inventory",
    }
    return scopes.get(job_type)


async def _run_reconciliation(session: AsyncSession, scope: str) -> tuple[int, int]:
    """Record differences only; reconciliation never changes a source balance."""
    run = ReconciliationRun(
        id=uuid.uuid4(), scope=scope, status="running", auto_fixed=False
    )
    session.add(run)
    await session.flush()

    total = 0
    exceptions: list[tuple[str, dict, dict]] = []
    if scope in ("all", "cash"):
        journals = (await session.execute(select(CashJournal))).scalars().all()
        for journal in journals:
            total += 1
            entries = (
                await session.execute(
                    select(CashEntry).where(CashEntry.journal_id == journal.id)
                )
            ).scalars().all()
            debit = sum((entry.debit or Decimal(0) for entry in entries), Decimal(0))
            credit = sum((entry.credit or Decimal(0) for entry in entries), Decimal(0))
            if debit != credit:
                exceptions.append(
                    (
                        f"journal:{journal.id}",
                        {"debit": str(debit), "credit": str(debit)},
                        {"debit": str(debit), "credit": str(credit)},
                    )
                )

    if scope in ("all", "inventory"):
        movements = (await session.execute(select(Movement))).scalars().all()
        expected: dict[tuple[str, str], Decimal] = {}
        for movement in movements:
            key = (str(movement.location_id), str(movement.item_id))
            expected[key] = expected.get(key, Decimal(0)) + (
                movement.quantity_signed or Decimal(0)
            )

        balances = (await session.execute(select(Balance))).scalars().all()
        actual = {
            (str(balance.location_id), str(balance.item_id)): balance.quantity
            or Decimal(0)
            for balance in balances
        }
        for key in expected.keys() | actual.keys():
            total += 1
            expected_quantity = expected.get(key, Decimal(0))
            actual_quantity = actual.get(key)
            if actual_quantity is None or expected_quantity != actual_quantity:
                exceptions.append(
                    (
                        f"balance:{key[0]}:{key[1]}",
                        {"quantity": str(expected_quantity)},
                        {
                            "quantity": (
                                str(actual_quantity)
                                if actual_quantity is not None
                                else None
                            )
                        },
                    )
                )

    for subject, expected_json, actual_json in exceptions:
        session.add(
            ReconciliationException(
                id=uuid.uuid4(),
                run_id=run.id,
                subject=subject,
                expected_json=expected_json,
                actual_json=actual_json,
            )
        )
    run.status = "exception" if exceptions else "matched"
    return total, total


async def _run_sla_reminders(session: AsyncSession, job: Job) -> tuple[int, int]:
    """Queue reminders for real submitted inventory and cash requests."""
    inventory_requests = (
        await session.execute(
            select(InventoryRequest).where(InventoryRequest.status == "submitted")
        )
    ).scalars().all()
    cash_requests = (
        await session.execute(select(CashRequest).where(CashRequest.status == "submitted"))
    ).scalars().all()
    pending_requests = [*inventory_requests, *cash_requests]

    for request in pending_requests:
        session.add(
            OutboxEvent(
                id=uuid.uuid4(),
                event_type="sla.reminder.dispatched",
                aggregate_id=str(request.id),
                payload_json={
                    "request_id": str(request.id),
                    "status": request.status,
                    "created_at": (
                        request.created_at.isoformat() if request.created_at else None
                    ),
                    "job_id": str(job.id),
                },
                created_at=_utcnow(),
                attempts=0,
            )
        )
    return len(pending_requests), len(pending_requests)


async def _run_inventory_thresholds(
    session: AsyncSession, job: Job
) -> tuple[int, int]:
    """Queue one low-stock event per configured stock level below its minimum."""
    statement = select(Balance, StockLevel).join(
        StockLevel,
        and_(
            StockLevel.location_id == Balance.location_id,
            StockLevel.item_id == Balance.item_id,
        ),
    )
    rows = (await session.execute(statement)).all()
    breaches = 0
    for balance, stock_level in rows:
        available_quantity = balance.available_quantity
        minimum = stock_level.min_qty or Decimal(0)
        if minimum <= 0 or available_quantity >= minimum:
            continue
        breaches += 1
        session.add(
            OutboxEvent(
                id=uuid.uuid4(),
                event_type="inventory.threshold.breached",
                aggregate_id=f"{balance.location_id}:{balance.item_id}",
                payload_json={
                    "location_id": str(balance.location_id),
                    "item_id": str(balance.item_id),
                    "available_quantity": str(available_quantity),
                    "min_quantity": str(minimum),
                    "job_id": str(job.id),
                },
                created_at=_utcnow(),
                attempts=0,
            )
        )
    return breaches, len(rows)


async def _execute_job_payload(
    session: AsyncSession, job: Job
) -> tuple[int, int]:
    """Run an explicitly registered job type against the real ORM models."""
    job_type = job.type.lower().strip()
    scope = _reconciliation_scope(job_type)
    if scope is not None:
        return await _run_reconciliation(session, scope)
    if job_type == "sla_reminder":
        return await _run_sla_reminders(session, job)
    if job_type == "inventory_thresholds":
        return await _run_inventory_thresholds(session, job)
    raise ValueError(f"Unsupported job type: {job.type!r}")


async def _record_job_failure(
    session: AsyncSession, job_id: object, lease_token: str, error: Exception
) -> bool:
    """Release an owned lease for retry, or terminally fail it after MAX_RETRY."""
    statement = (
        select(Job)
        .where(
            Job.id == job_id,
            Job.status == "running",
            Job.lease_token == lease_token,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    job = (await session.execute(statement)).scalar_one_or_none()
    if job is None:
        await session.rollback()
        return False

    retry_count = (getattr(job, "retry_count", None) or 0) + 1
    job.retry_count = retry_count
    job.error_code = type(error).__name__[:64]
    job.heartbeat_at = _utcnow()
    job.lease_owner = None
    job.lease_token = None
    job.lease_until = None
    if retry_count >= MAX_RETRY:
        job.status = "failed"
        job.finished_at = _utcnow()
        job.next_attempt = None
    else:
        job.status = "queued"
        job.next_attempt = _utcnow() + timedelta(seconds=2 ** min(retry_count, 6))
    await session.commit()
    return True


async def run_job_with_retry(session: AsyncSession, claimed_job: Job) -> bool:
    """Run a leased job once and persist its result or an eligible retry."""
    job_id = claimed_job.id
    lease_token = claimed_job.lease_token
    if not lease_token:
        logger.warning("Refusing to execute job %s without a lease token", job_id)
        return False

    try:
        job = await _load_owned_job(session, job_id, lease_token)
        if job is None:
            await session.rollback()
            logger.info("Job %s lease was superseded before execution", job_id)
            return False

        now = _utcnow()
        job.heartbeat_at = now
        job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        processed, total = await _execute_job_payload(session, job)
        job.processed = processed
        job.total = total
        job.status = "succeeded"
        job.finished_at = _utcnow()
        job.heartbeat_at = _utcnow()
        job.lease_owner = None
        job.lease_token = None
        job.lease_until = None
        job.next_attempt = None
        await session.commit()
        logger.info("Job %s succeeded (processed=%s/%s)", job_id, processed, total)
        return True
    except Exception as error:  # side effects above are rolled back before retry
        await session.rollback()
        recorded = await _record_job_failure(session, job_id, lease_token, error)
        logger.warning("Job %s failed; retry recorded=%s: %s", job_id, recorded, error)
        return False


async def dispatch_outbox(session: AsyncSession) -> int:
    """Materialize unpublished outbox rows as durable activity events once."""
    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .with_for_update(skip_locked=True)
        .limit(OUTBOX_BATCH_SIZE)
    )
    events = list((await session.execute(statement)).scalars().all())
    if not events:
        return 0

    now = _utcnow()
    for event in events:
        session.add(
            ActivityEvent(
                id=uuid.uuid4(),
                type=event.event_type,
                subject=event.aggregate_id,
                message_key=event.event_type,
                payload=(event.payload_json if isinstance(event.payload_json, dict) else {}),
                occurred_at=now,
                outbox_event_id=event.id,
            )
        )
        event.attempts = (event.attempts or 0) + 1
        event.published_at = now
    await session.commit()
    return len(events)


async def poll_once(session: AsyncSession) -> dict[str, str | int | None]:
    """Claim and run one job, then publish a bounded outbox batch."""
    job = await claim_job(session)
    if job is not None:
        succeeded = await run_job_with_retry(session, job)
        _worker_job_results.add(1, {"outcome": "succeeded" if succeeded else "retryable_failure"})
        _worker_poll_results.add(1, {"outcome": "job_claimed"})
    else:
        _worker_poll_results.add(1, {"outcome": "idle"})
    dispatched = await dispatch_outbox(session)
    if dispatched:
        _worker_outbox_dispatched.add(dispatched)
    return {"job_id": str(job.id) if job is not None else None, "dispatched": dispatched}


async def process_jobs() -> None:
    """Run the polling loop in a dedicated process sharing the FastAPI package."""
    from app.api.structured_logging import configure_json_logging
    from app.api.telemetry import (
        create_meter_provider,
        create_tracer_provider,
        instrument_sqlalchemy,
    )
    from app.database import AsyncSessionLocal, engine

    configure_json_logging()
    tracer_provider = create_tracer_provider(service_name="bankops-worker")
    trace.set_tracer_provider(tracer_provider)
    instrument_sqlalchemy(engine, tracer_provider=tracer_provider)
    LoggingInstrumentor().instrument(tracer_provider=tracer_provider, set_logging_format=False)
    meter_provider = create_meter_provider(service_name="bankops-worker")
    metrics.set_meter_provider(meter_provider)
    logger.info("Worker %s started", WORKER_ID)
    try:
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    outcome = await poll_once(session)
                    if outcome["job_id"] or outcome["dispatched"]:
                        logger.info("Worker heartbeat job=%s outbox=%s", outcome["job_id"], outcome["dispatched"])
            except Exception as error:
                _worker_poll_results.add(1, {"outcome": "error"})
                logger.warning("Worker poll failed; retrying later: %s", error)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        meter_provider.shutdown()
        tracer_provider.shutdown()


def main() -> None:
    """Entry point for the background worker process."""
    asyncio.run(process_jobs())


if __name__ == "__main__":
    main()
