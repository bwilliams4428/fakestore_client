"""Base client — shared HTTP machinery for sync and async modes."""

from __future__ import annotations

from typing import Any, Optional

import httpx


class APIError(Exception):
    """Raised when the Fake Store API returns a non-2xx status code."""

    def __init__(self, status_code: int, message: str, url: str) -> None:
        self.status_code = status_code
        self.message = message
        self.url = url
        super().__init__(f"HTTP {status_code}: {message} (url={url})")


class _ResourceBase:
    """Common request helpers inherited by every resource class."""

    def __init__(self, client: httpx.Client | httpx.AsyncClient) -> None:
        self._client = client

    # -- helpers used by all resources ----------------------------------------

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise APIError(
                status_code=response.status_code,
                message=response.text,
                url=str(response.url),
            )


class SyncResource(_ResourceBase):
    """Base for synchronous resource classes (uses httpx.Client)."""

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self._client.request(method, path, **kwargs)
        self._raise_for_status(response)
        return response

    def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._request("GET", path, **kwargs)

    def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._request("POST", path, **kwargs)

    def _put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._request("PUT", path, **kwargs)

    def _patch(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._request("PATCH", path, **kwargs)

    def _delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._request("DELETE", path, **kwargs)


class AsyncResource(_ResourceBase):
    """Base for asynchronous resource classes (uses httpx.AsyncClient)."""

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = await self._client.request(method, path, **kwargs)
        self._raise_for_status(response)
        return response

    async def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("GET", path, **kwargs)

    async def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("POST", path, **kwargs)

    async def _put(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("PUT", path, **kwargs)

    async def _patch(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("PATCH", path, **kwargs)

    async def _delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("DELETE", path, **kwargs)