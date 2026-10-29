"""Link reversed inventory requests to their original via reversed_from_id.

Revision ID: 023_reversal_link
Revises: 022_movement_cost_and_sub_kind
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "023_reversal_link"
down_revision = "022_movement_cost_and_sub_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = {c["name"] for c in insp.get_columns("inv_requests")}
    if "reversed_from_id" not in cols:
        op.add_column(
            "inv_requests",
            sa.Column(
                "reversed_from_id",
                UUID(as_uuid=True),
                sa.ForeignKey("inv_requests.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index("ix_inv_requests_reversed_from_id", "inv_requests", ["reversed_from_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = {c["name"] for c in insp.get_columns("inv_requests")}
    if "reversed_from_id" in cols:
        indexes = {i["name"] for i in insp.get_indexes("inv_requests")}
        if "ix_inv_requests_reversed_from_id" in indexes:
            op.drop_index("ix_inv_requests_reversed_from_id", table_name="inv_requests")
        op.drop_column("inv_requests", "reversed_from_id")
