"""LangGraph state for RetailOps Agent.

RetailState is the agent working memory (NOT DB order state).
Business order state lives in QuanLyKho: Order, OrderLine tables.
"""

import operator
from typing import Annotated

from typing_extensions import TypedDict


class RetailState(TypedDict):
    """Full state for a retail order workflow run."""

    # --- Input ---
    query: str
    buyer_id: str
    branch_id: str

    # --- Intent ---
    intent: str
    intent_source: str
    requested_items: list[dict]
    ambiguous: bool
    clarification_needed: bool

    # --- Draft ---
    draft_id: str | None
    confirmation_token: str | None
    order_quote: dict | None
    created_at: str

    # --- Validation ---
    stock_level: dict
    validation_result: str
    validation_message: str | None

    # --- Confirmation ---
    confirmed: bool
    confirmation_by: str | None
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
    tool_calls: Annotated[list[str], operator.add]
    audit_trail: list[dict]

    # --- Errors ---
    error: str | None
    error_context: dict | None

    # --- Metrics ---
    latency_ms: float | None
    tool_call_count: int
    tokens_used: int | None
    final_message: str | None
