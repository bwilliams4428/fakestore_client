"""Products resource — read + CRUD operations on /products."""

from __future__ import annotations

from typing import Any, Optional, Union

from fakestore_client.base import AsyncResource, SyncResource
from fakestore_client.models import Product, ProductCreate, ProductUpdate


def _validate_product(data: dict[str, Any]) -> Product:
    """Validate product data, filling in defaults for missing required fields.

    The Fake Store API may return only ``{"id": N}`` for create/update/delete.
    """
    defaults: dict[str, Any] = {
        "title": data.get("title", ""),
        "price": data.get("price", 0.0),
        "description": data.get("description", ""),
        "category": data.get("category", ""),
        "image": data.get("image", ""),
    }
    merged = {**defaults, **data}
    return Product.model_validate(merged)


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class SyncProducts(SyncResource):
    """Synchronous product operations (backed by ``/products``)."""

    def list(
        self,
        *,
        sort: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[Product]:
        """Return all products, optionally sorted or limited."""
        params: dict[str, Any] = {}
        if sort is not None:
            params["sort"] = sort
        if limit is not None:
            params["limit"] = limit
        resp = self._get("/products", params=params)
        return [Product.model_validate(item) for item in resp.json()]

    def get(self, product_id: int) -> Product:
        """Retrieve a single product by ID."""
        resp = self._get(f"/products/{product_id}")
        return Product.model_validate(resp.json())

    def categories(self) -> list[str]:
        """Return all product category names."""
        resp = self._get("/products/categories")
        return resp.json()

    def by_category(self, category: str) -> list[Product]:
        """Return products in a given category."""
        resp = self._get(f"/products/category/{category}")
        return [Product.model_validate(item) for item in resp.json()]

    def create(self, data: Union[dict[str, Any], ProductCreate]) -> Product:
        """Create a new product."""
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, ProductCreate)
            else data
        )
        resp = self._post("/products", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_product(merged)

    def update(
        self, product_id: int, data: Union[dict[str, Any], ProductUpdate]
    ) -> Product:
        """Replace a product (PUT)."""
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, ProductUpdate)
            else data
        )
        resp = self._put(f"/products/{product_id}", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_product(merged)

    def delete(self, product_id: int) -> Product:
        """Delete a product by ID."""
        resp = self._delete(f"/products/{product_id}")
        return _validate_product(resp.json())


# ---------------------------------------------------------------------------
# Async
# ---------------------------------------------------------------------------


class AsyncProducts(AsyncResource):
    """Asynchronous product operations (backed by ``/products``)."""

    async def list(
        self,
        *,
        sort: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[Product]:
        params: dict[str, Any] = {}
        if sort is not None:
            params["sort"] = sort
        if limit is not None:
            params["limit"] = limit
        resp = await self._get("/products", params=params)
        return [Product.model_validate(item) for item in resp.json()]

    async def get(self, product_id: int) -> Product:
        resp = await self._get(f"/products/{product_id}")
        return Product.model_validate(resp.json())

    async def categories(self) -> list[str]:
        resp = await self._get("/products/categories")
        return resp.json()

    async def by_category(self, category: str) -> list[Product]:
        resp = await self._get(f"/products/category/{category}")
        return [Product.model_validate(item) for item in resp.json()]

    async def create(self, data: Union[dict[str, Any], ProductCreate]) -> Product:
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, ProductCreate)
            else data
        )
        resp = await self._post("/products", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_product(merged)

    async def update(
        self, product_id: int, data: Union[dict[str, Any], ProductUpdate]
    ) -> Product:
        payload = (
            data.model_dump(by_alias=True, exclude_none=True)
            if isinstance(data, ProductUpdate)
            else data
        )
        resp = await self._put(f"/products/{product_id}", json=payload)
        response_data = resp.json()
        merged = {**payload, **response_data}
        return _validate_product(merged)

    async def delete(self, product_id: int) -> Product:
        resp = await self._delete(f"/products/{product_id}")
        return _validate_product(resp.json())