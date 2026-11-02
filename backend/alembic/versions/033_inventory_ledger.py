"""Inventory ledger sub-journals for stock movement postings (P0-3)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "033_inventory_ledger"
down_revision = "032_device_registrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.create_table(
        "inv_journals",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inv_requests.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "correlation_id", sa.String(64), nullable=False
        ),
        sa.Column(
            "reversal_of",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inv_journals.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
    )
    op.create_table(
        "inv_journal_entries",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "journal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inv_journals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_code", sa.String(128), nullable=False),
        sa.Column(
            "debit",
            sa.Numeric(20, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "credit",
            sa.Numeric(20, 2),
            nullable=False,
            server_default="0",
        ),
        sa.CheckConstraint(
            "debit >= 0 AND credit >= 0",
            name="inv_journal_entries_debit_credit_non_negative",
        ),
        sa.CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="inv_journal_entries_exactly_one_positive",
        ),
    )
    op.create_index(
        "ix_inv_journal_entries_journal_id",
        "inv_journal_entries",
        ["journal_id"],
    )


def downgrade() -> None:
    op.drop_table("inv_journal_entries")
    op.drop_table("inv_journals")
