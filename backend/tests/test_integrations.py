"""Tests for /integrations/* and /integration-runs/* endpoints (Track B)."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import time
import uuid

import httpx

DEMO_PASSWORD = "DemoPass123!"


def _login(client, username: str) -> dict[str, str]:
    r = client.post(
        "/auth/login", data={"username": username, "password": DEMO_PASSWORD}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed_sku_and_loc(client, headers: dict[str, str]) -> tuple[str, str]:
    items = client.get("/inventory/items", headers=headers).json()["items"]
    locs = client.get("/inventory/locations", headers=headers).json()["locations"]
    sku = next(i["sku"] for i in items if not i.get("tracked_serial"))
    loc_code = locs[0]["code"]
    return sku, loc_code


class TestIntegrationsUploadAndConfirm:
    def test_csv_upload_with_invalid_row_isolates_errors_and_blocks_confirm(
        self, client
    ):
        """G1: Dòng lỗi không chặn dòng hợp lệ lúc preview, nhưng chặn confirm."""
        h = _login(client, "demo_maker")
        sku, loc_code = _seed_sku_and_loc(client, h)
        unique_tag = uuid.uuid4().hex[:8]
        csv_bytes = (
            "sku,location_code,quantity,source_row_key\n"
            f"{sku},{loc_code},5,valid-{unique_tag}\n"
            f"INVALID_SKU_{unique_tag},{loc_code},-3,bad-{unique_tag}\n"
        ).encode()

        up = client.post(
            "/integrations/uploads",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            files={"file": ("mixed.csv", io.BytesIO(csv_bytes), "text/csv")},
            data={"type": "csv"},
        )
        assert up.status_code == 200, up.text
        body = up.json()
        assert body["valid_count"] == 1
        assert body["invalid_count"] == 1
        run_id = body["run_id"]

        # Preview via both canonical and alias routes
        prev1 = client.get(f"/integrations/runs/{run_id}/preview", headers=h)
        prev2 = client.get(f"/integration-runs/{run_id}/staging", headers=h)
        assert prev1.status_code == 200 and prev2.status_code == 200
        assert prev1.json()["invalid_count"] == 1
        assert prev2.json()["valid_count"] == 1

        # Confirm must reject because invalid_count > 0
        conf = client.post(
            f"/integrations/runs/{run_id}/confirm",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert conf.status_code == 409
        assert conf.json()["error"]["code"] == "CONFIRM_HAS_ERRORS"

    def test_json_upload_dedup_and_confirm_creates_draft_not_ledger(self, client):
        """Upload hợp lệ -> confirm tạo InventoryRequest draft, dedup theo fingerprint."""
        h = _login(client, "demo_maker")
        sku, loc_code = _seed_sku_and_loc(client, h)
        tag = uuid.uuid4().hex[:8]
        payload_bytes = json.dumps(
            {
                "rows": [
                    {
                        "sku": sku,
                        "location_code": loc_code,
                        "quantity": 4,
                        "source_row_key": f"json-{tag}",
                    }
                ]
            }
        ).encode("utf-8")

        up1 = client.post(
            "/integrations/uploads",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            files={
                "file": ("items.json", io.BytesIO(payload_bytes), "application/json")
            },
            data={"type": "json"},
        )
        assert up1.status_code == 200, up1.text
        b1 = up1.json()
        assert b1["deduplicated"] is False
        assert b1["valid_count"] == 1
        assert b1["invalid_count"] == 0
        run_id = b1["run_id"]

        # Re-uploading identical content deduplicates by fingerprint
        up2 = client.post(
            "/integrations/uploads",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            files={
                "file": ("items.json", io.BytesIO(payload_bytes), "application/json")
            },
            data={"type": "json"},
        )
        assert up2.status_code == 200
        assert up2.json()["deduplicated"] is True
        assert up2.json()["run_id"] == run_id

        # Movements before confirm
        mv_before = len(
            client.get("/inventory/movements", headers=h).json().get("movements", [])
        )

        # Confirm creates draft request(s) and replays on same Idempotency-Key
        idem_key = str(uuid.uuid4())
        c1 = client.post(
            f"/integration-runs/{run_id}/confirm",
            headers={**h, "Idempotency-Key": idem_key},
        )
        assert c1.status_code == 200, c1.text
        cb1 = c1.json()
        assert cb1["status"] == "confirmed"
        assert len(cb1["draft_requests"]) == 1

        c_replay = client.post(
            f"/integration-runs/{run_id}/confirm",
            headers={**h, "Idempotency-Key": idem_key},
        )
        assert c_replay.status_code == 200
        assert c_replay.json()["draft_requests"] == cb1["draft_requests"]

        # Confirm with a different Idempotency-Key returns 409 STATE_CONFLICT
        c_dup = client.post(
            f"/integration-runs/{run_id}/confirm",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert c_dup.status_code == 409
        assert c_dup.json()["error"]["code"] == "STATE_CONFLICT"

        # No movement was written directly to ledger
        mv_after = len(
            client.get("/inventory/movements", headers=h).json().get("movements", [])
        )
        assert mv_after == mv_before


class TestGoogleSheetsAndWebhooks:
    def test_google_sheets_fetch_mocked_and_validation(self, client, monkeypatch):
        from app.config import settings

        h = _login(client, "demo_maker")
        sku, loc_code = _seed_sku_and_loc(client, h)

        # Invalid sheet_id -> 422 INVALID_SHEET_ID
        bad = client.post(
            "/integrations/google-sheets/fetch",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            json={"sheet_id": "bad!id", "tab": "Sheet1"},
        )
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "INVALID_SHEET_ID"

        # Mock API key + httpx response
        monkeypatch.setattr(settings, "google_sheets_api_key", "fake-sheets-key")
        tag = uuid.uuid4().hex[:8]

        class _FakeResp:
            status_code = 200
            text = "OK"

            def json(self):
                return {
                    "values": [
                        ["sku", "location_code", "quantity", "source_row_key"],
                        [sku, loc_code, "9", f"sheet-{tag}"],
                    ]
                }

        class _FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, url, params=None):
                return _FakeResp()

        monkeypatch.setattr(
            "app.features.integrations.routes.httpx.AsyncClient", _FakeAsyncClient
        )
        ok = client.post(
            "/integrations/google-sheets/fetch",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "sheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                "tab": "Sheet1",
            },
        )
        assert ok.status_code == 200, ok.text
        obody = ok.json()
        assert obody["valid_count"] == 1
        assert obody["invalid_count"] == 0
        assert obody["status"] == "staged"

    def test_apps_script_webhook_hmac_replay_and_dedup(self, client, monkeypatch):
        from app.config import settings

        secret = "test-webhook-hmac-secret"
        monkeypatch.setattr(settings, "apps_script_webhook_secret", secret)

        h = _login(client, "demo_maker")
        sku, loc_code = _seed_sku_and_loc(client, h)

        # Create an apps_script connection
        conn_r = client.post(
            "/integrations/connections",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            json={"type": "apps_script", "name": "Test Apps Script"},
        )
        assert conn_r.status_code == 201, conn_r.text
        conn_id = conn_r.json()["id"]

        event_id = f"ev-{uuid.uuid4().hex[:10]}"
        raw_payload = json.dumps(
            {
                "event_id": event_id,
                "rows": [
                    {
                        "sku": sku,
                        "location_code": loc_code,
                        "quantity": 3,
                        "source_row_key": f"wh-{event_id}",
                    }
                ],
            }
        ).encode("utf-8")

        now_ts = str(int(time.time()))
        valid_sig = hmac.new(
            secret.encode(), f"{now_ts}.".encode() + raw_payload, hashlib.sha256
        ).hexdigest()

        # 1. Bad signature -> 401 WEBHOOK_BAD_SIGNATURE
        r_bad_sig = client.post(
            f"/integrations/webhooks/{conn_id}",
            content=raw_payload,
            headers={
                "Content-Type": "application/json",
                "X-BankOps-Timestamp": now_ts,
                "X-BankOps-Signature": "0" * 64,
            },
        )
        assert r_bad_sig.status_code == 401
        assert r_bad_sig.json()["error"]["code"] == "WEBHOOK_BAD_SIGNATURE"

        # 2. Expired timestamp (>300s) -> 401 WEBHOOK_REPLAY
        old_ts = str(int(time.time()) - 600)
        old_sig = hmac.new(
            secret.encode(), f"{old_ts}.".encode() + raw_payload, hashlib.sha256
        ).hexdigest()
        r_replay = client.post(
            f"/integrations/webhooks/{conn_id}",
            content=raw_payload,
            headers={
                "Content-Type": "application/json",
                "X-BankOps-Timestamp": old_ts,
                "X-BankOps-Signature": old_sig,
            },
        )
        assert r_replay.status_code == 401
        assert r_replay.json()["error"]["code"] == "WEBHOOK_REPLAY"

        # 3. Valid webhook -> 200 staged
        r_ok = client.post(
            f"/integrations/webhooks/{conn_id}",
            content=raw_payload,
            headers={
                "Content-Type": "application/json",
                "X-BankOps-Timestamp": now_ts,
                "X-BankOps-Signature": valid_sig,
            },
        )
        assert r_ok.status_code == 200, r_ok.text
        assert r_ok.json()["deduplicated"] is False
        run_id = r_ok.json()["run_id"]

        # 4. Duplicate webhook push -> deduplicated=True
        r_dup = client.post(
            f"/integrations/webhooks/{conn_id}",
            content=raw_payload,
            headers={
                "Content-Type": "application/json",
                "X-BankOps-Timestamp": now_ts,
                "X-BankOps-Signature": valid_sig,
            },
        )
        assert r_dup.status_code == 200
        assert r_dup.json()["deduplicated"] is True
        assert r_dup.json()["run_id"] == run_id


class TestConnectionManagement:
    """Tests for GET /connections/{id}, POST /connections/{id}/test, POST /connections/{id}/schema."""

    def test_get_connection_detail(self, client, monkeypatch):
        h = _login(client, "demo_maker")
        sku, loc_code = _seed_sku_and_loc(client, h)

        # Create a connection
        conn_r = client.post(
            "/integrations/connections",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            json={"type": "apps_script", "name": "Test Conn"},
        )
        assert conn_r.status_code == 201, conn_r.text
        conn_id = conn_r.json()["id"]
        assert conn_r.json()["status"] == "pending_test"

        # GET connection detail
        detail = client.get(f"/integrations/connections/{conn_id}", headers=h)
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["id"] == conn_id
        assert body["type"] == "apps_script"
        assert body["name"] == "Test Conn"
        assert body["status"] == "pending_test"
        assert "last_tested_at" in body
        assert "last_error" in body
        assert "schema" in body

    def test_get_connection_not_found(self, client):
        h = _login(client, "demo_maker")
        r = client.get(f"/integrations/connections/{uuid.uuid4()}", headers=h)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NOT_FOUND"

    def test_get_connection_invalid_uuid(self, client):
        h = _login(client, "demo_maker")
        r = client.get("/integrations/connections/not-a-uuid", headers=h)
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INVALID_UUID"

    def test_test_connection_missing_api_key(self, monkeypatch, client):
        h = _login(client, "demo_maker")
        monkeypatch.setattr("app.config.settings.google_sheets_api_key", "")

        conn_r = client.post(
            "/integrations/connections",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "type": "google_sheets",
                "name": "Sheets Conn",
                "config": {"sheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"},
            },
        )
        assert conn_r.status_code == 201
        conn_id = conn_r.json()["id"]

        r = client.post(
            f"/integrations/connections/{conn_id}/test",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is False
        assert body["status"] == "error"
        assert "GOOGLE_SHEETS_API_KEY" in body["error"]

    def test_test_connection_invalid_sheet_id(self, client, monkeypatch):
        from app.config import settings

        h = _login(client, "demo_maker")
        monkeypatch.setattr(settings, "google_sheets_api_key", "fake-key")

        conn_r = client.post(
            "/integrations/connections",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "type": "google_sheets",
                "name": "Bad Sheet",
                "config": {"sheet_id": "bad!id"},
            },
        )
        conn_id = conn_r.json()["id"]

        r = client.post(
            f"/integrations/connections/{conn_id}/test",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["error"] == "INVALID_SHEET_ID"

    def test_test_connection_network_error(self, monkeypatch, client):
        from app.config import settings

        h = _login(client, "demo_maker")
        monkeypatch.setattr(settings, "google_sheets_api_key", "fake-key")

        class _RaiseHTTPError:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, url, params=None):
                raise httpx.ConnectError("refused")

        monkeypatch.setattr(
            "app.features.integrations.routes.httpx.AsyncClient", _RaiseHTTPError
        )

        conn_r = client.post(
            "/integrations/connections",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "type": "google_sheets",
                "name": "Net Err",
                "config": {"sheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"},
            },
        )
        conn_id = conn_r.json()["id"]

        r = client.post(
            f"/integrations/connections/{conn_id}/test",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["status"] == "error"
        assert "Network error" in body["error"]

    def test_test_connection_success(self, monkeypatch, client):
        from app.config import settings

        h = _login(client, "demo_maker")
        monkeypatch.setattr(settings, "google_sheets_api_key", "fake-key")

        class _FakeResp:
            status_code = 200
            text = "OK"

            def json(self):
                return {"spreadsheetId": "test123"}

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, url, params=None):
                return _FakeResp()

        monkeypatch.setattr(
            "app.features.integrations.routes.httpx.AsyncClient", _FakeClient
        )

        conn_r = client.post(
            "/integrations/connections",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "type": "google_sheets",
                "name": "OK Sheet",
                "config": {"sheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"},
            },
        )
        conn_id = conn_r.json()["id"]

        r = client.post(
            f"/integrations/connections/{conn_id}/test",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["status"] == "connected"
        assert body["error"] is None

        detail = client.get(f"/integrations/connections/{conn_id}", headers=h)
        assert detail.json()["last_tested_at"] is not None
        assert detail.json()["status"] == "connected"

    def test_get_run_detail(self, client):
        """GET /integrations/runs/{id} trả về thông tin chi tiết run."""
        import io

        h = _login(client, "demo_maker")
        sku, loc_code = _seed_sku_and_loc(client, h)
        payload_bytes = json.dumps(
            {
                "rows": [
                    {
                        "sku": sku,
                        "location_code": loc_code,
                        "quantity": 4,
                        "source_row_key": "run-detail-test",
                    }
                ]
            }
        ).encode()

        up = client.post(
            "/integrations/uploads",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            files={
                "file": ("items.json", io.BytesIO(payload_bytes), "application/json")
            },
            data={"type": "json"},
        )
        assert up.status_code == 200, up.text
        run_id = up.json()["run_id"]

        r = client.get(f"/integrations/runs/{run_id}", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["run_id"] == run_id
        assert body["status"] == "staged"
        assert body["phase"] == "staged"
        assert body["valid_count"] == 1
        assert body["invalid_count"] == 0
        assert body["source_fingerprint"] is not None
        assert len(body["rows"]) == 1

    def test_get_run_not_found(self, client):
        h = _login(client, "demo_maker")
        r = client.get(f"/integrations/runs/{uuid.uuid4()}", headers=h)
        assert r.status_code == 404

    def test_connection_schema_json_upload(self, client):
        """POST /connections/{id}/schema với json_upload trả về columns từ sample row."""
        h = _login(client, "demo_maker")

        conn_r = client.post(
            "/integrations/connections",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            json={"type": "csv_upload", "name": "CSV Schema Test"},
        )
        conn_id = conn_r.json()["id"]

        r = client.post(
            f"/integrations/connections/{conn_id}/schema",
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            json={"rows": [{"sku": "ABC", "location_code": "WH1", "quantity": 5}]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["schema"]) == 3
        names = [c["name"] for c in body["schema"]]
        assert "sku" in names and "location_code" in names and "quantity" in names
