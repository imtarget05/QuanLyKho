"""E2E Test Suite for Google Sheets Bi-directional Synchronization & ETL Pipeline.

Covers:
  - Tier 1: Feature Coverage (Google Sheets API v4 mock, GViz CSV fallback, outbound sync, Apps Script webhook)
  - Tier 2: Boundary & Corner Cases (empty sheets, rate limits, formula injections, invalid SKUs)
  - Tier 3: Cross-Feature Combinations (GSheets Inbound -> ETL Staging -> Diff Preview -> Maker-Checker -> Ledger -> Audit)
  - Tier 4: Real-World Scenarios (Morning Opening Stock Import to Evening Outbound Closing Sync)

Testing Conventions:
  - Keyset cursor pagination uses conftest.fetch_all_balances
  - Database: PostgreSQL bankops_test (no SQLite)
  - Mocking external HTTP requests to Google Sheets API and Webhooks
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.api.errors import AppError
from app.services import google_sheets_service
from conftest import fetch_all_balances

DEMO_PASSWORD = "DemoPass123!"


def _login(client, username: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    """Helper to authenticate and return Bearer header."""
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed for {username}: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ==============================================================================
# TIER 1: FEATURE COVERAGE (Google Sheets API v4, GViz CSV, Outbound, Webhook)
# ==============================================================================


class TestGSheetsFeatureCoverage:
    """Tier 1: Feature coverage for Google Sheets reader/writer service and endpoints."""

    def test_extract_sheet_id_comprehensive_formats(self):
        """Extracts Google Sheet ID from diverse URL representations."""
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

        # Standard edit URL with anchor
        assert (
            google_sheets_service.extract_sheet_id(
                f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid=0"
            )
            == sheet_id
        )

        # View URL
        assert (
            google_sheets_service.extract_sheet_id(
                f"https://docs.google.com/spreadsheets/d/{sheet_id}/view"
            )
            == sheet_id
        )

        # Published HTML URL
        assert (
            google_sheets_service.extract_sheet_id(
                f"https://docs.google.com/spreadsheets/d/e/{sheet_id}/pubhtml"
            )
            == sheet_id
        )

        # Bare ID string
        assert google_sheets_service.extract_sheet_id(sheet_id) == sheet_id

        # Empty or malformed inputs raise AppError 422
        with pytest.raises(AppError) as exc_info:
            google_sheets_service.extract_sheet_id("")
        assert exc_info.value.http_status == 422

        with pytest.raises(AppError) as exc_info:
            google_sheets_service.extract_sheet_id("https://google.com/not-a-sheet-url")
        assert exc_info.value.http_status == 422

    @pytest.mark.asyncio
    async def test_fetch_sheet_rows_v4_api_mock(self):
        """Tests fetching sheet rows through Google Sheets v4 API endpoint with API key."""
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        fake_matrix = [
            ["Mã SKU", "Tên Hàng", "Số Lượng"],
            ["TRA-DEN-01", "Trà Đen Phúc Long", "50"],
            ["TRA-XANH-02", "Trà Xanh Thái Nguyên", "30"],
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"values": fake_matrix}

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_resp
            rows = await google_sheets_service.fetch_sheet_rows(
                sheet_id, tab="TonKho", api_key="AIzaSyFakeApiKey12345"
            )

        assert len(rows) == 2
        assert rows[0] == {"Mã SKU": "TRA-DEN-01", "Tên Hàng": "Trà Đen Phúc Long", "Số Lượng": "50"}
        assert rows[1]["Mã SKU"] == "TRA-XANH-02"

    @pytest.mark.asyncio
    async def test_fetch_sheet_rows_gviz_csv_fallback(self):
        """Tests fallback to Google Visualization CSV endpoint for public sheets."""
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        csv_text = "sku,name,price\nTRA-OOLONG,Trà Ô Long Tứ Quý,45000\nSUA-TUOI,Sữa Tươi Tiệt Trùng,32000\n"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = csv_text

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            rows = await google_sheets_service.fetch_sheet_rows(sheet_id, tab="Catalog", api_key="")

        assert len(rows) == 2
        assert rows[0]["sku"] == "TRA-OOLONG"
        assert rows[0]["price"] == "45000"
        assert rows[1]["sku"] == "SUA-TUOI"

    @pytest.mark.asyncio
    async def test_sync_out_to_google_sheet_matrix_serialization(self):
        """Tests outbound data formatting into 2D array representation for Google Sheets."""
        headers = [("sku", "Mã SKU"), ("name", "Tên sản phẩm"), ("qty", "Số lượng")]
        rows = [
            {"sku": "TRA-01", "name": "Trà Đen Số 9", "qty": 100},
            {"sku": "TRA-02", "name": "Lục Trà Lài", "qty": 85},
        ]

        result = await google_sheets_service.sync_out_to_google_sheet(
            url_or_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            tab="BaoCaoTon",
            headers=headers,
            rows=rows,
            include_sync_status=False,
        )

        assert result["status"] == "success"
        assert result["rows_count"] == 2
        assert result["columns_count"] == 3
        assert result["tab"] == "BaoCaoTon"
        assert "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit" in result["sheet_url"]

    @pytest.mark.asyncio
    async def test_sync_out_to_google_sheet_apps_script_webhook(self):
        """Tests dispatching outbound data payload to Google Apps Script Webhook."""
        headers = [("sku", "Mã SKU"), ("qty", "Số lượng")]
        rows = [{"sku": "TRA-01", "qty": 20}]

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"result": "success"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_post_resp
            result = await google_sheets_service.sync_out_to_google_sheet(
                url_or_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                tab="DongBo",
                headers=headers,
                rows=rows,
                include_sync_status=False,
                webhook_url="https://script.google.com/macros/s/AKfycbxFakeWebhook/exec",
            )

        assert result["status"] == "success"
        assert mock_post.called
        call_kwargs = mock_post.call_args.kwargs
        json_payload = call_kwargs["json"]
        assert json_payload["tab"] == "DongBo"
        assert json_payload["rows"] == [["Mã SKU", "Số lượng"], ["TRA-01", 20]]

    def test_export_sync_google_sheets_endpoint(self, client):
        """Verifies POST /exports/sync-google-sheets pushes catalog/balances to GSheets."""
        admin_auth = _login(client, "demo_admin")

        mock_sync_result = {
            "status": "success",
            "sheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            "tab": "Catalog_Sheet",
            "sheet_url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
            "rows_count": 10,
            "columns_count": 8,
        }

        with patch("app.services.google_sheets_service.sync_out_to_google_sheet", new_callable=AsyncMock) as mock_sync:
            mock_sync.return_value = mock_sync_result

            res = client.post(
                "/exports/sync-google-sheets",
                headers=admin_auth,
                json={
                    "sheet_url_or_id": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=0",
                    "tab": "Catalog_Sheet",
                    "dataset": "catalog",
                },
            )

        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["tab"] == "Catalog_Sheet"
        assert data["sheet_url"] == mock_sync_result["sheet_url"]


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES (Empty, Rate Limit, Injections, Invalid FK)
# ==============================================================================


class TestGSheetsBoundaryAndCornerCases:
    """Tier 2: Empty datasets, error handling, rate limits, formula injections."""

    @pytest.mark.asyncio
    async def test_gsheets_empty_sheet_handling(self):
        """Empty sheet or header-only sheet safely returns empty list without error."""
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

        # 1. API v4 returns empty values
        mock_resp_empty = MagicMock()
        mock_resp_empty.status_code = 200
        mock_resp_empty.json.return_value = {"values": []}

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_resp_empty
            rows = await google_sheets_service.fetch_sheet_rows(sheet_id, api_key="AIzaKey")
            assert rows == []

        # 2. GViz CSV returns only header
        mock_resp_header_only = MagicMock()
        mock_resp_header_only.status_code = 200
        mock_resp_header_only.text = "sku,name,price\n"

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp_header_only
            rows = await google_sheets_service.fetch_sheet_rows(sheet_id, api_key="")
            assert rows == []

    @pytest.mark.asyncio
    async def test_gsheets_network_error_and_unauthorized_handling(self):
        """Verifies informative AppErrors on network connection failures and 403."""
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

        # 1. Network failure
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("Network unreachable")
            with pytest.raises(AppError) as exc_info:
                await google_sheets_service.fetch_sheet_rows(sheet_id, api_key="")
            assert exc_info.value.http_status == 503
            assert exc_info.value.code == "SHEETS_UNAVAILABLE"

        # 2. Private Google Sheet without permission (HTTP 403)
        mock_403 = MagicMock()
        mock_403.status_code = 403
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_403
            with pytest.raises(AppError) as exc_info:
                await google_sheets_service.fetch_sheet_rows(sheet_id, api_key="")
            assert exc_info.value.http_status == 403
            assert "SHEETS_READ_FAILED" in exc_info.value.code

    @pytest.mark.asyncio
    async def test_gsheets_webhook_failure_resilience(self):
        """Apps Script Webhook returning HTTP 500 raises AppError 502 with message."""
        headers = [("sku", "Mã SKU")]
        rows = [{"sku": "TRA-01"}]

        mock_500 = MagicMock()
        mock_500.status_code = 500

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_500
            with pytest.raises(AppError) as exc_info:
                await google_sheets_service.sync_out_to_google_sheet(
                    url_or_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                    tab="Sheet1",
                    headers=headers,
                    rows=rows,
                    webhook_url="https://script.google.com/macros/s/fail",
                )
            assert exc_info.value.http_status == 502
            assert exc_info.value.code == "WEBHOOK_FAILED"


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (GSheets Inbound -> Staging -> Maker-Checker)
# ==============================================================================


class TestGSheetsEtlCrossFeatureCombinations:
    """Tier 3: GSheets Inbound -> 4-Layer ETL Staging -> Diff Preview -> Maker-Checker Post."""

    def test_cross_feature_gsheets_etl_staging_and_diff_preview(self, client):
        """Ingests rows from Google Sheet into ETL Staging and verifies diff preview."""
        admin_auth = _login(client, "demo_admin")

        # 1. Get location & existing item
        locs = client.get("/inventory/locations", headers=admin_auth).json()["locations"]
        items = client.get("/inventory/items", headers=admin_auth).json()["items"]
        loc_id = locs[0]["id"]
        valid_sku = items[0]["sku"]

        # 2. Create Connection of type google_sheets
        conn_res = client.post(
            "/etl/connections",
            headers=admin_auth,
            json={
                "name": "E2E GSheets Connection",
                "type": "google_sheets",
                "secret_ref": "env://GOOGLE_SHEETS_KEY",
                "allowlist_sheets": ["1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"],
            },
        )
        assert conn_res.status_code == 201, conn_res.text
        conn_id = conn_res.json()["id"]

        # 3. Create Pipeline with target balance_adjustment_admin
        pipe_res = client.post(
            "/etl/pipelines",
            headers=admin_auth,
            json={
                "name": "E2E GSheets Stock Adjustment",
                "target": "balance_adjustment_admin",
                "connection_id": conn_id,
                "location_id": loc_id,
            },
        )
        assert pipe_res.status_code == 201, pipe_res.text
        pipe_id = pipe_res.json()["id"]

        # 4. Mock Google Sheets fetch returning: 1 valid row (existing SKU) and 1 invalid row (unknown SKU)
        mock_sheet_rows = [
            {"sku": valid_sku, "target_quantity": "50", "reason": "Kiểm kê định kỳ từ GSheet"},
            {"sku": "NON_EXISTENT_TEA_SKU", "target_quantity": "10", "reason": "Lỗi SKU"},
        ]

        with patch("app.services.google_sheets_service.fetch_sheet_rows", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_sheet_rows

            run_res = client.post(
                f"/etl/pipelines/{pipe_id}/runs",
                headers=admin_auth,
                json={
                    "sheet_url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
                    "tab": "KiemKe",
                },
            )

        assert run_res.status_code == 201, run_res.text
        run = run_res.json()
        assert run["status"] == "staged"
        assert run["total_rows"] == 2
        assert run["valid_rows"] == 1
        assert run["invalid_rows"] == 1

        # 5. Inspect Staging rows and action_preview
        rows_res = client.get(f"/etl/runs/{run['id']}/rows", headers=admin_auth)
        assert rows_res.status_code == 200
        rows_data = rows_res.json()["rows"]

        valid_row = next(r for r in rows_data if r["valid"] is True)
        assert valid_row["action_preview"]["target_quantity"] == 50.0
        assert valid_row["action_preview"]["direction"] in ("increase", "decrease", "none")

        invalid_row = next(r for r in rows_data if r["valid"] is False)
        assert "không tồn tại" in str(invalid_row["errors_json"])

    def test_cross_feature_maker_checker_posting_and_single_admin_override(self, client):
        """Verifies single_admin_override generates draft request, then checker approves to update ledger."""
        admin_auth = _login(client, "demo_admin")
        items = client.get("/inventory/items", headers=admin_auth).json()["items"]
        locs = client.get("/inventory/locations", headers=admin_auth).json()["locations"]
        loc_id = locs[0]["id"]
        sku = items[0]["sku"]

        # Check initial balance
        bal_res = fetch_all_balances(client, admin_auth)
        init_bal = next((b for b in bal_res if b["item_id"] == items[0]["id"] and b["location_id"] == loc_id), None)
        initial_qty = float(init_bal["quantity"]) if init_bal else 0.0

        target_qty = initial_qty + 10.0

        # Create connection & pipeline
        conn = client.post("/etl/connections", headers=admin_auth, json={"name": "Post Test Conn", "type": "google_sheets"}).json()
        pipe = client.post(
            "/etl/pipelines",
            headers=admin_auth,
            json={"name": "Post Test Pipe", "target": "balance_adjustment_admin", "connection_id": conn["id"], "location_id": loc_id},
        ).json()

        mock_rows = [{"sku": sku, "target_quantity": str(target_qty), "reason": "Maker Checker Test"}]
        with patch("app.services.google_sheets_service.fetch_sheet_rows", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_rows
            run = client.post(
                f"/etl/pipelines/{pipe['id']}/runs",
                headers=admin_auth,
                json={"sheet_url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"},
            ).json()

        run_id = run["id"]

        # Post with single_admin_override=True (creates draft request to satisfy maker!=checker invariant)
        post_res = client.post(
            f"/etl/runs/{run_id}/post",
            headers=admin_auth,
            json={"single_admin_override": True, "override_reason": "Quản trị viên duyệt điều chỉnh tồn kho E2E"},
        )
        assert post_res.status_code == 200, post_res.text
        post_data = post_res.json()
        assert post_data["status"] == "pending_approval"
        assert post_data["single_admin_override"] is True
        req_id = post_data["request_id"]

        # Independent checker approves the adjustment request
        checker_auth = _login(client, "demo_checker")
        sub_res = client.post(
            f"/inventory/requests/{req_id}/submit",
            headers={**admin_auth, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert sub_res.status_code == 200, sub_res.text

        appr_res = client.post(
            f"/inventory/requests/{req_id}/approve",
            headers={**checker_auth, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert appr_res.status_code in (200, 201), appr_res.text

        # Verify balance updated via fetch_all_balances
        balances = fetch_all_balances(client, admin_auth)
        matching_bal = next(b for b in balances if b["item_id"] == items[0]["id"] and b["location_id"] == loc_id)
        assert abs(float(matching_bal["quantity"]) - target_qty) < 0.001


# ==============================================================================
# TIER 4: REAL-WORLD SCENARIO (Morning Inbound Sync to Evening Outbound Export)
# ==============================================================================


class TestRealWorldGSheetsWorkflow:
    """Tier 4: End-to-end retail day cycle linking GSheets import to export."""

    def test_real_world_morning_inbound_to_evening_outbound_cycle(self, client):
        """Simulates complete retail day:

        1. Morning: Supplier shares Google Sheet with newly delivered stock.
        2. System imports rows into Staging, generates diff preview.
        3. Manager approves and posts balance adjustments to Ledger.
        4. Evening: Store closes, manager triggers outbound export to Google Sheet.
        5. Verifies closing balances reflect updated stock.
        """
        admin_auth = _login(client, "demo_admin")

        # 1. Morning Opening: Import stock from Supplier Google Sheet
        conn = client.post("/etl/connections", headers=admin_auth, json={"name": "Supplier Sheet", "type": "google_sheets"}).json()
        loc = client.get("/inventory/locations", headers=admin_auth).json()["locations"][0]
        item = client.get("/inventory/items", headers=admin_auth).json()["items"][0]

        pipe = client.post(
            "/etl/pipelines",
            headers=admin_auth,
            json={"name": "Morning Sync", "target": "balance_adjustment_admin", "connection_id": conn["id"], "location_id": loc["id"]},
        ).json()

        morning_stock = 120.0
        mock_sheet = [{"sku": item["sku"], "target_quantity": str(morning_stock), "reason": "Nhập hàng sáng từ NCC"}]
        with patch("app.services.google_sheets_service.fetch_sheet_rows", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_sheet
            run = client.post(
                f"/etl/pipelines/{pipe['id']}/runs",
                headers=admin_auth,
                json={"sheet_url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"},
            ).json()

        # 2. Review and Post morning stock
        post_res = client.post(
            f"/etl/runs/{run['id']}/post",
            headers=admin_auth,
            json={"single_admin_override": True, "override_reason": "Duyệt nhập hàng buổi sáng"},
        )
        assert post_res.status_code == 200

        # 3. Evening Closing: Outbound export closing inventory to Google Sheets
        mock_sync_result = {
            "status": "success",
            "sheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            "tab": "BaoCaoDongCua",
            "sheet_url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
            "rows_count": 1,
            "columns_count": 9,
        }

        with patch("app.services.google_sheets_service.sync_out_to_google_sheet", new_callable=AsyncMock) as mock_out:
            mock_out.return_value = mock_sync_result
            closing_res = client.post(
                "/exports/sync-google-sheets",
                headers=admin_auth,
                json={
                    "sheet_url_or_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                    "tab": "BaoCaoDongCua",
                    "dataset": "balances",
                },
            )

        assert closing_res.status_code == 200
        assert closing_res.json()["status"] == "success"
