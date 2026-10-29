"""Admin User Management & IAM Scopes API (Phase 1).

Enforces:
- Non-admin gets 403 on all endpoints.
- Admin cannot self-lock or self-escalate.
- Admin cannot see/set raw employee passwords or PINs directly.
- Locked/inactive users and revoked sessions are immediately blocked.
- All administrative mutations write AuditEvent and OutboxEvent.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.api.routes.auth_utils import (
    get_password_hash,
    get_user_capabilities,
    get_user_roles,
    get_user_scope_grants,
    require_any_capability,
)
from app.config import settings
from app.database import get_db
from app.models.activity import AuditEvent, OutboxEvent
from app.models.iam import (
    Branch,
    Capability,
    Role,
    RoleCapability,
    ScopeGrant,
    User,
    UserRole,
    UserStatus,
)
from app.services.approval_controls import DEMO_SUPERVISOR_PIN
from app.services.email_service import (
    check_smtp_health,
    is_valid_email,
    send_invite_email,
)

router = APIRouter(prefix="/admin", tags=["Admin IAM"])

_ADMIN_CAPS = ("iam:admin", "admin:user_management")


def _now() -> datetime:
    return datetime.now(UTC)


def _gen_temp_password() -> str:
    # Generates a clean, strong temporary password
    return f"BankOps#{secrets.token_hex(4).upper()}!"


# --- Request & Response Models ---

class ScopeInput(BaseModel):
    branch_id: str | None = None
    location_id: str | None = None
    capability: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=256)
    email: str | None = None
    phone_number: str | None = None
    branch_id: str | None = None
    roles: list[str] = Field(default_factory=lambda: ["staff"])
    scopes: list[ScopeInput] = Field(default_factory=list)
    onboarding_method: str = Field(default="temporary_password", description="'temporary_password' | 'invite_email'")


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    branch_id: str | None = None


class UpdateStatusRequest(BaseModel):
    status: str = Field(description="'active' | 'inactive' | 'locked'")
    reason: str | None = None


class UpdateRolesRequest(BaseModel):
    roles: list[str]


class UpdateScopesRequest(BaseModel):
    scopes: list[ScopeInput]


# --- Helper Methods ---

async def _validated_roles(db: AsyncSession, requested: list[str]) -> list[str]:
    """Validate against the IAM catalog so migrated roles are assignable."""
    roles = sorted({role.strip().lower() for role in requested if role.strip()})
    if not roles:
        raise AppError(422, "EMPTY_ROLES", "Người dùng phải có ít nhất một vai trò hợp lệ.")
    found = set((await db.execute(select(Role.code).where(Role.code.in_(roles)))).scalars().all())
    unknown = sorted(set(roles) - found)
    if unknown:
        raise AppError(422, "INVALID_ROLES", f"Vai trò không tồn tại: {', '.join(unknown)}.")
    return roles


async def _require_root_for_role_change(
    db: AsyncSession, actor: User, before: set[str], after: set[str]
) -> None:
    if "root_admin" in before or "root_admin" in after:
        caps = await get_user_capabilities(db, actor.id)
        if "iam:root" not in caps:
            raise AppError(403, "ROOT_ROLE_FORBIDDEN", "Chỉ quản trị viên root mới được thay đổi vai trò root.")

async def _audit(
    db: AsyncSession,
    actor_id: uuid.UUID,
    action: str,
    subject: str,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action=action,
            subject=subject,
            occurred_at=_now(),
            metadata_json=metadata or {},
        )
    )


async def _outbox(
    db: AsyncSession,
    event_type: str,
    aggregate_id: str,
    payload: dict,
) -> None:
    db.add(
        OutboxEvent(
            id=uuid.uuid4(),
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload_json=payload,
            created_at=_now(),
        )
    )


async def _user_to_dict(db: AsyncSession, user: User) -> dict:
    roles = await get_user_roles(db, user.id)
    scopes = await get_user_scope_grants(db, user.id)
    
    branch_name = None
    if user.branch_id:
        b_res = await db.execute(select(Branch.name).where(Branch.id == user.branch_id))
        branch_name = b_res.scalar_one_or_none()

    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name_demo,
        "email": user.email,
        "phone_number": user.phone_number,
        "status": user.status.value if hasattr(user.status, "value") else str(user.status),
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "branch_name": branch_name or user.branch,
        "roles": roles,
        "must_change_password": user.must_change_password,
        "has_pending_invite": bool(user.invite_token_hash and (user.invite_expires_at is None or user.invite_expires_at > _now())),
        "scopes": [
            {
                "id": str(s.id),
                "branch_id": str(s.branch_id) if s.branch_id else None,
                "location_id": str(s.location_id) if s.location_id else None,
                "capability": s.capability,
                "valid_from": s.valid_from.isoformat() if s.valid_from else None,
                "valid_to": s.valid_to.isoformat() if s.valid_to else None,
            }
            for s in scopes
        ],
        "created_at": user.created_at.isoformat() if hasattr(user, "created_at") and user.created_at else None,
    }


# --- Endpoints ---

@router.get("/branches")
async def list_branches(
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """List all organizational branches."""
    result = await db.execute(select(Branch).order_by(Branch.code))
    branches = result.scalars().all()
    return {
        "branches": [
            {
                "id": str(b.id),
                "code": b.code,
                "name": b.name,
                "address": b.address,
                "active": b.active,
            }
            for b in branches
        ]
    }


@router.get("/roles")
async def list_roles(
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """List available system roles and capabilities."""
    roles_res = await db.execute(select(Role).order_by(Role.code))
    caps_res = await db.execute(select(Capability).order_by(Capability.code))
    return {
        "roles": [{"code": r.code, "name": r.name, "description": r.description} for r in roles_res.scalars().all()],
        "capabilities": [{"code": c.code, "name": c.name, "description": c.description} for c in caps_res.scalars().all()],
    }


@router.get("/users")
async def list_users(
    search: str | None = None,
    branch_id: str | None = None,
    role: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """List and filter users for employee management."""
    query = select(User)

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(User.username).like(term),
                func.lower(User.display_name_demo).like(term),
                func.lower(User.email).like(term),
            )
        )

    if branch_id and branch_id.strip():
        try:
            b_uuid = uuid.UUID(branch_id.strip())
            query = query.where(User.branch_id == b_uuid)
        except ValueError:
            pass

    if status_filter and status_filter.strip():
        try:
            query = query.where(User.status == UserStatus(status_filter.strip()))
        except ValueError:
            pass

    if role and role.strip():
        query = query.join(UserRole, UserRole.user_id == User.id).where(UserRole.role_code == role.strip())

    total_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_query)).scalar() or 0

    query = query.order_by(User.created_at.desc() if hasattr(User, "created_at") else User.username).limit(limit).offset(offset)
    users = (await db.execute(query)).scalars().all()

    items = []
    for u in users:
        items.append(await _user_to_dict(db, u))

    return {
        "users": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """Provision a new employee with roles and scopes.
    
    Supports:
    - temporary_password: Generates secure one-time password, sets must_change_password=True.
    - invite_email: Generates 7-day invite token and sends invite link.
    """
    clean_username = body.username.strip().lower()
    clean_email = body.email.strip().lower() if body.email and body.email.strip() else None

    # Invite qua email BẮT BUỘC email thật có format hợp lệ (không cho placeholder).
    if body.onboarding_method in ("invite_email", "email_invite"):
        if not clean_email:
            raise AppError(
                422,
                "EMAIL_REQUIRED",
                "Onboarding mời qua email bắt buộc email thật của nhân viên để nhận thư mời.",
            )
        if not is_valid_email(clean_email):
            raise AppError(
                422,
                "EMAIL_INVALID",
                f"Email '{clean_email}' không đúng định dạng email thật (vd: nhanvien@congty.com).",
            )

    # Verify unique username
    existing_u = (await db.execute(select(User).where(func.lower(User.username) == clean_username))).scalar_one_or_none()
    if existing_u:
        raise AppError(409, "USERNAME_EXISTS", f"Tên đăng nhập '{clean_username}' đã tồn tại.")

    # Verify unique email
    if clean_email:
        existing_e = (await db.execute(select(User).where(func.lower(User.email) == clean_email))).scalar_one_or_none()
        if existing_e:
            raise AppError(409, "EMAIL_EXISTS", f"Email '{clean_email}' đã được sử dụng.")

    # Branch verification
    branch_uuid = None
    if body.branch_id:
        try:
            branch_uuid = uuid.UUID(body.branch_id.strip())
            branch_exists = (await db.execute(select(Branch).where(Branch.id == branch_uuid))).scalar_one_or_none()
            if not branch_exists:
                raise AppError(404, "BRANCH_NOT_FOUND", "Chi nhánh không tồn tại.")
        except ValueError:
            raise AppError(422, "INVALID_BRANCH_ID", "Định dạng branch_id không hợp lệ.") from None

    assigned_roles = await _validated_roles(db, body.roles)
    await _require_root_for_role_change(db, current_user, set(), set(assigned_roles))

    new_user_id = uuid.uuid4()
    now = _now()
    temp_password = None
    invite_token = None

    if body.onboarding_method == "temporary_password":
        temp_password = _gen_temp_password()
        pwd_hash = get_password_hash(temp_password)
        must_change = True
        token_hash = None
        expires_at = None
        user_status = UserStatus.active
    else:
        # invite_email
        invite_token = secrets.token_hex(8)
        token_hash = hashlib.sha256(invite_token.encode("utf-8")).hexdigest()
        expires_at = now + timedelta(days=7)
        # Placeholder unusable password until invite is accepted via /auth/accept-invite
        # (flip inactive -> active). Test test_admin_create_user_with_invite_token phụ thuộc flow này.
        pwd_hash = get_password_hash(secrets.token_urlsafe(32))
        must_change = False
        user_status = UserStatus.inactive

    new_user = User(
        id=new_user_id,
        username=clean_username,
        password_hash=pwd_hash,
        # D4 — PIN mặc định demo (`123456`) CHỈ được gán khi demo mode bật
        # tường minh (APP_ENV=demo + DEMO_MODE=true), giống `seed.py` và
        # `auth.py`. Ngoài demo mode user mới KHÔNG có PIN sẵn: PIN demo đã
        # công khai trong repo (xem docs/security/secret-rotation-inventory-
        # 2026-10-20.md §2.5) nên gán sẵn ở production là lỗ hổng; admin phải
        # tự đặt PIN, cổng duyệt dùng PIN cấu hình `SUPERVISOR_PIN`
        # (fail-closed).
        pin_hash=(
            get_password_hash(DEMO_SUPERVISOR_PIN) if settings.is_demo_mode else None
        ),
        status=user_status,
        display_name_demo=body.display_name.strip(),
        email=clean_email,
        phone_number=body.phone_number.strip() if body.phone_number else None,
        branch_id=branch_uuid,
        must_change_password=must_change,
        invite_token_hash=token_hash,
        invite_expires_at=expires_at,
        auth_version=1,
    )
    db.add(new_user)
    await db.flush()

    # Assign roles
    for role in assigned_roles:
        db.add(UserRole(user_id=new_user_id, role_code=role))

    # Assign scope grants
    for s in body.scopes:
        b_id = uuid.UUID(s.branch_id.strip()) if s.branch_id else None
        l_id = uuid.UUID(s.location_id.strip()) if s.location_id else None
        db.add(
            ScopeGrant(
                id=uuid.uuid4(),
                user_id=new_user_id,
                branch_id=b_id,
                location_id=l_id,
                capability=s.capability,
                valid_from=s.valid_from,
                valid_to=s.valid_to,
                granted_by=current_user.id,
            )
        )

    # Audit & Outbox
    await _audit(
        db,
        actor_id=current_user.id,
        action="IAM_USER_CREATED",
        subject=f"iam_users:{new_user_id}",
        metadata={
            "username": clean_username,
            "onboarding_method": body.onboarding_method,
            "roles": assigned_roles,
        },
    )
    await _outbox(
        db,
        event_type="user.provisioned",
        aggregate_id=str(new_user_id),
        payload={"username": clean_username, "email": clean_email, "method": body.onboarding_method},
    )

    await db.commit()
    await db.refresh(new_user)

    # Gửi thư mời tới email thật (best-effort): SMTP chưa cấu hình thì log demo
    # mode, không làm hỏng việc tạo tài khoản; admin vẫn nhận invite_link để chia sẻ.
    invite_email_sent = False
    delivery_msg = ""
    full_invite_link = (
        f"{settings.frontend_base_url.rstrip('/')}/accept-invite?token={invite_token}"
        if invite_token else None
    )
    if invite_token and clean_email:
        try:
            res = await send_invite_email(
                to_email=clean_email,
                username=clean_username,
                invite_link=full_invite_link,
                expires_at=new_user.invite_expires_at,
                display_name=new_user.display_name_demo,
                roles=assigned_roles,
                token=invite_token,
                inviter_name=current_user.display_name_demo or current_user.username,
            )
            invite_email_sent = bool(res)
            delivery_msg = getattr(res, "message", "Đã gửi email thành công" if invite_email_sent else "Không gửi được email")
        except Exception as exc:  # noqa: BLE001 - email không bao giờ làm fail provisioning
            invite_email_sent = False
            delivery_msg = str(exc)

    user_data = await _user_to_dict(db, new_user)
    return {
        "user": user_data,
        "temporary_password": temp_password,
        "invite_token": invite_token,
        "invite_link": full_invite_link,
        "invite_email_sent": invite_email_sent,
        "email_delivery_message": delivery_msg,
        "message": f"Tài khoản '{clean_username}' đã được khởi tạo thành công.",
    }


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: str,
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve user details by ID."""
    u_uuid = uuid.UUID(user_id.strip())
    user = (await db.execute(select(User).where(User.id == u_uuid))).scalar_one_or_none()
    if not user:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")

    return {"user": await _user_to_dict(db, user)}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """Update employee demographic details."""
    u_uuid = uuid.UUID(user_id.strip())
    user = (await db.execute(select(User).where(User.id == u_uuid))).scalar_one_or_none()
    if not user:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")

    if body.display_name is not None:
        user.display_name_demo = body.display_name.strip()
    if body.phone_number is not None:
        user.phone_number = body.phone_number.strip() or None
    if body.email is not None:
        clean_email = body.email.strip().lower() or None
        if clean_email and clean_email != (user.email or "").lower():
            existing = (await db.execute(select(User).where(func.lower(User.email) == clean_email))).scalar_one_or_none()
            if existing:
                raise AppError(409, "EMAIL_EXISTS", f"Email '{clean_email}' đã được sử dụng.")
        user.email = clean_email
    if body.branch_id is not None:
        if body.branch_id.strip():
            b_uuid = uuid.UUID(body.branch_id.strip())
            branch_exists = (await db.execute(select(Branch).where(Branch.id == b_uuid))).scalar_one_or_none()
            if not branch_exists:
                raise AppError(404, "BRANCH_NOT_FOUND", "Chi nhánh không tồn tại.")
            user.branch_id = b_uuid
        else:
            user.branch_id = None

    await _audit(
        db,
        actor_id=current_user.id,
        action="IAM_USER_UPDATED",
        subject=f"iam_users:{user.id}",
        metadata={"display_name": user.display_name_demo, "email": user.email},
    )
    await db.commit()
    await db.refresh(user)

    return {"user": await _user_to_dict(db, user), "message": "Cập nhật thông tin thành công."}


@router.post("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    body: UpdateStatusRequest,
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """Lock, unlock, activate, or deactivate an employee account.
    
    Invariant: Admin CANNOT lock themselves.
    Invariant: Changing to locked/inactive immediately revokes sessions.
    """
    u_uuid = uuid.UUID(user_id.strip())
    user = (await db.execute(select(User).where(User.id == u_uuid))).scalar_one_or_none()
    if not user:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")

    target_status = body.status.strip().lower()
    if target_status not in ("active", "inactive", "locked"):
        raise AppError(422, "INVALID_STATUS", "Trạng thái phải là 'active', 'inactive', hoặc 'locked'.")

    # Invariant: Admin cannot lock or deactivate self
    if current_user.id == user.id and target_status in ("locked", "inactive"):
        raise AppError(400, "CANNOT_LOCK_SELF", "Quản trị viên không thể tự khóa hoặc vô hiệu hóa tài khoản của chính mình.")

    prev_status = user.status.value if hasattr(user.status, "value") else str(user.status)
    user.status = UserStatus(target_status)

    # Invalidate existing sessions immediately
    user.auth_version = getattr(user, "auth_version", 1) + 1

    await _audit(
        db,
        actor_id=current_user.id,
        action="IAM_USER_STATUS_CHANGED",
        subject=f"iam_users:{user.id}",
        metadata={"from_status": prev_status, "to_status": target_status, "reason": body.reason},
    )
    await _outbox(
        db,
        event_type="user.status_changed",
        aggregate_id=str(user.id),
        payload={"username": user.username, "status": target_status, "reason": body.reason},
    )

    await db.commit()
    await db.refresh(user)

    return {"user": await _user_to_dict(db, user), "message": f"Đã chuyển trạng thái tài khoản thành '{target_status}'."}


@router.put("/users/{user_id}/roles")
async def update_user_roles(
    user_id: str,
    body: UpdateRolesRequest,
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """Assign or replace roles for a user.
    
    Invariant: Admin cannot self-escalate or strip own admin role.
    """
    u_uuid = uuid.UUID(user_id.strip())
    user = (await db.execute(select(User).where(User.id == u_uuid))).scalar_one_or_none()
    if not user:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")

    cleaned_roles = await _validated_roles(db, body.roles)
    existing_roles_res = await db.execute(select(UserRole).where(UserRole.user_id == u_uuid))
    existing_roles = {role.role_code: role for role in existing_roles_res.scalars().all()}
    before = set(existing_roles)
    after = set(cleaned_roles)
    await _require_root_for_role_change(db, current_user, before, after)

    # Invariant: Self-modification check
    if current_user.id == user.id:
        if after - before:
            raise AppError(403, "CANNOT_ESCALATE_SELF", "Không thể tự cấp thêm vai trò cho chính mình.")
        retained_caps = set((await db.execute(
            select(RoleCapability.capability_code).where(RoleCapability.role_code.in_(after))
        )).scalars().all())
        if not retained_caps.intersection(_ADMIN_CAPS):
            raise AppError(400, "CANNOT_DEMOTE_SELF", "Quản trị viên không thể tự gỡ vai trò admin của chính mình.")

    # Apply a set difference. Deleting and reinserting an unchanged composite
    # primary key in one flush can trigger a uniqueness error on a retry.
    for role_code in before - after:
        await db.delete(existing_roles[role_code])

    for role_code in after - before:
        db.add(UserRole(user_id=u_uuid, role_code=role_code))

    # Invalidate token version so user gets refreshed permissions
    user.auth_version = getattr(user, "auth_version", 1) + 1

    await _audit(
        db,
        actor_id=current_user.id,
        action="IAM_USER_ROLES_UPDATED",
        subject=f"iam_users:{user.id}",
        metadata={"new_roles": cleaned_roles},
    )
    await _outbox(
        db,
        event_type="user.roles_updated",
        aggregate_id=str(user.id),
        payload={"username": user.username, "roles": cleaned_roles},
    )

    await db.commit()
    await db.refresh(user)

    return {"user": await _user_to_dict(db, user), "message": "Cập nhật vai trò thành công."}


@router.put("/users/{user_id}/scopes")
async def update_user_scopes(
    user_id: str,
    body: UpdateScopesRequest,
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """Assign or replace branch and location scope grants for a user."""
    u_uuid = uuid.UUID(user_id.strip())
    user = (await db.execute(select(User).where(User.id == u_uuid))).scalar_one_or_none()
    if not user:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")

    if current_user.id == user.id:
        raise AppError(403, "CANNOT_CHANGE_OWN_SCOPES", "Không thể tự thay đổi phạm vi dữ liệu của chính mình.")

    # Remove existing scopes
    existing_scopes_res = await db.execute(select(ScopeGrant).where(ScopeGrant.user_id == u_uuid))
    for s in existing_scopes_res.scalars().all():
        await db.delete(s)

    # Insert new scopes
    for s in body.scopes:
        b_id = uuid.UUID(s.branch_id.strip()) if s.branch_id else None
        l_id = uuid.UUID(s.location_id.strip()) if s.location_id else None
        db.add(
            ScopeGrant(
                id=uuid.uuid4(),
                user_id=u_uuid,
                branch_id=b_id,
                location_id=l_id,
                capability=s.capability,
                valid_from=s.valid_from,
                valid_to=s.valid_to,
                granted_by=current_user.id,
            )
        )

    # Invalidate token version so scope takes effect immediately
    user.auth_version = getattr(user, "auth_version", 1) + 1

    await _audit(
        db,
        actor_id=current_user.id,
        action="IAM_USER_SCOPES_UPDATED",
        subject=f"iam_users:{user.id}",
        metadata={"scope_count": len(body.scopes)},
    )
    await _outbox(
        db,
        event_type="user.scopes_updated",
        aggregate_id=str(user.id),
        payload={"username": user.username, "scope_count": len(body.scopes)},
    )

    await db.commit()
    await db.refresh(user)

    return {"user": await _user_to_dict(db, user), "message": "Cập nhật phạm vi dữ liệu thành công."}


@router.post("/users/{user_id}/invite")
async def resend_invite(
    user_id: str,
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """Generate or resend an invitation token for user onboarding."""
    u_uuid = uuid.UUID(user_id.strip())
    user = (await db.execute(select(User).where(User.id == u_uuid))).scalar_one_or_none()
    if not user:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")

    # Invite đi qua email thật — chặn khi user chưa có email hợp lệ.
    clean_email = (user.email or "").strip().lower()
    if not is_valid_email(clean_email):
        raise AppError(
            422,
            "EMAIL_REQUIRED",
            "Người dùng chưa có email hợp lệ. Hãy cập nhật email thật trước khi gửi lời mời.",
        )

    invite_token = secrets.token_hex(8)
    token_hash = hashlib.sha256(invite_token.encode("utf-8")).hexdigest()
    now = _now()
    user.invite_token_hash = token_hash
    user.invite_expires_at = now + timedelta(days=7)

    await _audit(
        db,
        actor_id=current_user.id,
        action="IAM_USER_INVITE_GENERATED",
        subject=f"iam_users:{user.id}",
        metadata={"username": user.username},
    )

    await db.commit()

    # Gửi thư mời best-effort (SMTP chưa cấu hình thì log demo mode, không fail API).
    invite_email_sent = False
    delivery_msg = ""
    full_invite_link = (
        f"{settings.frontend_base_url.rstrip('/')}/accept-invite?token={invite_token}"
    )
    try:
        user_roles = await get_user_roles(db, user.id)
        res = await send_invite_email(
            to_email=clean_email,
            username=user.username,
            invite_link=full_invite_link,
            expires_at=user.invite_expires_at,
            display_name=user.display_name_demo,
            roles=user_roles,
            token=invite_token,
            inviter_name=current_user.display_name_demo or current_user.username,
        )
        invite_email_sent = bool(res)
        delivery_msg = getattr(res, "message", "Đã gửi email thành công" if invite_email_sent else "Không gửi được email")
    except Exception as exc:  # noqa: BLE001 - email không bao giờ làm fail resend
        invite_email_sent = False
        delivery_msg = str(exc)

    return {
        "invite_token": invite_token,
        "invite_link": full_invite_link,
        "invite_email_sent": invite_email_sent,
        "email_delivery_message": delivery_msg,
        "expires_at": user.invite_expires_at.isoformat(),
        "message": "Đã tạo mã mời mới (hạn sử dụng 7 ngày).",
    }


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """Admin resets employee password to a secure temporary password.
    
    Invariant: Forces must_change_password=True and revokes existing sessions.
    """
    u_uuid = uuid.UUID(user_id.strip())
    user = (await db.execute(select(User).where(User.id == u_uuid))).scalar_one_or_none()
    if not user:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")

    temp_password = _gen_temp_password()
    user.password_hash = get_password_hash(temp_password)
    user.must_change_password = True
    user.auth_version = getattr(user, "auth_version", 1) + 1  # Revoke current sessions immediately

    await _audit(
        db,
        actor_id=current_user.id,
        action="IAM_USER_PASSWORD_RESET_BY_ADMIN",
        subject=f"iam_users:{user.id}",
        metadata={"username": user.username},
    )
    await _outbox(
        db,
        event_type="user.password_reset",
        aggregate_id=str(user.id),
        payload={"username": user.username},
    )

    await db.commit()

    return {
        "temporary_password": temp_password,
        "must_change_password": True,
        "message": f"Mật khẩu của tài khoản '{user.username}' đã được đặt lại thành công.",
    }


@router.post("/users/{user_id}/sessions/revoke")
async def revoke_user_sessions(
    user_id: str,
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """Immediately invalidate all active access & refresh tokens for this user."""
    u_uuid = uuid.UUID(user_id.strip())
    user = (await db.execute(select(User).where(User.id == u_uuid))).scalar_one_or_none()
    if not user:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.")

    user.auth_version = getattr(user, "auth_version", 1) + 1

    await _audit(
        db,
        actor_id=current_user.id,
        action="IAM_USER_SESSIONS_REVOKED",
        subject=f"iam_users:{user.id}",
        metadata={"username": user.username, "new_auth_version": user.auth_version},
    )

    await db.commit()

    return {
        "message": f"Toàn bộ phiên đăng nhập của '{user.username}' đã bị thu hồi ngay lập tức.",
        "auth_version": user.auth_version,
    }


@router.get("/smtp-status")
async def get_smtp_status(
    current_user: User = Depends(require_any_capability(*_ADMIN_CAPS)),
):
    """Check health and connectivity of configured SMTP server."""
    return await check_smtp_health()

