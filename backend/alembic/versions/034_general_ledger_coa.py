"""Add the consolidated general ledger and seed the chart of accounts."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "034_general_ledger_coa"
down_revision = "033_inventory_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coa_accounts",
        sa.Column("code", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("account_type", sa.String(32), nullable=False),
        sa.Column("normal_balance", sa.String(8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "simulation_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "account_type IN ('asset', 'liability', 'equity', 'revenue', 'expense')",
            name="ck_coa_accounts_account_type_valid",
        ),
        sa.CheckConstraint(
            "normal_balance IN ('debit', 'credit')",
            name="ck_coa_accounts_normal_balance_valid",
        ),
    )
    op.create_table(
        "gl_journals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_journal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column(
            "simulation_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "source_type",
            "source_journal_id",
            name="uq_gl_journals_source",
        ),
        sa.CheckConstraint(
            "source_type IN ('inventory', 'cash_simulation')",
            name="ck_gl_journals_source_type_valid",
        ),
    )
    op.create_table(
        "gl_journal_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "journal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "gl_journals.id",
                ondelete="CASCADE",
                name="fk_gl_journal_entries_journal_id_gl_journals",
            ),
            nullable=False,
        ),
        sa.Column(
            "account_code",
            sa.String(128),
            sa.ForeignKey(
                "coa_accounts.code",
                name="fk_gl_journal_entries_account_code_coa_accounts",
            ),
            nullable=False,
        ),
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
            name="ck_gl_journal_entries_debit_credit_non_negative",
        ),
        sa.CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="ck_gl_journal_entries_exactly_one_positive",
        ),
    )

    op.execute(
        """
        INSERT INTO coa_accounts
            (code, name, account_type, normal_balance, simulation_only)
        VALUES
            ('111', 'Cash on hand', 'asset', 'debit', false),
            ('112', 'Bank deposits', 'asset', 'debit', false),
            ('152', 'Raw materials', 'asset', 'debit', false),
            ('156', 'Merchandise inventory', 'asset', 'debit', false),
            ('331', 'Trade payables', 'liability', 'credit', false),
            ('511', 'Sales revenue', 'revenue', 'credit', false),
            ('632', 'Cost of goods sold', 'expense', 'debit', false),
            ('SIM_OFFSET:DEMO', 'Simulation opening and offset account',
             'equity', 'credit', true)
        """
    )
    op.execute(
        """
        INSERT INTO coa_accounts
            (code, name, account_type, normal_balance, simulation_only)
        SELECT DISTINCT
            entry.account_code,
            CASE
                WHEN entry.account_code LIKE 'SIM_CASH:%'
                    THEN 'Simulated cashbox ' || substr(entry.account_code, 10)
                ELSE 'Legacy simulated cash account ' || entry.account_code
            END,
            CASE
                WHEN entry.account_code LIKE 'SIM_CASH:%' THEN 'asset'
                ELSE 'equity'
            END,
            CASE
                WHEN entry.account_code LIKE 'SIM_CASH:%' THEN 'debit'
                ELSE 'credit'
            END,
            true
        FROM cash_entries AS entry
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO gl_journals
            (id, source_type, source_journal_id, posted_at, correlation_id,
             simulation_only)
        SELECT gen_random_uuid(), 'inventory', journal.id, journal.posted_at,
               journal.correlation_id, false
        FROM inv_journals AS journal
        ON CONFLICT (source_type, source_journal_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO gl_journals
            (id, source_type, source_journal_id, posted_at, correlation_id,
             simulation_only)
        SELECT gen_random_uuid(), 'cash_simulation', journal.id, journal.posted_at,
               journal.correlation_id, true
        FROM cash_journals AS journal
        ON CONFLICT (source_type, source_journal_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO gl_journal_entries (id, journal_id, account_code, debit, credit)
        SELECT gen_random_uuid(), gl.id, entry.account_code, entry.debit, entry.credit
        FROM inv_journal_entries AS entry
        JOIN gl_journals AS gl
          ON gl.source_type = 'inventory'
         AND gl.source_journal_id = entry.journal_id
        """
    )
    op.execute(
        """
        INSERT INTO gl_journal_entries (id, journal_id, account_code, debit, credit)
        SELECT
            gen_random_uuid(),
            gl.id,
            '632',
            CASE WHEN totals.debit_total < totals.credit_total
                 THEN totals.credit_total - totals.debit_total ELSE 0 END,
            CASE WHEN totals.debit_total > totals.credit_total
                 THEN totals.debit_total - totals.credit_total ELSE 0 END
        FROM gl_journals AS gl
        JOIN inv_journals AS source ON source.id = gl.source_journal_id
        JOIN inv_requests AS request ON request.id = source.request_id
        JOIN (
            SELECT journal_id, sum(debit) AS debit_total, sum(credit) AS credit_total
            FROM inv_journal_entries
            GROUP BY journal_id
        ) AS totals ON totals.journal_id = source.id
        WHERE gl.source_type = 'inventory'
          AND request.kind = 'adjustment'
          AND totals.debit_total <> totals.credit_total
        """
    )
    op.execute(
        """
        INSERT INTO gl_journal_entries (id, journal_id, account_code, debit, credit)
        SELECT gen_random_uuid(), gl.id, entry.account_code, entry.debit, entry.credit
        FROM cash_entries AS entry
        JOIN gl_journals AS gl
          ON gl.source_type = 'cash_simulation'
         AND gl.source_journal_id = entry.journal_id
        """
    )


def downgrade() -> None:
    op.drop_table("gl_journal_entries")
    op.drop_table("gl_journals")
    op.drop_table("coa_accounts")
