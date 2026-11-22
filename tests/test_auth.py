import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from birdai.api.app import app
from birdai.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from birdai.db.models import Base
from birdai.db.session import get_db


@pytest.fixture
def test_db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/auth_test.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield session
    finally:
        session.close()
        app.dependency_overrides.pop(get_db, None)


def test_hash_and_verify_password():
    raw_pw = "SuperSecret123!"
    hashed = hash_password(raw_pw)
    assert hashed != raw_pw
    assert verify_password(raw_pw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_create_and_decode_jwt():
    payload = {"sub": "user-uuid-1234", "email": "test@example.com"}
    token = create_access_token(payload)
    decoded = decode_access_token(token)
    assert decoded["sub"] == "user-uuid-1234"
    assert decoded["email"] == "test@example.com"
    assert "exp" in decoded


def test_auth_registration_and_login_flow(test_db_session):
    client = TestClient(app)
    test_email = f"birder_{uuid.uuid4().hex[:6]}@example.com"
    test_pw = "password1234"

    # Register
    reg_res = client.post(
        "/api/auth/register",
        json={
            "email": test_email,
            "password": test_pw,
            "full_name": "Field Naturalist",
        },
    )
    assert reg_res.status_code == 201
    user_data = reg_res.json()
    assert user_data["email"] == test_email
    assert user_data["full_name"] == "Field Naturalist"
    assert "id" in user_data

    # Duplicate registration fails
    dup_res = client.post(
        "/api/auth/register",
        json={"email": test_email, "password": test_pw},
    )
    assert dup_res.status_code == 400
    assert "already exists" in dup_res.json()["detail"]

    # Invalid email fails
    inv_res = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": test_pw},
    )
    assert inv_res.status_code == 400

    # Login with wrong password fails
    bad_login = client.post(
        "/api/auth/token",
        data={"username": test_email, "password": "wrongpassword"},
    )
    assert bad_login.status_code == 401

    # Login with correct credentials succeeds
    login_res = client.post(
        "/api/auth/token",
        data={"username": test_email, "password": test_pw},
    )
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    token = token_data["access_token"]

    # Access protected /me endpoint
    me_res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == test_email


def test_unauthenticated_request_rejected():
    client = TestClient(app)
    res = client.get("/api/auth/me")
    assert res.status_code == 401

