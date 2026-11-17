"""Add processed_events table and enhance outbox/idempotency schema.

Revision ID: 036_banking_idempotency_outbox
Revises: 035_banking_patterns
Create Date: 2026-11-16

Features added:
- processed_events table for consumer deduplication (exactly-once processing).
- topic, payload, trace_id, and status columns on outbox_events.
- status and request_path columns on idempotency_keys.
- Indexes on outbox topic, trace_id, status, and idempotency status.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "036_banking_idempotency_outbox"
down_revision = "035_banking_patterns"
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
    # 1. Create processed_events table for consumer deduplication
    if not _has_table("processed_events"):
        op.create_table(
            "processed_events",
            sa.Column("event_id", sa.String(36), primary_key=True),
            sa.Column("consumer_group", sa.String(64), primary_key=True),
            sa.Column(
                "processed_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

    # 2. Add missing columns to outbox_events
    if _has_table("outbox_events"):
        if not _has_column("outbox_events", "topic"):
            op.add_column(
                "outbox_events",
                sa.Column("topic", sa.String(128), nullable=False, server_default=""),
            )
        if not _has_column("outbox_events", "payload"):
            op.add_column(
                "outbox_events",
                sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
            )
        if not _has_column("outbox_events", "trace_id"):
            op.add_column(
                "outbox_events",
                sa.Column("trace_id", sa.String(64), nullable=False, server_default=""),
            )
        if not _has_column("outbox_events", "status"):
            op.add_column(
                "outbox_events",
                sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
            )

        # Create indexes
        if not _has_index("outbox_events", "ix_outbox_events_topic"):
            op.create_index("ix_outbox_events_topic", "outbox_events", ["topic"])
        if not _has_index("outbox_events", "ix_outbox_events_aggregate_id"):
            op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
        if not _has_index("outbox_events", "ix_outbox_events_trace_id"):
            op.create_index("ix_outbox_events_trace_id", "outbox_events", ["trace_id"])
        if not _has_index("outbox_events", "ix_outbox_events_status"):
            op.create_index("ix_outbox_events_status", "outbox_events", ["status"])

    # 3. Add missing columns to idempotency_keys
    if _has_table("idempotency_keys"):
        if not _has_column("idempotency_keys", "status"):
            op.add_column(
                "idempotency_keys",
                sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
            )
        if not _has_column("idempotency_keys", "request_path"):
            op.add_column(
                "idempotency_keys",
                sa.Column("request_path", sa.String(255), nullable=True),
            )
        if not _has_index("idempotency_keys", "ix_idempotency_keys_status"):
            op.create_index("ix_idempotency_keys_status", "idempotency_keys", ["status"])


def downgrade() -> None:
    if _has_table("idempotency_keys"):
        if _has_index("idempotency_keys", "ix_idempotency_keys_status"):
            op.drop_index("ix_idempotency_keys_status", table_name="idempotency_keys")
        if _has_column("idempotency_keys", "request_path"):
            op.drop_column("idempotency_keys", "request_path")
        if _has_column("idempotency_keys", "status"):
            op.drop_column("idempotency_keys", "status")

    if _has_table("outbox_events"):
        if _has_index("outbox_events", "ix_outbox_events_status"):
            op.drop_index("ix_outbox_events_status", table_name="outbox_events")
        if _has_index("outbox_events", "ix_outbox_events_trace_id"):
            op.drop_index("ix_outbox_events_trace_id", table_name="outbox_events")
        if _has_index("outbox_events", "ix_outbox_events_aggregate_id"):
            op.drop_index("ix_outbox_events_aggregate_id", table_name="outbox_events")
        if _has_index("outbox_events", "ix_outbox_events_topic"):
            op.drop_index("ix_outbox_events_topic", table_name="outbox_events")
        if _has_column("outbox_events", "status"):
            op.drop_column("outbox_events", "status")
        if _has_column("outbox_events", "trace_id"):
            op.drop_column("outbox_events", "trace_id")
        if _has_column("outbox_events", "payload"):
            op.drop_column("outbox_events", "payload")
        if _has_column("outbox_events", "topic"):
            op.drop_column("outbox_events", "topic")

    if _has_table("processed_events"):
        op.drop_table("processed_events")
