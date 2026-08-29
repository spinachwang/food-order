"""Smoke test for the M0 /healthz endpoint.

Writes the test FIRST per TDD (RED → GREEN → IMPROVE).
"""
from fastapi.testclient import TestClient


def test_healthz_returns_ok(client: TestClient) -> None:
    """GET /healthz must respond with {"status": "ok"} and 200."""
    # Act
    response = client.get("/healthz")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}