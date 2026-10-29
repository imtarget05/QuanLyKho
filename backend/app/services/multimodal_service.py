"""Backward-compat shim: code AI da chuyen sang `app/ai/multimodal` (P1.13)."""
from app.ai.multimodal import (  # noqa: F401
    parse_invoice_text,
    validate_invoice_math,
)
