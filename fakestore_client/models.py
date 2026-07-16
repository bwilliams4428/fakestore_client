"""Pydantic models for Fake Store API responses and request bodies.

The Fake Store API uses these resources:
  - /users   → Customer (we expose "customers" as the domain-friendly name)
  - /carts   → Order (carts represent orders in this API)
  - /products → Product
  - /auth/login → AuthToken
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Nested / shared models
# ---------------------------------------------------------------------------


class Geolocation(BaseModel):
    lat: str
    long: str


class Name(BaseModel):
    firstname: str
    lastname: str


class Address(BaseModel):
    geolocation: Geolocation
    city: str
    street: str
    number: int
    zipcode: str


class Rating(BaseModel):
    rate: float
    count: int


class CartItem(BaseModel):
    """A single line-item inside an Order/Cart."""

    productId: int
    quantity: int


# ---------------------------------------------------------------------------
# Customer (maps to /users)
# ---------------------------------------------------------------------------


class Customer(BaseModel):
    """Full customer record returned by the API."""

    id: Optional[int] = None
    email: str
    username: str
    password: Optional[str] = None
    name: Name
    address: Address
    phone: str
    version: Optional[int] = Field(None, alias="__v")

    model_config = {"populate_by_name": True}


class CustomerCreate(BaseModel):
    """Payload for creating a new customer.

    Only ``email`` and ``username`` are required by the API schema,
    but most realistic payloads include name, address, and phone.
    """

    email: str
    username: str
    password: Optional[str] = None
    name: Optional[Name] = None
    address: Optional[Address] = None
    phone: Optional[str] = None


class CustomerUpdate(BaseModel):
    """Payload for updating a customer. All fields are optional."""

    email: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    name: Optional[Name] = None
    address: Optional[Address] = None
    phone: Optional[str] = None


# ---------------------------------------------------------------------------
# Order (maps to /carts)
# ---------------------------------------------------------------------------


class Order(BaseModel):
    """An order (cart) returned by the API."""

    id: Optional[int] = None
    userId: int
    date: str  # ISO-8601 date string, e.g. "2020-03-02T00:00:00.000Z"
    products: list[CartItem] = []
    status: str = "not shipped"  # "shipped" or "not shipped"
    tracking_url: Optional[str] = None
    shipped_date: Optional[str] = None
    delivery_date: Optional[str] = None
    version: Optional[int] = Field(None, alias="__v")

    model_config = {"populate_by_name": True}


class OrderCreate(BaseModel):
    """Payload for creating a new order/cart."""

    userId: int
    date: str
    products: list[CartItem] = []
    status: str = "not shipped"
    tracking_url: Optional[str] = None
    shipped_date: Optional[str] = None
    delivery_date: Optional[str] = None


class OrderUpdate(BaseModel):
    """Payload for updating an order. All fields are optional."""

    userId: Optional[int] = None
    date: Optional[str] = None
    products: Optional[list[CartItem]] = None
    status: Optional[str] = None
    tracking_url: Optional[str] = None
    shipped_date: Optional[str] = None
    delivery_date: Optional[str] = None


# ---------------------------------------------------------------------------
# Product (maps to /products)
# ---------------------------------------------------------------------------


class Product(BaseModel):
    """Full product record returned by the API."""

    id: Optional[int] = None
    title: str
    price: float
    description: str
    category: str
    image: str
    rating: Optional[Rating] = None


class ProductCreate(BaseModel):
    """Payload for creating a new product."""

    id: Optional[int] = None
    title: str
    price: float
    description: str
    category: str
    image: str


class ProductUpdate(BaseModel):
    """Payload for updating a product. All fields are optional."""

    title: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
    category: Optional[str] = None
    image: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class AuthToken(BaseModel):
    """JWT token returned by ``POST /auth/login``."""

    token: str


class LoginRequest(BaseModel):
    """Credentials for the auth/login endpoint."""

    username: str
    password: str