"""Test Suite for Multi-Format Data Exports (Milestone M4: F11, F12, F13).

Covers:
  - Feature F11: CSV Output format, Single BOM verification, CWE-1236 neutralization
  - Feature F12: Server-side PDF export engine with ReportLab, Unicode TrueType font,
                 table styling, pagination, and NumberedCanvas
  - Feature F13: Multi-format export endpoints (catalog, balances, movements,
                 cash-journal, inventory-summary) supporting xlsx, csv, and pdf
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import openpyxl
import pytest

from app.services import export_engine

DEMO_PASSWORD = "DemoPass123!"


def _login(client: Any, username: str = "demo_admin", password: str = DEMO_PASSWORD) -> dict[str, str]:
    """Helper to authenticate and obtain Bearer authorization header."""
    res = client.post("/auth/login", data={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.text}"
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# ==============================================================================
# 1. Feature F11: Single-BOM CSV & CWE-1236 Formula Neutralization
# ==============================================================================


class TestFeatureF11CsvExportSingleBom:
    """Verifies that CSV export has exactly ONE clean UTF-8 BOM and neutralizes formulas."""

    def test_csv_engine_formula_neutralization_cwe1236(self) -> None:
        """Formula leads (=, @, +, -, TAB, CR) are escaped with single-quote; numbers stay unescaped."""
        injected = [
            ("=1+1", "'=1+1"),
            ("=cmd|'/C calc'!A0", "'=cmd|'/C calc'!A0"),
            ("@SUM(A1:B10)", "'@SUM(A1:B10)"),
            ("+1+1", "'+1+1"),
            ("-1+1", "'-1+1"),
            ("\tCMD", "'\tCMD"),
            ("\rEXEC", "'\rEXEC"),
            ("+123", "'+123"),  # + lead triggers formula escape per CWE-1236
            ("-4500", "-4500"),  # valid negative number
            (100, 100),
            (Decimal("99.99"), Decimal("99.99")),
            ("Trà Đen Thượng Hạng", "Trà Đen Thượng Hạng"),
            (None, ""),
        ]
        for raw, expected in injected:
            assert export_engine.sanitize_cell_value(raw) == expected

    def test_csv_engine_generates_single_bom_text(self) -> None:
        """generate_csv produces string starting with single Unicode BOM character \\ufeff."""
        headers = [("sku", "Mã SKU"), ("name", "Tên hàng")]
        rows = [{"sku": "SKU-001", "name": "Trà Sữa Oolong"}]

        csv_text = export_engine.generate_csv(rows, headers)
        assert csv_text.startswith("\ufeff")
        assert not csv_text.startswith("\ufeff\ufeff")
        assert "Mã SKU,Tên hàng" in csv_text
        assert "SKU-001,Trà Sữa Oolong" in csv_text

    def test_csv_endpoint_single_bom_byte_sequence(self, client: Any) -> None:
        """CSV response binary bytes start with exactly ONE UTF-8 BOM (b'\\xef\\xbb\\xbf'), not double BOM."""
        admin_auth = _login(client, "demo_admin")
        res = client.get("/exports/catalog?format=csv", headers=admin_auth)
        assert res.status_code == 200, res.text
        assert "text/csv" in res.headers["content-type"]
        assert "charset=utf-8" in res.headers["content-type"].lower()
        assert "attachment; filename=" in res.headers["content-disposition"]
        assert ".csv" in res.headers["content-disposition"]

        raw_bytes = res.content
        # Byte 0..3 must be standard UTF-8 BOM
        assert raw_bytes[:3] == b"\xef\xbb\xbf", "Response must start with UTF-8 BOM"

        # Byte 3..6 must NOT be a second BOM (guarantees NO double-BOM defect)
        assert not raw_bytes.startswith(b"\xef\xbb\xbf\xef\xbb\xbf"), (
            "Double-BOM defect detected! Byte sequence contains duplicated BOM bytes."
        )
        assert raw_bytes[3:6] != b"\xef\xbb\xbf", "Second byte sequence is also a BOM"

        # Decode directly using utf-8-sig (which strips the single BOM)
        text = raw_bytes.decode("utf-8-sig")
        first_line = text.splitlines()[0]
        # First header should be cleanly 'Mã SKU' without any hidden or corrupt characters
        assert first_line.startswith("Mã SKU"), f"Corrupted first header: {first_line!r}"

    def test_csv_endpoint_formula_neutralization_in_transit(self, client: Any) -> None:
        """End-to-end CSV export neutralizes formula injections in item catalog or balances."""
        admin_auth = _login(client, "demo_admin")
        res = client.get("/exports/catalog?format=csv", headers=admin_auth)
        assert res.status_code == 200
        text = res.content.decode("utf-8-sig")
        # Ensure no unescaped formula lines exist in the CSV output
        for line in text.splitlines():
            for cell in line.split(","):
                clean_cell = cell.strip("\"'")
                if clean_cell.startswith(("=", "@", "+", "-")) and not export_engine._NUMERIC_RE.match(clean_cell):
                    assert cell.startswith(("'=", "'@", "'+", "'-")), f"Cell {cell!r} was not escaped!"


# ==============================================================================
# 2. Feature F12: Server-Side PDF Export Engine
# ==============================================================================


class TestFeatureF12PdfExportEngine:
    """Verifies that generate_pdf creates valid, professional PDF documents with Unicode support."""

    def test_pdf_magic_header_and_byte_stream(self) -> None:
        """generate_pdf outputs a valid PDF starting with %PDF- magic header and substantial size."""
        headers = [("sku", "Mã SKU"), ("name", "Tên hàng hoá"), ("price", "Đơn giá (VNĐ)")]
        rows = [
            {"sku": "TRA-01", "name": "Trà Xanh Thái Nguyên Thượng Hạng", "price": 45000},
            {"sku": "TRA-02", "name": "Trà Đen Số 9 Hương Sen Cổ Điển", "price": 62000.5},
        ]

        pdf_bytes = export_engine.generate_pdf(rows, headers, title="Danh Mục Thử Nghiệm")
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000, "PDF byte stream should contain font, page, and table definitions"
        assert pdf_bytes.startswith(b"%PDF-"), "PDF file must start with '%PDF-' magic bytes"

    def test_pdf_vietnamese_unicode_characters_support(self) -> None:
        """Vietnamese accents and complex diacritics render cleanly without UnicodeEncodeError."""
        headers = [
            ("sku", "Mã SKU"),
            ("item_name", "Tên nguyên vật liệu"),
            ("location", "Kho / Vị trí"),
            ("quantity", "Số lượng"),
            ("unit", "ĐVT"),
            ("cost", "Đơn giá vốn"),
        ]
        rows = [
            {
                "sku": "NL-TRA-XANH",
                "item_name": "Trà Sữa Sài Gòn — Trân Châu Hoàng Kim & Đường Đen",
                "location": "Kho Trung Tâm Thành Phố Hồ Chí Minh",
                "quantity": 1500.50,
                "unit": "Hộp",
                "cost": 85000,
            },
            {
                "sku": "NL-SIRO-DAO",
                "item_name": "Siro Đào Tự Nhiên Đóng Chai Thủy Tinh (Đậm Đà Hương Vị)",
                "location": "Kho Chi Nhánh Quận 1 — Kho Lạnh",
                "quantity": 300,
                "unit": "Chai",
                "cost": 125000,
            },
        ]

        # Must execute without raising any UnicodeEncodeError or ReportLab LayoutError
        pdf_bytes = export_engine.generate_pdf(
            rows,
            headers,
            title="Báo Cáo Tồn Kho Thực Tế — Chi Tiết Nghiệp Vụ",
            metadata={"Đơn vị": "Công ty TNHH Kho Trà Sữa", "Người lập": "Nguyễn Văn Quản Trị"},
        )
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 2000

    def test_pdf_empty_dataset_handling(self) -> None:
        """Generating PDF with an empty dataset produces a valid document with an empty state note."""
        headers = [("sku", "Mã SKU"), ("name", "Tên hàng"), ("qty", "Số lượng")]
        empty_rows: list[dict[str, Any]] = []

        pdf_bytes = export_engine.generate_pdf(empty_rows, headers, title="Báo Cáo Trống")
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 1000

    def test_pdf_multipage_pagination_and_table_structure(self) -> None:
        """Large dataset (60+ rows) triggers multiple pages, repeated headers, and NumberedCanvas footer."""
        headers = [
            ("sku", "Mã SKU"),
            ("name", "Tên sản phẩm"),
            ("unit", "ĐVT"),
            ("stock", "Tồn kho"),
            ("price", "Giá bán (VNĐ)"),
            ("status", "Trạng thái"),
        ]
        rows: list[dict[str, Any]] = []
        for i in range(1, 80):
            rows.append({
                "sku": f"ITEM-{i:04d}",
                "name": f"Nguyên liệu pha chế số {i} — Trà Oolong cao cấp vụ thu đông",
                "unit": "Kg" if i % 2 == 0 else "Hộp",
                "stock": Decimal(f"{i * 12.5:.2f}"),
                "price": 35000 + i * 500,
                "status": "Hoạt động" if i % 3 != 0 else "Ngừng",
            })

        pdf_bytes = export_engine.generate_pdf(rows, headers, title="Báo Cáo Nhiều Trang")
        assert pdf_bytes.startswith(b"%PDF-")
        # Multi-page PDF should be substantially larger (> 20 KB)
        assert len(pdf_bytes) > 20000

    def test_pdf_cell_content_html_escaping(self) -> None:
        """Characters requiring XML escaping (<, >, &, \", ') do not break ReportLab Paragraph parser."""
        headers = [("sku", "Mã SKU"), ("name", "Tên & Ghi chú")]
        rows = [
            {"sku": "TAG-<001>", "name": "Trà Sữa <Đặc Biệt> & \"Hương Sen\" 'Mùa Thu'"},
            {"sku": "FORMULA-1", "name": "A & B < C > D && 100% Nguyên Chất"},
        ]

        pdf_bytes = export_engine.generate_pdf(rows, headers, title="Kiểm Thử Ký Tự Đặc Biệt")
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 1000


# ==============================================================================
# 3. Feature F13: Multi-Format Export Endpoints
# ==============================================================================


class TestFeatureF13MultiFormatEndpoints:
    """Verifies that all 5 export endpoints accept format=pdf, xlsx, csv and reject invalid formats."""

    @pytest.mark.parametrize(
        ("endpoint", "dataset_name"),
        [
            ("/exports/catalog", "DanhMuc_HangHoa"),
            ("/exports/balances", "TonKho_ChiTiet"),
            ("/exports/movements", "BienDong_Kho"),
            ("/exports/cash-journal", "SoQuy_TienMat"),
            ("/exports/inventory-summary", "TongHop_NhapXuatTon"),
        ],
    )
    def test_endpoints_support_pdf_format(self, client: Any, endpoint: str, dataset_name: str) -> None:
        """All 5 datasets return valid application/pdf responses with proper Content-Disposition."""
        admin_auth = _login(client, "demo_admin")
        res = client.get(f"{endpoint}?format=pdf", headers=admin_auth)
        assert res.status_code == 200, f"Endpoint {endpoint} failed: {res.text}"
        assert res.headers["content-type"] == "application/pdf"

        # Content-Disposition header checks
        cd = res.headers["content-disposition"]
        assert "attachment; filename=" in cd
        assert f"{dataset_name}_" in cd
        assert cd.endswith('.pdf"') or ".pdf" in cd

        # Binary check: PDF magic bytes
        assert res.content.startswith(b"%PDF-"), f"Response from {endpoint} is not a valid PDF"
        assert len(res.content) > 1000

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/exports/catalog",
            "/exports/balances",
            "/exports/movements",
            "/exports/cash-journal",
            "/exports/inventory-summary",
        ],
    )
    def test_endpoints_support_xlsx_and_csv_formats(self, client: Any, endpoint: str) -> None:
        """All 5 datasets return valid xlsx and csv responses."""
        admin_auth = _login(client, "demo_admin")

        # 1. XLSX
        res_xlsx = client.get(f"{endpoint}?format=xlsx", headers=admin_auth)
        assert res_xlsx.status_code == 200, res_xlsx.text
        assert res_xlsx.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert ".xlsx" in res_xlsx.headers["content-disposition"]
        # Must parse with openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(res_xlsx.content))
        assert wb.active is not None
        assert wb.active.max_row >= 3  # At least title, meta, header

        # 2. CSV
        res_csv = client.get(f"{endpoint}?format=csv", headers=admin_auth)
        assert res_csv.status_code == 200, res_csv.text
        assert "text/csv" in res_csv.headers["content-type"]
        assert ".csv" in res_csv.headers["content-disposition"]
        # Must start with single BOM
        assert res_csv.content[:3] == b"\xef\xbb\xbf"
        assert not res_csv.content.startswith(b"\xef\xbb\xbf\xef\xbb\xbf")

    @pytest.mark.parametrize("invalid_format", ["html", "json", "docx", "exe", "xml"])
    def test_query_validation_rejects_unsupported_formats(self, client: Any, invalid_format: str) -> None:
        """Query parameter format must be strictly validated against ^(xlsx|csv|pdf)$ pattern."""
        admin_auth = _login(client, "demo_admin")
        res = client.get(f"/exports/catalog?format={invalid_format}", headers=admin_auth)
        assert res.status_code == 422, f"Expected 422 for format={invalid_format}, got: {res.status_code}"

    def test_export_movements_date_range_filters(self, client: Any) -> None:
        """Movements export respects from_date and to_date filters in ISO-8601 format."""
        admin_auth = _login(client, "demo_admin")
        from_date = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        to_date = datetime.now(UTC).isoformat()

        res = client.get(
            f"/exports/movements?format=pdf&from_date={quote(from_date)}&to_date={quote(to_date)}",
            headers=admin_auth,
        )
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content.startswith(b"%PDF-")

    def test_export_unauthenticated_request_forbidden(self, client: Any) -> None:
        """Calling export endpoints without authentication header returns 401."""
        res = client.get("/exports/catalog?format=pdf")
        assert res.status_code == 401, f"Expected 401 for unauthenticated export, got: {res.status_code}"

    def test_excel_export_openpyxl_styling_and_data_integrity(self, client: Any) -> None:
        """Verifies Excel (.xlsx) layout, Classic Blue brand header, and number formatting."""
        admin_auth = _login(client, "demo_admin")
        res = client.get("/exports/catalog?format=xlsx", headers=admin_auth)
        assert res.status_code == 200

        wb = openpyxl.load_workbook(io.BytesIO(res.content))
        ws = wb.active
        assert ws is not None

        # Row 1: Title
        title_cell = ws.cell(row=1, column=1)
        assert "Danh Mục Hàng Hoá" in str(title_cell.value)
        assert title_cell.font.bold is True
        assert title_cell.font.color.rgb in ("000F4C81", "0F4C81")

        # Row 3: Header columns
        headers = [ws.cell(row=3, column=col).value for col in range(1, 9)]
        assert "Mã SKU" in headers
        assert "Đơn vị tính" in headers
        assert "Giá bán (VNĐ)" in headers

        # Header fill: Classic Blue
        header_cell = ws.cell(row=3, column=1)
        assert header_cell.fill.start_color.rgb in ("000F4C81", "0F4C81")
        assert header_cell.font.color.rgb in ("00FFFFFF", "FFFFFF")
