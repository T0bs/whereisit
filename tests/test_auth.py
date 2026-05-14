import pytest


@pytest.fixture
def with_token(monkeypatch):
    monkeypatch.setenv("WHEREISIT_TOKEN", "test-secret")
    yield "test-secret"


@pytest.fixture
def without_token(monkeypatch):
    monkeypatch.delenv("WHEREISIT_TOKEN", raising=False)


def test_health_open_in_dev_mode(client, without_token):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_open_in_strict_mode(client, with_token):
    response = client.get("/health")
    assert response.status_code == 200


def test_protected_endpoint_open_in_dev_mode(client, without_token):
    response = client.get("/items/")
    assert response.status_code == 200


def test_protected_endpoint_rejects_missing_token(client, with_token):
    response = client.get("/items/")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"
    assert response.json() == {"detail": "Unauthorized"}


def test_protected_endpoint_rejects_wrong_token(client, with_token):
    response = client.get("/items/", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_protected_endpoint_rejects_wrong_scheme(client, with_token):
    response = client.get("/items/", headers={"Authorization": f"Basic {with_token}"})
    assert response.status_code == 401


def test_protected_endpoint_accepts_correct_token(client, with_token):
    response = client.get(
        "/items/", headers={"Authorization": f"Bearer {with_token}"}
    )
    assert response.status_code == 200


def test_empty_token_env_var_means_dev_mode(client, monkeypatch):
    monkeypatch.setenv("WHEREISIT_TOKEN", "")
    response = client.get("/items/")
    assert response.status_code == 200
