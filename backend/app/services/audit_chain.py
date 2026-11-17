"""Audit trail hash-chain bất biến (interview-prep 02/01 §7, 02/05 §8).

Mỗi AuditEvent mới ghi chuỗi hash SHA-256:
  previous_hash = chain_hash của sự kiện trước cùng subject (hoặc GENESIS)
  chain_hash    = SHA256(previous_hash || action || subject || payload_hash
                         || occurred_at || hash_seq)
  hash_seq      = thứ tự sự kiện trong subject (tăng dần)

Guard append-only hiện có ở app/models/activity.py (chặn UPDATE/DELETE)
duy trì ở đây: chỉ INSERT mới, không sửa chuỗi cũ.

verify_chain(subject) tính lại toàn chuỗi từ sự kiện đầu, so sánh chain_hash
lưu trữ; trả False nếu phát hiện biến đổi bất kỳ nút nào.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import AuditEvent

GENESIS_HASH = "0" * 64


def _payload_hash(
    *,
    action: str,
    subject: str,
    before_hash: str | None,
    after_hash: str | None,
    metadata_json: dict[str, Any] | None,
) -> str:
    canonical = json.dumps(
        {
            "action": action,
            "subject": subject,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "metadata": metadata_json or {},
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _chain_hash(
    *,
    previous_hash: str,
    action: str,
    subject: str,
    payload_hash: str,
    occurred_at: datetime,
    hash_seq: int,
) -> str:
    canonical = "|".join(
        [
            previous_hash,
            action,
            subject,
            payload_hash,
            occurred_at.astimezone(UTC).isoformat(),
            str(hash_seq),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _last_chain_hash(
    session: AsyncSession, subject: str
) -> tuple[str | None, int]:
    """Trả (chain_hash, hash_seq) của sự kiện gần nhất theo subject."""
    result = await session.execute(
        select(AuditEvent.chain_hash, AuditEvent.hash_seq)
        .where(AuditEvent.subject == subject)
        .order_by(AuditEvent.hash_seq.desc().nullslast(), AuditEvent.occurred_at.desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None, 0
    return row[0], int(row[1] or 0)


async def append_audit_event(
    session: AsyncSession,
    *,
    subject: str,
    action: str,
    actor_id: str | None = None,
    request_id: str | None = None,
    before_hash: str | None = None,
    after_hash: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> AuditEvent:
    """Ghi một sự kiện audit append-only kèm hash-chain."""
    previous_hash, last_seq = await _last_chain_hash(session, subject)
    if previous_hash is None:
        previous_hash = GENESIS_HASH
    hash_seq = last_seq + 1

    occurred_at = datetime.now(UTC)
    payload_hash = _payload_hash(
        action=action,
        subject=subject,
        before_hash=before_hash,
        after_hash=after_hash,
        metadata_json=metadata_json,
    )
    chain_hash = _chain_hash(
        previous_hash=previous_hash,
        action=action,
        subject=subject,
        payload_hash=payload_hash,
        occurred_at=occurred_at,
        hash_seq=hash_seq,
    )

    event = AuditEvent(
        id=uuid.uuid4(),
        actor_id=actor_id,
        action=action,
        subject=subject,
        before_hash=before_hash,
        after_hash=after_hash,
        request_id=request_id,
        occurred_at=occurred_at,
        metadata_json=metadata_json,
        previous_hash=previous_hash,
        chain_hash=chain_hash,
        hash_seq=hash_seq,
    )
    session.add(event)
    await session.flush()
    return event


async def verify_chain(session: AsyncSession, subject: str) -> bool:
    """Xác minh toàn vẹn hash-chain của một subject.

    Trả True nếu mọi sự kiện đều khớp chain_hash tính lại và hash_seq liên
    tục. Trả False nếu phát hiện biến đổi, thiếu sự kiện, hoặc subject chưa
    từng được hash-chain (stored chain_hash None).
    """
    result = await session.execute(
        select(AuditEvent)
        .where(AuditEvent.subject == subject)
        .order_by(AuditEvent.hash_seq.asc().nullslast(), AuditEvent.occurred_at.asc())
    )
    events = result.scalars().all()
    if not events:
        return True

    previous_hash = GENESIS_HASH
    expected_seq = 1
    for event in events:
        if event.chain_hash is None or event.hash_seq is None:
            return False
        if int(event.hash_seq) != expected_seq:
            return False
        payload_hash = _payload_hash(
            action=event.action,
            subject=event.subject,
            before_hash=event.before_hash,
            after_hash=event.after_hash,
            metadata_json=event.metadata_json,
        )
        expected = _chain_hash(
            previous_hash=previous_hash,
            action=event.action,
            subject=event.subject,
            payload_hash=payload_hash,
            occurred_at=event.occurred_at,
            hash_seq=int(event.hash_seq),
        )
        if expected != event.chain_hash:
            return False
        previous_hash = event.chain_hash
        expected_seq += 1
    return True
