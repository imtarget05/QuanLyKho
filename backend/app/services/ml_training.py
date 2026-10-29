"""Backward-compat shim: code AI da chuyen sang `app/ai/training` (P1.13)."""
from app.ai.training import (  # noqa: F401
    generate_synthetic_inventory_demand,
    run_full_pipeline,
    time_aware_split,
    train_demand_forecast_model,
)
