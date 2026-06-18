import psycopg
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service
from app.db.postgres import connect
from app.main import create_app
from app.services.auth_service import AuthService


@pytest.fixture
def test_db(pg_dsn: str) -> psycopg.Connection:
    conn = connect(pg_dsn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def client(test_db: psycopg.Connection) -> TestClient:
    app = create_app()

    def override_auth_service() -> AuthService:
        return AuthService(test_db)

    app.dependency_overrides[get_auth_service] = override_auth_service
    return TestClient(app)


def test_login_returns_token_for_valid_user(client: TestClient, test_db: psycopg.Connection) -> None:
    AuthService(test_db).create_user("alice", "secret")

    response = client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"] == {"id": "alice", "username": "alice", "is_admin": False}


def test_login_rejects_invalid_password(client: TestClient, test_db: psycopg.Connection) -> None:
    AuthService(test_db).create_user("alice", "secret")

    response = client.post("/api/v1/auth/login", json={"username": "alice", "password": "wrong"})

    assert response.status_code == 401


def test_me_returns_current_user(client: TestClient, test_db: psycopg.Connection) -> None:
    AuthService(test_db).create_user("alice", "secret")
    login_response = client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
    token = login_response.json()["access_token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"id": "alice", "username": "alice", "is_admin": False}


def test_me_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401

