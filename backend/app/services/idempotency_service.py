"""Strict Financial Idempotency Engine (Milestone M3).

Implements PROJECT.md § Interface Contracts:
1. Order-independent canonical SHA-256 payload fingerprinting (`compute_canonical_hash`).
2. Atomic check and in-flight mutex locking (`PENDING` -> `COMPLETED` / `FAILED`) with TTL expiry.
3. Cached response replay returning exact status code and body with `is_replay=True`.
4. Semantic conflict rejection (HTTP 409 Conflict) when key is reused with altered payload.
5. Dialect-agnostic execution for SQLite (in-memory) and PostgreSQL.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import IdempotencyKeyRecord

__all__ = [
    "BankingException",
    "IdempotencyConflict",
    "IdempotencyConflictException",
    "IdempotencyInFlightException",
    "clear_in_flight_locks",
    "compute_canonical_hash",
    "execute_idempotent_operation",
    "payload_hash",
]


# ============================================================================
# 1. CANONICAL REQUEST FINGERPRINTING
# ============================================================================

def compute_canonical_hash(payload: Any) -> str:
    """Computes SHA-256 fingerprint of canonicalized JSON (sorted keys, compact delimiters)."""
    if payload is None:
        payload = {}
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


# Function alias for existing codebase parity
payload_hash = compute_canonical_hash


# ============================================================================
# 2. EXCEPTIONS
# ============================================================================

class BankingException(Exception):
    """Base exception for banking and treasury operations."""


class IdempotencyConflictException(BankingException):
    """Raised when an idempotency key is reused with an altered payload (HTTP 409)."""

    def __init__(
        self,
        message: str = "Idempotency key reused with conflicting payload",
        status_code: int = 409,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class IdempotencyConflict(IdempotencyConflictException):
    """Parity alias for legacy route error handlers."""

    def __init__(
        self,
        existing_status: int = 409,
        existing_body: Any = None,
        message: str = "Idempotency-Key đã dùng cho payload khác",
    ):
        super().__init__(message=message, status_code=409)
        self.existing_status = existing_status
        self.existing_body = existing_body or {}


class IdempotencyInFlightException(BankingException):
    """Raised when a concurrent request with the same idempotency key is in-flight (HTTP 409)."""

    def __init__(
        self,
        message: str = "Request currently in-flight",
        status_code: int = 409,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ============================================================================
# 3. IN-FLIGHT MUTEX LOCK MANAGER
# ============================================================================

_in_flight_locks: dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


async def _get_key_mutex(key: str) -> asyncio.Lock:
    """Atomically acquires or creates a coroutine mutex lock for a given idempotency key."""
    async with _locks_guard:
        if key not in _in_flight_locks:
            _in_flight_locks[key] = asyncio.Lock()
        return _in_flight_locks[key]


def clear_in_flight_locks() -> None:
    """Clears the in-memory mutex registry (used between test fixtures)."""
    _in_flight_locks.clear()


# ============================================================================
# 4. IDEMPOTENT OPERATION COORDINATOR
# ============================================================================

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

    p_hash = compute_canonical_hash(request_payload)
    now = datetime.now(UTC)

    mutex = await _get_key_mutex(idempotency_key)
    if mutex.locked():
        raise IdempotencyInFlightException(
            f"Concurrent in-flight request on key '{idempotency_key}' (HTTP 409)",
            status_code=409,
        )

    async with mutex:
        res = await session.execute(
            select(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == idempotency_key)
        )
        record = res.scalars().first()

        if record is not None:
            # Check for expired TTL
            exp = record.expires_at
            if exp and exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)

            if exp and exp < now:
                await session.execute(
                    delete(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == idempotency_key)
                )
                await session.flush()
                record = None
            elif record.status == "COMPLETED":
                if record.request_hash == p_hash:
                    if isinstance(record.response_body, str):
                        try:
                            cached_body = json.loads(record.response_body) if record.response_body else {}
                        except Exception:
                            cached_body = {"raw": record.response_body}
                    elif isinstance(record.response_body, dict):
                        cached_body = record.response_body
                    else:
                        cached_body = {}
                    return (record.status_code or 200, cached_body, True)
                else:
                    raise IdempotencyConflictException(
                        f"Idempotency key '{idempotency_key}' already used with different payload (HTTP 409)",
                        status_code=409,
                    )
            elif record.status in ("PENDING", "PROCESSING"):
                raise IdempotencyInFlightException(
                    f"Concurrent request in-flight for key '{idempotency_key}' (HTTP 409)",
                    status_code=409,
                )
            elif record.status == "FAILED":
                # Previous attempt failed; permit retry by resetting to PENDING
                record.status = "PENDING"
                record.request_hash = p_hash
                record.request_path = request_path
                record.expires_at = now + timedelta(seconds=ttl_seconds)
                record.response_body = None
                record.status_code = None
                await session.flush()
                target_record = record

        if record is None:
            # First-time registration: status = PENDING
            expires_at = now + timedelta(seconds=ttl_seconds)
            target_record = IdempotencyKeyRecord(
                key=idempotency_key,
                request_hash=p_hash,
                request_path=request_path,
                status="PENDING",
                created_at=now,
                expires_at=expires_at,
            )
            session.add(target_record)
            await session.flush()

        try:
            status_code, body = await operation_coroutine()
            target_record.status = "COMPLETED"
            target_record.status_code = status_code
            target_record.response_body = (
                json.dumps(body, default=str) if isinstance(body, (dict, list)) else str(body)
            )
            await session.flush()
            return (status_code, body, False)
        except Exception as exc:
            target_record.status = "FAILED"
            target_record.response_body = json.dumps({"error": str(exc)}, default=str)
            await session.flush()
            raise
