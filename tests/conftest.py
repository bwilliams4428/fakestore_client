"""Shared test fixtures and sample data for the Fake Store API client tests."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from fakestore_client import FakeStoreClient

# ---------------------------------------------------------------------------
# Sample response data (matching the real API)
# ---------------------------------------------------------------------------

SAMPLE_CUSTOMER: dict[str, Any] = {
    "id": 1,
    "email": "john@gmail.com",
    "username": "johnd",
    "password": "m38rmF$",
    "name": {"firstname": "john", "lastname": "doe"},
    "address": {
        "geolocation": {"lat": "-37.3159", "long": "81.1496"},
        "city": "kilcoole",
        "street": "new road",
        "number": 7682,
        "zipcode": "12926-3874",
    },
    "phone": "1-570-236-7033",
    "__v": 0,
}

SAMPLE_ORDER: dict[str, Any] = {
    "id": 1,
    "userId": 1,
    "date": "2020-03-02T00:00:00.000Z",
    "products": [
        {"productId": 1, "quantity": 4},
        {"productId": 2, "quantity": 1},
        {"productId": 3, "quantity": 6},
    ],
    "__v": 0,
}

SAMPLE_PRODUCT: dict[str, Any] = {
    "id": 1,
    "title": "Fjallraven - Foldsack No. 1 Backpack, Fits 15 Laptops",
    "price": 109.95,
    "description": "Your perfect pack for everyday use.",
    "category": "men's clothing",
    "image": "https://fakestoreapi.com/img/81fPKd-2AYL._AC_SL1500_t.png",
    "rating": {"rate": 3.9, "count": 120},
}

SAMPLE_AUTH_TOKEN: dict[str, Any] = {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
}

SAMPLE_CATEGORIES = [
    "electronics",
    "jewelery",
    "men's clothing",
    "women's clothing",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> FakeStoreClient:
    """Return a FakeStoreClient with transport set to a mock router.

    Tests should register routes on ``client._client``'s transport.
    """
    return FakeStoreClient()


def make_client_with_handler(
    handler: Any,
    base_url: str = "https://fakestoreapi.com",
) -> FakeStoreClient:
    """Create a FakeStoreClient backed by a mock transport.

    Parameters
    ----------
    handler : callable
        An ``httpx.MockTransport`` handler.
    """
    transport = httpx.MockTransport(handler)
    inner = httpx.Client(base_url=base_url, transport=transport)
    c = FakeStoreClient(base_url=base_url)
    c._client = inner  # type: ignore[attr-defined]
    c.customers._client = inner  # type: ignore[attr-defined]
    c.orders._client = inner  # type: ignore[attr-defined]
    c.products._client = inner  # type: ignore[attr-defined]
    c.auth._client = inner  # type: ignore[attr-defined]
    return c