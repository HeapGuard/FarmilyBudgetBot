from fastapi.testclient import TestClient
from app.main import app
from app.web.auth import get_current_web_user


def test_serve_mini_app_route():
    client = TestClient(app)
    response = client.get("/app")
    assert response.status_code == 200
    assert "Family Budget" in response.text


def test_get_summary_api_route():
    app.dependency_overrides[get_current_web_user] = lambda: {"id": 12345, "first_name": "Test"}
    try:
        client = TestClient(app)
        response = client.get("/api/summary")
        assert response.status_code == 200
        data = response.json()
        assert "balance" in data
        assert "accounts" in data
    finally:
        app.dependency_overrides.clear()


def test_user_settings_api_validation():
    app.dependency_overrides[get_current_web_user] = lambda: {"id": 12345, "first_name": "Test"}
    try:
        client = TestClient(app)

        # GET user settings
        res_get = client.get("/api/user-settings")
        assert res_get.status_code == 200

        # POST valid settings
        valid_payload = {
            "payday_schedule": "2_monthly",
            "payday_day_1": 15,
            "payday_day_2": 30,
            "payday_amount": 80000.0,
            "budget_ratio_essential": 50,
            "budget_ratio_personal": 30,
            "budget_ratio_savings": 20
        }
        res_valid = client.post("/api/user-settings", json=valid_payload)
        assert res_valid.status_code == 200
        assert res_valid.json() == {"status": "ok"}

        # POST invalid settings (day_1 out of range)
        invalid_payload_1 = {"payday_day_1": 35}
        res_invalid_1 = client.post("/api/user-settings", json=invalid_payload_1)
        assert res_invalid_1.status_code == 422

        # POST invalid settings (ratio out of range)
        invalid_payload_2 = {"budget_ratio_essential": 150}
        res_invalid_2 = client.post("/api/user-settings", json=invalid_payload_2)
        assert res_invalid_2.status_code == 422
    finally:
        app.dependency_overrides.clear()


