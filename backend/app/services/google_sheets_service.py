"""Google Sheets Integration Service (Milestone M3: F8, F9, F10).

Dịch vụ tích hợp Google Sheets API v4 bất đồng bộ (Pure Async):
  - Xác thực linh hoạt qua Service Account JSON, OAuth 2.0 Credentials hoặc API Key.
  - Hỗ trợ đầy đủ các thao tác đọc và ghi trực tiếp (fetch_sheet_values, write_sheet_values, batch_update_sheet_values).
  - Tự động thử lại với Exponential Backoff & Jitter khi gặp HTTP 429 (Rate Limit) hoặc 503.
  - Bảo vệ chống Spreadsheet Formula Injection (CWE-1236) trên toàn bộ dữ liệu ghi.
  - Phản hồi trạng thái xử lý (_sync_status) hai chiều trực tiếp lên từng hàng của Google Sheet.
  - Tương thích ngược với Google Apps Script Webhook và Google Visualization CSV export.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import random
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import credentials as oauth_credentials
from google.oauth2 import service_account

from app.api.errors import AppError
from app.api.observability import record_external_dependency
from app.config import settings
from app.services.export_engine import sanitize_cell_value

# Scopes chuẩn cho Google Sheets & Google Drive
GOOGLE_SHEETS_SCOPES: list[str] = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

SHEETS_API_BASE: str = "https://sheets.googleapis.com/v4/spreadsheets"

# Regex nhận diện Google Sheet ID: 10 đến 128 ký tự chữ, số, gạch nối, gạch dưới
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


def column_index_to_letter(col_idx: int) -> str:
    """Chuyển đổi chỉ số cột dạng số (1-based) thành chữ cái Google Sheets (1 -> A, 26 -> Z, 27 -> AA)."""
    if col_idx < 1:
        raise ValueError("Chỉ số cột phải >= 1")
    letters: list[str] = []
    while col_idx > 0:
        col_idx, rem = divmod(col_idx - 1, 26)
        letters.append(chr(65 + rem))
    return "".join(reversed(letters))


def _format_range(tab: str, cell_range: str | None = None) -> str:
    """Định dạng tên dải ô kèm tên tab có dấu hoặc khoảng trắng chuẩn Sheets API."""
    tab_clean = tab.strip()
    if "!" in tab_clean:
        return tab_clean
    # Thoát ký tự nháy đơn trong tên tab
    escaped = tab_clean.replace("'", "''")
    if cell_range:
        return f"'{escaped}'!{cell_range.strip()}"
    return f"'{escaped}'"


def resolve_credentials(credentials_info: dict[str, Any] | str | None = None) -> dict[str, Any] | str | None:
    """Tìm nạp thông tin xác thực từ tham số, biến môi trường hoặc cấu hình."""
    if credentials_info:
        return credentials_info

    # 1. Kiểm tra cấu hình env GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON
    env_sa = os.environ.get("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON")
    if env_sa and env_sa.strip():
        return env_sa.strip()

    # 2. Kiểm tra biến môi trường GOOGLE_APPLICATION_CREDENTIALS
    env_app_creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_app_creds and os.path.exists(env_app_creds):
        try:
            with open(env_app_creds, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return None


async def get_authorization_header(
    credentials_info: dict[str, Any] | str | None = None,
) -> str | None:
    """Khởi tạo hoặc làm mới Bearer Token từ Service Account JSON hoặc OAuth credentials."""
    resolved = resolve_credentials(credentials_info)
    if not resolved:
        return None

    # Trường hợp chuỗi token hoặc JSON string
    if isinstance(resolved, str):
        trimmed = resolved.strip()
        if trimmed.startswith("{"):
            try:
                resolved = json.loads(trimmed)
            except Exception as e:
                raise AppError(422, "INVALID_CREDENTIALS", f"Không thể phân tích chuỗi JSON credentials: {e}") from None
        elif trimmed.startswith("Bearer "):
            return trimmed
        else:
            return f"Bearer {trimmed}"

    if isinstance(resolved, dict):
        # A. Có sẵn access_token trực tiếp
        if "access_token" in resolved or "token" in resolved:
            tok = resolved.get("access_token") or resolved.get("token")
            if not resolved.get("private_key") and not resolved.get("refresh_token"):
                return f"Bearer {tok}"

        # B. Service Account JSON dict
        if resolved.get("type") == "service_account" or "private_key" in resolved:
            try:
                creds = service_account.Credentials.from_service_account_info(
                    resolved, scopes=GOOGLE_SHEETS_SCOPES
                )
                if resolved.get("token"):
                    creds.token = resolved["token"]
                elif not creds.valid or not creds.token:
                    await asyncio.to_thread(creds.refresh, GoogleAuthRequest())
                return f"Bearer {creds.token}"
            except Exception as e:
                raise AppError(401, "INVALID_SERVICE_ACCOUNT", f"Xác thực Service Account thất bại: {e}") from None

        # C. OAuth 2.0 Credentials dict
        if "refresh_token" in resolved:
            try:
                creds = oauth_credentials.Credentials(
                    token=resolved.get("token") or resolved.get("access_token"),
                    refresh_token=resolved.get("refresh_token"),
                    token_uri=resolved.get("token_uri", "https://oauth2.googleapis.com/token"),
                    client_id=resolved.get("client_id"),
                    client_secret=resolved.get("client_secret"),
                    scopes=GOOGLE_SHEETS_SCOPES,
                )
                if not creds.valid or not creds.token:
                    await asyncio.to_thread(creds.refresh, GoogleAuthRequest())
                return f"Bearer {creds.token}"
            except Exception as e:
                raise AppError(401, "INVALID_OAUTH_CREDENTIALS", f"Xác thực OAuth 2.0 thất bại: {e}") from None

        for k in ("bearer_token", "jwt", "auth_token"):
            if k in resolved:
                return f"Bearer {resolved[k]}"

    return None


async def _request_with_retry(
    method: str,
    url: str,
    client: httpx.AsyncClient | None = None,
    max_retries: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    **kwargs: Any,
) -> httpx.Response:
    """Thực thi HTTP request với cơ chế Exponential Backoff & Jitter khi bị giới hạn hạn ngạch (429/503)."""
    attempt = 0
    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        close_client = True

    try:
        while True:
            try:
                resp = await client.request(method, url, **kwargs)
                if resp.status_code in (429, 503) and attempt < max_retries:
                    attempt += 1
                    delay = min(10.0, initial_delay * (backoff_factor ** (attempt - 1))) + random.uniform(0.01, 0.05)
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass
                    await asyncio.sleep(delay)
                    continue
                return resp
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt < max_retries:
                    attempt += 1
                    delay = min(10.0, initial_delay * (backoff_factor ** (attempt - 1))) + random.uniform(0.01, 0.05)
                    await asyncio.sleep(delay)
                    continue
                record_external_dependency("google_sheets", "unavailable")
                raise AppError(503, "SHEETS_UNAVAILABLE", f"Không kết nối được Google Sheets: {exc}") from None
    finally:
        if close_client:
            await client.aclose()


# --------------------------------------------------------------------------
# Feature F8: Pure Async Google Sheets API v4 Core Methods
# --------------------------------------------------------------------------


async def fetch_sheet_values(
    sheet_id: str,
    range_name: str,
    credentials_info: dict[str, Any] | str | None = None,
    api_key: str | None = None,
    client: httpx.AsyncClient | None = None,
    max_retries: int = 3,
    initial_delay: float = 0.5,
) -> list[list[Any]]:
    """Đọc dữ liệu ma trận các ô từ Google Sheet qua Sheets API v4 (spreadsheets.values.get)."""
    clean_id = extract_sheet_id(sheet_id)
    quoted_range = quote(range_name, safe="!:")
    url = f"{SHEETS_API_BASE}/{clean_id}/values/{quoted_range}"

    headers: dict[str, str] = {}
    params: dict[str, str] = {"majorDimension": "ROWS"}

    auth_header = await get_authorization_header(credentials_info)
    if auth_header:
        headers["Authorization"] = auth_header
    else:
        key = api_key or getattr(settings, "google_sheets_api_key", None)
        if key:
            params["key"] = key

    resp = await _request_with_retry(
        "GET",
        url,
        client=client,
        max_retries=max_retries,
        initial_delay=initial_delay,
        headers=headers,
        params=params,
    )

    if resp.status_code == 200:
        record_external_dependency("google_sheets", "success")
        return resp.json().get("values", [])
    elif resp.status_code == 404:
        record_external_dependency("google_sheets", "http_error")
        raise AppError(404, "SHEET_NOT_FOUND", f"Không tìm thấy Google Sheet '{clean_id}' hoặc dải ô '{range_name}' (HTTP 404).")
    elif resp.status_code == 403:
        record_external_dependency("google_sheets", "http_error")
        raise AppError(
            403,
            "SHEET_FORBIDDEN",
            "Không có quyền truy cập Google Sheet. Vui lòng chia sẻ bảng tính với tài khoản Service Account.",
        )
    elif resp.status_code == 429:
        record_external_dependency("google_sheets", "rate_limited")
        raise AppError(429, "SHEET_RATE_LIMITED", "Google Sheets API bị giới hạn hạn ngạch (HTTP 429). Vui lòng thử lại sau.")
    else:
        record_external_dependency("google_sheets", "http_error")
        raise AppError(resp.status_code, "SHEET_API_ERROR", f"Lỗi Google Sheets API khi đọc (HTTP {resp.status_code}): {resp.text}")


async def write_sheet_values(
    sheet_id: str,
    range_name: str,
    values: list[list[Any]],
    credentials_info: dict[str, Any] | str | None = None,
    value_input_option: str = "USER_ENTERED",
    client: httpx.AsyncClient | None = None,
    max_retries: int = 3,
    initial_delay: float = 0.5,
) -> dict[str, Any]:
    """Ghi đè dữ liệu lên một dải ô Google Sheet qua Sheets API v4 (spreadsheets.values.update).

    Tự động áp dụng khử Formula Injection (CWE-1236) trên toàn bộ ô dữ liệu.
    """
    clean_id = extract_sheet_id(sheet_id)
    quoted_range = quote(range_name, safe="!:")
    url = f"{SHEETS_API_BASE}/{clean_id}/values/{quoted_range}"

    headers: dict[str, str] = {"Content-Type": "application/json"}
    auth_header = await get_authorization_header(credentials_info)
    if not auth_header:
        raise AppError(401, "UNAUTHORIZED", "Cần cung cấp Service Account hoặc OAuth token để ghi vào Google Sheet.")
    headers["Authorization"] = auth_header

    # Sanitization (CWE-1236)
    sanitized_values = [[sanitize_cell_value(c) for c in row] for row in values]
    body = {
        "range": range_name,
        "majorDimension": "ROWS",
        "values": sanitized_values,
    }

    resp = await _request_with_retry(
        "PUT",
        url,
        client=client,
        max_retries=max_retries,
        initial_delay=initial_delay,
        headers=headers,
        params={"valueInputOption": value_input_option},
        json=body,
    )

    if resp.status_code == 200:
        record_external_dependency("google_sheets", "success")
        return resp.json()
    elif resp.status_code == 404:
        record_external_dependency("google_sheets", "http_error")
        raise AppError(404, "SHEET_NOT_FOUND", f"Không tìm thấy Google Sheet '{clean_id}' hoặc dải ô '{range_name}' (HTTP 404).")
    elif resp.status_code == 403:
        record_external_dependency("google_sheets", "http_error")
        raise AppError(
            403,
            "SHEET_FORBIDDEN",
            "Không có quyền ghi vào Google Sheet. Đảm bảo Service Account đã được cấp quyền Editor (Chỉnh sửa).",
        )
    elif resp.status_code == 429:
        record_external_dependency("google_sheets", "rate_limited")
        raise AppError(429, "SHEET_RATE_LIMITED", "Google Sheets API bị giới hạn hạn ngạch khi ghi (HTTP 429).")
    else:
        record_external_dependency("google_sheets", "http_error")
        raise AppError(resp.status_code, "SHEET_API_ERROR", f"Lỗi Google Sheets API khi ghi (HTTP {resp.status_code}): {resp.text}")


async def batch_update_sheet_values(
    sheet_id: str,
    data: list[dict[str, Any]],
    credentials_info: dict[str, Any] | str | None = None,
    value_input_option: str = "USER_ENTERED",
    client: httpx.AsyncClient | None = None,
    max_retries: int = 3,
    initial_delay: float = 0.5,
) -> dict[str, Any]:
    """Cập nhật hàng loạt nhiều dải ô trên Google Sheet qua Sheets API v4 (spreadsheets.values.batchUpdate)."""
    clean_id = extract_sheet_id(sheet_id)
    url = f"{SHEETS_API_BASE}/{clean_id}/values:batchUpdate"

    headers: dict[str, str] = {"Content-Type": "application/json"}
    auth_header = await get_authorization_header(credentials_info)
    if not auth_header:
        raise AppError(401, "UNAUTHORIZED", "Cần cung cấp Service Account hoặc OAuth token để cập nhật Google Sheet.")
    headers["Authorization"] = auth_header

    # Chuẩn hóa và khử injection cho từng phần tử trong data
    sanitized_data: list[dict[str, Any]] = []
    for item in data:
        rng = item.get("range", "")
        raw_vals = item.get("values", [])
        sanitized_vals = [[sanitize_cell_value(c) for c in row] for row in raw_vals]
        sanitized_data.append({
            "range": rng,
            "majorDimension": item.get("majorDimension", "ROWS"),
            "values": sanitized_vals,
        })

    body = {
        "valueInputOption": value_input_option,
        "data": sanitized_data,
    }

    resp = await _request_with_retry(
        "POST",
        url,
        client=client,
        max_retries=max_retries,
        initial_delay=initial_delay,
        headers=headers,
        json=body,
    )

    if resp.status_code == 200:
        record_external_dependency("google_sheets", "success")
        return resp.json()
    elif resp.status_code == 404:
        record_external_dependency("google_sheets", "http_error")
        raise AppError(404, "SHEET_NOT_FOUND", f"Không tìm thấy Google Sheet '{clean_id}' (HTTP 404).")
    elif resp.status_code == 403:
        record_external_dependency("google_sheets", "http_error")
        raise AppError(403, "SHEET_FORBIDDEN", "Không có quyền ghi vào Google Sheet.")
    elif resp.status_code == 429:
        record_external_dependency("google_sheets", "rate_limited")
        raise AppError(429, "SHEET_RATE_LIMITED", "Google Sheets API bị giới hạn hạn ngạch khi ghi hàng loạt (HTTP 429).")
    else:
        record_external_dependency("google_sheets", "http_error")
        raise AppError(resp.status_code, "SHEET_API_ERROR", f"Lỗi Google Sheets API khi batch update (HTTP {resp.status_code}): {resp.text}")


# --------------------------------------------------------------------------
# Feature F9: Inbound Google Sheets Parsing & ETL Integration
# --------------------------------------------------------------------------


async def fetch_sheet_rows(
    url_or_id: str,
    tab: str = "Sheet1",
    credentials_info: dict[str, Any] | str | None = None,
    api_key: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Đọc các dòng dữ liệu từ Google Sheet thành danh sách dictionary.

    Quy trình:
    1. Nếu có Service Account / OAuth credentials hoặc API Key: gọi Google Sheets API v4 trực tiếp.
    2. Fallback: gọi Google Visualization endpoint (tqx=out:csv) hỗ trợ các trang tính công khai.
    """
    sheet_id = extract_sheet_id(url_or_id)
    key = api_key or getattr(settings, "google_sheets_api_key", None)
    resolved_creds = resolve_credentials(credentials_info)

    # Cách 1: Google Sheets API v4 nếu có Credentials hoặc API Key
    if resolved_creds or key:
        range_target = _format_range(tab, "A1:ZZ")
        try:
            values = await fetch_sheet_values(
                sheet_id=sheet_id,
                range_name=range_target,
                credentials_info=resolved_creds,
                api_key=key,
                client=client,
            )
            if not values:
                return []
            header = [str(h).strip() for h in values[0]]
            rows: list[dict[str, Any]] = []
            for r in values[1:]:
                # Khớp cột theo header
                row_dict = dict(zip(header, [str(cell) if cell is not None else "" for cell in r], strict=False))
                rows.append(row_dict)
            return rows
        except AppError as e:
            # Nếu truyền credentials mà bị từ chối quyền (403/401/404), báo lỗi rõ ràng
            if resolved_creds and e.status_code in (401, 403, 404):
                raise
            # Nếu chỉ là API key lỗi hoặc quota, thử fallback sang public Gviz
            pass
        except Exception:
            if resolved_creds:
                raise

    # Cách 2: Public Google Visualization CSV export endpoint
    gviz_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
    params = {"tqx": "out:csv", "sheet": tab}
    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
        close_client = True

    try:
        resp = await client.get(gviz_url, params=params)
    except httpx.HTTPError as e:
        record_external_dependency("google_sheets", "unavailable")
        raise AppError(503, "SHEETS_UNAVAILABLE", f"Không kết nối được Google Sheets: {e}") from None
    finally:
        if close_client:
            await client.aclose()

    if resp.status_code >= 400:
        record_external_dependency("google_sheets", "http_error")
        raise AppError(
            resp.status_code if resp.status_code in (403, 404) else 502,
            "SHEETS_READ_FAILED",
            f"Không thể tải Google Sheet (HTTP {resp.status_code}). Đảm bảo trang tính đã bật quyền 'Bất kỳ ai có đường liên kết đều có thể xem' hoặc cung cấp Service Account.",
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


# --------------------------------------------------------------------------
# Feature F10: Outbound Google Sheets Sync & Status Writeback
# --------------------------------------------------------------------------


async def writeback_sheet_status(
    sheet_id: str,
    tab: str,
    status_column_letter: str,
    statuses: list[str],
    start_row: int = 2,
    credentials_info: dict[str, Any] | str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Cập nhật cột trạng thái xử lý (_sync_status) cho từng dòng trên Google Sheet."""
    clean_id = extract_sheet_id(sheet_id)
    if not statuses:
        return {"updatedRows": 0}

    end_row = start_row + len(statuses) - 1
    range_target = _format_range(tab, f"{status_column_letter}{start_row}:{status_column_letter}{end_row}")
    values = [[s] for s in statuses]

    return await write_sheet_values(
        sheet_id=clean_id,
        range_name=range_target,
        values=values,
        credentials_info=credentials_info,
        client=client,
    )


async def sync_out_to_google_sheet(
    url_or_id: str,
    tab: str,
    headers: list[tuple[str, str]],
    rows: list[dict[str, Any]],
    webhook_url: str | None = None,
    credentials_info: dict[str, Any] | str | None = None,
    include_sync_status: bool = True,
    sync_status_value: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Đồng bộ dữ liệu từ hệ thống ra Google Sheet và ghi nhận trạng thái đồng bộ.

    - Tự động bổ sung cột `_sync_status` (Trạng thái đồng bộ).
    - Khử triệt để Spreadsheet Formula Injection (CWE-1236).
    - Ưu tiên ghi trực tiếp qua Google Sheets API v4 nếu có Credentials.
    - Hỗ trợ gửi song song qua Apps Script Webhook nếu webhook_url được cung cấp.
    """
    sheet_id = extract_sheet_id(url_or_id)
    view_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    status_text = sync_status_value or f"SYNCED_{now_str}"

    # Bổ sung cột _sync_status vào danh sách cột nếu chưa có
    effective_headers = list(headers)
    if include_sync_status and not any(k == "_sync_status" for k, _ in effective_headers):
        effective_headers.append(("_sync_status", "Trạng thái đồng bộ"))

    # Xây dựng ma trận dữ liệu (áp dụng sanitize_cell_value phòng chống CWE-1236)
    matrix_data: list[list[Any]] = []
    matrix_data.append([label for _, label in effective_headers])

    for r in rows:
        row_vals: list[Any] = []
        for key, _ in effective_headers:
            if key == "_sync_status":
                val = r.get("_sync_status") or status_text
            else:
                val = r.get(key, "")
            row_vals.append(sanitize_cell_value(val))
        matrix_data.append(row_vals)

    direct_api_success = False
    resolved_creds = resolve_credentials(credentials_info)
    if resolved_creds:
        target_range = _format_range(tab, "A1")
        try:
            await write_sheet_values(
                sheet_id=sheet_id,
                range_name=target_range,
                values=matrix_data,
                credentials_info=resolved_creds,
                client=client,
            )
            direct_api_success = True
        except Exception:
            # Nếu cả API v4 và webhook đều không có, ném ngoại lệ
            if not webhook_url:
                raise

    # Fallback hoặc bổ sung gửi qua Webhook nếu có cấu hình
    if webhook_url:
        close_client = False
        http_client = client
        if http_client is None:
            http_client = httpx.AsyncClient(timeout=20.0)
            close_client = True
        try:
            res = await http_client.post(
                webhook_url,
                json={
                    "sheet_id": sheet_id,
                    "tab": tab,
                    "rows": matrix_data,
                },
            )
            if res.status_code >= 400 and not direct_api_success:
                raise AppError(502, "WEBHOOK_FAILED", f"Apps Script Webhook trả mã lỗi: {res.status_code}")
        except httpx.HTTPError as e:
            if not direct_api_success:
                raise AppError(502, "WEBHOOK_FAILED", f"Lỗi gửi dữ liệu tới Apps Script: {e}") from None
        finally:
            if close_client and http_client:
                await http_client.aclose()

    return {
        "status": "success",
        "sheet_id": sheet_id,
        "tab": tab,
        "sheet_url": view_url,
        "rows_count": len(rows),
        "columns_count": len(effective_headers),
        "sync_status": status_text,
        "direct_api_synced": direct_api_success,
    }
