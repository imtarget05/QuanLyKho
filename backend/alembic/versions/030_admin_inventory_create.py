"""Allow an inventory admin to create requests, matching the tea-shop PRD.

Revision ID: 030_admin_inventory_create
Revises: 029_stocktake_version
"""

from alembic import op

revision = "030_admin_inventory_create"
down_revision = "029_stocktake_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO iam_role_capabilities (role_code, capability_code) "
        "VALUES ('admin', 'inventory:create_request') "
        "ON CONFLICT (role_code, capability_code) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM iam_role_capabilities "
        "WHERE role_code = 'admin' "
        "AND capability_code = 'inventory:create_request'"
    )
