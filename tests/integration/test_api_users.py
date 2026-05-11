"""
Integration tests for /users/register and /users/login endpoints.

These tests use FastAPI TestClient backed by the shared test database session
(provided by the `client` fixture in conftest.py).  Every test exercises the
real HTTP layer – path, status code, response body – and verifies the
resulting DB state where relevant.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from tests.conftest import create_fake_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
VALID_PASSWORD = "SecurePass123!"

def _user_payload(**overrides) -> dict:
    data = create_fake_user()
    data["password"] = VALID_PASSWORD
    data["confirm_password"] = VALID_PASSWORD
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Registration – success
# ---------------------------------------------------------------------------
class TestRegisterSuccess:
    def test_returns_201(self, client: TestClient):
        resp = client.post("/users/register", json=_user_payload())
        assert resp.status_code == 201

    def test_response_shape(self, client: TestClient):
        resp = client.post("/users/register", json=_user_payload())
        body = resp.json()
        for field in ("id", "username", "email", "first_name", "last_name",
                      "is_active", "is_verified", "created_at", "updated_at"):
            assert field in body, f"Missing field: {field}"

    def test_response_values(self, client: TestClient):
        payload = _user_payload()
        body = client.post("/users/register", json=payload).json()
        assert body["username"] == payload["username"]
        assert body["email"] == payload["email"]
        assert body["first_name"] == payload["first_name"]
        assert body["last_name"] == payload["last_name"]
        assert body["is_active"] is True
        assert body["is_verified"] is False

    def test_password_not_in_response(self, client: TestClient):
        body = client.post("/users/register", json=_user_payload()).json()
        assert "password" not in body

    def test_user_persisted_in_db(self, client: TestClient, db_session: Session):
        payload = _user_payload()
        client.post("/users/register", json=payload)
        db_session.expire_all()
        user = db_session.query(User).filter(User.email == payload["email"]).first()
        assert user is not None
        assert user.username == payload["username"]

    def test_password_is_hashed_in_db(self, client: TestClient, db_session: Session):
        payload = _user_payload()
        client.post("/users/register", json=payload)
        db_session.expire_all()
        user = db_session.query(User).filter(User.email == payload["email"]).first()
        assert user.password != payload["password"]
        assert user.verify_password(payload["password"]) is True


# ---------------------------------------------------------------------------
# Registration – duplicate / validation failures
# ---------------------------------------------------------------------------
class TestRegisterFailures:
    def test_duplicate_username_returns_400(self, client: TestClient):
        payload = _user_payload()
        client.post("/users/register", json=payload)
        duplicate = _user_payload()
        duplicate["username"] = payload["username"]
        resp = client.post("/users/register", json=duplicate)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_duplicate_email_returns_400(self, client: TestClient):
        payload = _user_payload()
        client.post("/users/register", json=payload)
        duplicate = _user_payload()
        duplicate["email"] = payload["email"]
        resp = client.post("/users/register", json=duplicate)
        assert resp.status_code == 400

    def test_password_mismatch_returns_422(self, client: TestClient):
        payload = _user_payload()
        payload["confirm_password"] = "DifferentPass99!"
        resp = client.post("/users/register", json=payload)
        assert resp.status_code == 422

    def test_weak_password_no_uppercase_returns_422(self, client: TestClient):
        payload = _user_payload()
        payload["password"] = "weakpass1!"
        payload["confirm_password"] = "weakpass1!"
        resp = client.post("/users/register", json=payload)
        assert resp.status_code == 422

    def test_weak_password_no_digit_returns_422(self, client: TestClient):
        payload = _user_payload()
        payload["password"] = "NoDigitPass!"
        payload["confirm_password"] = "NoDigitPass!"
        resp = client.post("/users/register", json=payload)
        assert resp.status_code == 422

    def test_weak_password_no_special_char_returns_422(self, client: TestClient):
        payload = _user_payload()
        payload["password"] = "NoSpecial123"
        payload["confirm_password"] = "NoSpecial123"
        resp = client.post("/users/register", json=payload)
        assert resp.status_code == 422

    def test_missing_required_fields_returns_422(self, client: TestClient):
        resp = client.post("/users/register", json={"username": "onlyuser"})
        assert resp.status_code == 422

    def test_invalid_email_returns_422(self, client: TestClient):
        payload = _user_payload()
        payload["email"] = "not-an-email"
        resp = client.post("/users/register", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login – success
# ---------------------------------------------------------------------------
class TestLoginSuccess:
    @pytest.fixture
    def registered(self, client: TestClient) -> dict:
        """Register a user and return its payload."""
        payload = _user_payload()
        client.post("/users/register", json=payload)
        return payload

    def test_returns_200(self, client: TestClient, registered: dict):
        resp = client.post(
            "/users/login",
            json={"username": registered["username"], "password": registered["password"]},
        )
        assert resp.status_code == 200

    def test_response_contains_tokens(self, client: TestClient, registered: dict):
        resp = client.post(
            "/users/login",
            json={"username": registered["username"], "password": registered["password"]},
        )
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_response_contains_user_info(self, client: TestClient, registered: dict):
        resp = client.post(
            "/users/login",
            json={"username": registered["username"], "password": registered["password"]},
        )
        body = resp.json()
        assert body["username"] == registered["username"]
        assert body["email"] == registered["email"]

    def test_login_with_email(self, client: TestClient, registered: dict):
        """Users can authenticate using their email address instead of username."""
        resp = client.post(
            "/users/login",
            json={"username": registered["email"], "password": registered["password"]},
        )
        assert resp.status_code == 200

    def test_last_login_updated_in_db(self, client: TestClient, db_session: Session, registered: dict):
        client.post(
            "/users/login",
            json={"username": registered["username"], "password": registered["password"]},
        )
        db_session.expire_all()
        user = db_session.query(User).filter(User.email == registered["email"]).first()
        assert user.last_login is not None


# ---------------------------------------------------------------------------
# Login – failures
# ---------------------------------------------------------------------------
class TestLoginFailures:
    @pytest.fixture
    def registered(self, client: TestClient) -> dict:
        payload = _user_payload()
        client.post("/users/register", json=payload)
        return payload

    def test_wrong_password_returns_401(self, client: TestClient, registered: dict):
        resp = client.post(
            "/users/login",
            json={"username": registered["username"], "password": "WrongPass99!"},
        )
        assert resp.status_code == 401

    def test_nonexistent_user_returns_401(self, client: TestClient):
        resp = client.post(
            "/users/login",
            json={"username": "ghost_user_xyz", "password": VALID_PASSWORD},
        )
        assert resp.status_code == 401

    def test_missing_password_returns_422(self, client: TestClient, registered: dict):
        resp = client.post("/users/login", json={"username": registered["username"]})
        assert resp.status_code == 422

    def test_empty_credentials_returns_422(self, client: TestClient):
        resp = client.post("/users/login", json={})
        assert resp.status_code == 422
