"""Add cryptographic hash-chained audit_trail table with append-only immutability.

Revision ID: 038_banking_audit_chain
Revises: 037_banking_saga_concurrency
Create Date: 2026-11-16

Features added:
- audit_trail table for institutional-grade cryptographic hash-chained audit logging.
- Formula: H_n = SHA-256(H_{n-1} || timestamp_iso || actor_id || action || entity_type || entity_id || payload_hash).
- Database-level immutability enforcement: PostgreSQL trigger preventing UPDATE and DELETE at SQL layer.
- Fully guarded with dialect/inspector checks for SQLite in-memory and PostgreSQL bankops_test.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "038_banking_audit_chain"
down_revision = "037_banking_saga_concurrency"
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

    # 1. Create audit_trail table
    if not _has_table("audit_trail"):
        id_col = sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
            autoincrement=True,
        ) if is_postgres else sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        )

        event_id_col = (
            sa.Column(
                "event_id",
                postgresql.UUID(as_uuid=False),
                nullable=False,
                unique=True,
                server_default=sa.text("gen_random_uuid()"),
            )
            if is_postgres
            else sa.Column("event_id", sa.String(36), nullable=False, unique=True)
        )

        payload_col = (
            postgresql.JSONB(astext_type=sa.Text())
            if is_postgres
            else sa.JSON()
        )

        op.create_table(
            "audit_trail",
            id_col,
            event_id_col,
            sa.Column("actor_id", sa.String(128), nullable=False),
            sa.Column("action", sa.String(128), nullable=False),
            sa.Column("entity_type", sa.String(128), nullable=False),
            sa.Column("entity_id", sa.String(128), nullable=False),
            sa.Column("state_payload", payload_col, nullable=False, server_default="{}" if not is_postgres else sa.text("'{}'::jsonb")),
            sa.Column("payload_hash", sa.String(64), nullable=False),
            sa.Column("prev_hash", sa.String(64), nullable=False),
            sa.Column("current_hash", sa.String(64), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    # 2. Indexes
    if _has_table("audit_trail"):
        if not _has_index("audit_trail", "ix_audit_trail_actor_id"):
            op.create_index("ix_audit_trail_actor_id", "audit_trail", ["actor_id"])
        if not _has_index("audit_trail", "ix_audit_trail_action"):
            op.create_index("ix_audit_trail_action", "audit_trail", ["action"])
        if not _has_index("audit_trail", "ix_audit_trail_entity_type"):
            op.create_index("ix_audit_trail_entity_type", "audit_trail", ["entity_type"])
        if not _has_index("audit_trail", "ix_audit_trail_entity_id"):
            op.create_index("ix_audit_trail_entity_id", "audit_trail", ["entity_id"])
        if not _has_index("audit_trail", "ix_audit_trail_current_hash"):
            op.create_index("ix_audit_trail_current_hash", "audit_trail", ["current_hash"])
        if not _has_index("audit_trail", "ix_audit_trail_prev_hash"):
            op.create_index("ix_audit_trail_prev_hash", "audit_trail", ["prev_hash"])
        if not _has_index("audit_trail", "ix_audit_trail_entity"):
            op.create_index("ix_audit_trail_entity", "audit_trail", ["entity_type", "entity_id"])

    # 3. Database-level immutability enforcement trigger (PostgreSQL)
    if is_postgres:
        op.execute("""
            CREATE OR REPLACE FUNCTION prevent_audit_trail_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'audit_trail is append-only: % operations are prohibited', TG_OP;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS trg_audit_trail_prevent_update ON audit_trail;
            CREATE TRIGGER trg_audit_trail_prevent_update
            BEFORE UPDATE ON audit_trail
            FOR EACH ROW
            EXECUTE FUNCTION prevent_audit_trail_mutation();

            DROP TRIGGER IF EXISTS trg_audit_trail_prevent_delete ON audit_trail;
            CREATE TRIGGER trg_audit_trail_prevent_delete
            BEFORE DELETE ON audit_trail
            FOR EACH ROW
            EXECUTE FUNCTION prevent_audit_trail_mutation();
        """)

        # Grant access to bankops user if role exists
        op.execute("""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bankops') THEN
                    GRANT ALL PRIVILEGES ON TABLE audit_trail TO bankops;
                    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO bankops;
                END IF;
            END $$;
        """)

        # If audit_events_chain view/table is not present, create a view pointing to audit_trail
        if not _has_table("audit_events_chain"):
            op.execute("""
                CREATE OR REPLACE VIEW audit_events_chain AS
                SELECT
                    id,
                    event_id,
                    actor_id,
                    action,
                    entity_type,
                    entity_id,
                    state_payload::text AS state_payload,
                    payload_hash,
                    prev_hash,
                    current_hash,
                    timestamp
                FROM audit_trail;
            """)

        if is_postgres:
            op.execute("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bankops') THEN
                        IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'audit_trail') THEN
                            ALTER TABLE audit_trail OWNER TO bankops;
                        END IF;
                        IF EXISTS (SELECT 1 FROM pg_views WHERE viewname = 'audit_events_chain') THEN
                            ALTER VIEW audit_events_chain OWNER TO bankops;
                        END IF;
                    END IF;
                END $$;
            """)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP VIEW IF EXISTS audit_events_chain;")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_trail_prevent_update ON audit_trail;")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_trail_prevent_delete ON audit_trail;")
        op.execute("DROP FUNCTION IF EXISTS prevent_audit_trail_mutation;")

    if _has_table("audit_trail"):
        op.drop_table("audit_trail")
