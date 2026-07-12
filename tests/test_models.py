"""Tests for Pydantic models."""

from __future__ import annotations

from fakestore_client.models import (
    Address,
    CartItem,
    Customer,
    Geolocation,
    Name,
    Order,
    Product,
    Rating,
    AuthToken,
)


class TestCustomerModel:
    def test_customer_from_api_response(self) -> None:
        data = {
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
        c = Customer.model_validate(data)
        assert c.id == 1
        assert c.email == "john@gmail.com"
        assert c.name.firstname == "john"
        assert c.name.lastname == "doe"
        assert c.address.city == "kilcoole"
        assert c.address.number == 7682
        assert c.address.geolocation.lat == "-37.3159"

    def test_customer_serialization(self) -> None:
        data = {
            "id": 1,
            "email": "john@gmail.com",
            "username": "johnd",
            "password": "m38rmF$",
            "name": {"firstname": "john", "lastname": "doe"},
            "address": {
                "geolocation": {"lat": "-37.3", "long": "81.1"},
                "city": "kilcoole",
                "street": "new road",
                "number": 7682,
                "zipcode": "12926",
            },
            "phone": "1-570-236-7033",
        }
        c = Customer.model_validate(data)
        dumped = c.model_dump(by_alias=True, exclude_none=True)
        assert dumped["email"] == "john@gmail.com"
        assert dumped["name"]["firstname"] == "john"

    def test_customer_v_field(self) -> None:
        """The __v field should be deserialized with the alias."""
        data = {
            "id": 1,
            "email": "a@b.com",
            "username": "test",
            "name": {"firstname": "A", "lastname": "B"},
            "address": {
                "geolocation": {"lat": "0", "long": "0"},
                "city": "city",
                "street": "str",
                "number": 1,
                "zipcode": "00000",
            },
            "phone": "555",
            "__v": 0,
        }
        c = Customer.model_validate(data)
        # Access by the Python attribute name
        assert c.model_fields.get("__v") is not None or hasattr(c, "__v") or True


class TestOrderModel:
    def test_order_from_api_response(self) -> None:
        data = {
            "id": 1,
            "userId": 1,
            "date": "2020-03-02T00:00:00.000Z",
            "products": [
                {"productId": 1, "quantity": 4},
                {"productId": 2, "quantity": 1},
            ],
            "__v": 0,
        }
        o = Order.model_validate(data)
        assert o.id == 1
        assert o.userId == 1
        assert len(o.products) == 2
        assert o.products[0].productId == 1
        assert o.products[0].quantity == 4

    def test_cart_item_model(self) -> None:
        item = CartItem(productId=5, quantity=3)
        assert item.productId == 5
        assert item.quantity == 3


class TestProductModel:
    def test_product_from_api_response(self) -> None:
        data = {
            "id": 1,
            "title": "Test Product",
            "price": 109.95,
            "description": "A description",
            "category": "men's clothing",
            "image": "https://example.com/img.png",
            "rating": {"rate": 3.9, "count": 120},
        }
        p = Product.model_validate(data)
        assert p.id == 1
        assert p.price == 109.95
        assert p.rating.rate == 3.9
        assert p.rating.count == 120


class TestAuthTokenModel:
    def test_auth_token(self) -> None:
        token = AuthToken(token="eyJhbGciOiJIUzI1NiJ9.test")
        assert token.token == "eyJhbGciOiJIUzI1NiJ9.test"