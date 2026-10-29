"""JWT helpers trên `joserfc` (ADR 023 — thay thế cho `python-jose`).

API ổn định dùng chung cho toàn bộ ứng dụng:
- `encode(payload, expires_delta, algorithm)` -> chuỗi JWT
- `decode(token, algorithms, verify_exp)` -> dict claims (ném JWTError khi sai)
- `JWTError` (thay cho `jose.JWTError`)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from joserfc import jwt as _joserfc_jwt
from joserfc.errors import BadSignatureError, DecodeError, JoseError
from joserfc.jwk import OctKey

from app.config import settings

__all__ = ["JWTError", "encode", "decode"]


class JWTError(Exception):
    """Lỗi mã hóa/giải mã JWT (thay cho `jose.JWTError`)."""


def _signing_key() -> OctKey:
    return OctKey.import_key(settings.signing_key.encode("utf-8"))


def encode(
    payload: dict[str, Any],
    expires_delta: timedelta | None = None,
    algorithm: str | None = None,
) -> str:
    """Mã hóa `payload` thành JWT chuỗi.

    `exp` nếu là `datetime` sẽ được chuyển thành epoch int (JSON-safe).
    Mặc định bổ sung trường `type` nếu payload chưa có.
    """
    to_encode = dict(payload)
    exp = to_encode.get("exp")
    if exp is None:
        expire = datetime.now(UTC) + (
            expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
        )
        to_encode["exp"] = int(expire.timestamp())
    elif isinstance(exp, datetime):
        to_encode["exp"] = int(exp.timestamp())
    to_encode.setdefault("type", "access")
    alg = algorithm or settings.jwt_algorithm
    header = {"alg": alg, "typ": "JWT"}
    return _joserfc_jwt.encode(
        header, to_encode, _signing_key(), algorithms=[alg]
    )


def decode(
    token: str,
    algorithms: list[str] | None = None,
    verify_exp: bool = True,
) -> dict[str, Any]:
    """Giải mã JWT và trả về dict claims.

    `verify_exp=False` dùng cho thu hồi token (vẫn kiểm tra chữ ký, không kiểm tra hạn).
    """
    try:
        token_obj = _joserfc_jwt.decode(
            token,
            _signing_key(),
            algorithms=algorithms or [settings.jwt_algorithm],
        )
    except (BadSignatureError, DecodeError, JoseError) as exc:  # noqa: BLE001
        raise JWTError(str(exc)) from exc
    claims = dict(token_obj.claims)
    if verify_exp:
        exp = claims.get("exp")
        if exp is not None and datetime.now(UTC).timestamp() > float(exp):
            raise JWTError("Token hết hạn")
    return claims
