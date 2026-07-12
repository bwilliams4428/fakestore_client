"""fakestore_client — typed Python client for the Fake Store API.

Quick start::

    from fakestore_client import FakeStoreClient

    client = FakeStoreClient()
    customers = client.customers.list()
    orders = client.orders.get(1)
"""

from fakestore_client.auth import AsyncAuth, SyncAuth
from fakestore_client.base import APIError
from fakestore_client.client import AsyncFakeStoreClient, FakeStoreClient
from fakestore_client.customers import AsyncCustomers, SyncCustomers
from fakestore_client.models import (
    Address,
    AuthToken,
    CartItem,
    Customer,
    CustomerCreate,
    CustomerUpdate,
    Geolocation,
    LoginRequest,
    Name,
    Order,
    OrderCreate,
    OrderUpdate,
    Product,
    ProductCreate,
    ProductUpdate,
    Rating,
)
from fakestore_client.orders import AsyncOrders, SyncOrders
from fakestore_client.products import AsyncProducts, SyncProducts

__all__ = [
    # Client facades
    "FakeStoreClient",
    "AsyncFakeStoreClient",
    # Exceptions
    "APIError",
    # Models
    "Address",
    "AuthToken",
    "CartItem",
    "Customer",
    "CustomerCreate",
    "CustomerUpdate",
    "Geolocation",
    "LoginRequest",
    "Name",
    "Order",
    "OrderCreate",
    "OrderUpdate",
    "Product",
    "ProductCreate",
    "ProductUpdate",
    "Rating",
    # Resource classes (advanced usage)
    "SyncCustomers",
    "AsyncCustomers",
    "SyncOrders",
    "AsyncOrders",
    "SyncProducts",
    "AsyncProducts",
    "SyncAuth",
    "AsyncAuth",
]