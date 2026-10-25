"""Add optimistic version for offline stocktake replay.

Revision ID: 029_stocktake_version
Revises: 028_reconcile_scope
"""

import sqlalchemy as sa

from alembic import op

revision = "029_stocktake_version"
down_revision = "028_reconcile_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("inv_stocktakes")}
    if "version" not in columns:
        op.add_column("inv_stocktakes", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("inv_stocktakes")}
    if "version" in columns:
        op.drop_column("inv_stocktakes", "version")
