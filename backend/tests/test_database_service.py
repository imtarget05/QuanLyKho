"""Unit tests for app.database — URL normalization and testing detection."""

from __future__ import annotations

from app.database import _normalize_async_database_url


class TestNormalizeAsyncDatabaseUrl:
    def test_postgresql_to_asyncpg(self):
        assert _normalize_async_database_url(
            "postgresql://user:pass@localhost:5432/db"
        ) == "postgresql+asyncpg://user:pass@localhost:5432/db"

    def test_postgresql_psycopg2_to_asyncpg(self):
        assert _normalize_async_database_url(
            "postgresql+psycopg2://user:pass@localhost:5432/db"
        ) == "postgresql+asyncpg://user:pass@localhost:5432/db"

    def test_sslmode_replaced_with_ssl(self):
        result = _normalize_async_database_url(
            "postgresql+asyncpg://user:pass@localhost:5432/db?sslmode=require"
        )
        assert "sslmode=" not in result
        assert "ssl=" in result

    def test_already_asyncpg_unchanged_except_ssl(self):
        result = _normalize_async_database_url(
            "postgresql+asyncpg://user:pass@localhost:5432/db"
        )
        assert result == "postgresql+asyncpg://user:pass@localhost:5432/db"

    def test_sqlite_unchanged(self):
        result = _normalize_async_database_url("sqlite:///./test.db")
        assert result == "sqlite:///./test.db"