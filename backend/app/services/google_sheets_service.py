"""Google Sheets Integration Service.

Hỗ trợ đồng bộ hai chiều với Google Sheets:
  - Trích xuất Sheet ID từ URL Google Sheets bất kỳ.
  - Đọc dữ liệu từ Google Sheets qua Google Sheets API v4 hoặc Google Visualization CSV export (hỗ trợ sheet công khai không cần API key).
  - Ghi dữ liệu lên Google Sheets qua API hoặc Apps Script Webhook.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

import httpx

from app.api.errors import AppError
from app.api.observability import record_external_dependency
from app.config import settings

# Regex bắt Sheet ID: 10 đến 128 ký tự chữ, số, gạch nối, gạch dưới
_SHEET_ID_RE = re.compile(r"^[A-Za-z0-9-_]{10,128}$")
_SHEET_URL_PATTERN = re.compile(r"/spreadsheets/d/(?:e/)?([A-Za-z0-9-_]+)")


def extract_sheet_id(url_or_id: str) -> str:
    """Trích xuất Sheet ID từ chuỗi URL Google Sheets hoặc ID thuần."""
    raw = (url_or_id or "").strip()
    if not raw:
        raise AppError(422, "INVALID_SHEET_INPUT", "Đường dẫn hoặc ID Google Sheet không được để trống")

    # Kiểm tra xem có phải URL Google Sheets không
    match = _SHEET_URL_PATTERN.search(raw)
    if match:
        return match.group(1)

    # Nếu truyền trực tiếp ID
    if _SHEET_ID_RE.match(raw):
        return raw

    raise AppError(
        422,
        "INVALID_SHEET_ID",
        "Không nhận diện được Google Sheet ID hợp lệ từ đường dẫn được cung cấp",
    )


async def fetch_sheet_rows(
    url_or_id: str,
    tab: str = "Sheet1",
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Đọc các dòng dữ liệu từ Google Sheet.

    Thử nghiệm theo 2 phương thức:
    1. Nếu có API key (từ tham số hoặc settings.google_sheets_api_key): gọi Google Sheets v4 API.
    2. Fallback: gọi Google Visualization endpoint (tqx=out:csv) hỗ trợ các trang tính được chia sẻ công khai.
    """
    sheet_id = extract_sheet_id(url_or_id)
    key = api_key or getattr(settings, "google_sheets_api_key", None) or ""

    # Cách 1: Google Sheets API v4 nếu có API Key
    if key:
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{tab}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params={"key": key, "majorDimension": "ROWS"})
            if resp.status_code == 200:
                record_external_dependency("google_sheets", "success")
                values = resp.json().get("values", [])
                if not values:
                    return []
                header, *body = values
                return [dict(zip(header, r, strict=False)) for r in body]
        except Exception:
            # Fallback sang cách 2 nếu API key lỗi hoặc quota
            pass

    # Cách 2: Public Google Visualization CSV export endpoint
    gviz_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
    params = {"tqx": "out:csv", "sheet": tab}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(gviz_url, params=params)
    except httpx.HTTPError as e:
        record_external_dependency("google_sheets", "unavailable")
        raise AppError(503, "SHEETS_UNAVAILABLE", f"Không kết nối được Google Sheets: {e}") from None

    if resp.status_code >= 400:
        record_external_dependency("google_sheets", "http_error")
        raise AppError(
            resp.status_code if resp.status_code in (403, 404) else 502,
            "SHEETS_READ_FAILED",
            f"Không thể tải Google Sheet (HTTP {resp.status_code}). Đảm bảo trang tính đã bật quyền 'Bất kỳ ai có đường liên kết đều có thể xem'.",
        )

    record_external_dependency("google_sheets", "success")
    text = resp.text
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return []
        rows = [dict(r) for r in reader]
        return rows
    except Exception as e:
        raise AppError(422, "SHEETS_PARSE_ERROR", f"Không phân tích được bảng tính Google Sheets: {e}") from None


async def sync_out_to_google_sheet(
    url_or_id: str,
    tab: str,
    headers: list[tuple[str, str]],
    rows: list[dict[str, Any]],
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """Đồng bộ dữ liệu từ trong ra Google Sheet.

    Nếu có webhook_url (Apps Script Webhook): gửi payload HTTP POST chứa mảng dữ liệu.
    Đồng thời trả về URL trực tiếp tới Google Sheet cho người dùng.
    """
    sheet_id = extract_sheet_id(url_or_id)
    view_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

    matrix_data: list[list[Any]] = []
    # Header row
    matrix_data.append([label for _, label in headers])
    # Data rows
    for r in rows:
        matrix_data.append([r.get(key, "") for key, _ in headers])

    if webhook_url:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(
                    webhook_url,
                    json={
                        "sheet_id": sheet_id,
                        "tab": tab,
                        "rows": matrix_data,
                    },
                )
            if res.status_code >= 400:
                raise AppError(502, "WEBHOOK_FAILED", f"Apps Script Webhook trả mã lỗi: {res.status_code}")
        except httpx.HTTPError as e:
            raise AppError(502, "WEBHOOK_FAILED", f"Lỗi gửi dữ liệu tới Apps Script: {e}") from None

    return {
        "status": "success",
        "sheet_id": sheet_id,
        "tab": tab,
        "sheet_url": view_url,
        "rows_count": len(rows),
        "columns_count": len(headers),
    }
