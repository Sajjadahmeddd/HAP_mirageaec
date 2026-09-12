"""Fixtures for the backend tests.

This file used to build a seeded identity database and hand out signed-in
clients. Both went to the maec-one-core repository with the identity package,
and the fixtures here shrank to one: a client that has not identified itself,
because there is currently no way for a client to identify itself.

The HAP PDF fixtures are in the repository-root conftest.py and were never
identity's — nothing there changed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client():
    """An unauthenticated client — which is now the only kind.

    It was called `app_client` when it meant "a browser that has not signed
    in yet", alongside `admin_client` and `engineer_client` for browsers that
    had. The name survives; the distinction does not, and will not until the
    OIDC client lands and there is a token to hold.
    """
    from backend.main import app
    return TestClient(app)
