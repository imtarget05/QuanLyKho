"""General ledger chart of accounts and consolidated postings."""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ChartOfAccounts(Base):
    __tablename__ = "coa_accounts"

    code: str = Column(String(128), primary_key=True)
    name: str = Column(String(256), nullable=False)
    account_type: str = Column(String(32), nullable=False)
    normal_balance: str = Column(String(8), nullable=False)
    is_active: bool = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    simulation_only: bool = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "account_type IN ('asset', 'liability', 'equity', 'revenue', 'expense')",
            name="account_type_valid",
        ),
        CheckConstraint(
            "normal_balance IN ('debit', 'credit')",
            name="normal_balance_valid",
        ),
    )


BASE_CHART_OF_ACCOUNTS = (
    ("111", "Cash on hand", "asset", "debit", False),
    ("112", "Bank deposits", "asset", "debit", False),
    ("152", "Raw materials", "asset", "debit", False),
    ("156", "Merchandise inventory", "asset", "debit", False),
    ("331", "Trade payables", "liability", "credit", False),
    ("511", "Sales revenue", "revenue", "credit", False),
    ("632", "Cost of goods sold", "expense", "debit", False),
    (
        "SIM_OFFSET:DEMO",
        "Simulation opening and offset account",
        "equity",
        "credit",
        True,
    ),
)


class GeneralLedgerJournal(Base):
    __tablename__ = "gl_journals"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_journal_id",
            name="uq_gl_journals_source",
        ),
        CheckConstraint(
            "source_type IN ('inventory', 'cash_simulation')",
            name="source_type_valid",
        ),
    )

    id: str = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source_type: str = Column(String(32), nullable=False)
    source_journal_id: str = Column(UUID(as_uuid=True), nullable=False)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    correlation_id: str = Column(String(64), nullable=False)
    simulation_only: bool = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class GeneralLedgerEntry(Base):
    __tablename__ = "gl_journal_entries"
    __table_args__ = (
        CheckConstraint(
            "debit >= 0 AND credit >= 0",
            name="debit_credit_non_negative",
        ),
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="exactly_one_positive",
        ),
    )

    id: str = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    journal_id: str = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "gl_journals.id",
            ondelete="CASCADE",
            name="fk_gl_journal_entries_journal_id_gl_journals",
        ),
        nullable=False,
    )
    account_code: str = Column(
        String(128),
        ForeignKey(
            "coa_accounts.code",
            name="fk_gl_journal_entries_account_code_coa_accounts",
        ),
        nullable=False,
    )
    debit = Column(Numeric(20, 2), nullable=False, default=0, server_default="0")
    credit = Column(Numeric(20, 2), nullable=False, default=0, server_default="0")
