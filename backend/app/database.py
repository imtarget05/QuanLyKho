"""Database module - handles SQLAlchemy engine, session, and base."""
import logging
import os
import sys
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

logger = logging.getLogger(__name__)

def _normalize_async_database_url(url: str) -> str:
    """Normalize database URL for asyncpg engine."""
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    # asyncpg expects ssl=require, not sslmode=require
    if "sslmode=" in url:
        url = url.replace("sslmode=", "ssl=")
    return url


DATABASE_URL = _normalize_async_database_url(settings.database_url)

_engine_kwargs = {
    "echo": False,
    "pool_pre_ping": True,
}

_is_testing = (
    "pytest" in sys.modules
    or "PYTEST_CURRENT_TEST" in os.environ
    or os.environ.get("TESTING", "").lower() in ("1", "true", "yes")
    or getattr(settings, "environment", "") == "test"
)

if "sqlite" in DATABASE_URL:
    from sqlalchemy.pool import StaticPool
    _engine_kwargs["poolclass"] = StaticPool
elif _is_testing:
    from sqlalchemy.pool import NullPool
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_recycle": 300,
    })

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def init_db() -> None:
    """Initialize database connection and verify connectivity.

    Fail-fast (R8): bất kỳ lỗi DB nào cũng **raise** ở mọi môi trường —
    orchestrator sẽ restart app thay vì phục vụ traffic với DB chết.

    Schema và dữ liệu demo không được khởi tạo ở startup. Alembic là nguồn sự
    thật; demo UI giữ dữ liệu riêng trong RAM.
    """
    try:
        import app.models.activity  # noqa: F401
        import app.models.approval  # noqa: F401
        import app.models.cash_sim  # noqa: F401
        import app.models.iam  # noqa: F401
        import app.models.integration  # noqa: F401
        import app.models.inventory  # noqa: F401
        import app.models.reconciliation  # noqa: F401

        # Never seed or mutate schema during app startup, including demo mode.
        # Migrations are an explicit deployment step; the standalone UI demo
        # uses an in-memory store and does not need a database connection.
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


async def get_db() -> AsyncIterator[AsyncSession]:
    """Get database session as an async iterator."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
