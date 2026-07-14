# Fake Store Client — Technical Documentation

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Database Layer](#database-layer)
4. [Data Model & Schema](#data-model--schema)
5. [Authentication & Authorization](#authentication--authorization)
6. [API Reference](#api-reference)
7. [Frontend Dashboard](#frontend-dashboard)
8. [Seeding & Data Generation](#seeding--data-generation)
9. [Migration System](#migration-system)
10. [Deployment](#deployment)

---

## Architecture Overview

Fake Store Client is a self-hosted e-commerce API and dashboard application built with **Flask** (Python) on the backend and vanilla **HTML/CSS/JavaScript** on the frontend. It provides a full CRUD REST API for managing customers, orders, and products, backed by a persistent database with dual SQLite/PostgreSQL support.

```
┌─────────────────────────────────────────────────────────┐
│                      Browser                            │
│  ┌─────────────────────────────────────────────────┐    │
│  │          index.html (Single-page app)           │    │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────┐  │    │
│  │  │Customers │ │ Orders   │ │ Batch/API Keys  │  │    │
│  │  │  Tab     │ │  Tab     │ │    Tabs         │  │    │
│  │  └────┬─────┘ └────┬─────┘ └───────┬────────┘  │    │
│  └───────┼─────────────┼───────────────┼───────────┘    │
│          │             │               │                  │
│          ▼             ▼               ▼                  │
│  ┌─────────────────────────────────────────────────┐    │
│  │            apiFetch() + Session Cookie            │    │
│  └─────────────────────┬───────────────────────────┘    │
└─────────────────────────┼───────────────────────────────┘
                          │ HTTP (JSON)
                          ▼
┌─────────────────────────────────────────────────────────┐
│                   Flask Server                          │
│  ┌────────────┐  ┌────────────┐  ┌───────────────┐    │
│  │ CORS +      │  │ before_    │  │ Route handlers │    │
│  │ Sessions    │  │ request    │  │ (customers,    │    │
│  │ middleware  │  │ auth check │  │  orders, etc.)  │    │
│  └────────────┘  └────────────┘  └───────┬───────┘    │
│                                           │             │
│                                           ▼             │
│  ┌─────────────────────────────────────────────────┐    │
│  │          Database Abstraction Layer               │    │
│  │   db_fetchone / db_fetchall / db_execute          │    │
│  │   (auto-translates ? → %s for Postgres)           │    │
│  └─────────────────────┬───────────────────────────┘    │
│                        │                                │
│           ┌────────────┴────────────┐                   │
│           ▼                         ▼                   │
│    ┌─────────────┐         ┌──────────────┐             │
│    │   SQLite     │         │  PostgreSQL   │             │
│    │ (local dev)  │         │  (Render)     │             │
│    └─────────────┘         └──────────────┘             │
└─────────────────────────────────────────────────────────┘
```

### Key Design Decisions

- **Single-file architecture** — All backend logic lives in `app/server.py` (one Flask app factory)
- **Single-page frontend** — All UI in `app/templates/index.html` (no build step, no framework)
- **Dual database** — SQLite for local development, PostgreSQL for production (auto-detected via `DATABASE_URL`)
- **API key auth** — SHA-256 hashed keys stored in DB; master key auto-generated on first run
- **Session-based dashboard** — Browser login uses Flask sessions (cookie), exempt from API key requirement
- **Auto-seeding** — On first run, fetches data from https://fakestoreapi.com; falls back to embedded data if API is unavailable

---

## Project Structure

```
fakestore_client/
├── app/
│   ├── server.py            # Flask backend (all routes, DB, auth, seeding)
│   └── templates/
│       └── index.html       # Single-page dashboard (HTML + CSS + JS)
├── data/
│   └── store.db             # SQLite database (auto-created, git-ignored)
├── .venv/                   # Python virtual environment
├── requirements.txt         # Python dependencies
├── render.yaml              # Render deployment config
└── README.md
```

---

## Database Layer

### Connection Management

The app uses Flask's `g` context to manage per-request database connections:

```python
def get_db():
    if "db" in g:
        return g.db
    if IS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
    else:
        conn = sqlite3.connect(DATABASE_URL)
        conn.row_factory = sqlite3.Row       # dict-like rows
        conn.execute("PRAGMA journal_mode=WAL")  # write-ahead logging
        conn.execute("PRAGMA foreign_keys=ON")    # enforce FK constraints
    g.db = conn
    return g.db
```

- `get_db()` returns the connection for the current request, creating one if needed
- `close_db()` is registered as a teardown handler — commits and closes the connection after each request
- SQLite uses WAL mode for concurrent read/write performance and `foreign_keys=ON` for cascade deletes

### Query Abstraction

Three helper functions abstract the SQLite/PostgreSQL dialect differences:

| Function | Purpose |
|---|---|
| `db_fetchone(db, sql, params)` | Fetch a single row as dict |
| `db_fetchall(db, sql, params)` | Fetch all rows as list of dicts |
| `db_execute(db, sql, params)` | Execute INSERT/UPDATE/DELETE |

**Dialect translation**: All SQL uses `?` placeholders (SQLite style). The helpers automatically replace `?` with `%s` when running on PostgreSQL:

```python
def q(sql: str) -> str:
    if IS_POSTGRES:
        return sql.replace("?", "%s")
    return sql
```

PostgreSQL queries use `psycopg2.extras.RealDictCursor` to return dict-like rows, matching SQLite's `sqlite3.Row` behavior.

### Row-to-Dict Conversion

`row_to_dict(row)` normalizes database rows to Python dicts. It also renames the `long_` column (SQL reserved word) to `long` in API output:

```python
def row_to_dict(row):
    if isinstance(row, dict):
        d = dict(row)
        if "long_" in d:
            d["long"] = d.pop("long_")
        return d
    # ... handles sqlite3.Row and psycopg2 RealDictCursor
```

---

## Data Model & Schema

### Entity Relationship Diagram

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────┐
│  customers   │       │     orders       │       │   products   │
│──────────────│       │──────────────────│       │──────────────│
│ email  (PK)  │──┐    │ order_number(PK) │    ┌──│ id      (PK) │
│ username     │  │    │ customer_email(FK)│───┘  │ title        │
│ password     │  └───→│ date             │       │ price        │
│ firstname    │       │ shipped_date     │       │ description  │
│ lastname     │       │ delivery_date    │       │ category     │
│ phone        │       │ created_at       │       │ image        │
│ city         │       └───────┬──────────┘       │ rate         │
│ street       │               │                  │ count        │
│ number       │               │                  └──────────────┘
│ zipcode      │               ▼
│ lat          │       ┌──────────────────┐
│ long_        │       │  order_items     │
│ created_at   │       │──────────────────│
└──────────────┘       │ id         (PK)  │
                       │ order_number(FK) │──→ orders.order_number
                       │ product_id  (FK) │──→ products.id
                       │ quantity         │
                       └──────────────────┘

┌──────────────┐
│  api_keys    │
│──────────────│
│ key_hash(PK) │    ← SHA-256 hash of the API key
│ label        │    ← "master" or user-defined
│ prefix       │    ← First 8 chars of the raw key (for identification)
│ created_at   │
│ revoked_at   │    ← NULL if active, timestamp if revoked
└──────────────┘
```

### Primary Keys

| Table | PK | Format |
|---|---|---|
| `customers` | `email` | String (e.g., `john@gmail.com`) |
| `orders` | `order_number` | 5-digit integer starting at 10001 |
| `order_items` | `id` | Auto-increment |
| `products` | `id` | Integer (1-20 from seed data) |
| `api_keys` | `key_hash` | SHA-256 hex digest |

### Order Number Generation

Order numbers are sequential 5-digit integers starting at 10001:

```python
def get_next_order_number(db) -> int:
    row = db.execute("SELECT COALESCE(MAX(order_number), 9999) + 1 FROM orders").fetchone()
    return row[0]
```

This means: first order = 10001, second = 10002, etc. Batch creation increments from this base.

### Cascade Deletes

Foreign keys use `ON DELETE CASCADE`:

- Deleting a **customer** → automatically deletes their `orders` and `order_items`
- Deleting an **order** → automatically deletes its `order_items`

The explicit DELETE routes also handle this manually for safety:

```python
# Deleting a customer also removes related orders and items
db_execute(db, "DELETE FROM order_items WHERE order_number IN (SELECT order_number FROM orders WHERE customer_email = ?)", (email,))
db_execute(db, "DELETE FROM orders WHERE customer_email = ?", (email,))
db_execute(db, "DELETE FROM customers WHERE email = ?", (email,))
```

---

## Authentication & Authorization

### Two-Layer Auth System

The app has two authentication mechanisms:

#### 1. API Key Auth (for external/API access)

Every `/api/*` request (except exempt endpoints) requires a valid API key. Three header formats are accepted:

```
Authorization: Bearer fsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Authorization: ApiKey fsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
X-API-Key: fsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Key lifecycle:**

1. **Master key** — Auto-generated on first startup (prefix `fsk_`, 48 hex chars). Printed to stdout once. Stored as SHA-256 hash in `api_keys` table with label `"master"`. Can also be set via the `API_KEY` environment variable.

2. **Additional keys** — Created via `POST /api/keys` (requires master key or dashboard session). Returns the raw key once (never stored in plaintext). Only the SHA-256 hash is persisted.

3. **Revocation** — `POST /api/keys/<prefix>/revoke` sets `revoked_at` timestamp. Revoked keys are rejected on all subsequent requests.

**Validation flow:**

```python
def require_api_key():
    # Skip auth for non-API paths, login/logout, health, and keys endpoints
    if not request.path.startswith("/api/"): return None
    if request.path in ("/api/login", "/api/logout"): return None
    if request.path == "/api/health": return None
    if request.path.startswith("/api/keys"): return None
    # Skip if dashboard session is active
    if session.get("dashboard_auth"): return None
    
    # Extract key from headers
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):  key = auth[7:].strip()
    elif auth.startswith("ApiKey "): key = auth[7:].strip()
    else: key = request.headers.get("X-API-Key", "")
    
    # Check master key first (fast path), then DB lookup
    if MASTER_API_KEY and key == MASTER_API_KEY:
        return {"label": "master", ...}
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    row = db.execute("SELECT * FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL", ...)
    return row if row else 401 error
```

#### 2. Dashboard Session Auth (for browser access)

The dashboard uses Flask's session cookie mechanism:

```python
# Login
POST /api/login  {"password": "admin"}
→ Sets session["dashboard_auth"] = True

# Logout
POST /api/logout
→ Clears session["dashboard_auth"]
```

When `session.get("dashboard_auth")` is truthy, the API key requirement is bypassed. This allows the browser dashboard to make API calls without header-based auth.

**Password:** Set via `DASHBOARD_PASSWORD` env var (defaults to `"admin"`).

### Exempt Endpoints (No Auth Required)

| Endpoint | Reason |
|---|---|
| `/api/login` | Must be accessible without auth to log in |
| `/api/logout` | Must be accessible without auth to log out |
| `/api/health` | Health checks should not require auth |
| `/api/keys` | Key management requires master key or dashboard session |
| All non-`/api/` paths | Static files, HTML templates |

---

## API Reference

Base URL: `http://localhost:5001` (local) or `https://fakestore-client.onrender.com` (production)

All endpoints below require API key auth unless noted as exempt.

### Authentication

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/login` | None | Dashboard login (`{"password": "..."}`) |
| `POST` | `/api/logout` | None | Dashboard logout |
| `GET` | `/api/health` | None | Health check with DB stats |

### API Key Management

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/keys` | Master/Dashboard | List all API keys (prefix, label, dates) |
| `POST` | `/api/keys` | Master/Dashboard | Create new key (`{"label": "my-key"}`) |
| `POST` | `/api/keys/<prefix>/revoke` | Master/Dashboard | Revoke a key by prefix |

### Customers

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/customers` | List all customers. Optional `?search=q` filters by firstname, lastname, email, or username. Each customer includes `order_count` and `order_numbers` array. |
| `GET` | `/api/customers/<email>` | Get single customer by email (URL-encoded). Includes `order_numbers` array. |
| `POST` | `/api/customers` | Create customer. Required: `email`. All other fields optional. |
| `PUT` | `/api/customers/<email>` | Update customer. Send only fields to change. Supports `long` → `long_` mapping. |
| `DELETE` | `/api/customers/<email>` | Delete customer and all their orders/items (cascade). |
| `POST` | `/api/customers/batch` | Batch create N fake customers via Faker. Body: `{"count": 5}`. Max 100. |
| `POST` | `/api/customers/delete-all` | Delete ALL customers and their orders/items. |

**Customer object:**
```json
{
  "email": "john@gmail.com",
  "username": "johnd",
  "password": "m38rmF$",
  "firstname": "John",
  "lastname": "Doe",
  "phone": "1-570-236-7033",
  "city": "kilcoole",
  "street": "new road",
  "number": 7682,
  "zipcode": "12926-3874",
  "lat": "-37.3159",
  "long": "81.1496",
  "created_at": "2024-01-01T00:00:00",
  "order_count": 2,
  "order_numbers": [10001, 10002]
}
```

### Orders

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/orders` | List all orders with customer name and products. Optional `?search=q` filters by order number, customer name, or email. |
| `GET` | `/api/orders/<order_number>` | Get single order with full product details. |
| `POST` | `/api/orders` | Create order. Required: `customer_email`. Optional: `date`, `shipped_date`, `delivery_date`, `products`/`items` array. |
| `DELETE` | `/api/orders/<order_number>` | Delete order and its items. |
| `POST` | `/api/orders/batch` | Batch create N fake orders via Faker. Body: `{"count": 5, "link_customer_emails": [...]}`. Max 100. |
| `POST` | `/api/orders/delete-all` | Delete ALL orders and items. |

**Order object:**
```json
{
  "order_number": 10001,
  "customer_email": "john@gmail.com",
  "customer_name": "John Doe",
  "date": "2024-01-15",
  "shipped_date": "2024-01-17",
  "delivery_date": "2024-01-22",
  "created_at": "2024-01-01T00:00:00",
  "products": [
    {
      "product_id": 1,
      "quantity": 4,
      "title": "Fjallraven - Foldsack No. 1 Backpack",
      "price": 109.95
    }
  ]
}
```

### Customer ↔ Order Linking

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/customers/<email>/orders` | Get all orders for a customer, with product details. |
| `PUT` | `/api/orders/<order_number>/customer` | Reassign an order to a different customer. Body: `{"customer_email": "new@email.com"}`. |

### Products (Read-Only)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/products` | List all products, sorted by category then title. |
| `GET` | `/api/products/<id>` | Get single product by ID. |

### Utility

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/stats` | Get counts: customers, orders, products, order_items, db_type. |
| `POST` | `/api/reseed` | Delete all data and re-seed from Fake Store API (or fallback). |

---

## Frontend Dashboard

The dashboard is a single-page application rendered from `app/templates/index.html`. No build tools or frameworks — pure HTML, CSS, and vanilla JavaScript.

### Tab Navigation

| Tab | Content |
|---|---|
| **👥 Customers** | Search, create, edit, delete customers. Side-by-side panel shows customer's orders. Click an order # to see full detail. |
| **📦 Orders** | Search, create, edit, delete orders. Shows customer info, products, totals. |
| **⚡ Batch Create** | Generate random customers and orders using Faker. Configurable count (1–100). |
| **🔑 API Keys** | View, create, and revoke API keys. Shows prefix, label, creation date, and revoked status. |
| **📖 API Docs** | Interactive API documentation with example requests and responses. |

### Customer Detail Panel

The Customers tab uses a **side-by-side grid layout** (`1fr 1fr`):

- **Left panel**: Customer table (Name, Email, Order #, Actions)
  - Entire row is clickable → opens order list for that customer in the right panel
  - Order # badges are individually clickable → opens that single order's detail
- **Right panel**: Context-sensitive panel with two views:
  1. **Order list** (default when clicking a customer row) — shows all orders with summary data
  2. **Order detail** (when clicking a specific order #) — shows full item breakdown with prices, subtotals, shipping dates

Navigation: "← Back to Orders" button returns from detail to list. "✕ Close" dismisses the panel.

### Search

The customer and order search bars use **debounced live search** (250ms delay). The `oninput` event calls `liveSearchCustomers()` / `liveSearchOrders()`, which fetches from the API with `?search=` query parameter.

Backend search uses `LIKE %term%` across multiple fields:
- **Customers**: firstname, lastname, email, username
- **Orders**: order number, customer firstname, lastname, full name, email

### Live Search Implementation

```javascript
let _customerSearchTimer;
function liveSearchCustomers() {
  clearTimeout(_customerSearchTimer);
  _customerSearchTimer = setTimeout(() => loadCustomers(
    document.getElementById('customer-search').value
  ), 250);
}
```

The search term is URL-encoded via `encodeURIComponent()` before being sent to the API, so special characters like `@` in email addresses work correctly.

### Theme

The dashboard uses a **light wireframe theme** with:
- White cards on `#f8fafc` background
- Outlined/ghost buttons (colored borders, white fill, tinted hover)
- Pastel badges for categories/status
- Focus glow rings on inputs (`box-shadow: 0 0 0 3px rgba(59,130,246,0.12)`)
- Subtle shadows (`0 1px 3px rgba(0,0,0,0.06)`)
- Color variables via CSS custom properties for easy theming

---

## Seeding & Data Generation

### Initial Seed

On first startup, `seed_if_empty()` checks if the products table has data. If empty:

1. **Try live API** — Fetches `https://fakestoreapi.com/products`, `/users`, and `/carts`
   - Products are stored as-is
   - Users are converted to customers (email as PK, address fields flattened)
   - Carts are converted to orders (5-digit order numbers starting at 10001)
   - Shipping/delivery dates are auto-generated (order date + 2 days / + 7 days)
2. **Fallback** — If the live API is unavailable, uses embedded `_FALLBACK_PRODUCTS`, `_FALLBACK_CUSTOMERS`, and `_FALLBACK_ORDERS` arrays (20 products, 10 customers, 7 orders)

### Faker Batch Generation

The `/api/customers/batch` and `/api/orders/batch` endpoints use the `faker` library to generate realistic random data:

- **Customers**: Random name, email, username, phone, address (city, street, number, zipcode, lat/long)
- **Orders**: Random customer assignment, 1–5 items per order, random quantities, realistic date ranges

Orders can optionally be linked to specific customers:

```json
POST /api/orders/batch
{
  "count": 5,
  "link_customer_emails": ["john@gmail.com", "jane@example.com"]
}
```

### Re-seeding

`POST /api/reseed` deletes all data and re-runs the seed process. Useful for resetting the database to a clean state.

---

## Migration System

### Schema Detection

On startup, `_needs_migration()` checks if the database has the **old schema** (UUID-based `id` column in customers table). If detected:

1. All tables are dropped (`order_items`, `orders`, `customers`, `products`, `api_keys`)
2. Tables are recreated with the new schema (email-based PK for customers, 5-digit order_number PK for orders)
3. Data is re-seeded from the live API or fallback data

This handles upgrades from the original Fake Store API schema (which used integer `id` for users) to the current schema (which uses `email` as customer PK).

---

## Deployment

### Render (Production)

The app is configured for deployment on [Render](https://render.com) via `render.yaml`:

- **Build**: `pip install -r requirements.txt`
- **Start**: `gunicorn app.server:create_app()` (via Render's Python runtime)
- **Database**: PostgreSQL on Render (auto-provisioned via `DATABASE_URL` env var)
- **Environment variables**:
  - `DATABASE_URL` — PostgreSQL connection string (auto-set by Render)
  - `SECRET_KEY` — Flask session key
  - `DASHBOARD_PASSWORD` — Login password for the dashboard (default: `admin`)
  - `API_KEY` — Optional: pre-set the master API key (otherwise auto-generated)

### Local Development

```bash
cd fakestore_client
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m app.server
# → 🛒 Fake Store running at http://localhost:5001
```

SQLite database is auto-created at `data/store.db`. The `data/` directory is git-ignored.

### Dependencies

- **Flask** — Web framework
- **flask-cors** — CORS support for API access
- **gunicorn** — Production WSGI server (used on Render)
- **httpx** — HTTP client for seeding from Fake Store API
- **Faker** — Random data generation for batch creation
- **psycopg2** — PostgreSQL adapter (only needed when `DATABASE_URL` points to Postgres)