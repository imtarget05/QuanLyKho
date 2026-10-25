"""Auth utilities and token management."""

import hashlib
import ipaddress
import logging
import os
import time
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.iam import (
    Capability,
    RoleCapability,
    ScopeGrant,
    User,
    UserRole,
    UserStatus,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

logger = logging.getLogger("bankops.auth")

# S13 — `must_change_password` phai duoc ENFORCE, khong phai chi la co.
# Cac endpoint duoc phep tiep tuc la nhung endpoint auth can thiet de user
# biet trang thai va doi mat khau (doi mat khau lan dau / doi mat khau /
# xem ho so / logout). Moi duong dan kiem tra bang SUFFIX nen ap dung ca
# `/auth/me` va `/api/v1/auth/me` (app mount 2 lan: co va khong co prefix).
_PASSWORD_CHANGE_EXEMPT_PATHS = (
    "/auth/me",
    "/auth/change-initial-password",
    "/auth/change-password",
    "/auth/logout",
    "/me",
)


def _is_password_change_exempt(path: str | None) -> bool:
    """`True` neu request duoc phep di tiep khi user chua doi mat khau.

    Khong co path (goi noi bo qua token thu) -> KHONG duoc exemption: user con
    mat khau tam thoi thi phai bi chan o moi duong dan nghiep vu.
    """
    if not path:
        return False
    normalized = path.rstrip("/") or path
    return any(normalized.endswith(exempt) for exempt in _PASSWORD_CHANGE_EXEMPT_PATHS)

# --- Token revocation (in-memory demo scope; thay Redis/DB khi scale) ---
_revoked_token_hashes: dict[str, float] = {}  # sha256(token) -> exp epoch


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def revoke_token(token: str) -> None:
    """Đưa token vào denylist tới khi nó tự hết hạn (logout/refresh rotation)."""
    try:
        payload = jwt.decode(
            token, settings.signing_key, algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
        exp = float(payload.get("exp", 0))
    except JWTError:
        return
    _revoked_token_hashes[_token_hash(token)] = exp
    purge_expired_revocations()


def is_token_revoked(token: str) -> bool:
    return _token_hash(token) in _revoked_token_hashes


def purge_expired_revocations() -> None:
    now = time.time()
    for key in [k for k, exp in _revoked_token_hashes.items() if exp < now]:
        del _revoked_token_hashes[key]


# --------------------------------------------------------------------------
# Client IP resolution (reverse proxy) — an toàn, fail-closed
# --------------------------------------------------------------------------
# Sau nginx / Cloudflare / Traefik, mọi request đều đến từ IP của proxy ->
# nếu lấy `request.client.host` thì MỌI user bị gộp cùng một IP và khoá
# rate-limit theo IP trở nên vô hiệu (hoặc oan).
#
# Nhưng đọc `X-Forwarded-For` một cách mù quáng lại cho phép client giả mạo
# IP để né rate-limit. Vì vậy:
#   - MẶC ĐỊNH: KHÔNG tin header nào -> dùng IP peer thật (fail-closed).
#   - Chỉ khi deploy cấu hình proxy đáng tin mới đọc `X-Forwarded-For`:
#       * `TRUSTED_PROXY_IPS`  : danh sách IP/CIDR của proxy (peer phải nằm
#                                trong danh sách mới được tin).
#       * `TRUSTED_PROXY_COUNT`: số proxy đáng tin trong chuỗi (tính cả proxy
#                                trực tiếp kết nối vào app) -> IP client là
#                                entry thứ `len(hops) - count` của XFF.
#   - Ngoài ra uvicorn có `--forwarded-allow-ips` (cấu hình ở `entrypoint.sh`
#     qua env `FORWARDED_ALLOW_IPS`): khi bật, uvicorn tự sửa `scope["client"]`
#     -> `request.client.host` đã là IP client thật, không cần header nào.
_TRUSTED_PROXY_IPS_ENV = "TRUSTED_PROXY_IPS"
_TRUSTED_PROXY_COUNT_ENV = "TRUSTED_PROXY_COUNT"


def _peer_ip(request: Request | None) -> str:
    """IP thật của kết nối TCP (không qua header nào)."""
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    return (host or "unknown").strip().lower()


def _trusted_proxy_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse `TRUSTED_PROXY_IPS` (danh sách IP/CIDR, phân tách bằng dấu phẩy)."""
    raw = (os.environ.get(_TRUSTED_PROXY_IPS_ENV) or "").strip()
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for chunk in raw.split(","):
        item = chunk.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning(
                "Bỏ qua %s không hợp lệ trong %s", item, _TRUSTED_PROXY_IPS_ENV
            )
    return networks


def _trusted_proxy_count() -> int:
    """Số proxy đáng tin trong chuỗi (>= 0)."""
    raw = (os.environ.get(_TRUSTED_PROXY_COUNT_ENV) or "").strip()
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("%s không phải số nguyên: %r", _TRUSTED_PROXY_COUNT_ENV, raw)
        return 0


def _ip_in_networks(ip: str, networks: list) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for network in networks:
        try:
            if addr in network:
                return True
        except TypeError:  # khác họ IPv4/IPv6 -> không trùng
            continue
    return False


def _forwarded_hops(request: Request | None) -> list[str]:
    """Các hop trong `X-Forwarded-For` (client đứng đầu, proxy gần nhất cuối)."""
    raw = (request.headers.get("x-forwarded-for") or "") if request is not None else ""
    return [hop.strip().lower() for hop in raw.split(",") if hop.strip()]


def client_ip(request: Request | None) -> str:
    """IP client thật, an toàn (fail-closed).

    - Không cấu hình proxy đáng tin -> trả IP peer, **bỏ qua** `X-Forwarded-For`
      (client tự gửi header để giả mạo IP sẽ không đổi được kết quả).
    - `TRUSTED_PROXY_IPS` -> chỉ tin XFF khi IP peer nằm trong danh sách; IP
      lấy là hop gần nhất KHÔNG thuộc danh sách proxy.
    - `TRUSTED_PROXY_COUNT` -> chỉ tin XFF khi peer là proxy đáng tin; IP lấy
      là hop thứ `len(hops) - count` (số proxy tính cả peer).

    Ghi chú tích hợp: `auth.py::_client_ip` (nơi tính IP cho rate-limit login)
    nên gọi hàm này. Hiện tại `auth.py` nằm ngoài phạm vi sửa của bước này,
    nên IP client thật được lấy ở TẦNG SERVER: `entrypoint.sh` truyền
    `--forwarded-allow-ips` cho uvicorn -> uvicorn tự sửa `scope["client"]`
    thành IP client thật, nên `request.client.host` đã đúng mà không cần tin
    header nào ở tầng app.
    """
    peer = _peer_ip(request)
    networks = _trusted_proxy_networks()
    count = _trusted_proxy_count()
    if not networks and count <= 0:
        # Không cấu hình -> KHÔNG tin header nào.
        return peer

    hops = _forwarded_hops(request)
    if not hops:
        return peer

    if count > 0:
        # Số proxy đáng tin = count (tính cả peer). Chuỗi XFF phải đủ hop thì
        # mới xác định được IP client; không đủ -> giữ IP peer (fail-closed).
        if len(hops) < count:
            return peer
        return hops[len(hops) - count]

    # Danh sách IP proxy: peer phải là proxy đáng tin, và ta lấy hop gần nhất
    # KHÔNG phải proxy (tức là IP client thật).
    if not _ip_in_networks(peer, networks):
        return peer
    for hop in reversed(hops):
        if not _ip_in_networks(hop, networks):
            return hop
    return hops[-1]


# --- Login rate limiting (docs/08: 5 lần / 15 phút, khóa tạm khi brute force) ---
# S11: khoá theo `username + IP` (không chỉ username) để attacker không khoá
# được tài khoản của người khác chỉ bằng cách đoán sai mật khẩu (DoS). Bộ đếm
# mặc định nằm trong RAM; nếu `REDIS_URL` được cấu hình thì dùng Redis (client
# `redis` đã có sẵn trong dependencies) để bộ đếm dùng chung giữa nhiều
# replica, tự động fallback về RAM nếu Redis lỗi.
_login_failures: dict[str, list[float]] = {}
_redis_client = None
_redis_resolved = False


def _get_redis_client():
    """Redis client cho rate limit (None nếu chưa cấu hình `REDIS_URL`)."""
    global _redis_client, _redis_resolved
    if _redis_resolved:
        return _redis_client
    _redis_resolved = True
    url = (os.environ.get("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        _redis_client = redis.Redis.from_url(
            url, socket_connect_timeout=0.25, socket_timeout=0.25
        )
    except Exception as exc:  # noqa: BLE001 - thiếu client/URL sai -> fallback RAM
        logger.warning("Không dùng được Redis cho rate limit: %s", exc)
        _redis_client = None
    return _redis_client


def _redis_key(rate_key: str) -> str:
    return "auth:login_fail:" + hashlib.sha256(rate_key.encode("utf-8")).hexdigest()


def _rate_key(username: str, ip: str | None = None) -> str:
    """Khoá rate limit = username (chu lower) + IP nguon ket noi."""
    user = username.strip().lower()
    return f"{user}|{(ip or 'unknown').strip().lower()}"


def login_rate_limited(username: str, ip: str | None = None) -> bool:
    window = settings.rate_limit_login_window_minutes * 60
    now = time.time()
    key = _rate_key(username, ip)

    client = _get_redis_client()
    if client is not None:
        try:
            count = int(client.get(_redis_key(key)) or 0)
            return count >= settings.rate_limit_login_attempts
        except Exception as exc:  # noqa: BLE001 - Redis lỗi -> fallback RAM
            logger.warning("Redis rate limit lỗi, fallback RAM: %s", exc)

    recent = [t for t in _login_failures.get(key, []) if now - t < window]
    _login_failures[key] = recent
    return len(recent) >= settings.rate_limit_login_attempts


def record_login_failure(username: str, ip: str | None = None) -> None:
    window = settings.rate_limit_login_window_minutes * 60
    key = _rate_key(username, ip)

    client = _get_redis_client()
    if client is not None:
        try:
            rkey = _redis_key(key)
            client.incr(rkey)
            client.expire(rkey, window)
            return
        except Exception as exc:  # noqa: BLE001 - Redis lỗi -> fallback RAM
            logger.warning("Redis rate limit lỗi, fallback RAM: %s", exc)

    _login_failures.setdefault(key, []).append(time.time())


def reset_login_failures(username: str, ip: str | None = None) -> None:
    """Xoá bộ đếm sai của user (theo IP nếu có, nếu không thì xoá hết các IP)."""
    user = username.strip().lower()
    key = _rate_key(username, ip)

    client = _get_redis_client()
    if client is not None:
        try:
            client.delete(_redis_key(key))
        except Exception as exc:  # noqa: BLE001 - Redis lỗi -> fallback RAM
            logger.warning("Redis rate limit lỗi, fallback RAM: %s", exc)

    if ip is None:
        for stale in [k for k in list(_login_failures) if k.split("|", 1)[0] == user]:
            _login_failures.pop(stale, None)
    else:
        _login_failures.pop(key, None)


def login_retry_after_seconds(username: str, ip: str | None = None) -> int:
    """Số giây còn lại của khoá rate limit (>= 1) để trả header `Retry-After`."""
    window = settings.rate_limit_login_window_minutes * 60
    now = time.time()
    key = _rate_key(username, ip)

    client = _get_redis_client()
    if client is not None:
        try:
            ttl = int(client.ttl(_redis_key(key)))
            if ttl and ttl > 0:
                return ttl
            if ttl == -1:  # khoá không có TTL -> còn hiệu lực hết window
                return window
        except Exception as exc:  # noqa: BLE001 - Redis lỗi -> fallback RAM
            logger.warning("Redis rate limit lỗi, fallback RAM: %s", exc)

    failures = _login_failures.get(key, [])
    if not failures:
        return window
    oldest = min(failures)
    return max(1, int(window - (now - oldest)))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# --- In-memory OTP storage for password reset (username_lower -> (otp, expire_epoch)) ---
_password_reset_otps: dict[str, tuple[str, float]] = {}


def generate_password_reset_otp(username: str, ttl_seconds: int = 900) -> str:
    """Generate a secure 6-digit OTP for password reset."""
    import secrets
    otp = f"{secrets.randbelow(1_000_000):06d}"
    key = _rate_key(username)
    _password_reset_otps[key] = (otp, time.time() + ttl_seconds)
    return otp


def verify_password_reset_otp(username: str, otp: str) -> bool:
    """Verify and consume the OTP for password reset."""
    import secrets
    key = _rate_key(username)
    record = _password_reset_otps.get(key)
    if not record:
        return False
    stored_otp, expires_at = record
    if time.time() > expires_at:
        _password_reset_otps.pop(key, None)
        return False
    if secrets.compare_digest(stored_otp, otp.strip()):
        _password_reset_otps.pop(key, None)
        return True
    return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    # jwt.encode json-hóa payload; `sub` từ DB là UUID -> phải ép str trước.
    if isinstance(to_encode.get("sub"), uuid.UUID):
        to_encode["sub"] = str(to_encode["sub"])
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.signing_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if isinstance(to_encode.get("sub"), uuid.UUID):
        to_encode["sub"] = str(to_encode["sub"])
    expire = datetime.now(UTC) + (expires_delta or timedelta(days=settings.refresh_token_expire_days))
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.signing_key, algorithm=settings.jwt_algorithm)


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_roles(db: AsyncSession, user_id: str) -> list[str]:
    result = await db.execute(
        select(UserRole.role_code)
        .where(UserRole.user_id == user_id)
    )
    # Không có nhánh đặc biệt theo tên đăng nhập: vai trò chỉ đến từ
    # `iam_user_roles` trong DB (backdoor `demo_checker` đã bị gỡ).
    return [row[0] for row in result.all()]


async def get_user_capabilities(db: AsyncSession, user_id: str) -> list[str]:
    roles = await get_user_roles(db, user_id)
    if "root_admin" in roles:
        # root_admin is the explicit superuser role. Resolve against the live
        # catalog so capabilities introduced after migration 019 are included.
        result = await db.execute(select(Capability.code))
        return sorted(set(result.scalars().all()))
    result = await db.execute(
        select(Capability.code)
        .join(RoleCapability, RoleCapability.capability_code == Capability.code)
        .join(UserRole, UserRole.role_code == RoleCapability.role_code)
        .where(UserRole.user_id == user_id)
    )
    # Không cấp capability nào ngoài DB (backdoor `demo_checker` đã bị gỡ).
    return [row[0] for row in result.all()]


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User | None:
    user = await get_user_by_username(db, username)
    if not user:
        return None
    try:
        password_ok = verify_password(password, user.password_hash)
    except Exception:  # noqa: BLE001 - placeholder/corrupt hashes (e.g. OAuth users) must fail closed, never 500
        return None
    # Không có bypass mật khẩu: hash trong DB là nguồn sự thật duy nhất.
    if not password_ok:
        return None
    if user.status != "active":
        return None
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.signing_key, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        if payload.get("type") != "access":
            # Refresh token (7 ngày) không được dùng như access token (30 phút).
            raise credentials_exception
    except JWTError:
        raise credentials_exception from None

    if is_token_revoked(token):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    # Enforce user active status immediately (locked/inactive users blocked on next command)
    if user.status != UserStatus.active and user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị khóa hoặc ngừng hoạt động.",
        )

    # S13 — user còn mật khẩu tạm thời chưa được dùng nghiệp vụ.
    if getattr(user, "must_change_password", False) and not _is_password_change_exempt(
        getattr(request, "scope", {}).get("path") if request is not None else None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PASSWORD_CHANGE_REQUIRED",
                "message": (
                    "Tài khoản đang dùng mật khẩu tạm thời. "
                    "Hãy đổi mật khẩu tại /auth/change-initial-password trước khi dùng nghiệp vụ."
                ),
            },
        )

    # Enforce immediate session revocation via auth_version
    token_auth_version = payload.get("auth_version")
    if token_auth_version is not None and getattr(user, "auth_version", 1) != token_auth_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã bị thu hồi.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_user_scope_grants(db: AsyncSession, user_id: str | uuid.UUID) -> list[ScopeGrant]:
    """Retrieve currently active scope grants for user."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(ScopeGrant).where(
            ScopeGrant.user_id == user_id,
            or_(ScopeGrant.valid_from.is_(None), ScopeGrant.valid_from <= now),
            or_(ScopeGrant.valid_to.is_(None), ScopeGrant.valid_to >= now),
        )
    )
    return list(result.scalars().all())


async def check_user_scope(
    db: AsyncSession,
    user: User,
    branch_id: str | uuid.UUID | None = None,
    location_id: str | uuid.UUID | None = None,
) -> bool:
    """Checks if user has permission in the given branch or location."""
    roles = await get_user_roles(db, user.id)
    if any(r in ("admin", "system_admin", "root_admin") for r in roles):
        return True

    # User primary branch
    if branch_id and user.branch_id and str(user.branch_id) == str(branch_id):
        return True

    scopes = await get_user_scope_grants(db, user.id)
    for grant in scopes:
        if branch_id and grant.branch_id and str(grant.branch_id) == str(branch_id):
            return True
        if location_id and grant.location_id and str(grant.location_id) == str(location_id):
            return True
    return False


async def get_accessible_location_ids(
    db: AsyncSession, user: User
) -> set[uuid.UUID] | None:
    """Return allowed inventory locations, or ``None`` for administrators.

    Inventory read/write routes must filter at query time, rather than relying
    on the caller to supply a location that happens to be in their scope.
    """
    roles = await get_user_roles(db, user.id)
    if any(role in ("admin", "system_admin", "root_admin") for role in roles):
        return None

    from app.models.inventory import Location

    location_ids: set[uuid.UUID] = set()
    if user.branch_id:
        branch_locations = await db.execute(
            select(Location.id).where(Location.branch_id == user.branch_id)
        )
        location_ids.update(branch_locations.scalars().all())

    for grant in await get_user_scope_grants(db, user.id):
        if grant.location_id:
            location_ids.add(grant.location_id)
        if grant.branch_id:
            branch_locations = await db.execute(
                select(Location.id).where(Location.branch_id == grant.branch_id)
            )
            location_ids.update(branch_locations.scalars().all())
    return location_ids


async def get_accessible_cashbox_ids(
    db: AsyncSession, user: User
) -> set[uuid.UUID] | None:
    """Danh sách két tiền user được phép xem, hoặc ``None`` cho admin.

    S6 — két tiền là dữ liệu theo chi nhánh (``cash_boxes.branch_id``). Két
    chưa gán chi nhánh (``branch_id IS NULL``) là két dùng chung nên ai cũng
    thấy; két đã gán chi nhánh thì chỉ user của chi nhánh đó (hoặc user có
    scope grant chi nhánh tương ứng) mới thấy.
    """
    from app.models import schema_parity as _schema_parity  # noqa: F401 - map branch_id
    from app.models.cash_sim import CashBox

    roles = await get_user_roles(db, user.id)
    if any(role in ("admin", "system_admin", "root_admin") for role in roles):
        return None

    branch_ids: set[str] = set()
    if getattr(user, "branch_id", None):
        branch_ids.add(str(user.branch_id))
    for grant in await get_user_scope_grants(db, user.id):
        if grant.branch_id:
            branch_ids.add(str(grant.branch_id))

    rows = (await db.execute(select(CashBox.id, CashBox.__table__.c.branch_id))).all()
    visible: set[uuid.UUID] = set()
    for box_id, branch_id in rows:
        if branch_id is None or str(branch_id) in branch_ids:
            visible.add(box_id)
    return visible


async def get_user_from_token_string(token: str, db: AsyncSession) -> User:
    return await get_current_user(token, db)


async def get_current_user_with_capabilities(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
) -> tuple[User, list[str]]:
    user = await get_current_user(token, db, request)
    try:
        payload = jwt.decode(token, settings.signing_key, algorithms=[settings.jwt_algorithm])
        caps = payload.get("caps")
        if isinstance(caps, list):
            return user, caps
    except Exception:
        pass
    capabilities = await get_user_capabilities(db, user.id)
    return user, capabilities



def require_capability(*required_caps: str):
    async def check(
        user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    ):
        user, caps = user_caps
        for cap in required_caps:
            if cap not in caps:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing capability: {cap}",
                )
        return user
    return check


def require_any_capability(*accepted_caps: str):
    """User cần ít nhất một capability trong danh sách (deny by default)."""
    async def check(
        user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    ):
        user, caps = user_caps
        if not any(cap in caps for cap in accepted_caps):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing one of capabilities: {', '.join(accepted_caps)}",
            )
        return user
    return check
