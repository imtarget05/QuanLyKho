"""Kiểm tra Saga rollback / bù trừ: bước 2 thất bại -> bù trừ bước 1."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.saga import CompensatingLog, SagaInstance, SagaStep
from app.services.saga import SagaError, SagaOrchestrator


@pytest.mark.asyncio
async def test_saga_step2_failure_compensates_step1():
    """Bước 2 ném lỗi -> bước 1 được bù trừ, status failed, log bù trừ ghi lại."""
    saga_id = uuid4()
    called = {"a": 0, "comp_a": 0}

    async def action_a(session, context):
        called["a"] += 1

    async def compensate_a(session, context):
        called["comp_a"] += 1

    async def action_b(session, context):
        raise RuntimeError("khoi luong bi het")

    async with AsyncSessionLocal() as session:
        orch = SagaOrchestrator(session)
        with pytest.raises(SagaError, match="khoi luong bi het"):
            await orch.execute(
                saga_id=str(saga_id),
                saga_type="rollback-test",
                steps=[
                    {"name": "a", "action": action_a, "compensate": compensate_a},
                    {"name": "b", "action": action_b},
                ],
                context={},
            )
        await session.commit()

        assert called["a"] == 1
        assert called["comp_a"] >= 1  # bù trừ bước 1 được gọi (ít nhất 1 lần)

        row = await session.execute(
            select(SagaInstance).where(SagaInstance.id == saga_id)
        )
        saga = row.scalars().first()
        assert saga is not None
        assert saga.status == "failed"

        steps = (
            await session.execute(select(SagaStep).where(SagaStep.saga_id == saga_id))
        ).scalars().all()
        statuses = {s.step_name: s.status for s in steps}
        assert statuses["a"] == "compensated"
        assert statuses["b"] == "failed"

        logs = (
            await session.execute(select(CompensatingLog).where(CompensatingLog.saga_id == saga_id))
        ).scalars().all()
        assert len(logs) >= 1
        assert logs[0].step_name == "a"
        assert logs[0].status == "done"
