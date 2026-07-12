"""Top-level client facades — ``FakeStoreClient`` (sync) and ``AsyncFakeStoreClient``.

Usage::

    # Synchronous
    from fakestore_client import FakeStoreClient
    client = FakeStoreClient()
    customers = client.customers.list()

    # Asynchronous
    from fakestore_client import AsyncFakeStoreClient
    async with AsyncFakeStoreClient() as client:
        customers = await client.customers.list()
"""

from __future__ import annotations

from typing import Optional

import httpx

from fakestore_client.auth import AsyncAuth, SyncAuth
from fakestore_client.customers import AsyncCustomers, SyncCustomers
from fakestore_client.orders import AsyncOrders, SyncOrders
from fakestore_client.products import AsyncProducts, SyncProducts

DEFAULT_BASE_URL = "https://fakestoreapi.com"
DEFAULT_TIMEOUT = 30


class FakeStoreClient:
    """Synchronous Fake Store API client.

    Parameters
    ----------
    base_url : str
        API base URL. Defaults to ``https://fakestoreapi.com``.
    timeout : int
        Request timeout in seconds. Defaults to 30.
    headers : dict, optional
        Additional headers to send with every request (e.g. auth tokens).
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers=headers or {},
        )
        self.customers = SyncCustomers(self._client)
        self.orders = SyncOrders(self._client)
        self.products = SyncProducts(self._client)
        self.auth = SyncAuth(self._client)

    # -- context manager support ---------------------------------------------

    def __enter__(self) -> FakeStoreClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._client.close()


class AsyncFakeStoreClient:
    """Asynchronous Fake Store API client.

    Parameters
    ----------
    base_url : str
        API base URL. Defaults to ``https://fakestoreapi.com``.
    timeout : int
        Request timeout in seconds. Defaults to 30.
    headers : dict, optional
        Additional headers to send with every request (e.g. auth tokens).
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers=headers or {},
        )
        self.customers = AsyncCustomers(self._client)
        self.orders = AsyncOrders(self._client)
        self.products = AsyncProducts(self._client)
        self.auth = AsyncAuth(self._client)

    # -- async context manager support ---------------------------------------

    async def __aenter__(self) -> AsyncFakeStoreClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        await self._client.aclose()