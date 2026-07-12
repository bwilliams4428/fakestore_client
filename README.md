# Fake Store API Client

A typed Python client library for the [Fake Store API](https://fakestoreapi.com/) — a free REST API for prototyping and testing e-commerce applications.

## Features

- **Customers** — CRUD operations on `/users` with full Pydantic models
- **Orders** — CRUD operations on `/carts` (the Fake Store API's order model) with line-item support
- **Products** — Read-only access to `/products` with category filtering and sorting
- **Auth** — Login endpoint returning JWT tokens
- **Async & Sync** — First-class `async`/`await` support via `httpx`, with a synchronous fallback
- **Typed models** — Pydantic v2 models with validation, serialization, and IDE autocomplete
- **Pagination & sorting** — Built-in `limit`, `sort`, and date-range helpers
- **Error handling** — Structured exceptions with HTTP status codes

## Installation

```bash
pip install fakestore-client
```

## Quick Start

```python
from fakestore_client import FakeStoreClient

client = FakeStoreClient()

# Get all customers
customers = client.customers.list()

# Get a specific order
order = client.orders.get(1)

# Create a new customer
new_customer = client.customers.create({
    "email": "jane@example.com",
    "username": "janed",
    "password": "m38rmF$",
    "name": {"firstname": "Jane", "lastname": "Doe"},
    "address": {
        "city": "Portland",
        "street": "Main St",
        "number": 42,
        "zipcode": "97201-1234",
        "geolocation": {"lat": "45.5152", "long": "-122.6784"},
    },
    "phone": "1-503-555-0123",
})

# Update an order (add items)
updated = client.orders.update(1, {
    "userId": 1,
    "date": "2024-01-15",
    "products": [
        {"productId": 1, "quantity": 3},
        {"productId": 5, "quantity": 1},
    ],
})

# Delete a customer
client.customers.delete(5)

# Auth — get a JWT token
token = client.auth.login("johnd", "m38rmF$")
```

## Async Usage

```python
import asyncio
from fakestore_client import AsyncFakeStoreClient

async def main():
    async with AsyncFakeStoreClient() as client:
        customers = await client.customers.list()
        order = await client.orders.get(1)

asyncio.run(main())
```

## API Reference

### `FakeStoreClient(base_url=..., timeout=...)`

| Parameter  | Default                        | Description              |
|------------|--------------------------------|--------------------------|
| `base_url` | `https://fakestoreapi.com`     | API base URL             |
| `timeout`  | `30`                           | Request timeout (seconds)|

### Customers (`client.customers`)

| Method                              | Endpoint            | Description             |
|-------------------------------------|---------------------|-------------------------|
| `.list(sort=..., limit=...)`        | `GET /users`        | List all customers      |
| `.get(user_id)`                     | `GET /users/{id}`   | Get a single customer   |
| `.create(data)`                     | `POST /users`       | Create a new customer   |
| `.update(user_id, data)`            | `PUT /users/{id}`   | Update a customer       |
| `.partial_update(user_id, data)`    | `PATCH /users/{id}` | Partially update       |
| `.delete(user_id)`                  | `DELETE /users/{id}`| Delete a customer      |

### Orders (`client.orders`)

The Fake Store API models orders as **carts** — each cart represents an order with a user, date, and list of product line items.

| Method                              | Endpoint            | Description             |
|-------------------------------------|---------------------|-------------------------|
| `.list(start_date=..., end_date=..., limit=..., sort=...)` | `GET /carts` | List all orders |
| `.get(cart_id)`                     | `GET /carts/{id}`   | Get a single order     |
| `.create(data)`                     | `POST /carts`       | Create a new order     |
| `.update(cart_id, data)`            | `PUT /carts/{id}`   | Update an order        |
| `.partial_update(cart_id, data)`    | `PATCH /carts/{id}` | Partially update       |
| `.delete(cart_id)`                  | `DELETE /carts/{id}`| Delete an order        |

### Products (`client.products`)

| Method                              | Endpoint                        | Description              |
|-------------------------------------|---------------------------------|--------------------------|
| `.list(sort=..., limit=...)`       | `GET /products`                  | List all products        |
| `.get(product_id)`                  | `GET /products/{id}`            | Get a single product     |
| `.categories()`                     | `GET /products/categories`      | List category names      |
| `.by_category(category)`            | `GET /products/category/{cat}`  | Products in a category   |
| `.create(data)`                     | `POST /products`                 | Create a product        |
| `.update(product_id, data)`        | `PUT /products/{id}`            | Update a product        |
| `.delete(product_id)`               | `DELETE /products/{id}`         | Delete a product        |

### Auth (`client.auth`)

| Method                          | Endpoint          | Description              |
|----------------------------------|-------------------|--------------------------|
| `.login(username, password)`    | `POST /auth/login`| Get a JWT auth token     |

## Models

All responses are returned as Pydantic models:

- **`Customer`** — id, email, username, password, name (firstname/lastname), address, phone
- **`Order`** — id, userId, date, products (list of CartItem), \_\_v
- **`CartItem`** — productId, quantity
- **`Product`** — id, title, price, description, category, image, rating
- **`AuthToken`** — token

## License

MIT