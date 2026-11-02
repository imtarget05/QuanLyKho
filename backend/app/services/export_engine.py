"""Export Engine — kết xuất dữ liệu sang Excel (.xlsx) & CSV an toàn (CWE-1236).

Cung cấp:
  - Sinh file Excel (.xlsx) có styling chuẩn, tự căn lề & độ rộng cột.
  - Sinh file CSV có BOM UTF-8 (chuẩn tiếng Việt cho Excel) và chống Formula Injection.
  - Bộ chuẩn hóa cấu trúc dữ liệu cho: Catalog, Balances, Movements, Cash Journal, Inventory Summary.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# CWE-1236: Ký tự đầu ô kích hoạt công thức trên Excel / Sheets
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")


def sanitize_cell_value(val: Any) -> Any:
    """Khử injection công thức trong ô bảng tính."""
    if val is None:
        return ""
    if isinstance(val, (int, float, Decimal, bool, datetime)):
        return val
    text = str(val)
    if text[:1] in _FORMULA_LEAD and not _NUMERIC_RE.match(text):
        return "'" + text
    return text


def generate_xlsx(
    rows: list[dict[str, Any]],
    headers: list[tuple[str, str]],  # [(field_key, display_label)]
    title: str = "Báo cáo Dữ liệu",
) -> bytes:
    """Tạo file Excel .xlsx được định dạng chuyên nghiệp."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31]  # Giới hạn tên tab Excel 31 ký tự

    # Theme colors
    header_fill = PatternFill(start_color="0F4C81", end_color="0F4C81", fill_type="solid")  # Brand Classic Blue
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)
    border_thin = Border(
        left=Side(style="thin", color="D1D5DB"),
        right=Side(style="thin", color="D1D5DB"),
        top=Side(style="thin", color="D1D5DB"),
        bottom=Side(style="thin", color="D1D5DB"),
    )
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    # 1. Title Row
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title_cell = ws.cell(row=1, column=1, value=title)
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="0F4C81")
    title_cell.alignment = align_left
    ws.row_dimensions[1].height = 28

    # 2. Generated metadata row
    ws.cell(
        row=2,
        column=1,
        value=f"Thời gian kết xuất: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
    ).font = Font(name="Calibri", size=9, italic=True, color="6B7280")
    ws.row_dimensions[2].height = 18

    # 3. Header Row (Row 3)
    ws.row_dimensions[3].height = 24
    for col_idx, (_, label) in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col_idx, value=label)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center
        cell.border = border_thin

    # 4. Data Rows (From Row 4)
    for row_idx, r in enumerate(rows, start=4):
        ws.row_dimensions[row_idx].height = 20
        for col_idx, (key, _) in enumerate(headers, start=1):
            val = r.get(key)
            safe_val = sanitize_cell_value(val)
            cell = ws.cell(row=row_idx, column=col_idx, value=safe_val)
            cell.font = data_font
            cell.border = border_thin

            if isinstance(safe_val, (int, float, Decimal)):
                cell.alignment = align_right
                if isinstance(safe_val, Decimal) or isinstance(safe_val, float):
                    cell.number_format = "#,##0.00"
                else:
                    cell.number_format = "#,##0"
            elif isinstance(safe_val, datetime):
                cell.alignment = align_center
                cell.number_format = "yyyy-mm-dd hh:mm"
            elif isinstance(safe_val, bool):
                cell.alignment = align_center
            else:
                cell.alignment = align_left

    # 5. Auto column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row in (1, 2):
                continue
            v = str(cell.value or "")
            max_len = max(max_len, len(v))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_csv(
    rows: list[dict[str, Any]],
    headers: list[tuple[str, str]],
) -> str:
    """Tạo file CSV có BOM UTF-8 (\ufeff) để Excel mở tiếng Việt không lỗi font."""
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM
    writer = csv.writer(output)

    # Header
    writer.writerow([label for _, label in headers])

    # Data
    for r in rows:
        row_vals = []
        for key, _ in headers:
            val = r.get(key)
            if isinstance(val, datetime):
                row_vals.append(val.strftime("%Y-%m-%d %H:%M:%S"))
            else:
                row_vals.append(sanitize_cell_value(val))
        writer.writerow(row_vals)

    return output.getvalue()


# --------------------------------------------------------------------------
# Datasets Serializers
# --------------------------------------------------------------------------


def serialize_catalog_dataset(items: list[Any]) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """Serializes danh mục hàng hóa."""
    headers = [
        ("sku", "Mã SKU"),
        ("name", "Tên hàng hoá / Nguyên liệu"),
        ("unit", "Đơn vị tính"),
        ("cost_price", "Giá vốn (VNĐ)"),
        ("selling_price", "Giá bán (VNĐ)"),
        ("min_stock", "Tồn tối thiểu"),
        ("tracked_serial", "Quản lý Serial/Lô"),
        ("active", "Đang kinh doanh"),
    ]
    rows = []
    for it in items:
        rows.append({
            "sku": it.sku,
            "name": it.name,
            "unit": it.unit or "",
            "cost_price": float(it.cost_price) if getattr(it, "cost_price", None) is not None else 0.0,
            "selling_price": float(it.selling_price) if getattr(it, "selling_price", None) is not None else 0.0,
            "min_stock": getattr(it, "min_stock", 0) or 0,
            "tracked_serial": "Có" if getattr(it, "tracked_serial", False) else "Không",
            "active": "Hoạt động" if getattr(it, "active", True) else "Ngừng",
        })
    return headers, rows


def serialize_balances_dataset(
    balance_records: list[tuple[Any, Any, Any]],
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """Serializes số dư tồn kho (Balance, Item, Location)."""
    headers = [
        ("sku", "Mã SKU"),
        ("item_name", "Tên hàng hoá"),
        ("unit", "ĐVT"),
        ("location_name", "Kho / Vị trí"),
        ("quantity", "Tồn thực tế"),
        ("reserved", "Đang giữ chỗ"),
        ("available", "Khả dụng"),
        ("cost_price", "Đơn giá vốn"),
        ("total_value", "Tổng giá trị tồn"),
    ]
    rows = []
    for bal, it, loc in balance_records:
        qty = float(bal.quantity or 0)
        res = float(getattr(bal, "reserved_quantity", 0) or 0)
        cost = float(it.cost_price or 0) if it and getattr(it, "cost_price", None) else 0.0
        avail = qty - res
        tot_val = qty * cost
        rows.append({
            "sku": it.sku if it else "",
            "item_name": it.name if it else "",
            "unit": it.unit if it else "",
            "location_name": loc.name if loc else "",
            "quantity": qty,
            "reserved": res,
            "available": avail,
            "cost_price": cost,
            "total_value": tot_val,
        })
    return headers, rows


def serialize_movements_dataset(
    movement_records: list[tuple[Any, Any, Any]],
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """Serializes biến động kho (Movement, Item, Location)."""
    headers = [
        ("posted_at", "Thời gian ghi sổ"),
        ("sub_kind", "Loại biến động"),
        ("sku", "Mã SKU"),
        ("item_name", "Tên hàng"),
        ("location_name", "Kho"),
        ("quantity_signed", "Số lượng (+/-)"),
        ("unit_cost", "Đơn giá"),
        ("cost_amount", "Thành tiền vốn"),
        ("request_id", "Mã phiếu liên quan"),
    ]
    rows = []
    for mv, it, loc in movement_records:
        rows.append({
            "posted_at": mv.posted_at or mv.created_at,
            "sub_kind": mv.sub_kind or "",
            "sku": it.sku if it else "",
            "item_name": it.name if it else "",
            "location_name": loc.name if loc else "",
            "quantity_signed": float(mv.quantity_signed or 0),
            "unit_cost": float(mv.unit_cost or 0) if mv.unit_cost is not None else 0.0,
            "cost_amount": float(mv.cost_amount or 0) if mv.cost_amount is not None else 0.0,
            "request_id": str(mv.request_id or ""),
        })
    return headers, rows


def serialize_cash_journal_dataset(
    records: list[tuple[Any, Any]],  # list of (CashJournal, CashRequest)
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """Serializes sổ nhật ký thu chi tiền mặt."""
    headers = [
        ("posted_at", "Ngày hạch toán"),
        ("journal_id", "Mã nhật ký"),
        ("request_id", "Mã phiếu thu/chi"),
        ("kind", "Phân loại"),
        ("amount", "Số tiền (VNĐ)"),
        ("status", "Trạng thái phiếu"),
        ("reason", "Lý do / Diễn giải"),
    ]
    rows = []
    for j, req in records:
        rows.append({
            "posted_at": j.posted_at or j.created_at,
            "journal_id": str(j.id),
            "request_id": str(req.id) if req else str(j.request_id),
            "kind": req.kind if req else "",
            "amount": float(req.amount or 0) if req else 0.0,
            "status": req.status if req else "posted",
            "reason": req.reason if req else "",
        })
    return headers, rows


def serialize_inventory_summary_dataset(
    summary_items: list[dict[str, Any]],
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """Serializes báo cáo tổng hợp Nhập - Xuất - Tồn."""
    headers = [
        ("period", "Kỳ báo cáo"),
        ("inbound_qty", "Số lượng Nhập"),
        ("outbound_qty", "Số lượng Xuất"),
        ("net_qty", "Biến động ròng"),
        ("receipt_count", "Số phiếu nhập"),
        ("issue_count", "Số phiếu xuất"),
    ]
    rows = []
    for s in summary_items:
        rows.append({
            "period": s.get("bucket", ""),
            "inbound_qty": float(s.get("inboundQty", s.get("inbound_qty", 0))),
            "outbound_qty": float(s.get("outboundQty", s.get("outbound_qty", 0))),
            "net_qty": float(s.get("netQty", s.get("net_qty", 0))),
            "receipt_count": int(s.get("receiptCount", s.get("receipt_count", 0))),
            "issue_count": int(s.get("issueCount", s.get("issue_count", 0))),
        })
    return headers, rows
