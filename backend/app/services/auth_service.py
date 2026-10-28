"""Authentication / account service - user management, login."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.exceptions import DomainError
from app.models.iam import User as DomainUser
from app.models.iam import UserStatus
from app.repositories.role_repository import RoleRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository


@dataclass(frozen=True)
class User:
    """Frontend-facing user domain object."""
    id: str
    code: str
    name: str
    email: str
    role: str
    status: str
    avatar_url: str | None
    last_login_at: datetime | None
    created_at: datetime
    is_active: bool
    is_admin: bool


class AuthService:
    """Dịch vụ xác thực & quản lý người dùng."""

    def __init__(
        self,
        user_repo: UserRepository,
        role_repo: RoleRepository,
        session_repo: SessionRepository,
    ):
        self.user_repo = user_repo
        self.role_repo = role_repo
        self.session_repo = session_repo

    def _hash_password(self, password: str) -> str:
        """Băm mật khẩu với salt ngẫu nhiên."""
        salt = secrets.token_hex(16)
        hashed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100000,
        )
        return f"{salt}${hashed.hex()}"

    def _verify_password(self, password: str, stored: str) -> bool:
        try:
            salt, hashed = stored.split("$")
            check = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt.encode("utf-8"),
                100000,
            )
            return check.hex() == hashed
        except (ValueError, AttributeError):
            return False

    def _get_session_expiry(self) -> datetime:
        """Expired trong 7 ngày."""
    def register(
        self,
        user_id: str,
        email: str,
        password: str,
        name: str,
        role_code: str,
        phone: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        """Đăng ký người dùng mới."""
        # Kiểm tra email đã tồn tại
        existing = self.user_repo.get_by_email(email)
        if existing:
            raise DomainError("EMAIL_EXISTS", "Email đã được đăng ký")

        # Lấy role
        role = self.role_repo.get_by_code(role_code)
        if role is None:
            raise DomainError("ROLE_NOT_FOUND", f"Role '{role_code}' không tồn tại")

        # Tạo domain user
        domain_user = DomainUser.create(
            user_id=user_id,
            email=email,
            password_hash=self._hash_password(password),
            name=name,
            role_code=role_code,
            role_id=role.id.value,
            phone=phone,
            avatar_url=avatar_url,
            status=UserStatus.ACTIVE,
        )

        # Lưu
        saved = self.user_repo.add(domain_user)

        return self._to_user_domain(saved)

    def login(
        self,
        email: str,
        password: str,
    ) -> tuple[User, str]:
        """
        Đăng nhập.
        Return: (user, session_token)
        """
        # Tìm user
        user = self.user_repo.get_by_email(email)
        if user is None:
            raise DomainError("INVALID_CREDENTIALS", "Email hoặc mật khẩu không đúng")

        # Kiểm tra status
        if user.status != UserStatus.ACTIVE:
            raise DomainError("ACCOUNT_DISABLED", "Tài khoản đã bị khóa")

        # Kiểm tra mật khẩu
        if not self._verify_password(password, user.password_hash):
            raise DomainError("INVALID_CREDENTIALS", "Email hoặc mật khẩu không đúng")

        # Tạo session
        token = secrets.token_urlsafe(32)
        self.session_repo.create_session(
            user_id=user.id.value,
            token=token,
            expires_at=self._get_session_expiry(),
        )

        return self._to_user_domain(user), token
    def logout(self, token: str) -> bool:
        """Hết session."""
        return self.session_repo.delete_session(token)

    def change_password(
        self,
        user_id: str,
        old_password: str,
        new_password: str,
    ) -> None:
        """Đổi mật khẩu - yêu cầu mật khẩu cũ đúng."""
        user = self.user_repo.get(user_id)
        if user is None:
            raise DomainError("USER_NOT_FOUND", "Người dùng không tồn tại")

        if not self._verify_password(old_password, user.password_hash):
            raise DomainError("INVALID_CREDENTIALS", "Mật khẩu cũ không đúng")

        if old_password == new_password:
            raise DomainError("SAME_PASSWORD", "Mật khẩu mới trùng với mật khẩu cũ")

        user.password_hash = self._hash_password(new_password)
        self.user_repo.update(user)

    def get_user(self, user_id: str) -> User:
        """Lấy thông tin user."""
        user = self.user_repo.get(user_id)
        if user is None:
            raise DomainError("USER_NOT_FOUND", "Người dùng không tồn tại")
        return self._to_user_domain(user)

    def list_users(
        self,
        skip: int = 0,
        limit: int = 50,
        role_code: str | None = None,
        status: str | None = None,
    ) -> list[User]:
        """Danh sách người dùng."""
        users = self.user_repo.list(skip=skip, limit=limit, role_code=role_code, status=status)
        return [self._to_user_domain(u) for u in users]

    def _to_user_domain(self, domain: DomainUser) -> User:
        """Chuyển đổi domain user sang frontend user domain."""
        role = self.role_repo.get_by_code(domain.role_code)
        return User(
            id=domain.id.value,
            code=domain.code,
            name=domain.name,
            email=domain.email,
            role=domain.role_code,
            status=domain.status.value,
            avatar_url=domain.avatar_url,
            last_login_at=domain.last_login_at,
            created_at=domain.created_at,
            is_active=domain.status == UserStatus.ACTIVE,
            is_admin=role.is_admin if role else False,
        )

    def get_current_user_domain(self, token: str) -> DomainUser:
        """Lấy domain user từ session."""
        session = self.session_repo.get_session(token)
        if session is None:
            raise DomainError("SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn")
        user = self.user_repo.get(session.user_id)
        if user is None:
            raise DomainError("USER_NOT_FOUND", "Người dùng không tồn tại")
        return user
        return datetime.utcnow() + timedelta(days=7)