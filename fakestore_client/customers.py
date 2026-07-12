"""Customers resource — CRUD operations on /users.

The Fake Store API exposes customers via the ``/users`` endpoint.
We surface them as ``client.customers`` for domain clarity.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from fakestore_client.base import AsyncResource, SyncResource
from fakestore_client.models import (
    Customer,
    CustomerCreate,
    CustomerUpdate,
)


def _validate_customer(data: dict[str, Any]) -> Customer:
    """Validate customer data, filling in defaults for missing required fields.

    The Fake Store API may return only ``{"id": N}`` for create/update/delete
    operations. We merge with defaults so the model validates cleanly.
    """
    defaults = {
        "email": data.get("email", ""),
        "username": data.get("username", ""),
        "name": data.get("name", {"firstname": "", "lastname": ""}),
        "address": data.get("address", {
            "geolocation": {"lat": "0", "long": "0"},
            "city": "",
            "street": "",
            "number": 0,
            "zipcode": "",
        }),
        "phone": data.get("phone", ""),
    }
    merged = {**defaults, **data}
    return Customer.model_validate(merged)


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class SyncCustomers(SyncResource):
    """Synchronous customer operations (backed by ``/users``)."""

    def list(
        self,
        *,
        sort: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[Customer]:
        """Return all customers, optionally sorted or limited.

        Parameters
        ----------
        sort : str, optional
            Sort order — ``"asc"`` or ``"desc"``.
        limit : int, optional
            Maximum number of results.
        """
        params: dict[str, Any] = {}
        if sort is not None:
            params["sort"] = sort
        if limit is not None:
            params["limit"] = limit
        resp = self._get("/users", params=params)
        return [Customer.model_validate(item) for item in resp.json()]

    def get(self, user_id: int) -> Customer:
        """Retrieve a single customer by ID."""
        resp = self._get(f"/users/{user_id}")
        return Customer.model_validate(resp.json())

    def create(self, data: Union[dict[str, Any], CustomerCreate]) -> Customer:
        """Create a new customer.

        Accepts a ``CustomerCreate`` model or a plain dict.
        The API may return only ``{"id": N}``; we merge with the input data.
        """
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, CustomerCreate)
            else data
        )
        resp = self._post("/users", json=payload)
        response_data = resp.json()
        # Merge input payload with response (API may return only {id: N})
        merged = {**payload, **response_data}
        return _validate_customer(merged)

    def update(
        self, user_id: int, data: Union[dict[str, Any], CustomerUpdate]
    ) -> Customer:
        """Replace a customer (PUT). Accepts a ``CustomerUpdate`` model or dict."""
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, CustomerUpdate)
            else data
        )
        resp = self._put(f"/users/{user_id}", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_customer(merged)

    def partial_update(
        self, user_id: int, data: Union[dict[str, Any], CustomerUpdate]
    ) -> Customer:
        """Partially update a customer (PATCH)."""
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, CustomerUpdate)
            else data
        )
        resp = self._patch(f"/users/{user_id}", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_customer(merged)

    def delete(self, user_id: int) -> Customer:
        """Delete a customer by ID. Returns the deleted record."""
        resp = self._delete(f"/users/{user_id}")
        return _validate_customer(resp.json())


# ---------------------------------------------------------------------------
# Async
# ---------------------------------------------------------------------------


class AsyncCustomers(AsyncResource):
    """Asynchronous customer operations (backed by ``/users``)."""

    async def list(
        self,
        *,
        sort: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[Customer]:
        params: dict[str, Any] = {}
        if sort is not None:
            params["sort"] = sort
        if limit is not None:
            params["limit"] = limit
        resp = await self._get("/users", params=params)
        return [Customer.model_validate(item) for item in resp.json()]

    async def get(self, user_id: int) -> Customer:
        resp = await self._get(f"/users/{user_id}")
        return Customer.model_validate(resp.json())

    async def create(self, data: Union[dict[str, Any], CustomerCreate]) -> Customer:
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, CustomerCreate)
            else data
        )
        resp = await self._post("/users", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_customer(merged)

    async def update(
        self, user_id: int, data: Union[dict[str, Any], CustomerUpdate]
    ) -> Customer:
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, CustomerUpdate)
            else data
        )
        resp = await self._put(f"/users/{user_id}", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_customer(merged)

    async def partial_update(
        self, user_id: int, data: Union[dict[str, Any], CustomerUpdate]
    ) -> Customer:
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, CustomerUpdate)
            else data
        )
        resp = await self._patch(f"/users/{user_id}", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_customer(merged)

    async def delete(self, user_id: int) -> Customer:
        resp = await self._delete(f"/users/{user_id}")
        return _validate_customer(resp.json())