"""Backward-compat shim: code AI da chuyen sang `app/ai/assessment` (P1.13)."""
from app.ai.assessment import (  # noqa: F401
    AI_UNAVAILABLE_CODE,
    ASSESSMENT_PROMPT,
    SYSTEM_PROMPT,
    UNAVAILABLE,
    assess_request,
    assess_request_heuristic,
    generate,
    stream_ollama,
)
