"""Service layer - business logic orchestration.

Các service còn lại (idempotency, approval_controls, approval_events,
ai, etl_engine, ml_registry, v.v.) được import trực tiếp tại route
cần dùng. Layer domain/repositories đã được gỡ vì chưa được wire vào
routes (để tránh duplicate logic với route handlers hiện có).
"""
