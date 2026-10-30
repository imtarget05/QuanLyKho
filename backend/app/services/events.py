"""SSE events publishing service."""
from app.features.events.routes import publish_sse_event  # noqa: F401

__all__ = ["publish_sse_event"]
