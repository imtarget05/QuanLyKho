"""Kiểm tra Idempotency-Key cho Saga: cùng saga_id không xử lý 2 lần."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.saga import SagaInstance, SagaStep
from app.services.saga import SagaOrchestrator


@pytest.mark.asyncio
async def test_saga_same_idempotency_key_executes_once():
    """Chạy saga cùng saga_id 2 lần -> action chỉ được gọi 1 lần, status completed."""
    saga_id = uuid4()
    calls = {"n": 0}

    async def action_a(session, context):
        calls["n"] += 1
        return {"step": "a"}

    async def action_b(session, context):
        calls["n"] += 1
        return {"step": "b"}

    async with AsyncSessionLocal() as session:
        orch = SagaOrchestrator(session)
        r1 = await orch.execute(
            saga_id=str(saga_id),
            saga_type="idem-test",
            steps=[
                {"name": "a", "action": action_a},
                {"name": "b", "action": action_b},
            ],
            context={},
        )
        await session.commit()
        assert r1["status"] == "completed"
        assert calls["n"] == 2

        # Lần gọi thứ 2 cùng saga_id: idempotent, không gọi action lại.
        r2 = await orch.execute(
            saga_id=str(saga_id),
            saga_type="idem-test",
            steps=[
                {"name": "a", "action": action_a},
                {"name": "b", "action": action_b},
            ],
            context={},
        )
        await session.commit()
        assert r2["status"] == "completed"
        assert calls["n"] == 2  # không tăng

        row = await session.execute(
            select(SagaInstance).where(SagaInstance.id == saga_id)
        )
        assert row.scalars().first() is not None

        step_rows = (
            await session.execute(select(SagaStep).where(SagaStep.saga_id == saga_id))
        ).scalars().all()
        assert len(step_rows) == 2
        assert all(s.status == "done" for s in step_rows)
