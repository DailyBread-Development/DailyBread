from fastapi.testclient import TestClient

from backend.auth import create_session_cookie_value
from backend.main import app

client = TestClient(app)


def _logged_in_headers():
    session_cookie = create_session_cookie_value(
        {
            "id": "123",
            "username": "dailybread-user",
            "avatar": None,
            "avatar_url": "https://example.com/avatar.png",
        },
        [],
    )
    return {"Cookie": f"dailybread_session={session_cookie}"}


def test_docs_homepage_route_returns_200():
    response = client.get("/docs", headers=_logged_in_headers())
    assert response.status_code == 200
    assert "Documentation" in response.text
    assert "Help" in response.text
    assert "Terms of Service" in response.text
    assert "Privacy Policy" in response.text


def test_docs_pages_routes_return_200():
    for path in ["/docs/help", "/docs/terms", "/docs/privacy"]:
        response = client.get(path, headers=_logged_in_headers())
        assert response.status_code == 200


def test_docs_content_is_loaded_from_docs_files():
    response = client.get("/docs/terms", headers=_logged_in_headers())
    assert response.status_code == 200
    assert "Welcome to DailyBread." in response.text
    assert "By using DailyBread, you agree to these Terms of Service." in response.text

    response = client.get("/docs/privacy", headers=_logged_in_headers())
    assert response.status_code == 200
    assert "DailyBread respects your privacy." in response.text
    assert "This Privacy Policy explains what information we collect and how it is used." in response.text
