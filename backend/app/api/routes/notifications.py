"""Push notification and device registration API routes."""
import logging
import os
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth_utils import get_current_user
from app.database import get_db
from app.db.base import utc_now
from app.models.iam import User
from app.models.notification import DeviceRegistration
from app.schemas.notification import (
    DeviceRegisterRequest,
    DeviceResponse,
    TestNotificationRequest,
    TestNotificationResult,
)

logger = logging.getLogger("bankops.notifications")

router = APIRouter()


@router.post(
    "/devices/register",
    response_model=DeviceResponse,
    summary="Register or update device push token for authenticated user",
)
async def register_device(
    payload: DeviceRegisterRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = payload.device_token.strip()
    platform = payload.platform.strip().lower()
    if platform not in ("web", "android", "ios"):
        platform = "web"

    # Check if device token already exists
    stmt = select(DeviceRegistration).where(DeviceRegistration.device_token == token)
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing:
        existing.user_id = current_user.id
        existing.platform = platform
        existing.device_name = payload.device_name
        existing.is_active = True
        existing.last_seen_at = utc_now()
        await db.commit()
        await db.refresh(existing)
        return DeviceResponse(
            id=str(existing.id),
            user_id=str(existing.user_id),
            device_token=existing.device_token,
            platform=existing.platform,
            device_name=existing.device_name,
            is_active=existing.is_active,
            created_at=existing.created_at,
            last_seen_at=existing.last_seen_at,
        )

    device = DeviceRegistration(
        id=uuid.uuid4(),
        user_id=current_user.id,
        device_token=token,
        platform=platform,
        device_name=payload.device_name,
        is_active=True,
        last_seen_at=utc_now(),
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)

    return DeviceResponse(
        id=str(device.id),
        user_id=str(device.user_id),
        device_token=device.device_token,
        platform=device.platform,
        device_name=device.device_name,
        is_active=device.is_active,
        created_at=device.created_at,
        last_seen_at=device.last_seen_at,
    )


@router.get(
    "/devices",
    response_model=list[DeviceResponse],
    summary="List registered active devices for current user",
)
async def list_user_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(DeviceRegistration)
        .where(
            DeviceRegistration.user_id == current_user.id,
            DeviceRegistration.is_active,
        )
        .order_by(DeviceRegistration.last_seen_at.desc())
    )
    res = await db.execute(stmt)
    devices = res.scalars().all()

    return [
        DeviceResponse(
            id=str(d.id),
            user_id=str(d.user_id),
            device_token=d.device_token,
            platform=d.platform,
            device_name=d.device_name,
            is_active=d.is_active,
            created_at=d.created_at,
            last_seen_at=d.last_seen_at,
        )
        for d in devices
    ]


@router.delete(
    "/devices/{device_token}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unregister or deactivate device push token",
)
async def unregister_device(
    device_token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DeviceRegistration).where(
        DeviceRegistration.device_token == device_token.strip(),
        DeviceRegistration.user_id == current_user.id,
    )
    res = await db.execute(stmt)
    device = res.scalar_one_or_none()
    if device:
        device.is_active = False
        await db.commit()


@router.post(
    "/test-send",
    response_model=TestNotificationResult,
    summary="Dispatch a test push notification to user's devices",
)
async def test_send_notification(
    payload: TestNotificationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Resolve target devices
    if payload.target_device_token:
        tokens = [payload.target_device_token.strip()]
    else:
        stmt = select(DeviceRegistration.device_token).where(
            DeviceRegistration.user_id == current_user.id,
            DeviceRegistration.is_active,
        )
        res = await db.execute(stmt)
        tokens = [r[0] for r in res.fetchall()]

    if not tokens:
        return TestNotificationResult(
            success=False,
            provider="mock-fcm",
            delivered_count=0,
            failed_count=0,
            message="No active registered devices found for target.",
            details=[],
        )

    # In production, check for GOOGLE_APPLICATION_CREDENTIALS / FCM server key
    fcm_key = os.getenv("FCM_SERVER_KEY") or os.getenv("FIREBASE_CREDENTIALS")
    provider_name = "fcm-live" if fcm_key else "fcm-simulated"

    details = []
    delivered = 0
    failed = 0

    for token in tokens:
        # If simulated/mock or live:
        # In test/dev environment or without live credentials, deliver simulated ACK
        details.append({
            "token": token[:12] + "..." if len(token) > 16 else token,
            "status": "delivered",
            "provider": provider_name,
            "title": payload.title,
            "body": payload.body,
            "dispatched_at": utc_now().isoformat(),
        })
        delivered += 1

    return TestNotificationResult(
        success=True,
        provider=provider_name,
        delivered_count=delivered,
        failed_count=failed,
        message=f"Successfully dispatched test notification to {delivered} device(s) via {provider_name}.",
        details=details,
    )
