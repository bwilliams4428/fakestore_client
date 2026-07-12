"""Tests for the Customers resource (sync)."""

from __future__ import annotations

import json

import httpx
import pytest

from fakestore_client import Customer, FakeStoreClient
from tests.conftest import SAMPLE_CUSTOMER, make_client_with_handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _customer_handler(request: httpx.Request) -> httpx.Response:
    """Route handler that dispatches customer-related requests."""
    path = request.url.path
    method = request.method

    if method == "GET" and path == "/users":
        return httpx.Response(200, json=[SAMPLE_CUSTOMER])
    if method == "GET" and path.startswith("/users/"):
        return httpx.Response(200, json=SAMPLE_CUSTOMER)
    if method == "POST" and path == "/users":
        body = json.loads(request.content)
        result = {**SAMPLE_CUSTOMER, **body, "id": 11}
        return httpx.Response(201, json=result)
    if method == "PUT" and path.startswith("/users/"):
        body = json.loads(request.content)
        result = {**SAMPLE_CUSTOMER, **body}
        return httpx.Response(200, json=result)
    if method == "PATCH" and path.startswith("/users/"):
        body = json.loads(request.content)
        result = {**SAMPLE_CUSTOMER, **body}
        return httpx.Response(200, json=result)
    if method == "DELETE" and path.startswith("/users/"):
        return httpx.Response(200, json=SAMPLE_CUSTOMER)

    return httpx.Response(404, json={"message": "Not found"})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCustomersList:
    def test_list_returns_customers(self) -> None:
        client = make_client_with_handler(_customer_handler)
        result = client.customers.list()
        assert len(result) == 1
        assert isinstance(result[0], Customer)
        assert result[0].email == "john@gmail.com"
        assert result[0].name.firstname == "john"

    def test_list_with_sort_and_limit(self) -> None:
        client = make_client_with_handler(_customer_handler)
        result = client.customers.list(sort="asc", limit=5)
        assert isinstance(result, list)


class TestCustomersGet:
    def test_get_single_customer(self) -> None:
        client = make_client_with_handler(_customer_handler)
        customer = client.customers.get(1)
        assert isinstance(customer, Customer)
        assert customer.id == 1
        assert customer.username == "johnd"
        assert customer.address.city == "kilcoole"
        assert customer.address.geolocation.lat == "-37.3159"


class TestCustomersCreate:
    def test_create_customer_with_dict(self) -> None:
        client = make_client_with_handler(_customer_handler)
        new_customer = client.customers.create({
            "email": "jane@example.com",
            "username": "janed",
            "password": "secret",
            "name": {"firstname": "Jane", "lastname": "Doe"},
            "address": {
                "city": "Portland",
                "street": "Main St",
                "number": 42,
                "zipcode": "97201",
                "geolocation": {"lat": "45.5", "long": "-122.6"},
            },
            "phone": "1-503-555-0123",
        })
        assert new_customer.email == "jane@example.com"
        assert new_customer.id == 11


class TestCustomersUpdate:
    def test_update_customer(self) -> None:
        client = make_client_with_handler(_customer_handler)
        updated = client.customers.update(1, {"email": "new@email.com"})
        assert updated.email == "new@email.com"

    def test_partial_update(self) -> None:
        client = make_client_with_handler(_customer_handler)
        updated = client.customers.partial_update(1, {"phone": "555-1234"})
        assert updated.phone == "555-1234"


class TestCustomersDelete:
    def test_delete_customer(self) -> None:
        client = make_client_with_handler(_customer_handler)
        deleted = client.customers.delete(1)
        assert isinstance(deleted, Customer)
        assert deleted.id == 1