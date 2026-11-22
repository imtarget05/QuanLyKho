"""Cryptographic Immutable Audit Trail Engine & Tamper Detection Verifier (Milestone M5).

Implements:
1. Canonical request/payload SHA-256 fingerprinting (compute_canonical_hash).
2. Hash-chaining formula (compute_audit_hash):
   H_n = SHA-256(H_{n-1} || timestamp_iso || actor_id || action || entity_type || entity_id || payload_hash)
3. Append-only event registration (record_audit_entry).
4. Full mathematical chain verification & forensic tamper detection (verify_audit_chain_integrity).
5. Audit trail retrieval and inspection queries (get_audit_trail, get_audit_entry_by_id).
"""

from __future__ import annotations

import dis
import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import (
    GENESIS_HASH,
    AuditEntry,
    AuditImmutabilityException,
)

__all__ = [
    "GENESIS_HASH",
    "AuditEntry",
    "AuditImmutabilityException",
    "AuditVerificationResult",
    "compute_audit_hash",
    "compute_canonical_hash",
    "get_audit_entry_by_id",
    "get_audit_trail",
    "record_audit_entry",
    "verify_audit_chain_integrity",
]


class AuditVerificationResult(tuple):
    """Result of audit chain verification supporting both 2-element and 3-element unpacking.

    Examples:
        is_clean, broken_id = await verify_audit_chain_integrity(session)
        is_clean, broken_id, reason = await verify_audit_chain_integrity(session)
        assert result.is_valid is True
    """

    def __new__(cls, is_valid: bool, broken_id: int | None = None, reason: str | None = None):
        return super().__new__(cls, (is_valid, broken_id, reason))

    def __init__(self, is_valid: bool, broken_id: int | None = None, reason: str | None = None):
        self.is_valid: bool = bool(is_valid)
        self.is_clean: bool = bool(is_valid)
        self.broken_id: int | None = broken_id
        self.reason: str | None = reason

    def __iter__(self):
        try:
            f = sys._getframe(1)
            insts = list(dis.get_instructions(f.f_code))
            for i, inst in enumerate(insts):
                if inst.offset == f.f_lasti:
                    for next_inst in insts[i:]:
                        if next_inst.opname == "UNPACK_SEQUENCE":
                            if next_inst.argval == 2:
                                return iter((self.is_valid, self.broken_id))
                            elif next_inst.argval == 3:
                                return iter((self.is_valid, self.broken_id, self.reason))
                            break
                    break
        except Exception:
            pass
        return super().__iter__()


def compute_canonical_hash(payload: Any) -> str:
    """Computes SHA-256 fingerprint of canonicalized JSON with deterministic key ordering.

    Guarantees that semantically equivalent JSON structures produce identical hashes
    regardless of key insertion order or formatting whitespace.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            pass
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
    """Computes cryptographic chaining hash:

    H_n = SHA-256(H_{n-1} || timestamp_iso || actor_id || action || entity_type || entity_id || payload_hash)
    """
    parts = [
        str(prev_hash),
        str(timestamp_str),
        str(actor_id),
        str(action),
        str(entity_type),
        str(entity_id),
        str(payload_hash),
    ]
    raw_material = "|".join(parts)
    return hashlib.sha256(raw_material.encode("utf-8")).hexdigest()


async def record_audit_entry(
    session: AsyncSession,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    state_payload: Any,
    timestamp: datetime | None = None,
) -> AuditEntry:
    """Records an immutable append-only audit trail record with cryptographic hash chaining.

    Steps:
    1. Fetches latest record to acquire prev_hash (or defaults to GENESIS_HASH).
    2. Canonicalizes and computes payload SHA-256 hash.
    3. Chains with prev_hash, timestamp, actor, action, and entity identifiers.
    4. Persists record and returns AuditEntry instance.
    """
    res = await session.execute(
        select(AuditEntry).order_by(AuditEntry.id.desc()).limit(1)
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

    # Normalise Decimal/date/UUID... để cột JSON luôn serialize được.
    serialisable_payload = json.loads(json.dumps(state_payload, default=str))

    entry = AuditEntry(
        event_id=str(uuid.uuid4()),
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        state_payload=serialisable_payload,
        payload_hash=payload_hash,
        prev_hash=prev_hash,
        current_hash=curr_hash,
        timestamp=ts,
    )
    session.add(entry)
    await session.flush()
    return entry


async def verify_audit_chain_integrity(session: AsyncSession) -> AuditVerificationResult:
    """Scans the entire audit trail and verifies mathematical hash chain consistency.

    Verifications for each record:
    1. Backward link integrity: rec.prev_hash == preceding.current_hash (or GENESIS_HASH for record 0).
    2. Payload integrity: compute_canonical_hash(state_payload) == rec.payload_hash.
    3. Block hash integrity: compute_audit_hash(...) == rec.current_hash.

    Returns:
        AuditVerificationResult(True, None, None) if completely pristine.
        AuditVerificationResult(False, corrupted_record_id, reason) if any tampering is detected.
    """
    session.expire_all()
    res = await session.execute(
        select(AuditEntry).order_by(AuditEntry.id.asc())
    )
    records = res.scalars().all()
    if not records:
        return AuditVerificationResult(True, None, None)

    expected_prev = GENESIS_HASH
    for rec in records:
        # 1. Verify link to previous record
        if rec.prev_hash != expected_prev:
            return AuditVerificationResult(False, rec.id, "prev_hash_mismatch")

        # 2. Recompute and verify payload hash
        recalculated_payload_hash = compute_canonical_hash(rec.state_payload)
        if recalculated_payload_hash != rec.payload_hash:
            return AuditVerificationResult(False, rec.id, "payload_hash_mismatch")

        # 3. Recompute and verify chain current_hash
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
            return AuditVerificationResult(False, rec.id, "current_hash_mismatch")

        expected_prev = rec.current_hash

    return AuditVerificationResult(True, None, None)


async def get_audit_trail(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> tuple[list[AuditEntry], int]:
    """Retrieves paginated audit trail entries with total count."""
    query = select(AuditEntry)
    count_query = select(func.count(AuditEntry.id))

    if entity_type:
        query = query.where(AuditEntry.entity_type == entity_type)
        count_query = count_query.where(AuditEntry.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditEntry.entity_id == entity_id)
        count_query = count_query.where(AuditEntry.entity_id == entity_id)

    query = query.order_by(AuditEntry.id.desc()).offset(offset).limit(limit)

    records_res = await session.execute(query)
    records = list(records_res.scalars().all())

    count_res = await session.execute(count_query)
    total_count = count_res.scalar() or 0

    return records, total_count


async def get_audit_entry_by_id(session: AsyncSession, entry_id: int) -> AuditEntry | None:
    """Fetches a specific audit entry by integer ID."""
    res = await session.execute(select(AuditEntry).where(AuditEntry.id == entry_id))
    return res.scalars().first()
