"""Add gl_account_balances table.

Creates table gl_account_balances:
- account_code: String(128), PK, FK to coa_accounts.code ON DELETE CASCADE
- currency: String(3), NOT NULL, default 'VND'
- ledger_balance: BigInteger, NOT NULL, default 0
- available_balance: BigInteger, NOT NULL, default 0
- hold_balance: BigInteger, NOT NULL, default 0
- version: Integer, NOT NULL, default 1
- updated_at: DateTime(timezone=True), NOT NULL
- Check constraints: chk_gl_hold_non_negative, chk_gl_available_balance
"""

import sqlalchemy as sa

from alembic import op

revision = "035_add_gl_account_balances"
down_revision = "034_general_ledger_coa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gl_account_balances",
        sa.Column(
            "account_code",
            sa.String(128),
            sa.ForeignKey("coa_accounts.code", ondelete="CASCADE", name="fk_gl_account_balances_account_code"),
            primary_key=True,
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default="VND",
        ),
        sa.Column(
            "ledger_balance",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "available_balance",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "hold_balance",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "hold_balance >= 0",
            name="chk_gl_hold_non_negative",
        ),
        sa.CheckConstraint(
            "available_balance = ledger_balance - hold_balance",
            name="chk_gl_available_balance",
        ),
    )


def downgrade() -> None:
    op.drop_table("gl_account_balances")
