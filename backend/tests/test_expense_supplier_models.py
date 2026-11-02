"""TDD: Expense & Supplier models (Phase M — S1).

Tests define the expected DB schema for Phase M data engineering:
- Supplier master data (code, name, contact, branch scoping)
- Expense transactions (amount, category, date, supplier link, status)
- Alembic migration 025 creates both tables idempotently.

The migration is exercised against a **throw-away database** on the same
PostgreSQL server the rest of the suite talks to.  Running ``alembic upgrade
head`` against the development database would migrate production-like data,
so the database is created and dropped by this module.  Set
``TEST_DATABASE_URL`` to point the tests at a specific database instead.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

import psycopg2
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_DATABASE = "postgres"

# A dedicated database is created per test session; the development database
# (settings.database_url) must never be migrated by this module.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _server_url() -> str:
    """PostgreSQL server the application is configured to use."""
    return os.environ.get("DATABASE_URL") or TEST_DATABASE_URL or _fallback_server_url()


def _fallback_server_url() -> str:
    from app.config import settings

    return settings.database_url


def _admin_dsn(server_url: str) -> str:
    parsed = make_url(server_url)
    return parsed.set(drivername="postgresql", database=ADMIN_DATABASE).render_as_string(
        hide_password=False
    )


def _create_isolated_database(server_url: str) -> str:
    """Create a throw-away database on the configured PostgreSQL server."""
    database_name = f"bankops_expense_{uuid.uuid4().hex[:12]}"
    connection = psycopg2.connect(_admin_dsn(server_url))
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
            "migration cannot be exercised against a disposable database. "
            "Grant CREATEDB to the role or set TEST_DATABASE_URL.",
            pytrace=False,
        )
    finally:
        connection.close()
    return database_name


def _drop_isolated_database(server_url: str, database_name: str) -> None:
    connection = psycopg2.connect(_admin_dsn(server_url))
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


@pytest.fixture(scope="session")
def disposable_database_url() -> str:
    """URL of a disposable database that the migrations may safely touch."""
    if TEST_DATABASE_URL:
        yield TEST_DATABASE_URL
        return

    server_url = _server_url()
    database_name = _create_isolated_database(server_url)
    url = (
        make_url(server_url)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    try:
        yield url
    finally:
        _drop_isolated_database(server_url, database_name)


@pytest.fixture
def db_session(disposable_database_url: str) -> Session:
    """Sync SQLAlchemy session for model tests (rollback after each test)."""
    engine = create_engine(disposable_database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
    engine.dispose()


@pytest.fixture
def alembic_runner(disposable_database_url: str):
    """Helper to run alembic commands against the disposable test database."""

    class Runner:
        def upgrade_head(self):
            env = {**os.environ, "DATABASE_URL": disposable_database_url}
            # ``sys.executable -m alembic`` guarantees the interpreter (and
            # therefore alembic + its dependencies) of the virtualenv that runs
            # the test suite.  Calling the ``alembic`` script from PATH can
            # resolve to a different interpreter with a different environment.
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=str(BACKEND_DIR),
                capture_output=True,
                text=True,
                env=env,
            )
            if result.returncode != 0:
                pytest.fail(
                    f"alembic upgrade head failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                )

    return Runner()


from app.models.expense import Expense, Supplier  # noqa: E402


def test_supplier_table_exists_after_migration(db_session: Session, alembic_runner):
    """Migration 025 must create `suppliers` table."""
    alembic_runner.upgrade_head()
    bind = db_session.get_bind()
    inspector = inspect(bind)
    table_names = inspector.get_table_names()
    assert "suppliers" in table_names, "suppliers table missing after migration 025"


def test_expense_table_exists_after_migration(db_session: Session, alembic_runner):
    """Migration 025 must create `expenses` table."""
    alembic_runner.upgrade_head()
    bind = db_session.get_bind()
    inspector = inspect(bind)
    table_names = inspector.get_table_names()
    assert "expenses" in table_names, "expenses table missing after migration 025"


def test_supplier_columns(db_session: Session, alembic_runner):
    alembic_runner.upgrade_head()
    bind = db_session.get_bind()
    inspector = inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("suppliers")}
    expected = {
        "id", "code", "name", "contact_person", "phone", "email", "address",
        "is_active", "branch_id", "created_at", "updated_at",
    }
    missing = expected - columns
    assert not missing, f"suppliers missing columns: {missing}"


def test_expense_columns(db_session: Session, alembic_runner):
    alembic_runner.upgrade_head()
    bind = db_session.get_bind()
    inspector = inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("expenses")}
    expected = {
        "id", "expense_code", "supplier_id", "category", "amount", "currency",
        "expense_date", "description", "status", "branch_id", "created_at", "updated_at",
    }
    missing = expected - columns
    assert not missing, f"expenses missing columns: {missing}"


def test_supplier_crud(db_session: Session, alembic_runner):
    """Supplier model can be created, queried, updated."""
    alembic_runner.upgrade_head()

    supplier = Supplier(
        code=f"SUP-001-{uuid.uuid4().hex[:8]}",
        name="Cty TNHH Thuc Pham An Toan",
        contact_person="Nguyen Van A",
        phone="0901234567",
        email="contact@example.com",
        address="123 Duong ABC, Quan 1, TP HCM",
        is_active=True,
        branch_id=None,
    )
    db_session.add(supplier)
    db_session.commit()
    db_session.refresh(supplier)

    assert supplier.id is not None
    assert supplier.code.startswith("SUP-001-")
    assert supplier.created_at is not None
    assert supplier.updated_at is not None

    found = db_session.query(Supplier).filter_by(code=supplier.code).first()
    assert found is not None
    assert found.name == "Cty TNHH Thuc Pham An Toan"

    found.is_active = False
    db_session.commit()
    db_session.refresh(found)
    assert found.is_active is False


def test_expense_crud_with_supplier_link(db_session: Session, alembic_runner):
    """Expense model links to Supplier and tracks amount/category/date/status."""
    alembic_runner.upgrade_head()

    supplier = Supplier(
        code=f"SUP-002-{uuid.uuid4().hex[:8]}",
        name="Nha Cung Cap Dich Vu",
        is_active=True,
        branch_id=None,
    )
    db_session.add(supplier)
    db_session.commit()
    db_session.refresh(supplier)

    expense = Expense(
        expense_code=f"EXP-2026-001-{uuid.uuid4().hex[:8]}",
        supplier_id=supplier.id,
        category="utility",
        amount=15000000,
        currency="VND",
        expense_date=date(2026, 10, 15),
        description="Tien dien thang 10 chi nhanh 1",
        status="posted",
        branch_id=None,
    )
    db_session.add(expense)
    db_session.commit()
    db_session.refresh(expense)

    assert expense.id is not None
    assert expense.expense_code.startswith("EXP-2026-001-")
    assert expense.supplier_id == supplier.id
    assert expense.amount == 15000000
    assert expense.currency == "VND"
    assert expense.status == "posted"

    expenses = (
        db_session.query(Expense)
        .filter_by(supplier_id=supplier.id)
        .all()
    )
    assert len(expenses) == 1
    assert expenses[0].expense_code.startswith("EXP-2026-001-")


def test_expense_defaults(db_session: Session, alembic_runner):
    """Expense defaults: currency VND, status draft."""
    alembic_runner.upgrade_head()

    supplier = Supplier(
        code=f"SUP-003-{uuid.uuid4().hex[:8]}",
        name="Default Test Supplier",
        is_active=True,
    )
    db_session.add(supplier)
    db_session.commit()
    db_session.refresh(supplier)

    expense = Expense(
        expense_code=f"EXP-DEFAULT-001-{uuid.uuid4().hex[:8]}",
        category="misc",
        amount=500000,
        expense_date=date(2026, 10, 15),
        branch_id=None,
    )
    db_session.add(expense)
    db_session.commit()
    db_session.refresh(expense)

    assert expense.currency == "VND"
    assert expense.status == "draft"


def test_migration_is_idempotent(db_session: Session, alembic_runner):
    """Running migration 025 twice must not error (idempotent)."""
    alembic_runner.upgrade_head()
    alembic_runner.upgrade_head()
    bind = db_session.get_bind()
    inspector = inspect(bind)
    assert "suppliers" in inspector.get_table_names()
    assert "expenses" in inspector.get_table_names()
