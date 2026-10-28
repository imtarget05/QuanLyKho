"""Multimodal Document Intake Service for invoices and stock receipts.

Guarantees:
- Documents (PDF, images, or synthetic text) are parsed into structured schemas.
- Strict mathematical verification:
    1. Line items: quantity * unit_price == line_total
    2. Subtotal: sum(line_totals) == subtotal
    3. Total: subtotal + tax_amount == total_amount
- Catalog item matching against database inventory catalog.
- Business rule adherence:
    - Never auto-posts or approves transactions directly into the ledger.
    - Creates `InventoryRequest` in 'draft' status, preserving Maker-Checker.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryRequest, InventoryRequestLine, Item, Location
from app.schemas.invoice_intake import (
    InvoiceExtraction,
    InvoiceLineItem,
    ValidationReport,
)

logger = logging.getLogger("quanlykho.multimodal")


def parse_invoice_text(text: str) -> InvoiceExtraction:
    """Extract structured invoice fields from text or JSON representation."""
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            data = json.loads(stripped)
            return InvoiceExtraction.model_validate(data)
        except Exception:
            pass

    # Regex extraction for synthetic formatted invoice text
    supplier_match = re.search(
        r"(?:Nhà cung cấp|Supplier|Đơn vị bán|Công ty):\s*(.+)", text, re.I
    )
    supplier_name = (
        supplier_match.group(1).strip()
        if supplier_match
        else "Nhà Cung Cấp Tổng Hợp"
    )

    tax_code_match = re.search(r"(?:Mã số thuế|MST|Tax ID):\s*([0-9\-]+)", text, re.I)
    tax_code = tax_code_match.group(1).strip() if tax_code_match else None

    invoice_no_match = re.search(
        r"(?:Số hóa đơn|Invoice No|Số HĐ|HD):\s*([A-Za-z0-9\-]+)", text, re.I
    )
    invoice_no = (
        invoice_no_match.group(1).strip()
        if invoice_no_match
        else f"INV-{uuid.uuid4().hex[:8].upper()}"
    )

    date_match = re.search(
        r"(?:Ngày|Date|Invoice Date):\s*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})",
        text,
        re.I,
    )
    if date_match:
        raw_date = date_match.group(1).strip()
        if "/" in raw_date:
            d, m, y = raw_date.split("/")
            invoice_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        else:
            invoice_date = raw_date
    else:
        invoice_date = datetime.now().strftime("%Y-%m-%d")

    line_items: list[InvoiceLineItem] = []
    # Lines pattern: item_name | qty | price | total
    # Example: 1. Trà Đen (SKU: TEA-BLK-01) | SL: 10 kg | Đơn giá: 120000 | Thành tiền: 1200000 | Lô: LOT-1 | HSD: 2027-10-24
    for line_str in text.splitlines():
        if "|" in line_str and any(
            marker in line_str.lower()
            for marker in ("sl:", "đơn giá:", "thành tiền:", "qty:", "price:")
        ):
            parts = [p.strip() for p in line_str.split("|")]
            raw_name = parts[0]
            # Strip leading number: "1. Trà Đen..." -> "Trà Đen..."
            raw_name = re.sub(r"^\d+[\.\)]\s*", "", raw_name)

            sku = None
            sku_m = re.search(r"\(SKU:\s*([^)]+)\)", raw_name, re.I)
            if sku_m:
                sku = sku_m.group(1).strip()
                raw_name = re.sub(r"\(SKU:\s*[^)]+\)", "", raw_name).strip()

            qty = Decimal("1")
            unit = None
            price = Decimal("0")
            total = Decimal("0")
            lot_no = None
            exp_date = None

            for part in parts[1:]:
                p_lower = part.lower()
                if "sl:" in p_lower or "qty:" in p_lower:
                    val = re.sub(r"(?i)(?:sl|qty):\s*", "", part).strip()
                    m_val = re.search(r"([\d\.,]+)\s*([a-zA-Z\w]*)", val)
                    if m_val:
                        qty = Decimal(m_val.group(1).replace(",", ""))
                        unit = m_val.group(2).strip() or None
                elif "đơn giá:" in p_lower or "price:" in p_lower:
                    val = re.sub(r"(?i)(?:đơn giá|price):\s*", "", part).strip()
                    digits = re.sub(r"[^\d\.]", "", val)
                    if digits:
                        price = Decimal(digits)
                elif "thành tiền:" in p_lower or "total:" in p_lower:
                    val = re.sub(r"(?i)(?:thành tiền|total):\s*", "", part).strip()
                    digits = re.sub(r"[^\d\.]", "", val)
                    if digits:
                        total = Decimal(digits)
                elif "lô:" in p_lower or "lot:" in p_lower:
                    lot_no = re.sub(r"(?i)(?:lô|lot):\s*", "", part).strip()
                elif "hsd:" in p_lower or "exp:" in p_lower:
                    exp_date = re.sub(r"(?i)(?:hsd|exp):\s*", "", part).strip()

            if total == Decimal("0") and price > 0:
                total = qty * price

            line_items.append(
                InvoiceLineItem(
                    raw_name=raw_name,
                    sku=sku,
                    quantity=qty,
                    unit=unit,
                    unit_price=price,
                    line_total=total,
                    lot_no=lot_no,
                    expiry_date=exp_date,
                )
            )

    # Subtotal and totals
    subtotal_m = re.search(
        r"(?:Cộng tiền hàng|Subtotal|Tiền hàng):\s*([\d\.,]+)", text, re.I
    )
    if subtotal_m:
        subtotal = Decimal(re.sub(r"[^\d\.]", "", subtotal_m.group(1)))
    else:
        subtotal = sum((item.line_total for item in line_items), Decimal("0"))

    tax_m = re.search(
        r"(?:Thuế GTGT|VAT|Tax|Tiền thuế)(?:\s*\([^)]*\))?:\s*([\d\.,]+)",
        text,
        re.I,
    )
    if tax_m:
        tax_amount = Decimal(re.sub(r"[^\d\.]", "", tax_m.group(1)))
    else:
        tax_amount = Decimal("0")

    total_m = re.search(
        r"(?:Tổng thanh toán|Total|Tổng cộng):\s*([\d\.,]+)", text, re.I
    )
    if total_m:
        total_amount = Decimal(re.sub(r"[^\d\.]", "", total_m.group(1)))
    else:
        total_amount = subtotal + tax_amount

    return InvoiceExtraction(
        supplier_name=supplier_name,
        supplier_tax_code=tax_code,
        invoice_no=invoice_no,
        invoice_date=invoice_date,
        line_items=line_items,
        subtotal=subtotal,
        tax_amount=tax_amount,
        total_amount=total_amount,
        confidence=0.98 if line_items else 0.50,
    )


def parse_invoice_bytes(content: bytes, filename: str) -> InvoiceExtraction:
    """Parse document bytes (PDF, text, or image-embedded metadata)."""
    # Try decoding as text / markdown first
    try:
        text = content.decode("utf-8")
        return parse_invoice_text(text)
    except UnicodeDecodeError:
        pass

    # Extract strings from PDF or binary
    # Simple robust text stream extractor without binary dependencies
    strings = re.findall(rb"[A-Za-z0-9\s\.\,\:\-\(\)\/\@\_\u0080-\uffff]{4,}", content)
    extracted_text = " ".join(s.decode("latin-1", errors="ignore") for s in strings)
    if extracted_text:
        return parse_invoice_text(extracted_text)

    raise ValueError(f"Could not extract readable invoice data from {filename}")


def validate_invoice_math(extraction: InvoiceExtraction) -> ValidationReport:
    """Reconcile all mathematical equations in the invoice."""
    errors: list[str] = []
    warnings: list[str] = []

    line_math_valid = True
    for i, line in enumerate(extraction.line_items, 1):
        expected_line = line.quantity * line.unit_price
        diff = abs(expected_line - line.line_total)
        # Allow minor rounding tolerance up to 0.05
        if diff > Decimal("0.05"):
            line_math_valid = False
            errors.append(
                f"Line item {i} ('{line.raw_name}'): quantity {line.quantity} * unit_price {line.unit_price} "
                f"= {expected_line} does not match stated line total {line.line_total}"
            )

    sum_lines = sum((item.line_total for item in extraction.line_items), Decimal("0"))
    subtotal_diff = abs(sum_lines - extraction.subtotal)
    subtotal_valid = subtotal_diff <= Decimal("0.05")
    if not subtotal_valid:
        errors.append(
            f"Sum of line totals ({sum_lines}) does not match invoice subtotal ({extraction.subtotal})"
        )

    expected_total = extraction.subtotal + extraction.tax_amount
    total_diff = abs(expected_total - extraction.total_amount)
    total_valid = total_diff <= Decimal("0.05")
    if not total_valid:
        errors.append(
            f"Subtotal ({extraction.subtotal}) + tax ({extraction.tax_amount}) = {expected_total} "
            f"does not match stated total payment ({extraction.total_amount})"
        )

    if not extraction.line_items:
        errors.append("No line items found in extracted invoice")

    is_valid = len(errors) == 0
    return ValidationReport(
        is_valid=is_valid,
        line_math_valid=line_math_valid,
        subtotal_valid=subtotal_valid,
        total_valid=total_valid,
        errors=errors,
        warnings=warnings,
    )


async def match_catalog_items(
    db: AsyncSession, extraction: InvoiceExtraction
) -> ValidationReport:
    """Resolve item SKUs against inv_items in the database."""
    report = validate_invoice_math(extraction)
    for line in extraction.line_items:
        item = None
        if line.sku:
            res = await db.execute(select(Item).where(Item.sku == line.sku))
            item = res.scalars().first()
        if item is None and line.raw_name:
            res = await db.execute(
                select(Item).where(
                    func.lower(Item.name) == line.raw_name.strip().lower()
                )
            )
            item = res.scalars().first()
        if item is not None:
            line.matched_item_id = str(item.id)
            if not line.sku:
                line.sku = item.sku
        else:
            report.warnings.append(
                f"Item '{line.raw_name}' (SKU: {line.sku or 'N/A'}) could not be resolved in inventory catalog"
            )
    return report


async def create_draft_receipt_from_invoice(
    db: AsyncSession,
    extraction: InvoiceExtraction,
    *,
    maker_id: str | uuid.UUID,
    dest_location_id: str | uuid.UUID,
) -> InventoryRequest:
    """Create an InventoryRequest in 'draft' status.

    CRITICAL INVARIANT: The request is ALWAYS created in 'draft' status.
    It NEVER auto-approves or posts to inventory balances directly.
    """
    report = validate_invoice_math(extraction)
    if not report.is_valid:
        raise ValueError(
            f"Cannot create draft receipt: mathematical discrepancies detected: {'; '.join(report.errors)}"
        )

    # Ensure all items are catalog matched
    for line in extraction.line_items:
        if not line.matched_item_id:
            if line.sku:
                res = await db.execute(select(Item).where(Item.sku == line.sku))
                item = res.scalars().first()
                if item:
                    line.matched_item_id = str(item.id)
            if not line.matched_item_id and line.raw_name:
                res = await db.execute(
                    select(Item).where(
                        func.lower(Item.name) == line.raw_name.strip().lower()
                    )
                )
                item = res.scalars().first()
                if item:
                    line.matched_item_id = str(item.id)
            if not line.matched_item_id:
                raise ValueError(
                    f"Line item '{line.raw_name}' (SKU: {line.sku or 'N/A'}) has no matching catalog item ID"
                )

    dest_uuid = uuid.UUID(str(dest_location_id))
    loc = (
        await db.execute(select(Location).where(Location.id == dest_uuid))
    ).scalar_one_or_none()
    if loc is None:
        raise ValueError(f"Destination location {dest_location_id} not found")

    req_id = uuid.uuid4()
    maker_uuid = uuid.UUID(str(maker_id))

    req = InventoryRequest(
        id=req_id,
        kind="receipt",
        status="draft",
        maker_id=maker_uuid,
        created_by=maker_uuid,
        dest_id=dest_uuid,
        supplier=extraction.supplier_name,
        invoice_no=extraction.invoice_no,
        reason=f"Multimodal document intake from invoice {extraction.invoice_no}",
        sub_kind="purchase",
    )
    db.add(req)
    await db.flush()

    for line in extraction.line_items:
        line_id = uuid.uuid4()
        exp_date = None
        if line.expiry_date:
            try:
                exp_date = datetime.strptime(line.expiry_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        req_line = InventoryRequestLine(
            id=line_id,
            request_id=req_id,
            item_id=uuid.UUID(str(line.matched_item_id)),
            quantity=line.quantity,
            unit=line.unit,
            unit_price=line.unit_price,
            direction="increase",
            lot_no=line.lot_no,
            expiry_date=exp_date,
        )
        db.add(req_line)

    await db.commit()
    await db.refresh(req)
    return req
