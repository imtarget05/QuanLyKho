"""Inventory models."""
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base, TimestampMixin, utc_now


class Location(Base, TimestampMixin):
    __tablename__ = "inv_locations"

    id: str = Column(UUID(as_uuid=True), primary_key=True)
    code: str = Column(String(64), unique=True, nullable=False, index=True)
    name: str = Column(String(256), nullable=False)
    active: bool = Column(Boolean, default=True, nullable=False)
    branch_id: str | None = Column(UUID(as_uuid=True), ForeignKey("org_branches.id", ondelete="SET NULL"), nullable=True)

    def __repr__(self):
        return f"<Location {self.code}>"


class Item(Base, TimestampMixin):
    __tablename__ = "inv_items"

    id: str = Column(UUID(as_uuid=True), primary_key=True)
    sku: str = Column(String(128), unique=True, nullable=False, index=True)
    name: str = Column(String(256), nullable=False)
    unit: str = Column(String(32), nullable=False)
    # Operational catalog data for food-and-beverage inventory.  These are
    # intentionally item-level attributes: the stock minimum itself remains
    # location-specific in ``inv_stock_levels``.
    category: str | None = Column(String(128), nullable=True)
    packaging: str | None = Column(String(256), nullable=True)
    cost_price: Decimal | None = Column(Numeric(14, 2), nullable=True)
    # NUMERIC(15, 2) — the precision the deployed database and the
    # `init_db` ALTER statement use; keeping the model identical to both
    # means `alembic check` reports no drift for a migrated *and* for a
    # bootstrapped database.
    selling_price: Decimal | None = Column(Numeric(15, 2), nullable=True)
    min_stock: Decimal | None = Column(Numeric(12, 2), nullable=True)
    tracked_serial: bool = Column(Boolean, default=False, nullable=False)
    active: bool = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<Item {self.sku}>"


class Asset(Base, TimestampMixin):
    __tablename__ = "inv_assets"

    id: str = Column(UUID(as_uuid=True), primary_key=True)
    item_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_items.id", ondelete="RESTRICT"), nullable=False)
    serial: str = Column(String(128), unique=True, nullable=False, index=True)
    location_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_locations.id", ondelete="RESTRICT"), nullable=False)
    assignee_demo: str = Column(String(128), nullable=True)
    status: str = Column(String(32), nullable=False, default="available")

    def __repr__(self):
        return f"<Asset {self.serial}>"


class InventoryRequest(Base, TimestampMixin):
    __tablename__ = "inv_requests"

    id: str = Column(UUID(as_uuid=True), primary_key=True)
    kind: str = Column(String(32), nullable=False)  # receipt, issue, transfer, adjustment
    status: str = Column(String(32), nullable=False, default="draft")
    maker_id: str = Column(UUID(as_uuid=True), ForeignKey("iam_users.id"), nullable=False)
    approver_id: str = Column(UUID(as_uuid=True), ForeignKey("iam_users.id"), nullable=True)
    source_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_locations.id"), nullable=True)
    dest_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_locations.id"), nullable=True)
    reason: str = Column(String(512), nullable=True)
    return_reason: str = Column(String(1024), nullable=True)
    supplier: str | None = Column(String(256), nullable=True)
    invoice_no: str | None = Column(String(128), nullable=True)
    sub_kind: str | None = Column(String(32), nullable=True)  # sale, spoilage, internal, transfer
    received_at = Column(DateTime(timezone=True), nullable=True)
    version: int = Column(Integer, default=1, nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_by: str = Column(UUID(as_uuid=True), ForeignKey("iam_users.id"), nullable=False)
    reversed_from_id: str | None = Column(
        UUID(as_uuid=True),
        ForeignKey("inv_requests.id", ondelete="SET NULL"),
        nullable=True,
    )

    __mapper_args__ = {
        "version_id_col": version
    }

    reversal_of = relationship("InventoryRequest", remote_side=[id], backref="reversals")

    def __repr__(self):
        return f"<InventoryRequest {self.kind} {self.status}>"


class InventoryRequestLine(Base):
    __tablename__ = "inv_request_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="qty_positive"),
        CheckConstraint(
            "direction IN ('increase', 'decrease')", name="request_line_direction_valid"
        ),
    )

    id: str = Column(UUID(as_uuid=True), primary_key=True)
    request_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_requests.id", ondelete="CASCADE"), nullable=False)
    item_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_items.id"), nullable=False)
    quantity = Column(Numeric(20, 3), nullable=False)
    # Direction is explicit because the amount itself is always positive.  This
    # keeps the database quantity invariant intact while allowing stocktake
    # shortage adjustments to reduce a balance.
    direction: str = Column(String(16), nullable=False, default="increase")
    serial: str = Column(String(128), nullable=True)
    unit: str | None = Column(String(32), nullable=True)
    conversion_rate = Column(Numeric(10, 4), nullable=True)
    unit_price = Column(Numeric(20, 2), nullable=True)
    lot_no: str | None = Column(String(64), nullable=True)
    expiry_date = Column(Date, nullable=True)

    def __repr__(self):
        return f"<InventoryRequestLine {self.request_id} qty={self.quantity}>"


class Movement(Base, TimestampMixin):
    __tablename__ = "inv_movements"
    __table_args__ = (
        UniqueConstraint("request_id", "line_id", "location_id", name="uq_movement_request_line_location"),
    )

    id: str = Column(UUID(as_uuid=True), primary_key=True)
    request_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_requests.id"), nullable=False)
    line_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_request_lines.id"), nullable=False)
    item_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_items.id"), nullable=False)
    location_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_locations.id"), nullable=False)
    quantity_signed = Column(Numeric(20, 3), nullable=False)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    sub_kind: str | None = Column(String(32), nullable=True)  # sale, spoilage, internal, transfer
    unit_cost = Column(Numeric(14, 2), nullable=True)
    cost_amount = Column(Numeric(20, 2), nullable=True)

    lot_movements = relationship("LotMovement", back_populates="movement", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Movement {self.quantity_signed} sub_kind={self.sub_kind}>"


class LotMovement(Base, TimestampMixin):
    __tablename__ = "inv_lot_movements"
    __table_args__ = (
        Index("ix_inv_lot_movements_movement_id", "movement_id"),
        Index("ix_inv_lot_movements_request_id", "request_id"),
    )

    id: str = Column(UUID(as_uuid=True), primary_key=True)
    movement_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_movements.id", ondelete="CASCADE"), nullable=False)
    request_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_requests.id", ondelete="CASCADE"), nullable=False)
    line_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_request_lines.id", ondelete="CASCADE"), nullable=False)
    item_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_items.id", ondelete="RESTRICT"), nullable=False)
    location_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_locations.id", ondelete="RESTRICT"), nullable=False)
    lot_no: str | None = Column(String(64), nullable=True, index=True)
    expiry_date = Column(Date, nullable=True, index=True)
    quantity_signed = Column(Numeric(20, 3), nullable=False)
    unit_cost = Column(Numeric(14, 2), nullable=True)
    cost_amount = Column(Numeric(20, 2), nullable=True)
    sub_kind: str | None = Column(String(32), nullable=True)

    movement = relationship("Movement", back_populates="lot_movements")

    def __repr__(self):
        return f"<LotMovement lot={self.lot_no} qty={self.quantity_signed} cost={self.cost_amount}>"


class Balance(Base):
    __tablename__ = "inv_balances"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="qty_non_negative"),
    )

    location_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_locations.id"), primary_key=True)
    item_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_items.id"), primary_key=True)
    quantity = Column(Numeric(20, 3), nullable=False, default=0)
    reserved_quantity = Column(Numeric(20, 3), nullable=False, default=0)
    version: int = Column(Integer, default=1, nullable=False)

    @property
    def available_quantity(self):
        return max(Decimal(0), (self.quantity or Decimal(0)) - (self.reserved_quantity or Decimal(0)))

    def __repr__(self):
        return f"<Balance loc={self.location_id} item={self.item_id} qty={self.quantity} reserved={self.reserved_quantity}>"


class LotBalance(Base, TimestampMixin):
    __tablename__ = "inv_lot_balances"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="lot_qty_non_negative"),
        Index("ix_inv_lot_balances_loc", "location_id"),
        Index("ix_inv_lot_balances_item", "item_id"),
        Index("ix_inv_lot_balances_exp", "expiry_date"),
    )

    id: str = Column(UUID(as_uuid=True), primary_key=True)
    location_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_locations.id", ondelete="RESTRICT"), nullable=False)
    item_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_items.id", ondelete="RESTRICT"), nullable=False)
    lot_no: str | None = Column(String(64), nullable=True)
    expiry_date = Column(Date, nullable=True)
    quantity = Column(Numeric(20, 3), nullable=False, default=0)
    unit_cost = Column(Numeric(14, 2), nullable=True)

    def __repr__(self):
        return f"<LotBalance loc={self.location_id} item={self.item_id} lot={self.lot_no} exp={self.expiry_date} qty={self.quantity}>"


# One lot-balance row per (location, item, lot, expiry). NULL lot/expiry are
# folded to a sentinel so the uniqueness also covers legacy rows without a
# lot number. Mirrors the expression index created by migration 021 so that
# autogenerate sees no drift between the ORM metadata and the database.
Index(
    "uq_lot_balance_record",
    LotBalance.location_id,
    LotBalance.item_id,
    func.coalesce(LotBalance.lot_no, literal_column("''::character varying")),
    func.coalesce(LotBalance.expiry_date, literal_column("'2099-12-31'::date")),
    unique=True,
)


class AssetLog(Base):
    __tablename__ = "inv_asset_logs"

    id: str = Column(UUID(as_uuid=True), primary_key=True)
    asset_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_assets.id", ondelete="CASCADE"), nullable=False)
    serial: str = Column(String(128), nullable=False, index=True)
    from_location_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_locations.id"), nullable=True)
    to_location_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_locations.id"), nullable=True)
    from_assignee: str = Column(String(128), nullable=True)
    to_assignee: str = Column(String(128), nullable=True)
    status_before: str = Column(String(32), nullable=True)
    status_after: str = Column(String(32), nullable=False)
    request_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_requests.id"), nullable=True)
    actor_id: str = Column(UUID(as_uuid=True), ForeignKey("iam_users.id"), nullable=True)
    notes: str = Column(String(1024), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    def __repr__(self):
        return f"<AssetLog {self.serial} {self.status_before}->{self.status_after}>"


class StockLevel(Base, TimestampMixin):
    __tablename__ = "inv_stock_levels"
    __table_args__ = (
        UniqueConstraint("location_id", "item_id", name="uq_inv_stock_levels_loc_item"),
    )

    id: str = Column(UUID(as_uuid=True), primary_key=True)
    location_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_locations.id", ondelete="CASCADE"), nullable=False)
    item_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_items.id", ondelete="CASCADE"), nullable=False)
    min_qty = Column(Numeric(20, 3), nullable=False, default=0)
    max_qty = Column(Numeric(20, 3), nullable=True)

    def __repr__(self):
        return f"<StockLevel loc={self.location_id} item={self.item_id} min={self.min_qty}>"


class Stocktake(Base, TimestampMixin):
    __tablename__ = "inv_stocktakes"

    id: str = Column(UUID(as_uuid=True), primary_key=True)
    location_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_locations.id", ondelete="RESTRICT"), nullable=False)
    status: str = Column(String(32), nullable=False, default="open")  # open, submitted, closed, cancelled
    version: int = Column(Integer, nullable=False, default=1, server_default="1")
    maker_id: str = Column(UUID(as_uuid=True), ForeignKey("iam_users.id"), nullable=False)
    approver_id: str = Column(UUID(as_uuid=True), ForeignKey("iam_users.id"), nullable=True)
    note: str = Column(String(512), nullable=True)
    business_date = Column(Date, nullable=True)
    # morning 07:30–15:00, afternoon 15:00–23:00, split 07:30–18:00
    shift_code: str | None = Column(String(16), nullable=True)
    adjustment_request_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_requests.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Stocktake {self.id} status={self.status}>"


# At most one open stocktake shift per (location, business date, shift).
# Mirrors the partial unique index created by migration 017.
Index(
    "uq_open_stocktake_shift",
    Stocktake.location_id,
    Stocktake.business_date,
    func.coalesce(Stocktake.shift_code, literal_column("'none'::character varying")),
    unique=True,
    postgresql_where=text("status::text = 'open'::text"),
)


class StocktakeLine(Base):
    __tablename__ = "inv_stocktake_lines"
    __table_args__ = (
        UniqueConstraint("stocktake_id", "item_id", name="uq_stocktake_lines_st_item"),
    )

    id: str = Column(UUID(as_uuid=True), primary_key=True)
    stocktake_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_stocktakes.id", ondelete="CASCADE"), nullable=False)
    item_id: str = Column(UUID(as_uuid=True), ForeignKey("inv_items.id"), nullable=False)
    book_qty = Column(Numeric(20, 3), nullable=False, default=0)
    opening_qty = Column(Numeric(20, 3), nullable=False, default=0)
    received_qty = Column(Numeric(20, 3), nullable=False, default=0)
    used_qty = Column(Numeric(20, 3), nullable=False, default=0)
    theoretical_qty = Column(Numeric(20, 3), nullable=False, default=0)
    counted_qty = Column(Numeric(20, 3), nullable=False, default=0)
    variance = Column(Numeric(20, 3), nullable=False, default=0)
    reason: str = Column(String(512), nullable=True)

    def __repr__(self):
        return f"<StocktakeLine item={self.item_id} book={self.book_qty} counted={self.counted_qty} diff={self.variance}>"
