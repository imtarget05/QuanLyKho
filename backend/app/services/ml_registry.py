"""Backward-compat shim: code AI da chuyen sang `app/ai/registry` (P1.13)."""
from app.ai.registry import (  # noqa: F401
    get_current_model_version,
    list_model_versions,
    promote_model,
    promote_model_with_r2_gate,
    register_model,
    rollback_model,
    set_experiment,
    set_tracking_uri,
)

PROMOTION_THRESHOLD_R2 = 0.7
