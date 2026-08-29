"""Shared pytest fixtures for the backend test suite."""
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="function")
def client() -> Generator[TestClient, None, None]:
    """Synchronous TestClient against an isolated app instance."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client