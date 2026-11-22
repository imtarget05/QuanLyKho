"""Tool adapters for RetailOps Agent.

Each tool translates LLM calls into business service calls over the
authenticated QuanLyKho order API. Business logic (price, stock, permission,
transaction) remains in backend services; the agent never fabricates results.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote, urlencode

import httpx

_BASE_URL = os.getenv("RETAIL_API_BASE_URL", "http://127.0.0.1:8000")
_TIMEOUT = float(os.getenv("RETAIL_API_TIMEOUT_S", "10"))

_client: httpx.AsyncClient | None = None


def _headers(access_token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"} if access_token else {}


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT)
    return _client


async def _request(
    method: str, path: str, json: dict[str, Any] | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Call the authenticated order API and return a normalized result."""
    if not access_token:
        return _unavailable()
    try:
        resp = await _get_client().request(method, path, json=json, headers=_headers(access_token))
    except httpx.TimeoutException:
        return {
            "success": False,
            "error_code": "RESULT_UNKNOWN",
            "message": "Request timed out; check operation status before any write retry",
        }
    except httpx.RequestError as exc:
        return {
            "success": False,
            "error_code": "DEPENDENCY_UNAVAILABLE",
            "message": f"Order service unreachable: {exc}",
        }

    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = {}
        error = body.get("error", {}) if isinstance(body, dict) else {}
        return {
            "success": False,
            "error_code": error.get("code", f"HTTP_{resp.status_code}"),
            "message": error.get("message", resp.text),
            "status_code": resp.status_code,
        }

    try:
        return resp.json()
    except Exception:
        return {"success": True, "raw": resp.text}


# ---------------------------------------------------------------------------
# Tool: get_stock
# ---------------------------------------------------------------------------
async def get_stock(
    item_id: str,
    location_id: str,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Check available stock for an item at a location.

    Read the tenant/location-scoped inventory balance API.
    """
    if not access_token:
        return _unavailable()
    response = await _request(
        "GET", f"/inventory/balances?{urlencode({'location_id': location_id, 'item_id': item_id})}",
        access_token=access_token,
    )
    if response.get("success") is False:
        return response
    balances = response.get("balances", [])
    if not balances:
        return {"success": False, "error_code": "STOCK_NOT_FOUND"}
    return {"success": True, "available": balances[0]["available_quantity"], "version": balances[0]["version"]}


async def search_catalog(query: str, access_token: str | None = None) -> dict[str, Any]:
    """Resolve an item by exact SKU/name, or report ambiguous partial matches."""
    if not query.strip():
        return {"success": False, "error_code": "EMPTY_CATALOG_QUERY"}
    response = await _request("GET", "/inventory/items", access_token=access_token)
    if response.get("success") is False:
        return response
    items = response.get("items")
    if not isinstance(items, list):
        return {"success": False, "error_code": "INVALID_CATALOG_RESPONSE"}
    needle = query.strip().casefold()
    exact = [i for i in items if isinstance(i, dict) and needle in {
        str(i.get("sku", "")).casefold(), str(i.get("name", "")).casefold()
    }]
    matches = exact or [i for i in items if isinstance(i, dict) and (
        needle in str(i.get("sku", "")).casefold()
        or needle in str(i.get("name", "")).casefold()
    )]
    candidates = [{"item_id": i.get("id"), "sku": i.get("sku"), "name": i.get("name")}
                  for i in matches if i.get("id")]
    if len(candidates) == 1:
        return {"success": True, "item_id": candidates[0]["item_id"], "candidates": candidates}
    return {"success": False, "error_code": "CATALOG_AMBIGUOUS" if candidates else "ITEM_NOT_FOUND",
            "candidates": candidates[:10]}


async def get_order(order_id: str, access_token: str | None = None) -> dict[str, Any]:
    """Read an order through the actor-scoped backend endpoint."""
    return await _request("GET", f"/orders/{quote(order_id, safe='')}", access_token=access_token)


async def get_operation_status(operation_id: str, access_token: str | None = None) -> dict[str, Any]:
    """Read a scoped idempotency result for timeout recovery."""
    return await _request(
        "GET", f"/orders/operations/{quote(operation_id, safe='')}", access_token=access_token
    )


# ---------------------------------------------------------------------------
# Tool: draft_order
# ---------------------------------------------------------------------------
async def draft_order(
    buyer_id: str,
    lines: list[dict],
    branch_id: str,
    idempotency_key: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Create a draft order quote (no stock commit).

    Backend decides price, validates stock, computes totals.
    Returns quote with draft_id, confirmation_token, expiry.
    """
    payload: dict[str, Any] = {
        "branch_id": branch_id,
        "lines": [
            {
                "item_id": line.get("item_id"),
                "location_id": line.get("location_id"),
                "quantity": line.get("quantity"),
            }
            for line in lines
        ],
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    return await _request("POST", "/orders/quote", json=payload, access_token=access_token)


# ---------------------------------------------------------------------------
# Tool: confirm_order
# ---------------------------------------------------------------------------
async def confirm_order(
    draft_id: str,
    confirmation_token: str,
    idempotency_key: str | None = None,
    buyer_id: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Commit a draft order (atomic stock decrement).

    Backend re-validates stock/price/permission before commit.
    Returns order_id and status.
    """
    payload: dict[str, Any] = {
        "draft_id": draft_id,
        "confirmation_token": confirmation_token,
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    result = await _request("POST", "/orders/confirm", json=payload, access_token=access_token)
    if result.get("error_code") != "RESULT_UNKNOWN" or not idempotency_key:
        return result
    status = await get_operation_status(idempotency_key, access_token=access_token)
    if status.get("status") == "committed" and isinstance(status.get("result"), dict):
        return {**status["result"], "recovered_from_status": True}
    return {**result, "operation_id": idempotency_key}


# ---------------------------------------------------------------------------
# Tool: cancel_order
# ---------------------------------------------------------------------------
async def cancel_order(
    order_id: str,
    reason: str | None = None,
    idempotency_key: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Request cancellation of a confirmed order.

    If manager approval required, returns pending approval status.
    Otherwise cancels and restores stock.
    """
    payload: dict[str, Any] = {"order_id": order_id}
    if reason:
        payload["reason"] = reason
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    return await _request("POST", "/orders/cancel", json=payload, access_token=access_token)


# ---------------------------------------------------------------------------
# Tool: check_permission
# ---------------------------------------------------------------------------
async def check_permission(
    user_id: str,
    action: str,
) -> dict[str, Any]:
    """Informational permission check.

    NOTE: This is informational only. Business service must enforce RBAC
    on every write. The LLM should not rely solely on this tool.
    """
    return {
        **_unavailable(),
        "can_perform": False,
        "detail": "No permission endpoint; RBAC enforced by backend service.",
    }


def _unavailable() -> dict[str, Any]:
    """Do not fabricate business results before an authenticated adapter exists."""
    return {
        "success": False,
        "error_code": "DEPENDENCY_UNAVAILABLE",
        "message": "RetailOps agent tool is not connected to the authenticated order service",
    }
