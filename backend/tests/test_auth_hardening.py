"""P1.14: Auth hardening (refresh-token rotation, logout-revoke, rate-limit).

TDD: test truoc, chay xanh. Test o muc ham auth_utils (bo nho), khong can DB.
"""

from __future__ import annotations

import time

from app.api.routes.auth_utils import (
    _revoked_token_hashes,
    _token_hash,
    create_access_token,
    create_refresh_token,
    is_token_revoked,
    login_rate_limited,
    login_retry_after_seconds,
    purge_expired_revocations,
    record_login_failure,
    reset_login_failures,
    revoke_token,
)
from app.core.jwt import decode


def test_refresh_token_rotation_revokes_old_token():
    """Refresh token cu bi thu hoi sau rotation -> replay bi chua."""
    refresh = create_refresh_token({"sub": "user-1", "username": "maker"})
    assert not is_token_revoked(refresh)
    revoke_token(refresh)
    assert is_token_revoked(refresh)
    # Token khac (khong bi revoke) van hop le
    other = create_refresh_token({"sub": "user-2"})
    assert not is_token_revoked(other)
    assert decode(other, verify_exp=False)["sub"] == "user-2"


def test_logout_revokes_access_token():
    """Logout dua access token vao denylist."""
    access = create_access_token({"sub": "user-2"})
    assert not is_token_revoked(access)
    revoke_token(access)
    assert is_token_revoked(access)


def test_login_rate_limit_locks_after_n_failures():
    from app.config import settings

    username = "attacker"
    ip = "10.0.0.1"
    reset_login_failures(username, ip)
    for _ in range(settings.rate_limit_login_attempts):
        record_login_failure(username, ip)
    assert login_rate_limited(username, ip)
    assert login_retry_after_seconds(username, ip) >= 1


def test_login_rate_limit_is_per_username_and_ip():
    reset_login_failures("victim", None)
    reset_login_failures("attacker", "1.2.3.4")
    for _ in range(10):
        record_login_failure("attacker", "1.2.3.4")
    assert login_rate_limited("attacker", "1.2.3.4")
    assert not login_rate_limited("victim", "1.2.3.4")


def test_reset_login_failures_clears_lock():
    reset_login_failures("user-3", "9.9.9.9")
    for _ in range(20):
        record_login_failure("user-3", "9.9.9.9")
    assert login_rate_limited("user-3", "9.9.9.9")
    reset_login_failures("user-3", "9.9.9.9")
    assert not login_rate_limited("user-3", "9.9.9.9")


def test_purge_removes_expired_revocations():
    """Entry het han trong denylist bi xoa bo; entry con han duoc giu nguyen."""
    _revoked_token_hashes.clear()
    # Entry het han (exp trong qua khua)
    _revoked_token_hashes[_token_hash("expired-token")] = time.time() - 100
    # Entry con han (exp 7 ngay tro den)
    _revoked_token_hashes[_token_hash("live-token")] = time.time() + 7 * 86400
    assert is_token_revoked("expired-token")
    purge_expired_revocations()
    assert not is_token_revoked("expired-token")
    assert is_token_revoked("live-token")
