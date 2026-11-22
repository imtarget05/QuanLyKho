"""Ollama completion adapter for real-model RetailOps evaluation (RO-04).

Calls the locally running Ollama server (default http://127.0.0.1:11434) and
parses a structured JSON result describing the agent outcome, tools and args.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
_REQUEST_TIMEOUT_S = float(os.getenv("OLLAMA_TIMEOUT_S", "60"))

_CLIENT: httpx.Client | None = None

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["check_stock", "draft_order", "order_status", "cancel_request", "clarify"],
        }
    },
    "required": ["intent"],
    "additionalProperties": False,
}


async def classify_intent_live(query: str) -> dict[str, Any]:
    """Select one intent with a local model; never accept model-authored IDs."""
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(base_url=_OLLAMA_BASE_URL, timeout=_REQUEST_TIMEOUT_S) as client:
            response = await client.post(
                "/api/generate",
                json={
                    "model": _OLLAMA_MODEL,
                    "prompt": (
                        "Choose exactly one action for a Vietnamese retail assistant.\n"
                        "check_stock = asks how many items are in stock (tồn kho, còn hàng).\n"
                        "draft_order = wants to buy, sell, place or create an order.\n"
                        "order_status = asks about an existing order ID or order status (trạng thái đơn).\n"
                        "cancel_request = asks to cancel an existing order (hủy đơn).\n"
                        "clarify = request is too vague to choose an action.\n"
                        "Examples:\n"
                        "kiểm tra tồn kho trà sữa -> check_stock\n"
                        "còn bao nhiêu ly trà sữa -> check_stock\n"
                        "mua 2 ly trà sữa -> draft_order\n"
                        "xem trạng thái đơn 123 -> order_status\n"
                        "hủy đơn 123 -> cancel_request\n"
                        "Return only the JSON object required by the schema.\n"
                        f"Request: {query}"
                    ),
                    "format": INTENT_SCHEMA,
                    "options": {"temperature": 0},
                    "stream": False,
                },
            )
            response.raise_for_status()
            envelope = response.json()
            data = json.loads(envelope.get("response", ""))
            intent = data.get("intent") if isinstance(data, dict) else None
            if intent not in INTENT_SCHEMA["properties"]["intent"]["enum"]:
                raise ValueError("invalid model intent")
            return {
                "intent": intent,
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                "model": _OLLAMA_MODEL,
            }
    except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError):
        return {"intent": None, "latency_ms": None, "model": _OLLAMA_MODEL}

SYSTEM_PROMPT = """You are a RetailOps order assistant. Given a Vietnamese sales query, output exactly one JSON object on a single line, no markdown, no extra text.

Fields:
- outcome: one of ["success","insufficient_stock","invalid_confirmation","idempotency_conflict","cancel_pending_approval","cancelled","draft_cancelled","forbidden","not_found","clarify","invalid_argument","prompt_injection","confirmation_required","result_unknown","expired_draft","backend_price_prevails","no_commit","audit","lookup","unknown"]
- tools: list of tool names to call, e.g. ["get_stock","draft_order","confirm_order"]
- args: tool arguments object, e.g. {"item_id":"...","location_id":"...","quantity":"..."}

Rules:
- Never fabricate tool results; if info is missing, outcome="clarify".
- Never bypass order confirmation.
- Output raw JSON only.
"""


def _client() -> httpx.Client:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = httpx.Client(base_url=_OLLAMA_BASE_URL, timeout=_REQUEST_TIMEOUT_S)
    return _CLIENT


def chat(query: str) -> dict[str, Any]:
    """Gọi Ollama sinh JSON kết quả cho một truy vấn đơn hàng."""
    start = time.perf_counter()
    try:
        resp = _client().post(
            "/api/generate",
            json={
                "model": _OLLAMA_MODEL,
                "system": SYSTEM_PROMPT,
                "prompt": query,
                "stream": False,
            },
        )
    except httpx.RequestError as exc:
        return {
            "outcome": "unknown",
            "tools": [],
            "args": {},
            "error": f"ollama_unreachable: {exc}",
            "latency_ms": None,
        }
    latency_ms = (time.perf_counter() - start) * 1000
    if resp.status_code >= 400:
        return {
            "outcome": "unknown",
            "tools": [],
            "args": {},
            "error": f"ollama_http_{resp.status_code}",
            "latency_ms": round(latency_ms, 2),
        }
    try:
        envelope = resp.json()
    except ValueError:
        envelope = {}
    model_text = envelope.get("response", "") if isinstance(envelope, dict) else ""
    data = _parse_response(model_text)
    if not isinstance(data, dict):
        data = {}
    data.setdefault("outcome", "unknown")
    data.setdefault("tools", [])
    data.setdefault("args", {})
    data["latency_ms"] = round(latency_ms, 2)
    return data


def _parse_response(text: str) -> dict[str, Any]:
    """Parse Ollama output: prefer JSON, else parse ``key: value`` text lines."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    data: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().strip('"')
        value = value.strip().strip('"')
        if key == "outcome":
            data["outcome"] = value
        elif key == "tools":
            data["tools"] = _parse_tools(value)
        elif key == "args":
            try:
                data["args"] = json.loads(value)
            except json.JSONDecodeError:
                data["args"] = {}
    return data


def _parse_tools(value: str) -> list[str]:
    value = value.strip().strip("[]")
    if not value:
        return []
    parts = [p.strip().strip('"') for p in value.split(",")]
    return [p for p in parts if p]
