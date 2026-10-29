"""R10/R12 — chính xác số thập phân trong ETL + commit một lần khi staging.

- R10: `etl_engine` không được dùng `float` cho tồn kho (0.3 - 0.1 = 0.2 mới
  đúng, không phải 0.19999999999999998).
- R12: `integrations._stage_run` commit **một lần** ở cuối vòng lặp, để crash
  giữa chừng không để lại run "staged" thiếu dữ liệu.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.etl import EtlConnection, EtlMappingVersion, EtlPipeline
from app.models.iam import User
from app.models.integration import IntegrationConnection
from app.models.inventory import Balance, Item, Location
from app.services import etl_engine


@pytest.mark.asyncio
async def test_balance_adjustment_preview_uses_exact_decimal_arithmetic():
    async with AsyncSessionLocal() as session:
        item = Item(
            id=uuid.uuid4(),
            sku=f"DEC_{uuid.uuid4().hex[:8].upper()}",
            name="Sản phẩm kiểm thử số thập phân",
            unit="kg",
            active=True,
        )
        location = Location(id=uuid.uuid4(), code=f"LOCDEC{uuid.uuid4().hex[:6].upper()}", name="Kho DEC", active=True)
        session.add_all([item, location])
        await session.flush()
        session.add(
            Balance(
                location_id=location.id,
                item_id=item.id,
                quantity=Decimal("0.1"),
                reserved_quantity=Decimal("0"),
                version=1,
            )
        )
        conn = EtlConnection(id=uuid.uuid4(), name="conn-dec", type="json")
        session.add(conn)
        await session.flush()
        pipeline = EtlPipeline(
            id=uuid.uuid4(),
            name="pipe-dec",
            target="balance_adjustment_admin",
            connection_id=conn.id,
            location_id=location.id,
        )
        session.add(pipeline)
        await session.flush()
        mapping = EtlMappingVersion(
            id=uuid.uuid4(),
            pipeline_id=pipeline.id,
            version=1,
            status="published",
            mapping_json=[
                {"source_field": "sku", "target_field": "sku", "required": True},
                {"source_field": "target_quantity", "target_field": "target_quantity"},
                {"source_field": "reason", "target_field": "reason"},
            ],
            duplicate_policy="reject",
        )
        session.add(mapping)
        await session.flush()

        runner = (
            await session.execute(select(User).where(User.username == "demo_admin"))
        ).scalars().first()
        assert runner is not None

        _run, rows = await etl_engine.generate_staging_run(
            db=session,
            pipeline=pipeline,
            mapping_version=mapping,
            raw_rows=[{"sku": item.sku, "target_quantity": "0.3", "reason": "Kiểm kê"}],
            runner=runner,
        )

        preview = rows[0].action_preview
        assert preview["current_quantity"] == 0.1
        assert preview["target_quantity"] == 0.3
        # 0.3 - 0.1 phải ra đúng 0.2 (float cho ra 0.19999999999999998)
        assert preview["delta_quantity"] == 0.2
        assert Decimal(str(preview["delta_quantity"])) == Decimal("0.2")
        await session.rollback()


@pytest.mark.asyncio
async def test_stage_run_commits_once_after_all_rows(monkeypatch):
    """`_stage_run` chỉ commit một lần ở cuối (không commit trong vòng lặp)."""
    from app.features.integrations import routes as integrations_routes

    commits: list[int] = []

    class _FakeSession:
        def __init__(self, inner):
            self._inner = inner
            self.added = 0

        def add(self, obj):
            self.added += 1
            self._inner.add(obj)

        async def flush(self):
            await self._inner.flush()

        async def commit(self):
            commits.append(1)
            await self._inner.commit()

        async def refresh(self, obj):
            await self._inner.refresh(obj)

        async def execute(self, stmt):
            return await self._inner.execute(stmt)

    async def _run_stage():
        async with AsyncSessionLocal() as setup:
            conn = IntegrationConnection(id=uuid.uuid4(), name="conn-stage", type="json")
            setup.add(conn)
            await setup.commit()
            connection_id = conn.id
        async with AsyncSessionLocal() as session:
            fake = _FakeSession(session)
            result = await integrations_routes._stage_run(
                fake,
                connection_id=connection_id,
                source="json",
                rows=[
                    {"sku": "SKU-1", "name": "Sản phẩm 1", "unit": "cái"},
                    {"sku": "SKU-2", "name": "Sản phẩm 2", "unit": "cái"},
                ],
            )
            await session.rollback()
            return result

    result = await _run_stage()
    assert result["status"] == "staged"
    # Một lần commit cho toàn bộ run, không phải một lần cho mỗi dòng.
    assert len(commits) == 1, commits
