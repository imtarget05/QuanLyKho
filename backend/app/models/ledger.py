"""General ledger chart of accounts and consolidated postings."""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
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
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
    ("338", "Inventory surplus and other payables", "liability", "credit", False),
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
            "source_type IN ('inventory', 'cash_simulation', 'order', 'transfer', 'manual', 'adjustment')",
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
        DateTime(timezone=True), nullable=False, server_default=func.now()
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


class GLAccountBalance(Base):
    __tablename__ = "gl_account_balances"

    account_code: str = Column(
        String(128),
        ForeignKey(
            "coa_accounts.code",
            ondelete="CASCADE",
            name="fk_gl_account_balances_account_code",
        ),
        primary_key=True,
    )
    currency: str = Column(String(3), nullable=False, default="VND", server_default="VND")
    ledger_balance = Column(BigInteger, nullable=False, default=0, server_default="0")
    available_balance = Column(BigInteger, nullable=False, default=0, server_default="0")
    hold_balance = Column(BigInteger, nullable=False, default=0, server_default="0")
    version: int = Column(Integer, nullable=False, default=1, server_default="1")
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "hold_balance >= 0",
            name="chk_gl_hold_non_negative",
        ),
        CheckConstraint(
            "available_balance = ledger_balance - hold_balance",
            name="chk_gl_available_balance",
        ),
    )

