"""
Integration tests for the Calculations BREAD endpoints.

POST   /calculations          – Add
GET    /calculations           – Browse
GET    /calculations/{id}     – Read
PUT    /calculations/{id}     – Edit
DELETE /calculations/{id}     – Delete

A registered-and-logged-in user is provided by the `auth_client` fixture so
individual test functions can focus purely on the calculation behaviour.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.calculation import Calculation
from tests.conftest import create_fake_user

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALID_PASSWORD = "SecurePass123!"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def auth_client(client: TestClient) -> tuple[TestClient, dict]:
    """
    Register a fresh user, log in, attach the bearer token to the client, and
    return (client, token_body) so tests can inspect token fields if needed.
    """
    user_payload = create_fake_user()
    user_payload["password"] = VALID_PASSWORD
    user_payload["confirm_password"] = VALID_PASSWORD

    client.post("/users/register", json=user_payload)

    resp = client.post(
        "/users/login",
        json={"username": user_payload["username"], "password": VALID_PASSWORD},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token_body = resp.json()
    access_token = token_body["access_token"]

    # Patch the client's default headers so every subsequent request is authenticated
    client.headers.update({"Authorization": f"Bearer {access_token}"})
    return client, token_body


@pytest.fixture
def created_calc(auth_client) -> tuple[TestClient, dict]:
    """Create one addition calculation and return (client, calc_body)."""
    client, _ = auth_client
    payload = {"type": "addition", "inputs": [10, 5, 3]}
    resp = client.post("/calculations", json=payload)
    assert resp.status_code == 201, f"Create failed: {resp.text}"
    return client, resp.json()


# ---------------------------------------------------------------------------
# Add (POST /calculations)
# ---------------------------------------------------------------------------
class TestCreateCalculation:
    def test_addition_returns_201(self, auth_client):
        client, _ = auth_client
        resp = client.post("/calculations", json={"type": "addition", "inputs": [1, 2, 3]})
        assert resp.status_code == 201

    def test_addition_result_correct(self, auth_client):
        client, _ = auth_client
        resp = client.post("/calculations", json={"type": "addition", "inputs": [10.5, 3, 2]})
        assert resp.json()["result"] == pytest.approx(15.5)

    def test_subtraction_result_correct(self, auth_client):
        client, _ = auth_client
        resp = client.post("/calculations", json={"type": "subtraction", "inputs": [20, 5, 3]})
        assert resp.json()["result"] == pytest.approx(12.0)

    def test_multiplication_result_correct(self, auth_client):
        client, _ = auth_client
        resp = client.post("/calculations", json={"type": "multiplication", "inputs": [2, 3, 4]})
        assert resp.json()["result"] == pytest.approx(24.0)

    def test_division_result_correct(self, auth_client):
        client, _ = auth_client
        resp = client.post("/calculations", json={"type": "division", "inputs": [100, 2, 5]})
        assert resp.json()["result"] == pytest.approx(10.0)

    def test_response_contains_expected_fields(self, auth_client):
        client, _ = auth_client
        resp = client.post("/calculations", json={"type": "addition", "inputs": [1, 2]})
        body = resp.json()
        for field in ("id", "user_id", "type", "inputs", "result", "created_at", "updated_at"):
            assert field in body, f"Missing field: {field}"

    def test_user_id_matches_logged_in_user(self, auth_client):
        client, token_body = auth_client
        resp = client.post("/calculations", json={"type": "addition", "inputs": [1, 2]})
        assert str(resp.json()["user_id"]) == str(token_body["user_id"])

    def test_unauthenticated_returns_401(self, client: TestClient):
        """Requests without a bearer token must be rejected."""
        resp = client.post("/calculations", json={"type": "addition", "inputs": [1, 2]})
        assert resp.status_code == 401

    def test_division_by_zero_returns_400(self, auth_client):
        client, _ = auth_client
        resp = client.post("/calculations", json={"type": "division", "inputs": [10, 0]})
        assert resp.status_code == 400

    def test_too_few_inputs_returns_422(self, auth_client):
        """Schema validation requires at least 2 inputs."""
        client, _ = auth_client
        resp = client.post("/calculations", json={"type": "addition", "inputs": [5]})
        assert resp.status_code == 422

    def test_invalid_type_returns_422(self, auth_client):
        client, _ = auth_client
        resp = client.post("/calculations", json={"type": "modulus", "inputs": [10, 3]})
        assert resp.status_code == 422

    def test_non_numeric_inputs_returns_422(self, auth_client):
        client, _ = auth_client
        resp = client.post("/calculations", json={"type": "addition", "inputs": ["a", "b"]})
        assert resp.status_code == 422

    def test_persisted_in_db(self, auth_client, db_session: Session):
        client, token_body = auth_client
        client.post("/calculations", json={"type": "addition", "inputs": [7, 8]})
        db_session.expire_all()
        import uuid
        calc = (
            db_session.query(Calculation)
            .filter(Calculation.user_id == uuid.UUID(str(token_body["user_id"])))
            .first()
        )
        assert calc is not None


# ---------------------------------------------------------------------------
# Browse (GET /calculations)
# ---------------------------------------------------------------------------
class TestListCalculations:
    def test_returns_200_with_list(self, auth_client):
        client, _ = auth_client
        resp = client.get("/calculations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_only_own_calculations_returned(self, auth_client, client: TestClient):
        """
        Two different users must not see each other's calculations.
        """
        client_a, _ = auth_client

        # Register & log in as a second user
        user_b = create_fake_user()
        user_b["password"] = VALID_PASSWORD
        user_b["confirm_password"] = VALID_PASSWORD
        client.post("/users/register", json=user_b)
        login_resp = client.post(
            "/users/login",
            json={"username": user_b["username"], "password": VALID_PASSWORD},
        )
        token_b = login_resp.json()["access_token"]

        # User A creates a calculation
        client_a.post("/calculations", json={"type": "addition", "inputs": [1, 2]})

        # User B should not see user A's calculation
        resp_b = client.get(
            "/calculations",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp_b.status_code == 200
        assert resp_b.json() == []

    def test_unauthenticated_returns_401(self, client: TestClient):
        resp = client.get("/calculations")
        assert resp.status_code == 401

    def test_multiple_calculations_listed(self, auth_client):
        client, _ = auth_client
        client.post("/calculations", json={"type": "addition", "inputs": [1, 2]})
        client.post("/calculations", json={"type": "subtraction", "inputs": [10, 3]})
        resp = client.get("/calculations")
        assert len(resp.json()) >= 2


# ---------------------------------------------------------------------------
# Read (GET /calculations/{id})
# ---------------------------------------------------------------------------
class TestGetCalculation:
    def test_returns_200(self, created_calc):
        client, calc = created_calc
        resp = client.get(f"/calculations/{calc['id']}")
        assert resp.status_code == 200

    def test_returned_data_matches(self, created_calc):
        client, calc = created_calc
        body = client.get(f"/calculations/{calc['id']}").json()
        assert body["id"] == calc["id"]
        assert body["result"] == calc["result"]
        assert body["type"] == calc["type"]

    def test_nonexistent_id_returns_404(self, auth_client):
        client, _ = auth_client
        import uuid
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/calculations/{fake_id}")
        assert resp.status_code == 404

    def test_invalid_uuid_returns_400(self, auth_client):
        client, _ = auth_client
        resp = client.get("/calculations/not-a-uuid")
        assert resp.status_code == 400

    def test_unauthenticated_returns_401(self, created_calc, client: TestClient):
        _, calc = created_calc
        resp = client.get(f"/calculations/{calc['id']}")
        assert resp.status_code == 401

    def test_other_user_cannot_read(self, created_calc, client: TestClient):
        """Another logged-in user must receive 404, not someone else's calculation."""
        _, calc = created_calc

        user_b = create_fake_user()
        user_b["password"] = VALID_PASSWORD
        user_b["confirm_password"] = VALID_PASSWORD
        client.post("/users/register", json=user_b)
        login_resp = client.post(
            "/users/login",
            json={"username": user_b["username"], "password": VALID_PASSWORD},
        )
        token_b = login_resp.json()["access_token"]

        resp = client.get(
            f"/calculations/{calc['id']}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Edit (PUT /calculations/{id})
# ---------------------------------------------------------------------------
class TestUpdateCalculation:
    def test_returns_200(self, created_calc):
        client, calc = created_calc
        resp = client.put(f"/calculations/{calc['id']}", json={"inputs": [20, 5]})
        assert resp.status_code == 200

    def test_result_recomputed_after_update(self, created_calc):
        client, calc = created_calc
        resp = client.put(f"/calculations/{calc['id']}", json={"inputs": [20, 5]})
        assert resp.json()["result"] == pytest.approx(25.0)

    def test_inputs_updated_in_response(self, created_calc):
        client, calc = created_calc
        resp = client.put(f"/calculations/{calc['id']}", json={"inputs": [100, 1]})
        assert resp.json()["inputs"] == [100.0, 1.0]

    def test_nonexistent_id_returns_404(self, auth_client):
        client, _ = auth_client
        import uuid
        resp = client.put(f"/calculations/{uuid.uuid4()}", json={"inputs": [1, 2]})
        assert resp.status_code == 404

    def test_invalid_uuid_returns_400(self, auth_client):
        client, _ = auth_client
        resp = client.put("/calculations/bad-id", json={"inputs": [1, 2]})
        assert resp.status_code == 400

    def test_too_few_inputs_returns_422(self, created_calc):
        client, calc = created_calc
        resp = client.put(f"/calculations/{calc['id']}", json={"inputs": [5]})
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, created_calc, client: TestClient):
        _, calc = created_calc
        resp = client.put(f"/calculations/{calc['id']}", json={"inputs": [1, 2]})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Delete (DELETE /calculations/{id})
# ---------------------------------------------------------------------------
class TestDeleteCalculation:
    def test_returns_204(self, created_calc):
        client, calc = created_calc
        resp = client.delete(f"/calculations/{calc['id']}")
        assert resp.status_code == 204

    def test_deleted_calc_no_longer_readable(self, created_calc):
        client, calc = created_calc
        client.delete(f"/calculations/{calc['id']}")
        resp = client.get(f"/calculations/{calc['id']}")
        assert resp.status_code == 404

    def test_deleted_calc_not_in_list(self, created_calc):
        client, calc = created_calc
        client.delete(f"/calculations/{calc['id']}")
        ids = [c["id"] for c in client.get("/calculations").json()]
        assert calc["id"] not in ids

    def test_nonexistent_id_returns_404(self, auth_client):
        client, _ = auth_client
        import uuid
        resp = client.delete(f"/calculations/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_invalid_uuid_returns_400(self, auth_client):
        client, _ = auth_client
        resp = client.delete("/calculations/not-a-uuid")
        assert resp.status_code == 400

    def test_unauthenticated_returns_401(self, created_calc, client: TestClient):
        _, calc = created_calc
        resp = client.delete(f"/calculations/{calc['id']}")
        assert resp.status_code == 401

    def test_removed_from_db(self, created_calc, db_session: Session):
        client, calc = created_calc
        client.delete(f"/calculations/{calc['id']}")
        db_session.expire_all()
        import uuid
        result = (
            db_session.query(Calculation)
            .filter(Calculation.id == uuid.UUID(calc["id"]))
            .first()
        )
        assert result is None
