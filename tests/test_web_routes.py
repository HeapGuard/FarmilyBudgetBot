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

