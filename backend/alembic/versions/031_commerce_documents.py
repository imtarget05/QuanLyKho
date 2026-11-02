"""Add customer, commercial document and payment ledgers.

Revision ID: 031_commerce_documents
Revises: 030_admin_inventory_create
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "031_commerce_documents"
down_revision = "030_admin_inventory_create"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commerce_customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("phone", sa.String(32)),
        sa.Column("email", sa.String(256)),
        sa.Column("address", sa.String(512)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("org_branches.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("branch_id", "code", name="uq_commerce_customer_branch_code"),
    )
    op.create_index("ix_commerce_customers_branch", "commerce_customers", ["branch_id"])
    op.create_index("ix_commerce_customers_name", "commerce_customers", ["name"])

    op.create_table(
        "commerce_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("document_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="confirmed"),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("commerce_customers.id", ondelete="RESTRICT")),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id", ondelete="RESTRICT")),
        sa.Column("inventory_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inv_requests.id", ondelete="RESTRICT"), unique=True),
        sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("subtotal", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("discount", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("vat", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("shipping", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("paid", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("note", sa.String(2048), nullable=False, server_default=""),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("org_branches.id", ondelete="SET NULL")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("iam_users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("branch_id", "code", name="uq_commerce_document_branch_code"),
        sa.CheckConstraint("document_type IN ('sale', 'quote', 'purchase')", name="ck_commerce_documents_document_type_valid"),
        sa.CheckConstraint("status IN ('draft', 'pending_inventory', 'confirmed', 'cancelled', 'converted')", name="ck_commerce_documents_status_valid"),
        sa.CheckConstraint("subtotal >= 0 AND discount >= 0 AND vat >= 0 AND shipping >= 0 AND total >= 0 AND paid >= 0 AND paid <= total", name="ck_commerce_documents_amounts_non_negative"),
        sa.CheckConstraint("(document_type = 'purchase' AND supplier_id IS NOT NULL AND customer_id IS NULL) OR (document_type IN ('sale', 'quote') AND customer_id IS NOT NULL AND supplier_id IS NULL)", name="ck_commerce_documents_party_matches_document_type"),
    )
    op.create_index("ix_commerce_documents_type_date", "commerce_documents", ["document_type", "document_date"])
    op.create_index("ix_commerce_documents_customer", "commerce_documents", ["customer_id"])
    op.create_index("ix_commerce_documents_supplier", "commerce_documents", ["supplier_id"])

    op.create_table(
        "commerce_document_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("commerce_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inv_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_sku", sa.String(128), nullable=False),
        sa.Column("item_name", sa.String(256), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(16, 2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(16, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(16, 2), nullable=False),
        sa.Column("lot_no", sa.String(64)),
        sa.Column("expiry_date", sa.Date()),
        sa.CheckConstraint("quantity > 0", name="ck_commerce_document_lines_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0 AND unit_cost >= 0", name="ck_commerce_document_lines_prices_non_negative"),
    )
    op.create_index("ix_commerce_document_lines_item", "commerce_document_lines", ["item_id"])

    op.create_table(
        "commerce_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("commerce_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("payment_type", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("method", sa.String(32), nullable=False, server_default="cash"),
        sa.Column("reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("note", sa.String(1024), nullable=False, server_default=""),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("iam_users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount > 0", name="ck_commerce_payments_amount_positive"),
        sa.CheckConstraint("payment_type IN ('receipt', 'disbursement')", name="ck_commerce_payments_payment_type_valid"),
    )
    op.create_index("ix_commerce_payments_document", "commerce_payments", ["document_id"])


def downgrade() -> None:
    op.drop_table("commerce_payments")
    op.drop_table("commerce_document_lines")
    op.drop_table("commerce_documents")
    op.drop_table("commerce_customers")
