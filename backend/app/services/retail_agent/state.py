"""RetailOps Agent state schema (LangGraph).

State is the agent's working memory (NOT DB order state). Business order state
lives in QuanLyKho: Order, OrderLine tables.
"""

import operator
from typing import Annotated

from typing_extensions import TypedDict


class RetailState(TypedDict):
    """Working memory for a single retail order workflow run."""

    # --- Input ---
    query: str
    buyer_id: str  # authenticated actor ID
    branch_id: str  # branch selected from authenticated business scope

    # --- Intent / extraction ---
    intent: str  # "check_stock" | "draft_order" | "order_status" | "cancel_request"
    intent_source: str  # "model" | "deterministic_fallback"
    requested_items: list[dict]  # [{item_id, location_id, quantity}]
    ambiguous: bool
    clarification_needed: bool

    # --- Draft state (agent working memory) ---
    draft_id: str | None
    confirmation_token: str | None
    order_quote: dict | None  # backend-computed quote
    created_at: str

    # --- Validation ---
    stock_level: dict | None  # {item_id: available, requested}
    validation_result: str | None  # "ok" | "insufficient_stock" | "invalid_token"
    validation_message: str | None

    # --- Confirmation ---
    confirmed: bool
    confirmation_by: str | None  # actor who confirmed
    confirmed_at: str | None

    # --- Commit ---
    order_id: str | None
    committed_at: str | None
    commit_result: dict | None

    # --- Cancel ---
    cancelled: bool
    cancel_reason: str | None
    cancel_result: dict | None

    # --- Audit ---
    tool_calls: Annotated[list[str], operator.add]  # tool names only; no user data
    audit_trail: list[dict]  # [{step, status, detail}]

    # --- Errors / recovery ---
    error: str | None
    error_context: dict | None
    retry_attempt: int

    # --- Metrics ---
    latency_ms: float | None
    tool_call_count: int
    tokens_used: int | None
    final_message: str | None
