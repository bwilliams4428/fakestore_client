"""Auth resource — login endpoint returning JWT tokens."""

from __future__ import annotations

from typing import Any

from fakestore_client.base import AsyncResource, SyncResource
from fakestore_client.models import AuthToken


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class SyncAuth(SyncResource):
    """Synchronous auth operations (backed by ``/auth/login``)."""

    def login(self, username: str, password: str) -> AuthToken:
        """Authenticate and return a JWT token."""
        resp = self._post(
            "/auth/login",
            json={"username": username, "password": password},
        )
        return AuthToken.model_validate(resp.json())


# ---------------------------------------------------------------------------
# Async
# ---------------------------------------------------------------------------


class AsyncAuth(AsyncResource):
    """Asynchronous auth operations (backed by ``/auth/login``)."""

    async def login(self, username: str, password: str) -> AuthToken:
        resp = await self._post(
            "/auth/login",
            json={"username": username, "password": password},
        )
        return AuthToken.model_validate(resp.json())