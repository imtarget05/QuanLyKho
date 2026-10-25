"""Integration and unit tests for Push Notification device registration and dispatch."""
import uuid


def test_device_registration_anonymous_returns_401(client):
    r = client.post("/api/v1/notifications/devices/register", json={
        "device_token": "fcm_token_1234567890_test",
        "platform": "web",
    })
    assert r.status_code == 401


def test_device_registration_and_list_flow(client, demo_mode):
    # Log in as demo admin/staff
    login_res = client.post("/auth/login", json={"username": "demo_admin", "password": "AdminPassword123!"})
    if login_res.status_code != 200:
        # Fallback to mock token or staff login
        token_res = client.post("/api/v1/auth/google", json={"id_token": f"mock-google-token:notif_user_{uuid.uuid4().hex[:6]}@bankops.internal:Notif User"})
        assert token_res.status_code == 200
        headers = {"Authorization": f"Bearer {token_res.json()['access_token']}"}
    else:
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    test_token = f"fcm_token_{uuid.uuid4().hex}_{uuid.uuid4().hex}"

    # 1. Register device
    reg_res = client.post(
        "/api/v1/notifications/devices/register",
        json={
            "device_token": test_token,
            "platform": "android",
            "device_name": "Samsung Galaxy Tab Active 3",
        },
        headers=headers,
    )
    assert reg_res.status_code == 200, reg_res.text
    data = reg_res.json()
    assert data["device_token"] == test_token
    assert data["platform"] == "android"
    assert data["is_active"] is True

    # 2. List devices
    list_res = client.get("/api/v1/notifications/devices", headers=headers)
    assert list_res.status_code == 200
    devices = list_res.json()
    assert any(d["device_token"] == test_token for d in devices)

    # 3. Test-send notification
    send_res = client.post(
        "/api/v1/notifications/test-send",
        json={
            "title": "Cảnh báo hết hàng trà sữa",
            "body": "Trà ô long túi lọc sắp cạn tồn kho",
            "target_device_token": test_token,
        },
        headers=headers,
    )
    assert send_res.status_code == 200
    send_data = send_res.json()
    assert send_data["success"] is True
    assert send_data["delivered_count"] >= 1

    # 4. De-register device
    del_res = client.delete(f"/api/v1/notifications/devices/{test_token}", headers=headers)
    assert del_res.status_code == 204

    # 5. Verify device is no longer in active list
    list_res2 = client.get("/api/v1/notifications/devices", headers=headers)
    assert list_res2.status_code == 200
    devices2 = list_res2.json()
    assert not any(d["device_token"] == test_token for d in devices2)
