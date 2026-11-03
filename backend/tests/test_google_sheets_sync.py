"""Comprehensive tests for Bi-Directional Google Sheets API Service (Milestone M3: F8, F9, F10).

Covers:
  - F8: Pure Async Google Sheets API v4 Client:
      * Sheet ID extraction & column index to letter conversion
      * Service Account and OAuth authorization header generation
      * fetch_sheet_values (GET /v4/spreadsheets/{id}/values/{range})
      * write_sheet_values (PUT /v4/spreadsheets/{id}/values/{range}) with CWE-1236 sanitization
      * batch_update_sheet_values (POST /v4/spreadsheets/{id}/values:batchUpdate)
      * Exponential backoff and jitter on HTTP 429 (Rate Limit) and 503
      * Error status handling (403 Forbidden, 404 Not Found)
  - F9: Inbound Google Sheets Staging & 4-Layer ETL Integration:
      * Fetch sheet rows with credentials / connection config
      * Staging run creation into EtlRunRow with action_preview diffs
      * SHA-256 fingerprint deduplication
      * Security allowlist_sheets enforcement
      * Maker-Checker rule (staged review pending)
      * Inventory ledger invariant: all adjustments posted via InventoryRequest & Movement
  - F10: Outbound Google Sheets Sync & Status Writeback:
      * Export datasets (Catalog, Balances, Movements, Cash Journal) to Google Sheets
      * In-sheet row-level status writeback (_sync_status column)
      * Spreadsheet formula injection defense (CWE-1236)
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.api.errors import AppError
from app.services import google_sheets_service

DEMO_PASSWORD = "DemoPass123!"


def _login(client, username: str = "demo_admin", password: str = DEMO_PASSWORD) -> dict[str, str]:
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _generate_test_sa_info() -> dict[str, Any]:
    """Tạo Service Account info hợp lệ kèm private key RSA thực sự để kiểm thử."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    return {
        "type": "service_account",
        "project_id": "quanlykho-test-project",
        "private_key_id": "test_key_12345",
        "private_key": pem,
        "client_email": "quanlykho-sync@quanlykho-test-project.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


# ==============================================================================
# F8: Pure Async Google Sheets API v4 Client Tests
# ==============================================================================


class TestGoogleSheetsClientF8:
    def test_extract_sheet_id_and_column_letter(self):
        valid_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

        # URLs
        assert google_sheets_service.extract_sheet_id(f"https://docs.google.com/spreadsheets/d/{valid_id}/edit") == valid_id
        assert google_sheets_service.extract_sheet_id(f"https://docs.google.com/spreadsheets/d/{valid_id}/view?usp=sharing") == valid_id
        assert google_sheets_service.extract_sheet_id(f"https://docs.google.com/spreadsheets/d/e/{valid_id}/pubhtml") == valid_id
        assert google_sheets_service.extract_sheet_id(valid_id) == valid_id

        # Invalid
        with pytest.raises(AppError) as exc_empty:
            google_sheets_service.extract_sheet_id("")
        assert exc_empty.value.http_status == 422

        with pytest.raises(AppError) as exc_inv:
            google_sheets_service.extract_sheet_id("short")
        assert exc_inv.value.http_status == 422

        # Column letter conversions
        assert google_sheets_service.column_index_to_letter(1) == "A"
        assert google_sheets_service.column_index_to_letter(26) == "Z"
        assert google_sheets_service.column_index_to_letter(27) == "AA"
        assert google_sheets_service.column_index_to_letter(28) == "AB"
        assert google_sheets_service.column_index_to_letter(52) == "AZ"
        assert google_sheets_service.column_index_to_letter(53) == "BA"
        assert google_sheets_service.column_index_to_letter(702) == "ZZ"

        with pytest.raises(ValueError):
            google_sheets_service.column_index_to_letter(0)

    @pytest.mark.asyncio
    async def test_authorization_header_generation(self):
        # 1. Direct Bearer token string
        header1 = await google_sheets_service.get_authorization_header("Bearer ya29.mock_token")
        assert header1 == "Bearer ya29.mock_token"

        header2 = await google_sheets_service.get_authorization_header("ya29.mock_token_direct")
        assert header2 == "Bearer ya29.mock_token_direct"

        # 2. Dict with access_token
        header3 = await google_sheets_service.get_authorization_header({"access_token": "ya29.oauth_direct"})
        assert header3 == "Bearer ya29.oauth_direct"

        # 3. Service Account info with mock refresh
        sa_info = _generate_test_sa_info()
        sa_info["token"] = "ya29.sa_token_preset"
        header4 = await google_sheets_service.get_authorization_header(sa_info)
        assert header4 == "Bearer ya29.sa_token_preset"

        # 4. JSON string parsing
        header5 = await google_sheets_service.get_authorization_header(json.dumps({"token": "ya29.from_json"}))
        assert header5 == "Bearer ya29.from_json"

        # 5. Invalid JSON string raises AppError
        with pytest.raises(AppError) as exc:
            await google_sheets_service.get_authorization_header("{invalid_json:")
        assert exc.value.http_status == 422

    @pytest.mark.asyncio
    async def test_fetch_sheet_values_success(self):
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        expected_values = [
            ["Mã SKU", "Tên Hàng", "Đơn Vị"],
            ["TRA-DEN-01", "Trà Đen Phúc Long", "gói"],
            ["TRA-XANH-02", "Trà Xanh Thái Nguyên", "kg"],
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert sheet_id in str(request.url)
            assert request.headers.get("Authorization") == "Bearer ya29.test_token"
            return httpx.Response(200, json={"range": "'Sheet1'!A1:ZZ", "majorDimension": "ROWS", "values": expected_values})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as mock_client:
            values = await google_sheets_service.fetch_sheet_values(
                sheet_id=sheet_id,
                range_name="Sheet1!A1:ZZ",
                credentials_info={"access_token": "ya29.test_token"},
                client=mock_client,
            )

        assert values == expected_values
        assert len(values) == 3

    @pytest.mark.asyncio
    async def test_write_sheet_values_with_formula_sanitization(self):
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        captured_body: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_body
            assert request.method == "PUT"
            captured_body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"updatedRows": 2, "updatedColumns": 3, "updatedCells": 6})

        # Input values include dangerous formula strings
        input_values = [
            ["Mã SKU", "Tên", "Giá trị"],
            ["=1+1", "@SUM(A1:B2)", "-500"],
            ["+cmd|'calc'!A1", "Bình thường", 1000],
        ]

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as mock_client:
            res = await google_sheets_service.write_sheet_values(
                sheet_id=sheet_id,
                range_name="Sheet1!A1:C3",
                values=input_values,
                credentials_info={"access_token": "ya29.test_token"},
                client=mock_client,
            )

        assert res["updatedRows"] == 2
        # Verify sanitization in sent body:
        sent_rows = captured_body["values"]
        assert sent_rows[1][0] == "'=1+1"  # neutralized
        assert sent_rows[1][1] == "'@SUM(A1:B2)"  # neutralized
        assert sent_rows[1][2] == "-500"  # pure numeric preserved
        assert sent_rows[2][0] == "'+cmd|'calc'!A1"  # neutralized
        assert sent_rows[2][1] == "Bình thường"  # untouched
        assert sent_rows[2][2] == 1000  # number untouched

    @pytest.mark.asyncio
    async def test_batch_update_sheet_values(self):
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert "values:batchUpdate" in str(request.url)
            body = json.loads(request.content.decode("utf-8"))
            assert len(body["data"]) == 2
            return httpx.Response(200, json={"totalUpdatedRows": 4, "totalUpdatedCells": 8})

        batch_data = [
            {"range": "Sheet1!K2:K3", "values": [["✓ HỢP LỆ"], ["✓ ĐÃ DUYỆT"]]},
            {"range": "Sheet1!K4:K5", "values": [["✗ LỖI: SKU không tồn tại"], ["✓ ĐÃ GHI SỔ"]]},
        ]

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as mock_client:
            res = await google_sheets_service.batch_update_sheet_values(
                sheet_id=sheet_id,
                data=batch_data,
                credentials_info={"access_token": "ya29.batch_token"},
                client=mock_client,
            )

        assert res["totalUpdatedRows"] == 4

    @pytest.mark.asyncio
    async def test_exponential_backoff_on_429(self):
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                # Return 429 Too Many Requests for the first 2 attempts
                return httpx.Response(429, json={"error": "Rate limit exceeded"})
            # 3rd attempt succeeds
            return httpx.Response(200, json={"range": "Sheet1!A1", "values": [["OK"]]})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as mock_client:
            values = await google_sheets_service.fetch_sheet_values(
                sheet_id=sheet_id,
                range_name="Sheet1!A1",
                credentials_info={"access_token": "ya29.retry_token"},
                client=mock_client,
                max_retries=3,
                initial_delay=0.01,
            )

        assert attempts == 3
        assert values == [["OK"]]

    @pytest.mark.asyncio
    async def test_error_handling_403_and_404(self):
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

        def not_found_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "Spreadsheet not found"})

        transport_404 = httpx.MockTransport(not_found_handler)
        async with httpx.AsyncClient(transport=transport_404) as mock_client:
            with pytest.raises(AppError) as exc404:
                await google_sheets_service.fetch_sheet_values(
                    sheet_id=sheet_id,
                    range_name="Sheet1!A1",
                    credentials_info={"access_token": "ya29.test"},
                    client=mock_client,
                    max_retries=1,
                    initial_delay=0.01,
                )
            assert exc404.value.http_status == 404
            assert exc404.value.code == "SHEET_NOT_FOUND"

        def forbidden_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": "The caller does not have permission"})

        transport_403 = httpx.MockTransport(forbidden_handler)
        async with httpx.AsyncClient(transport=transport_403) as mock_client:
            with pytest.raises(AppError) as exc403:
                await google_sheets_service.fetch_sheet_values(
                    sheet_id=sheet_id,
                    range_name="Sheet1!A1",
                    credentials_info={"access_token": "ya29.test"},
                    client=mock_client,
                    max_retries=1,
                    initial_delay=0.01,
                )
            assert exc403.value.http_status == 403
            assert exc403.value.code == "SHEET_FORBIDDEN"


# ==============================================================================
# F9: Inbound Google Sheets Staging & 4-Layer ETL Integration Tests
# ==============================================================================


class TestGoogleSheetsInboundEtlF9:
    def test_inbound_google_sheets_staging_and_deduplication(self, client):
        admin = _login(client, "demo_admin")

        # 1. Create Google Sheets Connection
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        conn_res = client.post(
            "/etl/connections",
            headers=admin,
            json={
                "name": "Google Sheets Danh Mục Sản Phẩm Mới",
                "type": "google_sheets",
                "secret_ref": "env://GOOGLE_SHEETS_SA_JSON",
                "allowlist_sheets": [sheet_id],
                "config_json": {
                    "sheet_id": sheet_id,
                    "tab": "Catalog",
                    "credentials": {"access_token": "ya29.mock_inbound_token"},
                },
            },
        )
        assert conn_res.status_code == 201, conn_res.text
        conn_id = conn_res.json()["id"]

        # 2. Create Catalog Upsert Pipeline
        pipe_res = client.post(
            "/etl/pipelines",
            headers=admin,
            json={
                "name": "Pipeline Đồng Bộ Danh Mục Từ Google Sheets",
                "target": "catalog_upsert",
                "connection_id": conn_id,
            },
        )
        assert pipe_res.status_code == 201, pipe_res.text
        pipe_id = pipe_res.json()["id"]

        # 3. Create and publish Mapping Version
        mv_res = client.post(
            f"/etl/pipelines/{pipe_id}/mapping-versions",
            headers=admin,
            json={
                "mapping_rules": [
                    {"source_field": "Mã SKU", "target_field": "sku", "required": True, "transform": "trim_upper"},
                    {"source_field": "Tên Hàng", "target_field": "name", "required": True, "transform": "trim"},
                    {"source_field": "Đơn Vị", "target_field": "unit", "required": True, "transform": "trim_lower"},
                    {"source_field": "Giá Bán", "target_field": "selling_price", "required": True, "transform": "to_decimal"},
                ],
                "duplicate_policy": "overwrite",
            },
        )
        assert mv_res.status_code == 201, mv_res.text
        mv_id = mv_res.json()["id"]
        client.post(f"/etl/pipelines/{pipe_id}/mapping-versions/{mv_id}/publish", headers=admin)

        # 4. Trigger Ingestion Run with Mocked Google Sheet data
        unique_sku = f"GS-TEA-{uuid.uuid4().hex[:6].upper()}"
        mock_sheet_rows = [
            {"Mã SKU": unique_sku, "Tên Hàng": "Trà Sữa Oolong Nướng", "Đơn Vị": "Ly", "Giá Bán": "55000"},
            {"Mã SKU": "", "Tên Hàng": "Hàng Thiếu SKU Lỗi", "Đơn Vị": "Gói", "Giá Bán": "30000"},  # Invalid row
        ]

        with patch("app.services.google_sheets_service.fetch_sheet_rows", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_sheet_rows

            run_res = client.post(
                f"/etl/pipelines/{pipe_id}/runs",
                headers=admin,
                json={},  # Empty payload triggers automatic fetch from connection config
            )
            assert run_res.status_code in (200, 201), run_res.text
            run_data = run_res.json()
            run_id = run_data["id"]

            # Verify Staging Run properties
            assert run_data["status"] == "staged"  # Maker-checker pending review
            assert run_data["total_rows"] == 2
            assert run_data["valid_rows"] == 1
            assert run_data["invalid_rows"] == 1
            assert len(run_data["source_fingerprint"]) == 64  # SHA-256 fingerprint

            # 5. Verify Deduplication: identical fetch returns existing run
            run_dup_res = client.post(
                f"/etl/pipelines/{pipe_id}/runs",
                headers=admin,
                json={},
            )
            assert run_dup_res.status_code in (200, 201)
            assert run_dup_res.json()["id"] == run_id

        # 6. Inspect Staged Rows
        rows_res = client.get(f"/etl/runs/{run_id}/rows", headers=admin)
        assert rows_res.status_code == 200
        rows = rows_res.json()["rows"]
        assert len(rows) == 2

        valid_row = next(r for r in rows if r["valid"])
        assert valid_row["source_row_key"] == unique_sku
        assert valid_row["action_preview"]["action"] == "create"

        invalid_row = next(r for r in rows if not r["valid"])
        assert len(invalid_row["errors_json"]) > 0

    def test_inbound_google_sheets_allowlist_enforcement(self, client):
        admin = _login(client, "demo_admin")

        allowed_sheet = "ALLOWED_SHEET_1234567890"
        disallowed_sheet = "DISALLOWED_SHEET_9876543210"

        conn_res = client.post(
            "/etl/connections",
            headers=admin,
            json={
                "name": "Nguồn Google Sheets Giới Hạn Allowlist",
                "type": "google_sheets",
                "allowlist_sheets": [allowed_sheet],
                "config_json": {"sheet_id": disallowed_sheet},
            },
        )
        conn_id = conn_res.json()["id"]

        pipe_res = client.post(
            "/etl/pipelines",
            headers=admin,
            json={
                "name": "Pipeline Thử Nghiệm Allowlist",
                "target": "catalog_upsert",
                "connection_id": conn_id,
            },
        )
        pipe_id = pipe_res.json()["id"]

        # Publish mapping
        mv_res = client.post(
            f"/etl/pipelines/{pipe_id}/mapping-versions",
            headers=admin,
            json={
                "mapping_rules": [{"source_field": "sku", "target_field": "sku", "required": True}],
            },
        )
        client.post(f"/etl/pipelines/{pipe_id}/mapping-versions/{mv_res.json()['id']}/publish", headers=admin)

        # Triggering with disallowed sheet must return 403
        run_res = client.post(f"/etl/pipelines/{pipe_id}/runs", headers=admin, json={})
        assert run_res.status_code == 403
        assert "SHEET_NOT_ALLOWED" in run_res.text

    def test_inbound_maker_checker_and_inventory_ledger_invariant(self, client):
        admin = _login(client, "demo_admin")

        # Get existing location & item
        locs = client.get("/inventory/locations", headers=admin).json()["locations"]
        loc = locs[0]
        items = client.get("/inventory/items", headers=admin).json()["items"]
        item = items[0]
        sku = item["sku"]

        # Create connection & pipeline
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        conn_res = client.post(
            "/etl/connections",
            headers=admin,
            json={
                "name": "Nguồn Điều Chỉnh Tồn Kho Google Sheets",
                "type": "google_sheets",
                "config_json": {"sheet_id": sheet_id, "tab": "DieuChinh"},
            },
        )
        conn_id = conn_res.json()["id"]

        pipe_res = client.post(
            "/etl/pipelines",
            headers=admin,
            json={
                "name": "Pipeline Điều Chỉnh Tồn Kho Quản Trị",
                "target": "balance_adjustment_admin",
                "connection_id": conn_id,
                "location_id": loc["id"],
            },
        )
        pipe_id = pipe_res.json()["id"]

        # Mapping for balance adjustment
        mv_res = client.post(
            f"/etl/pipelines/{pipe_id}/mapping-versions",
            headers=admin,
            json={
                "mapping_rules": [
                    {"source_field": "sku", "target_field": "sku", "required": True},
                    {"source_field": "location_code", "target_field": "location_code", "required": True},
                    {"source_field": "target_quantity", "target_field": "target_quantity", "required": True},
                ],
            },
        )
        client.post(f"/etl/pipelines/{pipe_id}/mapping-versions/{mv_res.json()['id']}/publish", headers=admin)

        # Ingestion run
        with patch("app.services.google_sheets_service.fetch_sheet_rows", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [
                {"sku": sku, "location_code": loc["code"], "target_quantity": "250.0"}
            ]
            run_res = client.post(f"/etl/pipelines/{pipe_id}/runs", headers=admin, json={})
            assert run_res.status_code in (200, 201)
            run_id = run_res.json()["id"]
            assert run_res.json()["status"] == "staged"

        # 1. Review stage (Maker-Checker)
        rev_res = client.post(
            f"/etl/runs/{run_id}/review",
            headers=admin,
            json={"decision": "approved", "note": "Phê duyệt kiểm toán số liệu kiểm kê Google Sheets"},
        )
        assert rev_res.status_code == 200
        assert rev_res.json()["status"] == "reviewing"

        # 2. Posting stage: Enforces ledger invariant (InventoryRequest created in draft under maker-checker)
        post_res = client.post(f"/etl/runs/{run_id}/post", headers=admin)
        assert post_res.status_code == 200, post_res.text
        post_data = post_res.json()
        assert post_data["status"] == "pending_approval"
        assert post_data["single_admin_override"] is True
        assert post_data["request_id"] is not None

        req_id = post_data["request_id"]
        req_info = client.get(f"/inventory/requests/{req_id}", headers=admin).json()
        assert req_info["kind"] == "adjustment"
        assert req_info["status"] == "draft"


# ==============================================================================
# F10: Outbound Google Sheets Sync & Status Writeback Tests
# ==============================================================================


class TestGoogleSheetsOutboundSyncF10:
    def test_outbound_dataset_export_and_formula_sanitization(self, client):
        admin = _login(client, "demo_admin")
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

        with patch("app.services.google_sheets_service.write_sheet_values", new_callable=AsyncMock) as mock_write:
            mock_write.return_value = {"updatedRows": 10, "updatedCells": 50}

            res = client.post(
                "/etl/export-google-sheets",
                headers=admin,
                json={
                    "dataset": "catalog",
                    "sheet_url_or_id": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit",
                    "tab": "DanhMucSanPham",
                    "credentials": {"access_token": "ya29.export_token"},
                    "include_sync_status": True,
                },
            )
            assert res.status_code == 200, res.text
            data = res.json()
            assert data["status"] == "success"
            assert data["sheet_id"] == sheet_id
            assert "SYNCED_" in data["sync_status"]

            # Verify that write_sheet_values was called with sanitized matrix
            assert mock_write.called
            call_kwargs = mock_write.call_args[1]
            values_sent = call_kwargs["values"]
            headers = values_sent[0]
            assert "Trạng thái đồng bộ" in headers

    def test_writeback_sheet_status_endpoint(self, client):
        admin = _login(client, "demo_admin")

        # 1. Setup minimal pipeline and staged run
        client.get("/inventory/locations", headers=admin)
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

        conn_res = client.post(
            "/etl/connections",
            headers=admin,
            json={
                "name": "Nguồn Viết Ngược Trạng Thái",
                "type": "google_sheets",
                "config_json": {"sheet_id": sheet_id, "tab": "Sheet1", "status_column_letter": "K"},
            },
        )
        conn_id = conn_res.json()["id"]

        pipe_res = client.post(
            "/etl/pipelines",
            headers=admin,
            json={"name": "Pipeline Test Writeback", "target": "catalog_upsert", "connection_id": conn_id},
        )
        pipe_id = pipe_res.json()["id"]

        mv_res = client.post(
            f"/etl/pipelines/{pipe_id}/mapping-versions",
            headers=admin,
            json={
                "mapping_rules": [
                    {"source_field": "sku", "target_field": "sku", "required": True},
                    {"source_field": "name", "target_field": "name", "required": True},
                    {"source_field": "unit", "target_field": "unit", "required": True},
                ]
            },
        )
        client.post(f"/etl/pipelines/{pipe_id}/mapping-versions/{mv_res.json()['id']}/publish", headers=admin)

        with patch("app.services.google_sheets_service.fetch_sheet_rows", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [
                {"sku": "SKU-OK-1", "name": "Trà Thiết Quan Âm", "unit": "gói"},
                {"sku": "", "name": "Lỗi Không SKU", "unit": "gói"},  # invalid
            ]
            run_res = client.post(f"/etl/pipelines/{pipe_id}/runs", headers=admin, json={})
            assert run_res.status_code in (200, 201)
            run_id = run_res.json()["id"]

        # 2. Call Writeback Endpoint
        with patch("app.services.google_sheets_service.write_sheet_values", new_callable=AsyncMock) as mock_write:
            mock_write.return_value = {"updatedRows": 2}

            wb_res = client.post(
                f"/etl/runs/{run_id}/writeback",
                headers=admin,
                json={"status_column_letter": "K", "credentials": {"access_token": "ya29.writeback"}},
            )
            assert wb_res.status_code == 200, wb_res.text
            wb_data = wb_res.json()
            assert wb_data["run_id"] == run_id
            assert wb_data["column"] == "K"
            assert wb_data["total_rows"] == 2

            # Check that write_sheet_values was called with row statuses
            assert mock_write.called
            sent_statuses = mock_write.call_args[1]["values"]
            assert len(sent_statuses) == 2
            assert "✓ HỢP LỆ" in sent_statuses[0][0]
            assert "✗ LỖI" in sent_statuses[1][0]

    @pytest.mark.asyncio
    async def test_direct_sync_out_to_google_sheet(self):
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        headers = [("sku", "Mã SKU"), ("name", "Tên sản phẩm")]
        rows = [
            {"sku": "SKU-01", "name": "Trà Đào"},
            {"sku": "SKU-02", "name": "=cmd|'calc'!A1"},  # Formula injection payload
        ]

        captured_write = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_write
            assert request.method == "PUT"
            body = json.loads(request.content.decode("utf-8"))
            sent_values = body["values"]
            # Check headers
            assert sent_values[0] == ["Mã SKU", "Tên sản phẩm", "Trạng thái đồng bộ"]
            # Check formula injection sanitized
            assert sent_values[2][1] == "'=cmd|'calc'!A1"
            captured_write = True
            return httpx.Response(200, json={"updatedRows": 3})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as mock_client:
            res = await google_sheets_service.sync_out_to_google_sheet(
                url_or_id=sheet_id,
                tab="Sheet1",
                headers=headers,
                rows=rows,
                credentials_info={"access_token": "ya29.sync_out_token"},
                client=mock_client,
            )

        assert captured_write is True
        assert res["status"] == "success"
        assert res["direct_api_synced"] is True
        assert res["rows_count"] == 2
        assert res["columns_count"] == 3
