"""Kiểm tra audit trail hash-chain bất biến: verify_chain phát hiện tam-per."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import update

from app.database import AsyncSessionLocal
from app.models.activity import AuditEvent
from app.services.audit_chain import append_audit_event, verify_chain


@pytest.mark.asyncio
async def test_audit_chain_valid_and_tamper_detection():
    subject = f"audit:{uuid4()}"

    async with AsyncSessionLocal() as session:
        e1 = await append_audit_event(
            session, subject=subject, action="CREATE", metadata_json={"k": "v1"}
        )
        e2 = await append_audit_event(
            session, subject=subject, action="UPDATE", metadata_json={"k": "v2"}
        )
        e3 = await append_audit_event(
            session, subject=subject, action="DELETE", metadata_json={"k": "v3"}
        )
        await session.commit()

        # Chuỗi ban đầu phải hợp lệ.
        assert await verify_chain(session, subject) is True
        assert e1.hash_seq == 1
        assert e2.hash_seq == 2
        assert e3.hash_seq == 3
        assert e1.previous_hash == "0" * 64
        assert e2.previous_hash == e1.chain_hash
        assert e3.previous_hash == e2.chain_hash

        # Tam-per: sửa chain_hash của sự kiện giữa.
        await session.execute(
            update(AuditEvent).where(AuditEvent.id == e2.id).values(chain_hash="tampered-hash")
        )
        await session.commit()
        assert await verify_chain(session, subject) is False
