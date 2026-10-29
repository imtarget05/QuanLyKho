"""STEP 5 — IP client sau reverse proxy phải lấy AN TOÀN (fail-closed).

Residual: rate-limit dùng `request.client.host` (không đọc `X-Forwarded-For`
để tránh giả mạo) -> sau nginx/Cloudflare, MỌI request cùng 1 IP của proxy
=> khoá theo IP vô hiệu. Nhưng đọc `X-Forwarded-For` mù quáng thì client tự
giả mạo IP để né rate-limit.

Quy tắc (xem `app/api/routes/auth_utils.py::client_ip`):
- KHÔNG cấu hình proxy đáng tin -> bỏ qua `X-Forwarded-For`, dùng IP peer.
- `TRUSTED_PROXY_COUNT=N` -> chỉ tin XFF khi chuỗi đủ N hop; IP client là hop
  thứ `len(hops) - N`.
- `TRUSTED_PROXY_IPS` -> chỉ tin XFF khi IP peer nằm trong danh sách; IP lấy là
  hop gần nhất KHÔNG thuộc danh sách proxy.
"""
from __future__ import annotations

from app.api.routes.auth_utils import client_ip


class _FakeClient:
    def __init__(self, host: str):
        self.host = host


class _FakeRequest:
    def __init__(self, peer: str, xff: str | None = None):
        self.client = _FakeClient(peer)
        self.headers = {}
        if xff is not None:
            self.headers["x-forwarded-for"] = xff


def test_without_trusted_proxy_config_xff_is_ignored(monkeypatch):
    """Mặc định KHÔNG tin header -> IP lấy từ kết nối thật."""
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_COUNT", raising=False)
    req = _FakeRequest("10.0.0.1", "203.0.113.7, 198.51.100.2")
    assert client_ip(req) == "10.0.0.1", (
        "không cấu hình proxy đáng tin thì PHẢI bỏ qua X-Forwarded-For "
        "(client có thể tự gửi header để giả mạo IP)"
    )


def test_trusted_proxy_count_resolves_real_client_ip(monkeypatch):
    """`TRUSTED_PROXY_COUNT=1` -> IP client là hop gần nhất trong XFF."""
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    # client 203.0.113.7 -> proxy 198.51.100.2 -> app
    req = _FakeRequest("198.51.100.2", "203.0.113.7")
    assert client_ip(req) == "203.0.113.7"


def test_trusted_proxy_count_two_hops(monkeypatch):
    """`TRUSTED_PROXY_COUNT=2` -> bỏ qua 2 hop proxy, lấy IP client thật."""
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "2")
    # client -> p1 -> p2 -> app ; XFF = "client, p1"
    req = _FakeRequest("192.0.2.9", "203.0.113.7, 198.51.100.2")
    assert client_ip(req) == "203.0.113.7"


def test_trusted_proxy_count_requires_enough_hops(monkeypatch):
    """Chuỗi XFF không đủ hop -> fail-closed, giữ IP peer."""
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "3")
    req = _FakeRequest("192.0.2.9", "203.0.113.7")
    assert client_ip(req) == "192.0.2.9", (
        "không xác minh được chuỗi proxy thì KHÔNG được tin XFF"
    )


def test_trusted_proxy_ips_list(monkeypatch):
    """`TRUSTED_PROXY_IPS` -> chỉ tin XFF khi peer là proxy đáng tin."""
    monkeypatch.delenv("TRUSTED_PROXY_COUNT", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.1,10.0.0.2")
    req = _FakeRequest("10.0.0.1", "203.0.113.7, 198.51.100.2")
    assert client_ip(req) == "198.51.100.2", (
        "hop gần nhất KHÔNG phải proxy đáng tin -> đó là IP client thật"
    )


def test_trusted_proxy_ips_peer_not_trusted_ignores_xff(monkeypatch):
    """Peer KHÔNG nằm trong danh sách proxy -> bỏ qua XFF (chống giả mạo)."""
    monkeypatch.delenv("TRUSTED_PROXY_COUNT", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.1")
    req = _FakeRequest("203.0.113.66", "203.0.113.7, 198.51.100.2")
    assert client_ip(req) == "203.0.113.66"


def test_trusted_proxy_ips_supports_cidr(monkeypatch):
    """Danh sách proxy nhận cả CIDR."""
    monkeypatch.delenv("TRUSTED_PROXY_COUNT", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/24")
    req = _FakeRequest("10.0.0.5", "203.0.113.7")
    assert client_ip(req) == "203.0.113.7"


def test_no_xff_header_falls_back_to_peer(monkeypatch):
    """Không có header -> IP peer."""
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    req = _FakeRequest("192.0.2.9")
    assert client_ip(req) == "192.0.2.9"


def test_request_without_client_falls_back_to_unknown(monkeypatch):
    """Request không có `client` -> 'unknown' (không crash)."""
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_COUNT", raising=False)
    assert client_ip(None) == "unknown"


# ---------------------------------------------------------------------------
# B1.2 — `auth.py` (route login) PHẢI dùng chung chính sách fail-closed
# ---------------------------------------------------------------------------
class TestAuthRouteUsesSharedClientIp:
    """Route `/auth/login` tính IP cho rate-limit -> phải gọi `client_ip()`.

    Trước đây `auth.py` tự đọc `request.client.host` (bỏ qua `X-Forwarded-For`
    hoàn toàn) -> sau reverse proxy, MỌI request bị gộp về 1 IP của proxy
    => rate-limit theo IP vô hiệu. Nhưng đọc header mù quáng thì client tự
    giả mạo IP để né rate-limit. `auth_utils.client_ip()` đã implement
    fail-closed; `auth.py` phải dùng chính hàm đó (một nguồn duy nhất).
    """

    def test_auth_module_delegates_to_shared_helper(self, monkeypatch):
        """`_client_ip` của route auth = `auth_utils.client_ip` (nguồn duy nhất)."""
        from app.api.routes.auth_utils import client_ip as _client_ip

        # (a) không cấu hình -> bỏ qua XFF
        monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
        monkeypatch.delenv("TRUSTED_PROXY_COUNT", raising=False)
        assert auth_client_ip(_FakeRequest("10.0.0.1", "203.0.113.7, 198.51.100.2")) == "10.0.0.1"

        # (b) TRUSTED_PROXY_COUNT=1 -> IP client thật
        monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
        assert auth_client_ip(_FakeRequest("198.51.100.2", "203.0.113.7")) == "203.0.113.7"

        # (c) thiếu hop -> fail-closed, giữ IP peer
        monkeypatch.setenv("TRUSTED_PROXY_COUNT", "3")
        assert auth_client_ip(_FakeRequest("192.0.2.9", "203.0.113.7")) == "192.0.2.9"

        # (d) TRUSTED_PROXY_IPS + CIDR -> IP client thật
        monkeypatch.delenv("TRUSTED_PROXY_COUNT", raising=False)
        monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/24")
        assert auth_client_ip(_FakeRequest("10.0.0.5", "203.0.113.7")) == "203.0.113.7"

    def test_auth_module_does_not_duplicate_xff_policy(self):
        """`auth.py` không được tự đọc `request.client.host` (chính sách nhân bản)."""
        import pathlib

        src = pathlib.Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "auth.py"
        text = src.read_text(encoding="utf-8")
        assert "client_ip" in text, "auth.py phải dùng `client_ip` của auth_utils"
        assert (
            "request.client.host" not in text
        ), "auth.py không được tự đọc `request.client.host` — phải dùng `client_ip()`"
        assert (
            'headers.get("x-forwarded-for")' not in text.lower()
        ), (
            "auth.py không được tự đọc header `X-Forwarded-For` — chính sách "
            "trust-proxy chỉ nằm trong `auth_utils.client_ip`"
        )

    def test_login_rate_limit_keyed_by_resolved_client_ip(self, client, monkeypatch):
        """Rate-limit login phải khoá theo IP ĐÃ GIẢI QUYẾT (fail-closed).

        Không cấu hình proxy đáng tin -> mọi request dùng chung IP peer ->
        client tự gán `X-Forwarded-For` không né được rate-limit.
        """
        import uuid

        monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
        monkeypatch.delenv("TRUSTED_PROXY_COUNT", raising=False)

        username = f"ghost_{uuid.uuid4().hex[:12]}"
        payload = {"username": username, "password": "wrong-password"}

        # 5 lần sai -> lần sau phải bị 429
        for _ in range(5):
            r = client.post("/api/v1/auth/login", json=payload)
            assert r.status_code in (401, 429), r.text
        blocked = client.post("/api/v1/auth/login", json=payload)
        assert blocked.status_code == 429, (
            "sau 5 lần sai cùng IP peer thì phải bị rate-limit: "
            f"{blocked.status_code} {blocked.text}"
        )

        # IP khác (client tự gán XFF) -> KHÔNG được dùng để né rate-limit:
        # không có proxy đáng tin thì IP lấy từ peer -> vẫn bị khoá.
        spoofed = client.post(
            "/api/v1/auth/login",
            json=payload,
            headers={"X-Forwarded-For": "203.0.113.7"},
        )
        assert spoofed.status_code == 429, (
            "client tự gửi `X-Forwarded-For` KHÔNG được né rate-limit khi "
            "chưa cấu hình proxy đáng tin: "
            f"{spoofed.status_code} {spoofed.text}"
        )

    def test_login_rate_limit_separates_trusted_proxy_clients(
        self, client, monkeypatch
    ):
        """Có proxy đáng tin -> 2 IP client thật là 2 bucket riêng."""
        import uuid

        monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
        monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")

        username = f"ghost_{uuid.uuid4().hex[:12]}"
        payload = {"username": username, "password": "wrong-password"}

        for _ in range(5):
            r = client.post(
                "/api/v1/auth/login",
                json=payload,
                headers={"X-Forwarded-For": "203.0.113.7"},
            )
            assert r.status_code in (401, 429), r.text
        blocked = client.post(
            "/api/v1/auth/login",
            json=payload,
            headers={"X-Forwarded-For": "203.0.113.7"},
        )
        assert blocked.status_code == 429, blocked.text

        # IP client KHÁC (qua cùng proxy) -> bucket riêng -> chỉ 401
        other = client.post(
            "/api/v1/auth/login",
            json=payload,
            headers={"X-Forwarded-For": "198.51.100.2"},
        )
        assert other.status_code == 401, (
            "2 IP client thật khác nhau phải là 2 bucket rate-limit riêng: "
            f"{other.status_code} {other.text}"
        )
