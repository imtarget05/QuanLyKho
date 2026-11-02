"""Sales, quotations, purchasing and payment records for store operations."""

from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, TimestampMixin, uuid_gen


class Customer(Base, TimestampMixin):
    __tablename__ = "commerce_customers"

    id: str = Column(UUID(as_uuid=True), primary_key=True, default=uuid_gen)
    code: str = Column(String(64), nullable=False)
    name: str = Column(String(256), nullable=False)
    phone: str | None = Column(String(32), nullable=True)
    email: str | None = Column(String(256), nullable=True)
    address: str | None = Column(String(512), nullable=True)
    active: bool = Column("is_active", default=True, nullable=False)
    branch_id: str | None = Column(
        UUID(as_uuid=True), ForeignKey("org_branches.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("branch_id", "code", name="uq_commerce_customer_branch_code"),
        Index("ix_commerce_customers_branch", "branch_id"),
        Index("ix_commerce_customers_name", "name"),
    )


class CommerceDocument(Base, TimestampMixin):
    __tablename__ = "commerce_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('sale', 'quote', 'purchase')",
            name="document_type_valid",
        ),
        CheckConstraint(
            "status IN ('draft', 'pending_inventory', 'confirmed', 'cancelled', 'converted')",
            name="status_valid",
        ),
        CheckConstraint(
            "subtotal >= 0 AND discount >= 0 AND vat >= 0 AND shipping >= 0 "
            "AND total >= 0 AND paid >= 0 AND paid <= total",
            name="amounts_non_negative",
        ),
        CheckConstraint(
            "(document_type = 'purchase' AND supplier_id IS NOT NULL AND customer_id IS NULL) "
            "OR (document_type IN ('sale', 'quote') AND customer_id IS NOT NULL AND supplier_id IS NULL)",
            name="party_matches_document_type",
        ),
        UniqueConstraint("branch_id", "code", name="uq_commerce_document_branch_code"),
        Index("ix_commerce_documents_type_date", "document_type", "document_date"),
        Index("ix_commerce_documents_customer", "customer_id"),
        Index("ix_commerce_documents_supplier", "supplier_id"),
    )

    id: str = Column(UUID(as_uuid=True), primary_key=True, default=uuid_gen)
    code: str = Column(String(64), nullable=False)
    document_type: str = Column(String(16), nullable=False)
    status: str = Column(String(24), nullable=False, default="confirmed")
    customer_id: str | None = Column(
        UUID(as_uuid=True), ForeignKey("commerce_customers.id", ondelete="RESTRICT"), nullable=True
    )
    supplier_id: str | None = Column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True
    )
    inventory_request_id: str | None = Column(
        UUID(as_uuid=True),
        ForeignKey("inv_requests.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    document_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    subtotal = Column(Numeric(16, 2), nullable=False, default=Decimal("0"))
    discount = Column(Numeric(16, 2), nullable=False, default=Decimal("0"))
    vat = Column(Numeric(16, 2), nullable=False, default=Decimal("0"))
    shipping = Column(Numeric(16, 2), nullable=False, default=Decimal("0"))
    total = Column(Numeric(16, 2), nullable=False, default=Decimal("0"))
    paid = Column(Numeric(16, 2), nullable=False, default=Decimal("0"))
    note = Column(String(2048), nullable=False, default="")
    branch_id: str | None = Column(
        UUID(as_uuid=True), ForeignKey("org_branches.id", ondelete="SET NULL"), nullable=True
    )
    created_by: str | None = Column(
        UUID(as_uuid=True), ForeignKey("iam_users.id", ondelete="SET NULL"), nullable=True
    )


class CommerceDocumentLine(Base):
    __tablename__ = "commerce_document_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0 AND unit_cost >= 0", name="prices_non_negative"),
        Index("ix_commerce_document_lines_item", "item_id"),
    )

    id: str = Column(UUID(as_uuid=True), primary_key=True, default=uuid_gen)
    document_id: str = Column(
        UUID(as_uuid=True), ForeignKey("commerce_documents.id", ondelete="CASCADE"), nullable=False
    )
    item_id: str = Column(
        UUID(as_uuid=True), ForeignKey("inv_items.id", ondelete="RESTRICT"), nullable=False
    )
    item_sku: str = Column(String(128), nullable=False)
    item_name: str = Column(String(256), nullable=False)
    unit: str = Column(String(32), nullable=False)
    quantity = Column(Numeric(20, 3), nullable=False)
    unit_price = Column(Numeric(16, 2), nullable=False)
    unit_cost = Column(Numeric(16, 2), nullable=False)
    line_total = Column(Numeric(16, 2), nullable=False)
    lot_no: str | None = Column(String(64), nullable=True)
    expiry_date = Column(Date, nullable=True)


class CommercePayment(Base, TimestampMixin):
    __tablename__ = "commerce_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("payment_type IN ('receipt', 'disbursement')", name="payment_type_valid"),
        Index("ix_commerce_payments_document", "document_id"),
    )

    id: str = Column(UUID(as_uuid=True), primary_key=True, default=uuid_gen)
    document_id: str = Column(
        UUID(as_uuid=True), ForeignKey("commerce_documents.id", ondelete="RESTRICT"), nullable=False
    )
    payment_type: str = Column(String(16), nullable=False)
    amount = Column(Numeric(16, 2), nullable=False)
    payment_date = Column(Date, nullable=False)
    method = Column(String(32), nullable=False, default="cash")
    reference = Column(String(128), nullable=False, default="")
    note = Column(String(1024), nullable=False, default="")
    created_by: str | None = Column(
        UUID(as_uuid=True), ForeignKey("iam_users.id", ondelete="SET NULL"), nullable=True
    )
