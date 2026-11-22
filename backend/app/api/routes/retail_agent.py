"""Authenticated entrypoints for the RetailOps order workflow."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field

from app.api.routes.auth_utils import (
    get_current_user,
    oauth2_scheme,
    require_any_capability,
)
from app.models.iam import User
from app.schemas.order import OrderLineBase
from app.services.retail_agent.graph import build_retail_graph
from app.services.retail_agent.tools import search_catalog

router = APIRouter(prefix="/retail-agent", tags=["retail-agent"])
_graph = build_retail_graph()
_WRITE_CAP = "retail:order:write"


def set_checkpointer(checkpointer) -> None:
    """Replace the process-local development graph with a durable saver."""
    global _graph
    _graph = build_retail_graph(checkpointer=checkpointer)


class CatalogSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=128)
    location_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    branch_id: UUID | None = None
    requested_items: list[OrderLineBase] = Field(default_factory=list, max_length=50)
    catalog_selection: CatalogSelection | None = None
    order_id: UUID | None = None
    use_llm: bool = False


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool


def _view(result: dict, thread_id: str | None) -> dict:
    quote = result.get("order_quote") or {}
    commit = result.get("commit_result") or {}
    cancel = result.get("cancel_result") or {}
    return {
        "thread_id": thread_id,
        "pending_confirmation": "__interrupt__" in result,
        "validation_result": result.get("validation_result"),
        "intent": result.get("intent"),
        "intent_source": result.get("intent_source"),
        "latency_ms": result.get("latency_ms"),
        "tool_calls": result.get("tool_calls") or [],
        "draft_id": result.get("draft_id"),
        "total_amount": quote.get("total_amount"),
        "currency": quote.get("currency"),
        "order_id": result.get("order_id"),
        "stock_level": result.get("stock_level"),
        "catalog_candidates": result.get("catalog_candidates") or [],
        "final_message": result.get("final_message"),
        "error_code": commit.get("error_code") or cancel.get("error_code"),
        "cancel_status": cancel.get("status"),
        "operation_id": commit.get("operation_id"),
    }


@router.post("/threads")
async def start_thread(
    body: StartRequest,
    token: str = Depends(oauth2_scheme),
    user: User = Depends(get_current_user),
):
    if body.catalog_selection and body.requested_items:
        raise HTTPException(422, "Choose catalog_selection or requested_items")
    requested_items = [line.model_dump(mode="json") for line in body.requested_items]
    initial_calls = []
    if body.catalog_selection:
        selection = body.catalog_selection
        match = await search_catalog(selection.query, access_token=token)
        if not match.get("success"):
            code = match.get("error_code", "CATALOG_UNAVAILABLE")
            message = (
                "Nhiều sản phẩm phù hợp. Vui lòng chọn SKU cụ thể."
                if code == "CATALOG_AMBIGUOUS" else
                "Không tìm thấy sản phẩm phù hợp. Vui lòng kiểm tra SKU hoặc tên."
                if code == "ITEM_NOT_FOUND" else
                "Không thể tra cứu catalog lúc này. Vui lòng thử lại."
            )
            return _view({
                "intent": "clarify", "validation_result": code,
                "catalog_candidates": match.get("candidates", []),
                "tool_calls": ["search_catalog"],
                "final_message": message,
            }, None)
        requested_items = [OrderLineBase(
            item_id=match["item_id"], location_id=selection.location_id,
            quantity=selection.quantity,
        ).model_dump(mode="json")]
        initial_calls = ["search_catalog"]
    thread_id = uuid4().hex
    state = {
        "query": body.query,
        "buyer_id": str(user.id),
        "branch_id": str(body.branch_id) if body.branch_id else None,
        "requested_items": requested_items,
        "tool_calls": initial_calls,
        "order_id": str(body.order_id) if body.order_id else None,
        "confirmed": False,
    }
    result = await _graph.ainvoke(
        state,
        {"configurable": {"thread_id": thread_id}},
        context={"actor_id": str(user.id), "access_token": token, "use_llm": body.use_llm},
    )
    return _view(result, thread_id)


@router.post("/threads/{thread_id}/resume")
async def resume_thread(
    thread_id: str,
    body: ResumeRequest,
    token: str = Depends(oauth2_scheme),
    user: User = Depends(require_any_capability(_WRITE_CAP)),
):
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await _graph.aget_state(config)
    if not snapshot.values or snapshot.values.get("buyer_id") != str(user.id):
        raise HTTPException(404, "Thread not found")
    if snapshot.next != ("await_confirmation",):
        raise HTTPException(409, "Thread is not awaiting confirmation")
    result = await _graph.ainvoke(
        Command(resume=body.confirmed),
        config,
        context={"actor_id": str(user.id), "access_token": token},
    )
    return _view(result, thread_id)


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
):
    """Allow an actor to remove their own checkpoint and pending context."""
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await _graph.aget_state(config)
    if not snapshot.values or snapshot.values.get("buyer_id") != str(user.id):
        raise HTTPException(404, "Thread not found")
    await _graph.checkpointer.adelete_thread(thread_id)
    return {"status": "deleted", "thread_id": thread_id}
