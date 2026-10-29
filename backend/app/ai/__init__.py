"""Bounded context AI Copilot (P1.13).

Tat ca code AI (du doan phong van, truy van tai lieu, ML registry/training,
da gia da gia, da gia da gia) duoc chuan hoa o module `app/ai` khong phai o
`app/services` theo cai dat flat cu.
"""

from app.ai.assessment import (  # noqa: F401
    assess_request,
    assess_request_heuristic,
    generate,
    stream_ollama,
)
from app.ai.multimodal import (  # noqa: F401
    parse_invoice_text,
    validate_invoice_math,
)
from app.ai.registry import (  # noqa: F401
    get_current_model_version,
    list_model_versions,
    promote_model,
    register_model,
    rollback_model,
    set_experiment,
    set_tracking_uri,
)
from app.ai.retrieval import (  # noqa: F401
    BUILTIN_SOP_KNOWLEDGE,
    grounded_prompt,
    retrieve,
)
from app.ai.training import (  # noqa: F401
    generate_synthetic_inventory_demand,
    run_full_pipeline,
    time_aware_split,
    train_demand_forecast_model,
)

__all__ = [
    "assess_request",
    "assess_request_heuristic",
    "generate",
    "stream_ollama",
    "BUILTIN_SOP_KNOWLEDGE",
    "grounded_prompt",
    "retrieve",
    "get_current_model_version",
    "list_model_versions",
    "promote_model",
    "register_model",
    "rollback_model",
    "set_experiment",
    "set_tracking_uri",
    "generate_synthetic_inventory_demand",
    "run_full_pipeline",
    "time_aware_split",
    "train_demand_forecast_model",
    "parse_invoice_text",
    "validate_invoice_math",
]
