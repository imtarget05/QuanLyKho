"""Google Sign-In: verify ID token, find-or-create user, issue BankOps JWTs.

Flow (Flutter `google_sign_in` -> ID token -> this endpoint):
  1. `POST /auth/google {"id_token": "..."}`
  2. Verify signature/expiry/issuer/audience with Google certs (`google-auth`).
  3. Require `email_verified=true`.
  4. Find-or-create user by email (= username): first sight = signup
     (role `staff`), later = login.
  5. Issue BankOps access (30 min) + refresh (7 days) JWTs, same shape as
     password login. `sub` is always `str(user.id)` (UUID is not JSON
     serializable for `jwt.encode`).

Errors follow the docs/06:44 envelope directly (this router does not rely on
the app-wide handler, which does not exist yet).

Secrets: only the OAuth *client IDs* (public identifiers) live here/in config.
The web *client secret* is never needed for the ID-token flow and must never
be committed — it stays in server env for a future code-exchange flow.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth_utils import (
    create_access_token,
    create_refresh_token,
    get_user_capabilities,
    get_user_roles,
)
from app.config import settings
from app.database import get_db
from app.models.iam import Role, User, UserRole, UserStatus

router = APIRouter()

GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class GoogleLoginIn(BaseModel):
    id_token: str | None = Field(default=None, description="Google OpenID Connect ID token")
    access_token: str | None = Field(default=None, description="Google OAuth2 access token")

    @model_validator(mode="after")
    def validate_tokens(self) -> GoogleLoginIn:
        if self.id_token is not None:
            self.id_token = self.id_token.strip() or None
        if self.access_token is not None:
            self.access_token = self.access_token.strip() or None

        if not self.id_token and not self.access_token:
            raise ValueError("Phải cung cấp id_token hoặc access_token")

        if self.id_token and len(self.id_token) < 10:
            raise ValueError("id_token quá ngắn (tối thiểu 10 ký tự)")

        if self.access_token and len(self.access_token) < 10:
            raise ValueError("access_token quá ngắn (tối thiểu 10 ký tự)")

        return self


def error_envelope(code: str, message: str, http_status: int, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": uuid.uuid4().hex,
                "details": details or {},
            }
        },
    )


def verify_google_id_token(id_token: str) -> dict:
    """Verify signature/expiry/issuer/audience. Raises ValueError when invalid."""
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    last_error: Exception | None = None
    for audience in settings.google_allowed_audiences:
        try:
            return google_id_token.verify_oauth2_token(
                id_token, google_requests.Request(), audience
            )
        except ValueError as exc:
            last_error = exc
    raise ValueError(f"Google ID token verification failed: {last_error}")


def verify_google_access_token(access_token: str) -> dict:
    """Verify Google access token using tokeninfo endpoint and userinfo."""
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    url = f"https://oauth2.googleapis.com/tokeninfo?access_token={urllib.parse.quote(access_token)}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Google access token verification failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Google verification network error: {exc}") from exc

    aud = data.get("audience") or data.get("issued_to") or data.get("aud") or data.get("azp")
    if aud and aud not in settings.google_allowed_audiences:
        raise ValueError(f"Audience {aud} not allowed")

    verified = (
        data.get("email_verified") is True
        or data.get("email_verified") == "true"
        or data.get("verified_email") is True
        or data.get("verified_email") == "true"
    )
    email = data.get("email")

    name = "Google User"
    try:
        userinfo_req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(userinfo_req, timeout=10) as resp:
            userinfo = json.loads(resp.read().decode())
            name = userinfo.get("name") or name
            if userinfo.get("email"):
                email = userinfo.get("email")
            if (
                userinfo.get("email_verified") is True
                or userinfo.get("email_verified") == "true"
            ):
                verified = True
    except Exception:
        pass

    if not verified and email and (email.endswith("@gmail.com") or email.endswith("@googlemail.com")):
        verified = True

    return {
        "iss": "https://accounts.google.com",
        "sub": data.get("user_id") or data.get("sub"),
        "email": email,
        "email_verified": verified,
        "name": name,
    }


@router.post("/google")
async def login_with_google(
    body: GoogleLoginIn,
    db: AsyncSession = Depends(get_db),
):
    """Login or signup with a Google ID token or access token (upsert by email)."""
    info: dict | None = None

    raw_token = (body.id_token or body.access_token or "").strip()
    if raw_token.startswith("mock-"):
        # Token `mock-` KHÔNG phải credential thật: ngoài chế độ demo bật
        # tường minh thì từ chối, nếu không ai cũng tự tạo user (và nhận
        # role admin) chỉ bằng một chuỗi bất kỳ.
        if not settings.is_demo_mode:
            return error_envelope(
                "GOOGLE_TOKEN_INVALID",
                "Google token không hợp lệ hoặc hết hạn.",
                401,
            )
        parts = raw_token.split(":")
        email = parts[1] if len(parts) > 1 else "demo_google@khotrasua.internal"
        name = parts[2] if len(parts) > 2 else "Google Demo User"
        info = {
            "iss": "https://accounts.google.com",
            "sub": f"mock-sub-{email}",
            "email": email,
            "email_verified": True,
            "name": name,
        }
    else:
        if body.id_token and len(body.id_token) >= 10:
            try:
                info = verify_google_id_token(body.id_token)
            except ValueError:
                info = None
            except Exception:  # noqa: BLE001 - network/cert failure must not 500 raw
                return error_envelope(
                    "GOOGLE_VERIFICATION_UNAVAILABLE",
                    "Không xác thực được với Google lúc này, thử lại sau.",
                    503,
                )

        if info is None and body.access_token and len(body.access_token) >= 10:
            try:
                info = verify_google_access_token(body.access_token)
            except ValueError:
                info = None
            except Exception:
                return error_envelope(
                    "GOOGLE_VERIFICATION_UNAVAILABLE",
                    "Không xác thực được với Google lúc này, thử lại sau.",
                    503,
                )

    if info is None:
        return error_envelope(
            "GOOGLE_TOKEN_INVALID",
            "Google token không hợp lệ hoặc hết hạn.",
            401,
        )

    if info.get("iss") not in GOOGLE_ISSUERS:
        return error_envelope("GOOGLE_TOKEN_INVALID", "Issuer không phải Google.", 401)
    email = (info.get("email") or "").strip().lower()
    if not email:
        return error_envelope("GOOGLE_EMAIL_MISSING", "ID token thiếu email.", 401)
    is_verified = (
        info.get("email_verified") is True
        or info.get("email_verified") == "true"
        or email.endswith("@gmail.com")
        or email.endswith("@googlemail.com")
    )
    if not is_verified:
        return error_envelope(
            "GOOGLE_EMAIL_UNVERIFIED",
            "Email Google chưa được xác minh.",
            401,
            {"email": email},
        )

    # Search user by email or username, prioritizing exact email match
    result = await db.execute(
        select(User)
        .where((User.email == email) | (User.username == email))
        .order_by(case((User.email == email, 1), else_=2))
    )
    user = result.scalars().first()
    is_new_user = user is None

    admin_email_set = {e.lower().strip() for e in settings.admin_emails}
    is_superadmin = email.lower().strip() in admin_email_set

    if is_new_user:
        new_id = uuid.uuid4()
        display_name = str(info.get("name") or email)
        user = User(
            id=new_id,
            username=email,
            email=email,
            password_hash=f"GOOGLE_OAUTH_NO_PASSWORD:{uuid.uuid4()}",
            status=UserStatus.active,
            display_name_demo=display_name,
        )
        db.add(user)
        # S9/A1 — user Google MOI chỉ được `staff`: KHÔNG tự cấp
        # `inventory_manager` (có `inventory:approve_request`) vì sẽ phá
        # nguyên tắc maker != checker. Quyền duyệt do admin cấp qua
        # `/admin/users/{id}/roles`.
        initial_roles = (
            ["admin", "inventory_manager", "approver", "system_admin"]
            if is_superadmin
            else ["staff"]
        )
        for role_code in initial_roles:
            role = (
                await db.execute(select(Role).where(Role.code == role_code))
            ).scalar_one_or_none()
            if role is not None:
                db.add(UserRole(user_id=new_id, role_code=role_code))
        await db.commit()
        await db.refresh(user)
    # S9 — user ĐÃ tồn tại: KHÔNG tự cấp/thay đổi role. Vai trò chỉ do admin
    # cấp qua `/admin/users/{id}/roles` (tránh leo thang đặc quyền qua OAuth).

    if user.status != UserStatus.active and user.status != "active":
        return error_envelope(
            "ACCOUNT_LOCKED",
            "Tài khoản đã bị khóa hoặc ngừng hoạt động.",
            403,
            {"email": email},
        )

    roles = await get_user_roles(db, user.id)
    capabilities = await get_user_capabilities(db, user.id)
    access_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        {
            "sub": str(user.id),
            "username": user.username,
            "roles": roles,
            "caps": capabilities,
            "auth_version": getattr(user, "auth_version", 1),
            "branch_id": str(user.branch_id) if getattr(user, "branch_id", None) else None,
        },
        access_expires,
    )
    refresh_token = create_refresh_token(
        {
            "sub": str(user.id),
            "username": user.username,
            "auth_version": getattr(user, "auth_version", 1),
        },
        timedelta(days=settings.refresh_token_expire_days),
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": int(access_expires.total_seconds()),
        "is_new_user": is_new_user,
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email or email,
            "display_name": user.display_name_demo,
            "roles": roles,
            "capabilities": capabilities,
        },
    }
