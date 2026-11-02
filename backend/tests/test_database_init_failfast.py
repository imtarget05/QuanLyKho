"""R8 — `init_db()` phải fail-fast, không tự `create_all`/seed ngoài demo mode.

- Lỗi DB lúc init => **raise** (mọi môi trường, kể cả production) để
  orchestrator restart, thay vì chỉ log rồi serve traffic với DB chết.
- Ngoài demo mode => KHÔNG `create_all` (bỏ qua Alembic) và KHÔNG seed.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app import database as database_module
from app.config import settings
from app.db.base import Base


def _broken_engine():
    """Engine không bao giờ kết nối được (cổng không có gì)."""
    return create_async_engine(
        "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/none",
        poolclass=NullPool,
    )


@pytest.mark.asyncio
async def test_init_db_raises_on_database_error_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(database_module, "engine", _broken_engine())

    with pytest.raises(Exception) as error:  # noqa: B017 - bất kỳ lỗi DB đều phải raise
        await database_module.init_db()
    assert error.value is not None


@pytest.mark.asyncio
async def test_init_db_never_creates_schema_or_seeds_demo(monkeypatch):
    """Startup only verifies DB; demo fixture belongs in RAM, migrations are explicit."""
    monkeypatch.setattr(settings, "app_env", "demo")
    monkeypatch.setattr(settings, "demo_mode", True)
    created: list[bool] = []
    seeded: list[bool] = []

    def _record_create_all(*args, **kwargs):
        created.append(True)
        return None

    async def _record_seed(*args, **kwargs):
        seeded.append(True)

    monkeypatch.setattr(Base.metadata, "create_all", _record_create_all)
    monkeypatch.setattr("app.seed.seed_demo", _record_seed)

    await database_module.init_db()  # không raise, không create_all, không seed
    assert created == []
    assert seeded == []


@pytest.mark.asyncio
async def test_init_db_does_not_seed_when_demo_mode_is_off(monkeypatch):
    seeded: list[bool] = []

    async def _record_seed(*args, **kwargs):
        seeded.append(True)

    monkeypatch.setattr(settings, "app_env", "demo")
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr("app.seed.seed_demo", _record_seed)

    await database_module.init_db()
    assert seeded == []
