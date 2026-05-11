"""
Tests for app/auth/dependencies.py.

get_current_user now accepts both `token` and `db` (real DB session required).
Tests that need a user in the database use the `db_session` fixture so they
hit the same in-memory transaction used by the rest of the test suite.
"""
import pytest
from unittest.mock import patch
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.auth.dependencies import get_current_user, get_current_active_user
from app.models.user import User
from app.schemas.user import UserResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_verify_token():
    with patch.object(User, "verify_token") as mock:
        yield mock


# ---------------------------------------------------------------------------
# get_current_user – valid token, user exists in DB
# ---------------------------------------------------------------------------
def test_get_current_user_valid_token_existing_user(mock_verify_token, db_session):
    """A valid token whose UUID maps to an existing user returns a UserResponse."""
    user_id = uuid4()
    mock_verify_token.return_value = user_id

    user = User(
        id=user_id,
        username="deptest_valid",
        email="deptest_valid@example.com",
        first_name="Dep",
        last_name="Test",
        password=User.hash_password("ValidPass1!"),
        is_active=True,
        is_verified=False,
    )
    db_session.add(user)
    db_session.commit()

    result = get_current_user(token="validtoken", db=db_session)

    assert isinstance(result, UserResponse)
    assert result.id == user_id
    assert result.username == "deptest_valid"
    assert result.email == "deptest_valid@example.com"
    mock_verify_token.assert_called_once_with("validtoken")


# ---------------------------------------------------------------------------
# get_current_user – invalid token (verify_token returns None)
# ---------------------------------------------------------------------------
def test_get_current_user_invalid_token(mock_verify_token, db_session):
    """An invalid token causes 401 before the database is ever queried."""
    mock_verify_token.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token="invalidtoken", db=db_session)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "Could not validate credentials"
    mock_verify_token.assert_called_once_with("invalidtoken")


# ---------------------------------------------------------------------------
# get_current_user – token valid but user not found in DB
# ---------------------------------------------------------------------------
def test_get_current_user_valid_token_user_not_in_db(mock_verify_token, db_session):
    """A syntactically valid token that references a non-existent user → 401."""
    mock_verify_token.return_value = uuid4()  # random UUID, no matching row

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token="validtoken", db=db_session)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "Could not validate credentials"


# ---------------------------------------------------------------------------
# get_current_active_user – active user passes through
# ---------------------------------------------------------------------------
def test_get_current_active_user_active(mock_verify_token, db_session):
    """An active user is returned unchanged by get_current_active_user."""
    user_id = uuid4()
    mock_verify_token.return_value = user_id

    user = User(
        id=user_id,
        username="deptest_active",
        email="deptest_active@example.com",
        first_name="Active",
        last_name="User",
        password=User.hash_password("ActivePass1!"),
        is_active=True,
        is_verified=False,
    )
    db_session.add(user)
    db_session.commit()

    current_user = get_current_user(token="validtoken", db=db_session)
    active_user = get_current_active_user(current_user=current_user)

    assert isinstance(active_user, UserResponse)
    assert active_user.is_active is True


# ---------------------------------------------------------------------------
# get_current_active_user – inactive user raises 400
# ---------------------------------------------------------------------------
def test_get_current_active_user_inactive(mock_verify_token, db_session):
    """An inactive user causes get_current_active_user to raise 400."""
    user_id = uuid4()
    mock_verify_token.return_value = user_id

    user = User(
        id=user_id,
        username="deptest_inactive",
        email="deptest_inactive@example.com",
        first_name="Inactive",
        last_name="User",
        password=User.hash_password("InactivePass1!"),
        is_active=False,
        is_verified=False,
    )
    db_session.add(user)
    db_session.commit()

    current_user = get_current_user(token="validtoken", db=db_session)

    with pytest.raises(HTTPException) as exc_info:
        get_current_active_user(current_user=current_user)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Inactive user"
