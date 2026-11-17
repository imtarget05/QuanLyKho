"""Add saga orchestration tables and audit hash-chain columns.

Creates:
- saga_instances: orchestrated long-running transaction state.
- saga_steps: per-step status + compensating action payload.
- compensating_logs: immutable log of every compensation executed.
- Hash-chain columns on audit_events (previous_hash, chain_hash, hash_seq)
  for immutable audit trail (idempotent: skips if column already exists).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "035_banking_patterns"
down_revision = "035_add_gl_account_balances"
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

    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)
    uuid_server_default = sa.text("gen_random_uuid()") if is_postgres else None
    json_type = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()
    json_default = sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'")

    op.create_table(
        "saga_instances",
        sa.Column(
            "id",
            uuid_type,
            primary_key=True,
            server_default=uuid_server_default,
        ),
        sa.Column("saga_type", sa.String(64), nullable=False, index=True),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'pending'"),
            index=True,
        ),
        sa.Column("current_step", sa.String(128), nullable=True),
        sa.Column("context_json", json_type, nullable=False, server_default=json_default),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'compensating', 'completed', 'failed')",
            name="ck_saga_instances_status_valid",
        ),
    )
    op.create_index(
        "ix_saga_instances_status_created",
        "saga_instances",
        ["status", "created_at"],
    )

    op.create_table(
        "saga_steps",
        sa.Column(
            "id",
            uuid_type,
            primary_key=True,
            server_default=uuid_server_default,
        ),
        sa.Column(
            "saga_id",
            uuid_type,
            sa.ForeignKey(
                "saga_instances.id",
                ondelete="CASCADE",
                name="fk_saga_steps_saga_id_saga_instances",
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("step_name", sa.String(128), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'pending'"),
            index=True,
        ),
        sa.Column("action_json", json_type, nullable=False, server_default=json_default),
        sa.Column("compensate_json", json_type, nullable=False, server_default=json_default),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'done', 'failed', 'compensated')",
            name="ck_saga_steps_status_valid",
        ),
        sa.UniqueConstraint(
            "saga_id", "step_name", name="uq_saga_steps_saga_id_step_name"
        ),
    )

    op.create_table(
        "compensating_logs",
        sa.Column(
            "id",
            uuid_type,
            primary_key=True,
            server_default=uuid_server_default,
        ),
        sa.Column(
            "saga_id",
            uuid_type,
            sa.ForeignKey(
                "saga_instances.id",
                ondelete="CASCADE",
                name="fk_compensating_logs_saga_id_saga_instances",
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("step_name", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'pending'"),
            index=True,
        ),
        sa.Column("detail_json", json_type, nullable=False, server_default=json_default),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'done', 'failed')",
            name="ck_compensating_logs_status_valid",
        ),
    )

    # --- Hash-chain columns on audit_events (idempotent) ------------------
    if _has_table("audit_events"):
        if not _has_column("audit_events", "previous_hash"):
            op.add_column(
                "audit_events",
                sa.Column("previous_hash", sa.String(128), nullable=True),
            )
        if not _has_column("audit_events", "chain_hash"):
            op.add_column(
                "audit_events",
                sa.Column("chain_hash", sa.String(128), nullable=True),
            )
        if not _has_column("audit_events", "hash_seq"):
            op.add_column(
                "audit_events",
                sa.Column("hash_seq", sa.BigInteger(), nullable=True),
            )
        if not _has_index("audit_events", "ix_audit_events_subject_hash_seq"):
            op.create_index(
                "ix_audit_events_subject_hash_seq",
                "audit_events",
                ["subject", "hash_seq"],
            )

    if is_postgres:
        op.execute("""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bankops') THEN
                    ALTER TABLE saga_instances OWNER TO bankops;
                    ALTER TABLE saga_steps OWNER TO bankops;
                    ALTER TABLE compensating_logs OWNER TO bankops;
                END IF;
            END $$;
        """)


def downgrade() -> None:
    if _has_table("audit_events"):
        if _has_index("audit_events", "ix_audit_events_subject_hash_seq"):
            op.drop_index("ix_audit_events_subject_hash_seq", table_name="audit_events")
        if _has_column("audit_events", "hash_seq"):
            op.drop_column("audit_events", "hash_seq")
        if _has_column("audit_events", "chain_hash"):
            op.drop_column("audit_events", "chain_hash")
        if _has_column("audit_events", "previous_hash"):
            op.drop_column("audit_events", "previous_hash")
    if _has_table("compensating_logs"):
        op.drop_table("compensating_logs")
    if _has_table("saga_steps"):
        op.drop_table("saga_steps")
    if _has_table("saga_instances"):
        op.drop_table("saga_instances")
