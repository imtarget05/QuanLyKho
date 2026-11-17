"""Add saga_step_logs table and enhance saga_instances with concurrency support.

Revision ID: 037_banking_saga_concurrency
Revises: 036_banking_idempotency_outbox
Create Date: 2026-11-16

Features added:
- saga_step_logs table for distributed saga step execution and compensation audit logging.
- saga_name, context_data, and error_message columns on saga_instances.
- Extended check constraint or dropped restrictive check on saga_instances.status to allow institutional lifecycle states.
- Fully guarded with dialect/inspector checks for SQLite in-memory and PostgreSQL bankops_test.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "037_banking_saga_concurrency"
down_revision = "036_banking_idempotency_outbox"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def _has_index(table: str, index: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return index in {i["name"] for i in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 0. Ensure gl_account_balances table exists
    if not _has_table("gl_account_balances"):
        op.create_table(
            "gl_account_balances",
            sa.Column(
                "account_code",
                sa.String(128),
                sa.ForeignKey("coa_accounts.code", ondelete="CASCADE", name="fk_gl_account_balances_account_code"),
                primary_key=True,
            ),
            sa.Column("currency", sa.String(3), nullable=False, server_default="VND"),
            sa.Column("ledger_balance", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("available_balance", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("hold_balance", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("hold_balance >= 0", name="chk_gl_hold_non_negative"),
            sa.CheckConstraint("available_balance = ledger_balance - hold_balance", name="chk_gl_available_balance"),
        )
        if _has_table("coa_accounts") and is_postgres:
            op.execute("""
                INSERT INTO gl_account_balances (account_code, currency, ledger_balance, available_balance, hold_balance, version, updated_at)
                SELECT code, 'VND', 100000000, 100000000, 0, 1, NOW() FROM coa_accounts
                ON CONFLICT (account_code) DO NOTHING
            """)

    # 1. Enhance saga_instances table
    if _has_table("saga_instances"):
        if not _has_column("saga_instances", "saga_name"):
            op.add_column(
                "saga_instances",
                sa.Column("saga_name", sa.String(128), nullable=False, server_default=""),
            )
            # Sync saga_name from existing saga_type
            if _has_column("saga_instances", "saga_type"):
                op.execute("UPDATE saga_instances SET saga_name = saga_type WHERE saga_name = '' OR saga_name IS NULL")

        if not _has_column("saga_instances", "context_data"):
            col_type = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()
            op.add_column(
                "saga_instances",
                sa.Column("context_data", col_type, nullable=True),
            )
            # Sync context_data from context_json
            if _has_column("saga_instances", "context_json"):
                op.execute("UPDATE saga_instances SET context_data = context_json WHERE context_data IS NULL")

        if not _has_column("saga_instances", "error_message"):
            op.add_column(
                "saga_instances",
                sa.Column("error_message", sa.Text(), nullable=True),
            )

        if not _has_index("saga_instances", "ix_saga_instances_saga_name"):
            op.create_index("ix_saga_instances_saga_name", "saga_instances", ["saga_name"])

        # Relax or update check constraint on status for postgres
        if is_postgres:
            op.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'ck_saga_instances_ck_saga_instances_status_valid'
                    ) THEN
                        ALTER TABLE saga_instances DROP CONSTRAINT ck_saga_instances_ck_saga_instances_status_valid;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'ck_saga_instances_status_valid'
                    ) THEN
                        ALTER TABLE saga_instances DROP CONSTRAINT ck_saga_instances_status_valid;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'ck_gl_journals_ck_gl_journals_source_type_valid'
                    ) THEN
                        ALTER TABLE gl_journals DROP CONSTRAINT ck_gl_journals_ck_gl_journals_source_type_valid;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'ck_gl_journals_source_type_valid'
                    ) THEN
                        ALTER TABLE gl_journals DROP CONSTRAINT ck_gl_journals_source_type_valid;
                    END IF;
                    ALTER TABLE gl_journals ADD CONSTRAINT ck_gl_journals_source_type_valid CHECK (source_type IN ('inventory', 'cash_simulation', 'order', 'transfer', 'manual', 'adjustment'));
                END $$;
            """)
    else:
        # Create saga_instances if not exists
        uuid_col = (
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
            if is_postgres
            else sa.Column("id", sa.String(36), primary_key=True)
        )
        json_col = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()
        op.create_table(
            "saga_instances",
            uuid_col,
            sa.Column("saga_name", sa.String(128), nullable=False, index=True),
            sa.Column("saga_type", sa.String(64), nullable=True, index=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="PENDING", index=True),
            sa.Column("current_step", sa.String(128), nullable=True),
            sa.Column("context_data", json_col, nullable=False, server_default="{}" if not is_postgres else sa.text("'{}'::jsonb")),
            sa.Column("context_json", json_col, nullable=True, server_default="{}" if not is_postgres else sa.text("'{}'::jsonb")),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    # 2. Create saga_step_logs table
    if not _has_table("saga_step_logs"):
        step_id_col = (
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
            if is_postgres
            else sa.Column("id", sa.String(36), primary_key=True)
        )
        step_saga_id_col = (
            sa.Column(
                "saga_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("saga_instances.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            )
            if is_postgres
            else sa.Column(
                "saga_id",
                sa.String(36),
                sa.ForeignKey("saga_instances.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            )
        )
        json_step_col = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()

        op.create_table(
            "saga_step_logs",
            step_id_col,
            step_saga_id_col,
            sa.Column("step_name", sa.String(128), nullable=False),
            sa.Column("step_index", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
            sa.Column("input_data", json_step_col, nullable=True),
            sa.Column("output_data", json_step_col, nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("compensated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_saga_step_logs_saga_step_idx", "saga_step_logs", ["saga_id", "step_index"])

    if is_postgres:
        op.execute("""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bankops') THEN
                    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'saga_step_logs') THEN
                        ALTER TABLE saga_step_logs OWNER TO bankops;
                    END IF;
                    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'saga_instances') THEN
                        ALTER TABLE saga_instances OWNER TO bankops;
                    END IF;
                    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'gl_account_balances') THEN
                        ALTER TABLE gl_account_balances OWNER TO bankops;
                    END IF;
                END IF;
            END $$;
        """)


def downgrade() -> None:
    if _has_table("saga_step_logs"):
        op.drop_table("saga_step_logs")

    if _has_table("saga_instances"):
        if _has_index("saga_instances", "ix_saga_instances_saga_name"):
            op.drop_index("ix_saga_instances_saga_name", table_name="saga_instances")
        if _has_column("saga_instances", "error_message"):
            op.drop_column("saga_instances", "error_message")
        if _has_column("saga_instances", "context_data"):
            op.drop_column("saga_instances", "context_data")
        if _has_column("saga_instances", "saga_name"):
            op.drop_column("saga_instances", "saga_name")
