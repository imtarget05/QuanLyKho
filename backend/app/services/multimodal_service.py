"""Backward-compat shim: code AI da chuyen sang `app/ai/multimodal` (P1.13)."""
from app.ai.multimodal import (  # noqa: F401
    parse_invoice_text,
    parse_invoice_bytes,
    validate_invoice_math,
    match_catalog_items,
    create_draft_receipt_from_invoice,
)
