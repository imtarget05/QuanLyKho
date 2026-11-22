"""LangGraph nodes for RetailOps Agent.

Each node is a callable ``(state: RetailState) -> dict`` that returns partial
state. They orchestrate tool calling but delegate business logic to services.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from langgraph.runtime import Runtime
from langgraph.types import interrupt

from app.services.retail_agent.llm import classify_intent_live
from app.services.retail_agent.state import RetailState
from app.services.retail_agent.tools import (
    cancel_order,
    confirm_order,
    draft_order,
    get_order,
    get_stock,
)


# --- Node: classify intent from user query ---
async def classify_intent(state: RetailState, runtime: Runtime | None = None) -> dict:
    """Use a typed local model when enabled, with a safe deterministic fallback."""
    query = state.get("query", "").lower()
    if runtime and (runtime.context or {}).get("use_llm"):
        model_result = await classify_intent_live(query)
        if model_result.get("intent"):
            return {
                "intent": model_result["intent"],
                "intent_source": "model",
                "latency_ms": model_result["latency_ms"],
                "ambiguous": model_result["intent"] == "clarify",
                "clarification_needed": model_result["intent"] == "clarify",
            }
    # Simple keyword-based classification for MVP
    if any(kw in query for kw in ["hủy", "huỷ", "cancel", "xoá"]):
        intent = "cancel_request"
    elif any(kw in query for kw in ["tồn", "kho", "hang", "stock", "inventory"]):
        intent = "check_stock"
    elif any(kw in query for kw in ["mua", "mua hàng", "mua", "order", "bán", "đặt", "buy", "place"]):
        intent = "draft_order"
    elif any(kw in query for kw in ["tra cứu", "tra cứu đơn", "trạng thái", "status", "check", "lịch sử"]):
        intent = "order_status"
    else:
        intent = "check_stock"

    return {
        "intent": intent,
        "intent_source": "deterministic_fallback",
        "ambiguous": False,
        "clarification_needed": False,
    }


# --- Node: check stock ---
async def check_stock_node(state: RetailState, runtime: Runtime | None = None) -> dict:
    """Check available stock for requested items."""
    requested = state.get("requested_items", [])
    if not requested:
        return {"stock_level": {}, "validation_result": "no_items"}

    stock_level = {}
    calls = []
    all_ok = True
    for item in requested:
        item_id = item.get("item_id")
        location_id = item.get("location_id")
        qty = item.get("quantity", 0)

        # Call get_stock tool
        result = await get_stock(
            item_id, location_id,
            access_token=(runtime.context or {}).get("access_token") if runtime else None,
        )
        calls.append("get_stock")
        if not result.get("success"):
            return {"stock_level": stock_level, "validation_result": "stock_unavailable", "tool_calls": calls}
        stock_level[item_id] = {
            "item_id": item_id,
            "location_id": location_id,
            "requested": qty,
            "available": result.get("available", 0),
        }
        if Decimal(str(result.get("available", 0))) < Decimal(str(qty)):
            all_ok = False

    return {
        "stock_level": stock_level,
        "validation_result": "ok" if all_ok else "insufficient_stock",
        "tool_calls": calls,
    }


async def get_order_node(state: RetailState, runtime: Runtime | None = None) -> dict:
    order_id = state.get("order_id")
    if not order_id:
        return {"validation_result": "no_order_id"}
    result = await get_order(
        order_id,
        access_token=(runtime.context or {}).get("access_token") if runtime else None,
    )
    return {
        "validation_result": "order_found" if result.get("order_id") else "order_unavailable",
        "commit_result": result,
        "tool_calls": ["get_order"],
    }


# --- Node: draft order ---
async def draft_order_node(state: RetailState, runtime: Runtime | None = None) -> dict:
    """Request backend to create a draft order quote."""
    buyer_id = state.get("buyer_id", "unknown")
    lines = state.get("requested_items", [])

    if not lines:
        return {"draft_id": None, "order_quote": None, "validation_result": "no_items"}
    if not state.get("branch_id"):
        return {"draft_id": None, "order_quote": None, "validation_result": "no_branch"}

    # Call backend quote endpoint
    quote = await draft_order(
        buyer_id=buyer_id,
        lines=lines,
        branch_id=state.get("branch_id", ""),
        access_token=(runtime.context or {}).get("access_token") if runtime else None,
    )

    return {
        "draft_id": quote.get("draft_id"),
        "confirmation_token": quote.get("confirmation_token"),
        "order_quote": quote,
        "validation_result": "draft_ready" if quote.get("draft_id") else "draft_failed",
        "tool_calls": ["draft_order"],
    }


# --- Node: validate conditions ---
async def validate_node(state: RetailState) -> dict:
    """Validate draft + stock + permission before confirmation."""
    draft_id = state.get("draft_id")
    validation_result = state.get("validation_result", "unknown")

    if validation_result in {"no_items", "no_branch"}:
        return {"validation_result": validation_result}

    if not draft_id:
        return {"validation_result": "no_draft"}

    if validation_result == "insufficient_stock":
        return {"validation_result": "insufficient_stock"}

    if validation_result == "no_draft":
        return {"validation_result": "no_draft"}

    return {"validation_result": "ready_to_confirm"}


# --- Node: await confirmation ---
def await_confirmation_node(state: RetailState, runtime: Runtime | None = None) -> dict:
    """Interrupt at confirmation. Returns state without committing."""
    if state.get("confirmed"):
        return {}
    decision = interrupt("awaiting_user_confirmation")
    actor_id = (runtime.context or {}).get("actor_id") if runtime else None
    return {
        "confirmed": decision is True and bool(actor_id) and actor_id == state.get("buyer_id"),
        "clarification_needed": decision is not True or actor_id != state.get("buyer_id"),
    }


# --- Node: commit order ---
async def commit_order_node(state: RetailState, runtime: Runtime | None = None) -> dict:
    """Commit order after confirmation."""
    if not state.get("confirmed"):
        return {"order_id": None, "commit_result": None}

    draft_id = state.get("draft_id")
    if not draft_id:
        return {"order_id": None, "commit_result": {"error": "no_draft"}}

    # Call backend confirm endpoint
    result = await confirm_order(
        draft_id=draft_id,
        confirmation_token=state.get("confirmation_token", ""),
        idempotency_key=f"retail-agent-confirm:{draft_id}",
        access_token=(runtime.context or {}).get("access_token") if runtime else None,
    )

    return {
        "order_id": result.get("order_id"),
        "committed_at": datetime.now(UTC).isoformat() if result.get("order_id") else None,
        "validation_result": "committed" if result.get("order_id") else "commit_failed",
        "commit_result": result,
        "tool_calls": ["confirm_order"],
    }


# --- Node: cancel order ---
async def cancel_order_node(state: RetailState, runtime: Runtime | None = None) -> dict:
    """Request cancellation of an order."""
    order_id = state.get("order_id")
    if not order_id:
        return {"cancelled": False, "cancel_result": {"error": "no_order"}}

    result = await cancel_order(
        order_id=order_id, reason="user requested cancellation",
        idempotency_key=f"retail-agent-cancel:{order_id}",
        access_token=(runtime.context or {}).get("access_token") if runtime else None,
    )
    return {
        "cancelled": result.get("status") == "cancelled",
        "cancel_result": result,
        "tool_calls": ["cancel_order"],
    }


# --- Node: report result ---
def report_result(state: RetailState) -> dict:
    """Format final result for the user."""
    if state.get("intent") == "clarify":
        return {"final_message": "Vui lòng nói rõ sản phẩm, số lượng hoặc thao tác cần thực hiện."}
    if state.get("intent") == "order_status" and state.get("validation_result") == "order_found":
        order = state.get("commit_result") or {}
        return {"final_message": f"Đơn hàng {order.get('order_id')}: {order.get('status')}", "order_id": order.get("order_id")}
    if state.get("intent") == "check_stock" and state.get("validation_result") in {"ok", "insufficient_stock"}:
        return {"final_message": "Đã kiểm tra tồn kho.", "stock_level": state.get("stock_level")}
    if state.get("confirmed") and state.get("order_id"):
        return {
            "final_message": f"Đơn hàng đã được tạo thành công (Order ID: {state['order_id']})",
            "order_id": state.get("order_id"),
        }
    elif state.get("cancelled"):
        return {"final_message": "Đơn hàng đã hủy"}
    elif (state.get("cancel_result") or {}).get("status") == "pending_approval":
        return {"final_message": "Yêu cầu hủy đơn đang chờ quản lý duyệt."}
    else:
        return {"final_message": "Không thể xử lý yêu cầu của bạn. Vui lòng thử lại."}
