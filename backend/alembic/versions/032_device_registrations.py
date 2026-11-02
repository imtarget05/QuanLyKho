"""Persist browser and mobile push notification registrations."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "032_device_registrations"
down_revision = "031_commerce_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "iam_device_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("iam_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_token", sa.String(512), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False, server_default="web"),
        sa.Column("device_name", sa.String(256)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
    op.create_index(
        "ix_iam_device_registrations_user_id",
        "iam_device_registrations",
        ["user_id"],
    )
    op.create_index(
        "ix_iam_device_registrations_device_token",
        "iam_device_registrations",
        ["device_token"],
        unique=True,
    )
    op.create_index(
        "ix_device_user_active",
        "iam_device_registrations",
        ["user_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_table("iam_device_registrations")
