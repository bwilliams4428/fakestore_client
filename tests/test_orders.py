"""Tests for the Orders resource (sync)."""

from __future__ import annotations

import json

import httpx
import pytest

from fakestore_client import Order, FakeStoreClient
from tests.conftest import SAMPLE_ORDER, make_client_with_handler


def _order_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    method = request.method

    if method == "GET" and path == "/carts":
        return httpx.Response(200, json=[SAMPLE_ORDER])
    if method == "GET" and path.startswith("/carts/"):
        return httpx.Response(200, json=SAMPLE_ORDER)
    if method == "POST" and path == "/carts":
        body = json.loads(request.content)
        result = {**SAMPLE_ORDER, **body, "id": 11}
        return httpx.Response(201, json=result)
    if method == "PUT" and path.startswith("/carts/"):
        body = json.loads(request.content)
        result = {**SAMPLE_ORDER, **body}
        return httpx.Response(200, json=result)
    if method == "PATCH" and path.startswith("/carts/"):
        body = json.loads(request.content)
        result = {**SAMPLE_ORDER, **body}
        return httpx.Response(200, json=result)
    if method == "DELETE" and path.startswith("/carts/"):
        return httpx.Response(200, json=SAMPLE_ORDER)

    return httpx.Response(404, json={"message": "Not found"})


class TestOrdersList:
    def test_list_returns_orders(self) -> None:
        client = make_client_with_handler(_order_handler)
        result = client.orders.list()
        assert len(result) == 1
        assert isinstance(result[0], Order)
        assert result[0].userId == 1
        assert len(result[0].products) == 3

    def test_list_with_date_range(self) -> None:
        client = make_client_with_handler(_order_handler)
        result = client.orders.list(
            start_date="2020-01-01", end_date="2020-12-31", sort="desc"
        )
        assert isinstance(result, list)


class TestOrdersGet:
    def test_get_single_order(self) -> None:
        client = make_client_with_handler(_order_handler)
        order = client.orders.get(1)
        assert isinstance(order, Order)
        assert order.id == 1
        assert order.products[0].productId == 1
        assert order.products[0].quantity == 4


class TestOrdersCreate:
    def test_create_order(self) -> None:
        client = make_client_with_handler(_order_handler)
        new_order = client.orders.create({
            "userId": 2,
            "date": "2024-01-15T00:00:00.000Z",
            "products": [
                {"productId": 5, "quantity": 2},
            ],
        })
        assert new_order.userId == 2
        assert new_order.id == 11


class TestOrdersUpdate:
    def test_update_order(self) -> None:
        client = make_client_with_handler(_order_handler)
        updated = client.orders.update(1, {
            "products": [{"productId": 10, "quantity": 3}],
        })
        assert isinstance(updated, Order)

    def test_partial_update(self) -> None:
        client = make_client_with_handler(_order_handler)
        updated = client.orders.partial_update(1, {"date": "2024-06-01"})
        assert isinstance(updated, Order)


class TestOrdersDelete:
    def test_delete_order(self) -> None:
        client = make_client_with_handler(_order_handler)
        deleted = client.orders.delete(1)
        assert isinstance(deleted, Order)
        assert deleted.id == 1