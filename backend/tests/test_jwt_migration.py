"""P1.15 (ADR 023): Migration `python-jose` -> `joserfc`.

DoD:
- ADR 023 co ban.
- pyproject.toml da thay python-jose bang joserfc + authlib.
- Unit test bao ham: roundtrip encode/decode, chua token bi sua doi/het han,
  va fail-start-up khi thieu signing key o moi truong production.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.core.jwt import JWTError, decode, encode


def test_python_jose_removed_joserfc_added():
    """pyproject.toml khong con python-jose, da them joserfc + authlib."""
    import tomllib

    pyproject = os.path.join(
        os.path.dirname(__file__), "..", "pyproject.toml"
    )
    with open(pyproject, "rb") as fh:
        data = tomllib.load(fh)
    deps = data["tool"]["poetry"]["dependencies"]
    assert "python-jose" not in deps, "python-jose can duoc phai xoa khoi dependencies"
    assert "joserfc" in deps, "joserfc can duoc them vao dependencies"
    assert "authlib" in deps, "authlib can duoc them vao dependencies"


def test_jwt_roundtrip_access_token():
    """encode sau decode tro lai duoc claims, exp la int JSON-safe."""
    now = datetime.now(UTC)
    token = encode(
        {"sub": "user-1", "username": "maker", "type": "access"},
        expires_delta=timedelta(minutes=30),
    )
    assert isinstance(token, str) and token.count(".") == 2
    claims = decode(token)
    assert claims["sub"] == "user-1"
    assert claims["username"] == "maker"
    assert claims["type"] == "access"
    assert isinstance(claims["exp"], int)
    assert claims["exp"] > int(now.timestamp())


def test_jwt_roundtrip_refresh_token():
    token = encode(
        {"sub": "user-1", "type": "refresh"},
        expires_delta=timedelta(days=7),
    )
    claims = decode(token)
    assert claims["type"] == "refresh"
    assert isinstance(token, str)


def test_jwt_decode_rejects_tampered_token():
    """Sua doi cuoi chuoi token -> JWTError (chua ky)."""
    token = encode({"sub": "user-1"}, expires_delta=timedelta(minutes=30))
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(JWTError):
        decode(tampered)


def test_jwt_decode_rejects_bad_token():
    """Chuoi khong phai JWT -> JWTError."""
    with pytest.raises(JWTError):
        decode("not.a.jwt.token")


def test_jwt_decode_rejects_expired_when_verify_exp():
    """Token het han, verify_exp=True (mac dinh) -> JWTError."""
    token = encode(
        {"sub": "user-1"},
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(JWTError):
        decode(token, verify_exp=True)


def test_jwt_decode_expired_allowed_when_verify_exp_false():
    """Token het han, verify_exp=False (dung cho revocation) van lay duoc claims."""
    token = encode(
        {"sub": "user-1"},
        expires_delta=timedelta(seconds=-1),
    )
    claims = decode(token, verify_exp=False)
    assert claims["sub"] == "user-1"


def test_fail_startup_production_without_signing_key(monkeypatch):
    """O moi truong production khong co BANKOPS_SIGNING_KEY -> app khong khoi duoc."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("BANKOPS_SIGNING_KEY", raising=False)
    monkeypatch.delenv("BANKOPS_dev_signing_key", raising=False)
    settings = Settings()
    with pytest.raises(RuntimeError, match="JWT signing key"):
        settings.assert_runtime_secrets()
