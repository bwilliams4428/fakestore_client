"""Tests for the Products resource and Auth (sync)."""

from __future__ import annotations

import json

import httpx
import pytest

from fakestore_client import Product, AuthToken, FakeStoreClient
from tests.conftest import (
    SAMPLE_PRODUCT,
    SAMPLE_AUTH_TOKEN,
    SAMPLE_CATEGORIES,
    make_client_with_handler,
)


def _product_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    method = request.method

    # Must check /products/categories BEFORE /products/{id}
    if method == "GET" and path == "/products/categories":
        return httpx.Response(200, json=SAMPLE_CATEGORIES)
    if method == "GET" and "/products/category/" in path:
        return httpx.Response(200, json=[SAMPLE_PRODUCT])
    if method == "GET" and path == "/products":
        return httpx.Response(200, json=[SAMPLE_PRODUCT])
    if method == "GET" and path.startswith("/products/"):
        return httpx.Response(200, json=SAMPLE_PRODUCT)
    if method == "POST" and path == "/products":
        body = json.loads(request.content)
        result = {**SAMPLE_PRODUCT, **body, "id": 21}
        return httpx.Response(201, json=result)
    if method == "PUT" and path.startswith("/products/"):
        body = json.loads(request.content)
        result = {**SAMPLE_PRODUCT, **body}
        return httpx.Response(200, json=result)
    if method == "DELETE" and path.startswith("/products/"):
        return httpx.Response(200, json=SAMPLE_PRODUCT)

    return httpx.Response(404, json={"message": "Not found"})


def _auth_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    method = request.method

    if method == "POST" and path == "/auth/login":
        body = json.loads(request.content)
        if body.get("username") == "johnd" and body.get("password") == "m38rmF$":
            return httpx.Response(200, json=SAMPLE_AUTH_TOKEN)
        return httpx.Response(401, json={"message": "Invalid credentials"})

    return httpx.Response(404, json={"message": "Not found"})


class TestProductsList:
    def test_list_returns_products(self) -> None:
        client = make_client_with_handler(_product_handler)
        result = client.products.list()
        assert len(result) == 1
        assert isinstance(result[0], Product)
        assert result[0].title.startswith("Fjallraven")

    def test_list_with_sort_and_limit(self) -> None:
        client = make_client_with_handler(_product_handler)
        result = client.products.list(sort="desc", limit=5)
        assert isinstance(result, list)


class TestProductsGet:
    def test_get_single_product(self) -> None:
        client = make_client_with_handler(_product_handler)
        product = client.products.get(1)
        assert product.id == 1
        assert product.price == 109.95
        assert product.rating.rate == 3.9


class TestProductsCategories:
    def test_categories(self) -> None:
        client = make_client_with_handler(_product_handler)
        cats = client.products.categories()
        assert cats == SAMPLE_CATEGORIES

    def test_by_category(self) -> None:
        client = make_client_with_handler(_product_handler)
        result = client.products.by_category("men's clothing")
        assert isinstance(result, list)
        assert len(result) == 1


class TestProductsCreate:
    def test_create_product(self) -> None:
        client = make_client_with_handler(_product_handler)
        p = client.products.create({
            "title": "New Item",
            "price": 29.99,
            "description": "A new product",
            "category": "electronics",
            "image": "https://example.com/img.png",
        })
        assert p.id == 21
        assert p.title == "New Item"


class TestProductsUpdate:
    def test_update_product(self) -> None:
        client = make_client_with_handler(_product_handler)
        p = client.products.update(1, {"price": 199.99})
        assert p.price == 199.99


class TestProductsDelete:
    def test_delete_product(self) -> None:
        client = make_client_with_handler(_product_handler)
        p = client.products.delete(1)
        assert isinstance(p, Product)


class TestAuth:
    def test_login_success(self) -> None:
        client = make_client_with_handler(_auth_handler)
        token = client.auth.login("johnd", "m38rmF$")
        assert isinstance(token, AuthToken)
        assert len(token.token) > 10

    def test_login_failure(self) -> None:
        from fakestore_client.base import APIError

        client = make_client_with_handler(_auth_handler)
        with pytest.raises(APIError) as exc_info:
            client.auth.login("wrong", "creds")
        assert exc_info.value.status_code == 401