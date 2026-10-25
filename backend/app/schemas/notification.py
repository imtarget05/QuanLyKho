"""Pydantic schemas for Device Registrations and Push Notifications."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    device_token: str = Field(..., min_length=10, max_length=512, description="FCM / APNs / WebPush registration token")
    platform: str = Field(default="web", description="Device platform: web, android, ios")
    device_name: str | None = Field(default=None, max_length=256, description="Human-readable device or browser name")


class DeviceResponse(BaseModel):
    id: str
    user_id: str
    device_token: str
    platform: str
    device_name: str | None
    is_active: bool
    created_at: datetime | None
    last_seen_at: datetime | None

    model_config = {"from_attributes": True}


class TestNotificationRequest(BaseModel):
    title: str = Field(default="Cảnh báo Kho Trà Sữa", max_length=256)
    body: str = Field(default="Kiểm tra hệ thống thông báo đẩy (Push Notification Test)", max_length=1024)
    target_device_token: str | None = Field(default=None, description="Optional single token target; if omitted, sends to all active devices of the caller")
    data: dict[str, Any] | None = Field(default=None, description="Optional arbitrary key-value payload")


class TestNotificationResult(BaseModel):
    success: bool
    provider: str
    delivered_count: int
    failed_count: int
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)
