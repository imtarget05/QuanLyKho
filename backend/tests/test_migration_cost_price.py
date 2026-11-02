"""Regression coverage for the fresh-database Alembic chain."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg2
import pytest
from sqlalchemy.engine import make_url

from app.config import settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# The migration chain must be exercised against a database that is guaranteed
# to be empty. Instead of pointing at a hard-coded host/port, the test uses the
# same PostgreSQL server the rest of the suite talks to and creates its own
# throw-away database on that server. The server therefore follows whichever
# ``DATABASE_URL`` the environment provides (CI, local dev, docker compose).
ADMIN_DATABASE = "postgres"


def _configured_database_url() -> str:
    """Return the PostgreSQL server the application is configured to use."""
    return os.environ.get("DATABASE_URL") or settings.database_url


def _psycog2_dsn(url: str, database: str) -> str:
    """Build a plain ``postgresql://`` DSN for direct psycopg2 usage."""
    parsed = make_url(url)
    return parsed.set(drivername="postgresql", database=database).render_as_string(
        hide_password=False
    )


def _create_isolated_database(server_url: str) -> str:
    """Create a throw-away database on the configured PostgreSQL server."""
    database_name = f"bankops_migration_{uuid.uuid4().hex[:12]}"
    admin_dsn = _psycog2_dsn(server_url, ADMIN_DATABASE)
    # ``with psycopg2.connect(...)`` opens a transaction, and CREATE/DROP
    # DATABASE cannot run inside one, so the connection is driven explicitly
    # with autocommit enabled.
    connection = psycopg2.connect(admin_dsn)
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            # Migrations seed non-ASCII text; do not inherit SQL_ASCII template1.
            cursor.execute(
                f'CREATE DATABASE "{database_name}" WITH ENCODING \'UTF8\' TEMPLATE template0'
            )
    except psycopg2.errors.InsufficientPrivilege:
        pytest.skip(
            "The configured PostgreSQL role may not create databases, so the "
            "fresh-migration chain cannot be exercised against an empty "
            "database. Grant CREATEDB to the role or point DATABASE_URL at a "
            "server whose role may create databases.",
            pytrace=False,
        )
    finally:
        connection.close()
    return database_name


def _drop_isolated_database(server_url: str, database_name: str) -> None:
    admin_dsn = _psycog2_dsn(server_url, ADMIN_DATABASE)
    connection = psycopg2.connect(admin_dsn)
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            cursor.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
    finally:
        connection.close()


def test_fresh_migration_chain_supports_lot_backfill_cost_price() -> None:
    """A clean database must reach head without querying a missing cost_price column."""
    server_url = _configured_database_url()
    database_name = _create_isolated_database(server_url)
    migration_database_url = (
        make_url(server_url)
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_ROOT,
            env={**os.environ, "DATABASE_URL": migration_database_url},
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr

        seed_result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.database import init_db; import asyncio; asyncio.run(init_db())",
            ],
            cwd=BACKEND_ROOT,
            env={**os.environ, "DATABASE_URL": migration_database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert seed_result.returncode == 0, seed_result.stdout + seed_result.stderr
    finally:
        _drop_isolated_database(server_url, database_name)
