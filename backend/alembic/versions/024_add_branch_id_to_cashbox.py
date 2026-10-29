"""Add branch_id to cash_boxes for branch-scoped cash isolation.

Revision ID: 024_add_branch_id_to_cashbox
Revises: 022_movement_cost_and_sub_kind
"""
import sqlalchemy as sa

from alembic import op

revision = "024_add_branch_id_to_cashbox"
down_revision = "023_reversal_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = {c["name"] for c in insp.get_columns("cash_boxes")}
    if "branch_id" not in cols:
        op.add_column(
            "cash_boxes",
            sa.Column(
                "branch_id",
                sa.UUID(as_uuid=True),
                sa.ForeignKey("org_branches.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_cash_boxes_branch_id",
            "cash_boxes",
            ["branch_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = {c["name"] for c in insp.get_columns("cash_boxes")}
    if "branch_id" in cols:
        op.drop_index("ix_cash_boxes_branch_id", table_name="cash_boxes")
        op.drop_column("cash_boxes", "branch_id")
