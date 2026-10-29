"""Create the durable `otp_codes` table (OTP single-use security).

Revision ID: 031_otp_codes
Revises: 030_admin_inventory_create
Create Date: 2026-10-28

Context
-------
OTP for password reset / login 2FA today lives only in RAM
(`_password_reset_otps` in `app/api/routes/auth_utils.py`). After a process
restart every pending OTP is lost, so a user who received a code by email can
never complete the reset. This migration adds a durable `otp_codes` table:

* `id` — PK
* `username` — owner of the OTP (indexed)
* `code_hash` — bcrypt hash of the 6-digit code (never plaintext)
* `purpose` — `password_reset` | `login_2fa` | `sensitive_action`
* `channel` — `email` | `sms` (demo uses email stub)
* `expires_at` — TTL, default 900s (15 minutes)
* `consumed_at` — set when the code is verified; NULL while valid
* `attempts` — failed verify counter; lock after 3
* `locked_until` — temporary lock timestamp when attempts exhausted
* `created_at` / `updated_at`

Unique constraint on (`username`, `purpose`) while not consumed, so a user
cannot have two pending OTPs for the same purpose.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "031_otp_codes"
down_revision = "030_admin_inventory_create"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "otp_codes" in inspector.get_table_names():
        return
    op.create_table(
        "otp_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False, index=True),
        sa.Column("code_hash", sa.String(length=256), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="email"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "username",
            "purpose",
            name="uq_otp_codes_username_purpose",
        ),
    )
    op.create_index("ix_otp_codes_expires_at", "otp_codes", ["expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "otp_codes" not in inspector.get_table_names():
        return
    indexes = {i["name"] for i in inspector.get_indexes("otp_codes")}
    if "ix_otp_codes_expires_at" in indexes:
        op.drop_index("ix_otp_codes_expires_at", table_name="otp_codes")
    op.drop_table("otp_codes")
