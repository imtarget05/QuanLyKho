"""Unit tests for Export Engine and Google Sheets Sync Service."""

from __future__ import annotations

import io
from decimal import Decimal

import openpyxl
import pytest

from app.api.errors import AppError
from app.services import export_engine, google_sheets_service


def test_sanitize_cell_value_neutralizes_formulas():
    assert export_engine.sanitize_cell_value("=1+1") == "'=1+1"
    assert export_engine.sanitize_cell_value("@SUM(A1:B2)") == "'@SUM(A1:B2)"
    assert export_engine.sanitize_cell_value("+1") == "'+1"
    assert export_engine.sanitize_cell_value("-1+1") == "'-1+1"
    assert export_engine.sanitize_cell_value("\tHIDDEN") == "'\tHIDDEN"

    # Numbers and normal text untouched
    assert export_engine.sanitize_cell_value(123) == 123
    assert export_engine.sanitize_cell_value("-500") == "-500"
    assert export_engine.sanitize_cell_value(Decimal("45.5")) == Decimal("45.5")
    assert export_engine.sanitize_cell_value("Trà Đen Số 9") == "Trà Đen Số 9"
    assert export_engine.sanitize_cell_value(None) == ""


def test_generate_xlsx_creates_valid_workbook():
    headers = [("sku", "Mã SKU"), ("name", "Tên hàng"), ("price", "Đơn giá")]
    rows = [
        {"sku": "TRA-01", "name": "Trà Xanh", "price": 45000},
        {"sku": "TRA-02", "name": "=cmd|'calc'!A1", "price": 60000.5},
    ]

    xlsx_bytes = export_engine.generate_xlsx(rows, headers, title="Kiểm thử Danh mục")
    assert isinstance(xlsx_bytes, bytes)
    assert len(xlsx_bytes) > 0

    # Load back using openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    assert ws.title == "Kiểm thử Danh mục"

    # Row 1: Title
    assert "Kiểm thử Danh mục" in ws.cell(row=1, column=1).value
    # Row 3: Headers
    assert ws.cell(row=3, column=1).value == "Mã SKU"
    assert ws.cell(row=3, column=2).value == "Tên hàng"
    assert ws.cell(row=3, column=3).value == "Đơn giá"

    # Row 4: Data
    assert ws.cell(row=4, column=1).value == "TRA-01"
    assert ws.cell(row=4, column=2).value == "Trà Xanh"
    assert ws.cell(row=4, column=3).value == 45000

    # Row 5: Injected formula cell sanitized
    assert ws.cell(row=5, column=2).value == "'=cmd|'calc'!A1"


def test_generate_csv_contains_bom_and_sanitizes():
    headers = [("sku", "Mã SKU"), ("name", "Tên")]
    rows = [{"sku": "SKU-99", "name": "@SUM(1,2)"}]

    csv_text = export_engine.generate_csv(rows, headers)
    assert csv_text.startswith("\ufeff")
    assert "Mã SKU,Tên" in csv_text
    assert "SKU-99" in csv_text
    assert "'@SUM(1,2)" in csv_text


def test_extract_sheet_id_from_various_formats():
    valid_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    # Standard edit URL
    url1 = f"https://docs.google.com/spreadsheets/d/{valid_id}/edit#gid=0"
    assert google_sheets_service.extract_sheet_id(url1) == valid_id

    # View URL
    url2 = f"https://docs.google.com/spreadsheets/d/{valid_id}/view"
    assert google_sheets_service.extract_sheet_id(url2) == valid_id

    # Published URL
    url3 = f"https://docs.google.com/spreadsheets/d/e/{valid_id}/pubhtml"
    assert google_sheets_service.extract_sheet_id(url3) == valid_id

    # Direct ID
    assert google_sheets_service.extract_sheet_id(valid_id) == valid_id

    # Invalid
    with pytest.raises(AppError):
        google_sheets_service.extract_sheet_id("")

    with pytest.raises(AppError):
        google_sheets_service.extract_sheet_id("invalid!format")
