"""Orders resource — CRUD operations on /carts.

The Fake Store API models orders as "carts". Each cart has a userId, date,
and a list of product line-items (productId + quantity). We expose them as
``client.orders`` for domain clarity.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from fakestore_client.base import AsyncResource, SyncResource
from fakestore_client.models import Order, OrderCreate, OrderUpdate


def _validate_order(data: dict[str, Any]) -> Order:
    """Validate order data, filling in defaults for missing required fields.

    The Fake Store API may return only ``{"id": N}`` for create/update/delete.
    """
    defaults: dict[str, Any] = {
        "userId": data.get("userId", 0),
        "date": data.get("date", ""),
        "products": data.get("products", []),
    }
    merged = {**defaults, **data}
    return Order.model_validate(merged)


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class SyncOrders(SyncResource):
    """Synchronous order operations (backed by ``/carts``)."""

    def list(
        self,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        sort: Optional[str] = None,
    ) -> list[Order]:
        """Return all orders, optionally filtered by date range.

        Parameters
        ----------
        start_date : str, optional
            ISO-8601 start date, e.g. ``"2020-01-01"``.
        end_date : str, optional
            ISO-8601 end date, e.g. ``"2020-12-31"``.
        limit : int, optional
            Maximum number of results.
        sort : str, optional
            Sort order — ``"asc"`` or ``"desc"``.
        """
        params: dict[str, Any] = {}
        if start_date is not None:
            params["startdate"] = start_date
        if end_date is not None:
            params["enddate"] = end_date
        if limit is not None:
            params["limit"] = limit
        if sort is not None:
            params["sort"] = sort
        resp = self._get("/carts", params=params)
        return [Order.model_validate(item) for item in resp.json()]

    def get(self, cart_id: int) -> Order:
        """Retrieve a single order by ID."""
        resp = self._get(f"/carts/{cart_id}")
        return Order.model_validate(resp.json())

    def create(self, data: Union[dict[str, Any], OrderCreate]) -> Order:
        """Create a new order (cart).

        Accepts an ``OrderCreate`` model or a plain dict.
        The API may return only ``{"id": N}``; we merge with the input data.
        """
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, OrderCreate)
            else data
        )
        resp = self._post("/carts", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_order(merged)

    def update(
        self, cart_id: int, data: Union[dict[str, Any], OrderUpdate]
    ) -> Order:
        """Replace an order (PUT)."""
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, OrderUpdate)
            else data
        )
        resp = self._put(f"/carts/{cart_id}", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_order(merged)

    def partial_update(
        self, cart_id: int, data: Union[dict[str, Any], OrderUpdate]
    ) -> Order:
        """Partially update an order (PATCH)."""
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, OrderUpdate)
            else data
        )
        resp = self._patch(f"/carts/{cart_id}", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_order(merged)

    def delete(self, cart_id: int) -> Order:
        """Delete an order by ID. Returns the deleted record."""
        resp = self._delete(f"/carts/{cart_id}")
        return _validate_order(resp.json())


# ---------------------------------------------------------------------------
# Async
# ---------------------------------------------------------------------------


class AsyncOrders(AsyncResource):
    """Asynchronous order operations (backed by ``/carts``)."""

    async def list(
        self,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        sort: Optional[str] = None,
    ) -> list[Order]:
        params: dict[str, Any] = {}
        if start_date is not None:
            params["startdate"] = start_date
        if end_date is not None:
            params["enddate"] = end_date
        if limit is not None:
            params["limit"] = limit
        if sort is not None:
            params["sort"] = sort
        resp = await self._get("/carts", params=params)
        return [Order.model_validate(item) for item in resp.json()]

    async def get(self, cart_id: int) -> Order:
        resp = await self._get(f"/carts/{cart_id}")
        return Order.model_validate(resp.json())

    async def create(self, data: Union[dict[str, Any], OrderCreate]) -> Order:
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, OrderCreate)
            else data
        )
        resp = await self._post("/carts", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_order(merged)

    async def update(
        self, cart_id: int, data: Union[dict[str, Any], OrderUpdate]
    ) -> Order:
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, OrderUpdate)
            else data
        )
        resp = await self._put(f"/carts/{cart_id}", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_order(merged)

    async def partial_update(
        self, cart_id: int, data: Union[dict[str, Any], OrderUpdate]
    ) -> Order:
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, OrderUpdate)
            else data
        )
        resp = await self._patch(f"/carts/{cart_id}", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_order(merged)

    async def delete(self, cart_id: int) -> Order:
        resp = await self._delete(f"/carts/{cart_id}")
        return _validate_order(resp.json())