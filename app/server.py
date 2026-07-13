"""Flask backend with PostgreSQL persistence for Fake Store API data.

- PostgreSQL via DATABASE_URL (use Neon free tier on Render)
- Falls back to local SQLite for development
- Auto-seeds from the live Fake Store API on first run
- Full CRUD for customers and orders
- API key authentication for external access
- REST JSON API at /api/*
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from flask import Flask, g, jsonify, request, session
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------
# DATABASE_URL can be either:
#   - PostgreSQL: postgresql://user:pass@host/dbname  (production / Neon)
#   - SQLite:     /path/to/store.db                    (local dev fallback)
_DEFAULT_DB = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "data", "store.db")
DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_DB)

IS_POSTGRES = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")

# Master API key — set via env var or auto-generated on first run
MASTER_API_KEY = os.environ.get("API_KEY", "")


# ---------------------------------------------------------------------------
# Schema — works for both SQLite and PostgreSQL
# ---------------------------------------------------------------------------
SCHEMA_SQLITE = """\
CREATE TABLE IF NOT EXISTS customers (
    id          TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    username    TEXT NOT NULL,
    password    TEXT,
    firstname   TEXT NOT NULL,
    lastname    TEXT NOT NULL,
    phone       TEXT,
    city        TEXT,
    street      TEXT,
    number      INTEGER,
    zipcode     TEXT,
    lat         TEXT,
    long        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    price       REAL NOT NULL,
    description TEXT,
    category    TEXT,
    image       TEXT,
    rate        REAL,
    count       INTEGER
);

CREATE TABLE IF NOT EXISTS orders (
    id          TEXT PRIMARY KEY,
    order_number INTEGER NOT NULL,
    customer_id TEXT NOT NULL REFERENCES customers(id),
    date        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_hash    TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    prefix      TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at  TEXT
);
"""

SCHEMA_POSTGRES = """\
CREATE TABLE IF NOT EXISTS customers (
    id          TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    username    TEXT NOT NULL,
    password    TEXT,
    firstname   TEXT NOT NULL,
    lastname    TEXT NOT NULL,
    phone       TEXT,
    city        TEXT,
    street      TEXT,
    number      INTEGER,
    zipcode     TEXT,
    lat         TEXT,
    long        TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    price       DOUBLE PRECISION NOT NULL,
    description TEXT,
    category    TEXT,
    image       TEXT,
    rate        DOUBLE PRECISION,
    count       INTEGER
);

CREATE TABLE IF NOT EXISTS orders (
    id          TEXT PRIMARY KEY,
    order_number SERIAL,  -- auto-incrementing
    customer_id TEXT NOT NULL REFERENCES customers(id),
    date        TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
    id          SERIAL PRIMARY KEY,
    order_id    TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_hash    TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    prefix      TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    revoked_at  TIMESTAMP
);

-- Ensure order_number is unique and sequential
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_order_number ON orders(order_number);
"""


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    """Get a database connection for the current request."""
    if "db" in g:
        return g.db

    if IS_POSTGRES:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        g.db = conn
        g.db_type = "postgres"
    else:
        os.makedirs(os.path.dirname(DATABASE_URL), exist_ok=True)
        conn = sqlite3.connect(DATABASE_URL)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        g.db = conn
        g.db_type = "sqlite"
    return g.db


def get_db_type() -> str:
    """Return 'postgres' or 'sqlite'."""
    if "db_type" not in g:
        get_db()
    return g.db_type


def close_db(exc: BaseException | None = None) -> None:
    db = g.pop("db", None)
    db_type = g.pop("db_type", None)
    if db is not None:
        try:
            if db_type == "sqlite":
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                db.commit()
            else:
                db.commit()
        except Exception:
            pass
        db.close()


def q(sql: str) -> str:
    """Convert ? placeholders to %s for PostgreSQL. SQLite uses ? natively."""
    if IS_POSTGRES:
        return sql.replace("?", "%s")
    return sql


def row_to_dict(row) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "keys"):
        # sqlite3.Row or psycopg2 RealDictRow
        return dict(row)
    # tuple — shouldn't happen, but fallback
    return {}


def init_db() -> None:
    db = get_db()
    db_type = get_db_type()

    if db_type == "sqlite":
        db.executescript(SCHEMA_SQLITE)
        # Migration: add order_number column if missing
        try:
            db.execute("ALTER TABLE orders ADD COLUMN order_number INTEGER")
        except sqlite3.OperationalError:
            pass
        # Backfill order_number
        rows = db.execute("SELECT id FROM orders WHERE order_number IS NULL ORDER BY created_at").fetchall()
        for i, row in enumerate(rows, 1):
            db.execute("UPDATE orders SET order_number = ? WHERE id = ?", (i, row["id"]))
    else:
        cur = db.cursor()
        cur.execute(SCHEMA_POSTGRES)
        db.commit()

    # Handle master API key
    global MASTER_API_KEY
    if MASTER_API_KEY:
        key_hash = _hash_key(MASTER_API_KEY)
        prefix = MASTER_API_KEY[:8]
        if db_type == "sqlite":
            existing = db.execute("SELECT key_hash FROM api_keys WHERE label = 'master'").fetchone()
            if not existing:
                db.execute(
                    "INSERT INTO api_keys (key_hash, label, prefix, created_at) VALUES (?, 'master', ?, datetime('now'))",
                    (key_hash, prefix),
                )
                db.commit()
        else:
            cur = db.cursor()
            cur.execute("SELECT key_hash FROM api_keys WHERE label = %s", ("master",))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO api_keys (key_hash, label, prefix, created_at) VALUES (%s, %s, %s, NOW())",
                    (key_hash, "master", prefix),
                )
                db.commit()
    else:
        if db_type == "sqlite":
            existing = db.execute("SELECT key_hash FROM api_keys WHERE label = 'master'").fetchone()
            if not existing:
                MASTER_API_KEY = "fsk_" + secrets.token_hex(24)
                key_hash = _hash_key(MASTER_API_KEY)
                prefix = MASTER_API_KEY[:8]
                db.execute(
                    "INSERT INTO api_keys (key_hash, label, prefix, created_at) VALUES (?, 'master', ?, datetime('now'))",
                    (key_hash, prefix),
                )
                db.commit()
                print(f"\n🔑 Master API Key (save this — it won't be shown again):\n   {MASTER_API_KEY}\n")
        else:
            cur = db.cursor()
            cur.execute("SELECT key_hash FROM api_keys WHERE label = %s", ("master",))
            if not cur.fetchone():
                MASTER_API_KEY = "fsk_" + secrets.token_hex(24)
                key_hash = _hash_key(MASTER_API_KEY)
                prefix = MASTER_API_KEY[:8]
                cur.execute(
                    "INSERT INTO api_keys (key_hash, label, prefix, created_at) VALUES (%s, %s, %s, NOW())",
                    (key_hash, "master", prefix),
                )
                db.commit()
                print(f"\n🔑 Master API Key (save this — it won't be shown again):\n   {MASTER_API_KEY}\n")
    db.commit()


def get_next_order_number(db) -> int:
    """Return the next sequential order number."""
    db_type = get_db_type()
    if db_type == "sqlite":
        row = db.execute("SELECT COALESCE(MAX(order_number), 0) + 1 FROM orders").fetchone()
    else:
        cur = db.cursor()
        cur.execute("SELECT COALESCE(MAX(order_number), 0) + 1 FROM orders")
        row = cur.fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# API Key authentication
# ---------------------------------------------------------------------------

def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def check_api_key(key: str) -> Optional[dict]:
    """Validate an API key. Returns the key record if valid, None otherwise.
    Also accepts the master API key (set via API_KEY env var)."""
    if not key:
        return None
    # Check if it's the master key
    if MASTER_API_KEY and key == MASTER_API_KEY:
        return {"label": "master", "prefix": key[:8], "key_hash": _hash_key(key)}
    key_hash = _hash_key(key)
    try:
        db = get_db()
        db_type = get_db_type()
        if db_type == "sqlite":
            row = db.execute(
                "SELECT * FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL",
                (key_hash,),
            ).fetchone()
        else:
            import psycopg2.extras
            cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM api_keys WHERE key_hash = %s AND revoked_at IS NULL",
                (key_hash,),
            )
            row = cur.fetchone()
        return row_to_dict(row) if row else None
    except Exception:
        return None


def require_api_key():
    """Flask before_request hook: require a valid API key for /api/* routes
    unless the request comes from the dashboard (session auth)."""
    if not request.path.startswith("/api/"):
        return None
    if request.path in ("/api/login", "/api/logout"):
        return None
    if request.path.startswith("/api/keys"):
        return None
    if session.get("dashboard_auth"):
        return None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        key = auth[7:].strip()
    elif auth.startswith("ApiKey "):
        key = auth[7:].strip()
    else:
        key = request.headers.get("X-API-Key", "")
    if not key:
        return jsonify({"error": "API key required. Pass via Authorization: Bearer *** or X-API-Key header."}), 401
    result = check_api_key(key)
    if result is None:
        return jsonify({"error": "Invalid or revoked API key."}), 401
    return None


# ---------------------------------------------------------------------------
# Seed from Fake Store API
# ---------------------------------------------------------------------------

def seed_if_empty() -> None:
    """Seed products from the live API if the products table is empty."""
    db = get_db()
    db_type = get_db_type()

    if db_type == "sqlite":
        count = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    else:
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM products")
        count = cur.fetchone()[0]

    if count > 0:
        return

    import httpx
    client = httpx.Client(base_url="https://fakestoreapi.com", timeout=30)

    # Seed products
    products = client.get("/products").json()
    for p in products:
        if db_type == "sqlite":
            db.execute(
                """INSERT OR IGNORE INTO products
                   (id, title, price, description, category, image, rate, count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (p["id"], p["title"], p["price"], p.get("description", ""),
                 p.get("category", ""), p.get("image", ""),
                 p.get("rating", {}).get("rate"), p.get("rating", {}).get("count")),
            )
        else:
            cur = db.cursor()
            cur.execute(
                """INSERT INTO products
                   (id, title, price, description, category, image, rate, count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING""",
                (p["id"], p["title"], p["price"], p.get("description", ""),
                 p.get("category", ""), p.get("image", ""),
                 p.get("rating", {}).get("rate"), p.get("rating", {}).get("count")),
            )

    # Seed customers from users
    users = client.get("/users").json()
    for u in users:
        cid = str(uuid.uuid4())
        if db_type == "sqlite":
            db.execute(
                """INSERT OR IGNORE INTO customers
                   (id, email, username, password, firstname, lastname, phone,
                    city, street, number, zipcode, lat, long)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cid, u.get("email", ""), u.get("username", ""), u.get("password", ""),
                 u.get("name", {}).get("firstname", ""), u.get("name", {}).get("lastname", ""),
                 u.get("phone", ""),
                 u.get("address", {}).get("city", ""), u.get("address", {}).get("street", ""),
                 u.get("address", {}).get("number", 0), u.get("address", {}).get("zipcode", ""),
                 u.get("address", {}).get("geolocation", {}).get("lat", ""),
                 u.get("address", {}).get("geolocation", {}).get("long", "")),
            )
        else:
            cur = db.cursor()
            cur.execute(
                """INSERT INTO customers
                   (id, email, username, password, firstname, lastname, phone,
                    city, street, number, zipcode, lat, long)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (cid, u.get("email", ""), u.get("username", ""), u.get("password", ""),
                 u.get("name", {}).get("firstname", ""), u.get("name", {}).get("lastname", ""),
                 u.get("phone", ""),
                 u.get("address", {}).get("city", ""), u.get("address", {}).get("street", ""),
                 u.get("address", {}).get("number", 0), u.get("address", {}).get("zipcode", ""),
                 u.get("address", {}).get("geolocation", {}).get("lat", ""),
                 u.get("address", {}).get("geolocation", {}).get("long", "")),
            )

    # Seed orders from carts
    carts = client.get("/carts").json()
    if db_type == "sqlite":
        customers = db.execute("SELECT id FROM customers ORDER BY created_at").fetchall()
    else:
        cur = db.cursor()
        cur.execute("SELECT id FROM customers ORDER BY created_at")
        customers = cur.fetchall()

    for i, c in enumerate(carts):
        oid = str(uuid.uuid4())
        cust_idx = min((c.get("userId", 1) - 1), len(customers) - 1) if customers else 0
        customer_id = customers[cust_idx][0] if customers else str(uuid.uuid4())
        onum = i + 1
        if db_type == "sqlite":
            db.execute(
                "INSERT OR IGNORE INTO orders (id, order_number, customer_id, date) VALUES (?, ?, ?, ?)",
                (oid, onum, customer_id, c.get("date", "")),
            )
            for item in c.get("products", []):
                db.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)",
                    (oid, item["productId"], item["quantity"]),
                )
        else:
            cur = db.cursor()
            cur.execute(
                "INSERT INTO orders (id, order_number, customer_id, date) VALUES (%s, %s, %s, %s)",
                (oid, onum, customer_id, c.get("date", "")),
            )
            for item in c.get("products", []):
                cur.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity) VALUES (%s, %s, %s)",
                    (oid, item["productId"], item["quantity"]),
                )

    db.commit()
    client.close()


# ---------------------------------------------------------------------------
# Faker-based batch generation
# ---------------------------------------------------------------------------

def generate_fake_customer() -> dict[str, Any]:
    from faker import Faker
    fake = Faker()
    fname = fake.first_name()
    lname = fake.last_name()
    return {
        "id": str(uuid.uuid4()),
        "email": fake.email(),
        "username": fake.user_name(),
        "password": fake.password(length=12),
        "firstname": fname,
        "lastname": lname,
        "phone": fake.phone_number()[:20],
        "city": fake.city(),
        "street": fake.street_name(),
        "number": fake.building_number(),
        "zipcode": fake.zipcode(),
        "lat": str(fake.latitude()),
        "long": str(fake.longitude()),
    }


def generate_fake_order(customer_ids: list[str], product_ids: list[int]) -> dict[str, Any]:
    from faker import Faker
    import random
    fake = Faker()
    num_items = random.randint(1, 5)
    items = []
    for _ in range(num_items):
        pid = random.choice(product_ids)
        qty = random.randint(1, 5)
        items.append({"product_id": pid, "quantity": qty})
    return {
        "id": str(uuid.uuid4()),
        "customer_id": random.choice(customer_ids),
        "date": fake.date_time_this_year().isoformat(),
        "items": items,
    }


# ---------------------------------------------------------------------------
# Query helper — executes SQL with correct placeholder style
# ---------------------------------------------------------------------------

def db_execute(db, sql: str, params=(), *, cursor=None):
    """Execute a query with the correct placeholder style (%s for PG, ? for SQLite)."""
    db_type = get_db_type()
    if db_type == "sqlite":
        return db.execute(sql, params)
    else:
        cur = cursor or db.cursor()
        pg_sql = sql.replace("?", "%s") if "?" in sql else sql
        cur.execute(pg_sql, params)
        return cur


def db_fetchone(db, sql: str, params=()):
    """Fetch one row."""
    db_type = get_db_type()
    if db_type == "sqlite":
        return db.execute(sql, params).fetchone()
    else:
        import psycopg2.extras
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        pg_sql = sql.replace("?", "%s") if "?" in sql else sql
        cur.execute(pg_sql, params)
        return cur.fetchone()


def db_fetchall(db, sql: str, params=()):
    """Fetch all rows."""
    db_type = get_db_type()
    if db_type == "sqlite":
        return db.execute(sql, params).fetchall()
    else:
        import psycopg2.extras
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        pg_sql = sql.replace("?", "%s") if "?" in sql else sql
        cur.execute(pg_sql, params)
        return cur.fetchall()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    CORS(app, supports_credentials=True)
    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()
        seed_if_empty()

    # Auth middleware
    app.before_request(require_api_key)

    DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "admin")

    @app.route("/api/login", methods=["POST"])
    def dashboard_login():
        data = request.get_json(force=True) if request.is_json else {}
        pw = data.get("password", "")
        if pw == DASHBOARD_PASSWORD:
            session["dashboard_auth"] = True
            return jsonify({"status": "ok"})
        return jsonify({"error": "Invalid password"}), 401

    @app.route("/api/logout", methods=["POST"])
    def dashboard_logout():
        session.pop("dashboard_auth", None)
        return jsonify({"status": "ok"})

    # ------------------------------------------------------------------
    # API: Key management (requires master key in X-Master-Key header)
    # ------------------------------------------------------------------

    @app.route("/api/keys", methods=["GET"])
    def list_api_keys():
        master = request.headers.get("X-Master-Key", "")
        if not MASTER_API_KEY or master != MASTER_API_KEY:
            if not session.get("dashboard_auth"):
                return jsonify({"error": "Master key or dashboard login required"}), 401
        db = get_db()
        rows = db_fetchall(
            db,
            "SELECT label, prefix, created_at, revoked_at FROM api_keys ORDER BY created_at DESC",
        )
        return jsonify([row_to_dict(r) for r in rows])

    @app.route("/api/keys", methods=["POST"])
    def create_api_key():
        master = request.headers.get("X-Master-Key", "")
        if not MASTER_API_KEY or master != MASTER_API_KEY:
            if not session.get("dashboard_auth"):
                return jsonify({"error": "Master key or dashboard login required"}), 401
        data = request.get_json(force=True) if request.is_json else {}
        label = data.get("label", "unnamed")
        raw_key = "fsk_" + secrets.token_hex(24)
        key_hash = _hash_key(raw_key)
        prefix = raw_key[:8]
        db = get_db()
        db_type = get_db_type()
        if db_type == "sqlite":
            db.execute(
                "INSERT INTO api_keys (key_hash, label, prefix, created_at) VALUES (?, ?, ?, datetime('now'))",
                (key_hash, label, prefix),
            )
        else:
            db_execute(db, "INSERT INTO api_keys (key_hash, label, prefix, created_at) VALUES (%s, %s, %s, NOW())",
                       (key_hash, label, prefix))
        db.commit()
        return jsonify({"key": raw_key, "label": label, "prefix": prefix}), 201

    @app.route("/api/keys/<prefix>/revoke", methods=["POST"])
    def revoke_api_key(prefix: str):
        master = request.headers.get("X-Master-Key", "")
        if not MASTER_API_KEY or master != MASTER_API_KEY:
            if not session.get("dashboard_auth"):
                return jsonify({"error": "Master key or dashboard login required"}), 401
        db = get_db()
        db_type = get_db_type()
        row = db_fetchone(db, "SELECT * FROM api_keys WHERE prefix = ? AND revoked_at IS NULL", (prefix,))
        if row is None:
            return jsonify({"error": "Key not found or already revoked"}), 404
        if db_type == "sqlite":
            db.execute("UPDATE api_keys SET revoked_at = datetime('now') WHERE prefix = ?", (prefix,))
        else:
            db_execute(db, "UPDATE api_keys SET revoked_at = NOW() WHERE prefix = %s", (prefix,))
        db.commit()
        return jsonify({"status": "revoked", "prefix": prefix})

    # ------------------------------------------------------------------
    # API: Customers
    # ------------------------------------------------------------------

    @app.route("/api/customers", methods=["GET"])
    def list_customers():
        db = get_db()
        search = request.args.get("search", "").strip()
        if search:
            rows = db_fetchall(
                db,
                """SELECT c.*, COUNT(o.id) as order_count
                   FROM customers c
                   LEFT JOIN orders o ON c.id = o.customer_id
                   WHERE c.firstname LIKE ? OR c.lastname LIKE ?
                      OR c.email LIKE ? OR c.username LIKE ?
                   GROUP BY c.id
                   ORDER BY c.created_at DESC""",
                (f"%{search}%",) * 4,
            )
        else:
            rows = db_fetchall(
                db,
                """SELECT c.*, COUNT(o.id) as order_count
                   FROM customers c
                   LEFT JOIN orders o ON c.id = o.customer_id
                   GROUP BY c.id
                   ORDER BY c.created_at DESC""",
            )
        return jsonify([row_to_dict(r) for r in rows])

    @app.route("/api/customers/<cid>", methods=["GET"])
    def get_customer(cid: str):
        row = db_fetchone(get_db(), "SELECT * FROM customers WHERE id = ?", (cid,))
        if row is None:
            return jsonify({"error": "Customer not found"}), 404
        return jsonify(row_to_dict(row))

    @app.route("/api/customers", methods=["POST"])
    def create_customer():
        data = request.get_json(force=True)
        db = get_db()
        cid = data.get("id") or str(uuid.uuid4())
        if get_db_type() == "sqlite":
            db.execute(
                """INSERT INTO customers
                   (id, email, username, password, firstname, lastname, phone,
                    city, street, number, zipcode, lat, long)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cid, data.get("email", ""), data.get("username", ""), data.get("password", ""),
                 data.get("firstname", data.get("name", {}).get("firstname", "")),
                 data.get("lastname", data.get("name", {}).get("lastname", "")),
                 data.get("phone", ""),
                 data.get("city", data.get("address", {}).get("city", "")),
                 data.get("street", data.get("address", {}).get("street", "")),
                 data.get("number", data.get("address", {}).get("number", 0)),
                 data.get("zipcode", data.get("address", {}).get("zipcode", "")),
                 data.get("lat", data.get("address", {}).get("geolocation", {}).get("lat", "")),
                 data.get("long", data.get("address", {}).get("geolocation", {}).get("long", ""))),
            )
        else:
            db_execute(db,
                """INSERT INTO customers
                   (id, email, username, password, firstname, lastname, phone,
                    city, street, number, zipcode, lat, long)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (cid, data.get("email", ""), data.get("username", ""), data.get("password", ""),
                 data.get("firstname", data.get("name", {}).get("firstname", "")),
                 data.get("lastname", data.get("name", {}).get("lastname", "")),
                 data.get("phone", ""),
                 data.get("city", data.get("address", {}).get("city", "")),
                 data.get("street", data.get("address", {}).get("street", "")),
                 data.get("number", data.get("address", {}).get("number", 0)),
                 data.get("zipcode", data.get("address", {}).get("zipcode", "")),
                 data.get("lat", data.get("address", {}).get("geolocation", {}).get("lat", "")),
                 data.get("long", data.get("address", {}).get("geolocation", {}).get("long", ""))),
            )
        db.commit()
        row = db_fetchone(db, "SELECT * FROM customers WHERE id = ?", (cid,))
        return jsonify(row_to_dict(row)), 201

    @app.route("/api/customers/<cid>", methods=["PUT"])
    def update_customer(cid: str):
        data = request.get_json(force=True)
        db = get_db()
        fields, values = [], []
        mapping = {
            "email": "email", "username": "username", "password": "password",
            "firstname": "firstname", "lastname": "lastname", "phone": "phone",
            "city": "city", "street": "street", "number": "number",
            "zipcode": "zipcode", "lat": "lat", "long": "long",
        }
        for key, col in mapping.items():
            if key in data:
                fields.append(f"{col} = ?")
                values.append(data[key])
        if "name" in data:
            for k, col in [("firstname", "firstname"), ("lastname", "lastname")]:
                if k in data["name"]:
                    fields.append(f"{col} = ?")
                    values.append(data["name"][k])
        if "address" in data:
            for k, col in [("city", "city"), ("street", "street"), ("number", "number"),
                           ("zipcode", "zipcode")]:
                if k in data["address"]:
                    fields.append(f"{col} = ?")
                    values.append(data["address"][k])
            if "geolocation" in data["address"]:
                for k, col in [("lat", "lat"), ("long", "long")]:
                    if k in data["address"]["geolocation"]:
                        fields.append(f"{col} = ?")
                        values.append(data["address"]["geolocation"][k])
        if not fields:
            row = db_fetchone(db, "SELECT * FROM customers WHERE id = ?", (cid,))
            return jsonify(row_to_dict(row))
        values.append(cid)
        sql = f"UPDATE customers SET {', '.join(fields)} WHERE id = ?"
        db_type = get_db_type()
        if db_type == "sqlite":
            db.execute(sql, values)
        else:
            db_execute(db, sql.replace("?", "%s"), tuple(values))
        db.commit()
        row = db_fetchone(db, "SELECT * FROM customers WHERE id = ?", (cid,))
        return jsonify(row_to_dict(row))

    @app.route("/api/customers/<cid>", methods=["DELETE"])
    def delete_customer(cid: str):
        db = get_db()
        row = db_fetchone(db, "SELECT * FROM customers WHERE id = ?", (cid,))
        if row is None:
            return jsonify({"error": "Customer not found"}), 404
        db_execute(db, "DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE customer_id = ?)", (cid,))
        db_execute(db, "DELETE FROM orders WHERE customer_id = ?", (cid,))
        db_execute(db, "DELETE FROM customers WHERE id = ?", (cid,))
        db.commit()
        return jsonify(row_to_dict(row))

    @app.route("/api/customers/batch", methods=["POST"])
    def batch_create_customers():
        count = request.get_json(force=True).get("count", 5)
        count = min(max(count, 1), 100)
        db = get_db()
        db_type = get_db_type()
        created = []
        for _ in range(count):
            c = generate_fake_customer()
            sql = """INSERT INTO customers
               (id, email, username, password, firstname, lastname, phone,
                city, street, number, zipcode, lat, long)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            params = (c["id"], c["email"], c["username"], c["password"],
                      c["firstname"], c["lastname"], c["phone"],
                      c["city"], c["street"], c["number"], c["zipcode"], c["lat"], c["long"])
            if db_type == "sqlite":
                db.execute(sql, params)
            else:
                db_execute(db, sql, params)
            created.append(c)
        db.commit()
        return jsonify(created), 201

    # ------------------------------------------------------------------
    # API: Customer ↔ Order linking
    # ------------------------------------------------------------------

    @app.route("/api/customers/<cid>/orders", methods=["GET"])
    def get_customer_orders(cid: str):
        db = get_db()
        row = db_fetchone(db, "SELECT * FROM customers WHERE id = ?", (cid,))
        if row is None:
            return jsonify({"error": "Customer not found"}), 404
        rows = db_fetchall(
            db,
            """SELECT o.*, c.firstname || ' ' || c.lastname as customer_name
               FROM orders o
               JOIN customers c ON o.customer_id = c.id
               WHERE o.customer_id = ?
               ORDER BY o.created_at DESC""",
            (cid,),
        )
        result = []
        for r in rows:
            d = row_to_dict(r)
            items = db_fetchall(db, "SELECT oi.*, p.title, p.price FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = ?", (d["id"],))
            d["products"] = [row_to_dict(i) for i in items]
            result.append(d)
        return jsonify(result)

    @app.route("/api/orders/<oid>/customer", methods=["PUT"])
    def link_order_to_customer(oid: str):
        data = request.get_json(force=True)
        customer_id = data.get("customer_id")
        if not customer_id:
            return jsonify({"error": "customer_id is required"}), 400
        db = get_db()
        order = db_fetchone(db, "SELECT * FROM orders WHERE id = ?", (oid,))
        if order is None:
            return jsonify({"error": "Order not found"}), 404
        cust = db_fetchone(db, "SELECT * FROM customers WHERE id = ?", (customer_id,))
        if cust is None:
            return jsonify({"error": "Customer not found"}), 404
        db_execute(db, "UPDATE orders SET customer_id = ? WHERE id = ?", (customer_id, oid))
        db.commit()
        row = db_fetchone(
            db,
            """SELECT o.*, c.firstname || ' ' || c.lastname as customer_name
               FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.id = ?""",
            (oid,),
        )
        d = row_to_dict(row)
        items = db_fetchall(db, "SELECT oi.*, p.title, p.price FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = ?", (oid,))
        d["products"] = [row_to_dict(i) for i in items]
        return jsonify(d)

    @app.route("/api/orders/batch", methods=["POST"])
    def batch_create_orders():
        body = request.get_json(force=True)
        count = body.get("count", 5)
        count = min(max(count, 1), 100)
        link_to = body.get("link_customer_ids")
        db = get_db()
        db_type = get_db_type()
        customer_rows = db_fetchall(db, "SELECT id FROM customers")
        product_rows = db_fetchall(db, "SELECT id FROM products")
        customer_ids = [r["id"] if isinstance(r, dict) else r[0] for r in customer_rows]
        product_ids = [r["id"] if isinstance(r, dict) else r[0] for r in product_rows]
        if not customer_ids or not product_ids:
            return jsonify({"error": "Need at least one customer and one product"}), 400
        created = []
        base_onum = get_next_order_number(db)
        for i in range(count):
            o = generate_fake_order(customer_ids, product_ids)
            if link_to and len(link_to) > 0:
                o["customer_id"] = link_to[i % len(link_to)]
            o["order_number"] = base_onum + i
            if db_type == "sqlite":
                db.execute(
                    "INSERT INTO orders (id, order_number, customer_id, date) VALUES (?, ?, ?, ?)",
                    (o["id"], o["order_number"], o["customer_id"], o["date"]),
                )
            else:
                db_execute(db,
                    "INSERT INTO orders (id, order_number, customer_id, date) VALUES (%s, %s, %s, %s)",
                    (o["id"], o["order_number"], o["customer_id"], o["date"]),
                )
            for item in o["items"]:
                if db_type == "sqlite":
                    db.execute(
                        "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)",
                        (o["id"], item["product_id"], item["quantity"]),
                    )
                else:
                    db_execute(db,
                        "INSERT INTO order_items (order_id, product_id, quantity) VALUES (%s, %s, %s)",
                        (o["id"], item["product_id"], item["quantity"]),
                    )
            created.append(o)
        db.commit()
        for o in created:
            cust = db_fetchone(db, "SELECT firstname, lastname FROM customers WHERE id = ?", (o["customer_id"],))
            o["customer_name"] = f"{cust['firstname']} {cust['lastname']}" if cust else o["customer_id"][:8]
        return jsonify(created), 201

    # ------------------------------------------------------------------
    # API: Orders
    # ------------------------------------------------------------------

    @app.route("/api/orders", methods=["GET"])
    def list_orders():
        db = get_db()
        search = request.args.get("search", "").strip()
        if search:
            rows = db_fetchall(
                db,
                """SELECT o.*, c.firstname || ' ' || c.lastname as customer_name
                   FROM orders o
                   JOIN customers c ON o.customer_id = c.id
                   WHERE c.firstname LIKE ? OR c.lastname LIKE ?
                      OR (c.firstname || ' ' || c.lastname) LIKE ?
                      OR CAST(o.order_number AS TEXT) LIKE ?
                      OR o.id LIKE ?
                   ORDER BY o.order_number DESC""",
                (f"%{search}%",) * 5,
            )
        else:
            rows = db_fetchall(
                db,
                """SELECT o.*, c.firstname || ' ' || c.lastname as customer_name
                   FROM orders o
                   JOIN customers c ON o.customer_id = c.id
                   ORDER BY o.order_number DESC""",
            )
        result = []
        for row in rows:
            d = row_to_dict(row)
            items = db_fetchall(db, "SELECT * FROM order_items WHERE order_id = ?", (d["id"],))
            d["products"] = [row_to_dict(i) for i in items]
            result.append(d)
        return jsonify(result)

    @app.route("/api/orders/<oid>", methods=["GET"])
    def get_order(oid: str):
        db = get_db()
        row = db_fetchone(
            db,
            """SELECT o.*, c.firstname || ' ' || c.lastname as customer_name
               FROM orders o
               JOIN customers c ON o.customer_id = c.id
               WHERE o.id = ?""",
            (oid,),
        )
        if row is None:
            return jsonify({"error": "Order not found"}), 404
        d = row_to_dict(row)
        items = db_fetchall(db, "SELECT oi.*, p.title, p.price FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = ?", (d["id"],))
        d["products"] = [row_to_dict(i) for i in items]
        return jsonify(d)

    @app.route("/api/orders", methods=["POST"])
    def create_order():
        data = request.get_json(force=True)
        db = get_db()
        db_type = get_db_type()
        oid = data.get("id") or str(uuid.uuid4())
        customer_id = data.get("customer_id") or data.get("userId")
        if not customer_id:
            return jsonify({"error": "customer_id is required"}), 400
        date = data.get("date") or datetime.now(timezone.utc).isoformat()
        products = data.get("products", data.get("items", []))
        onum = get_next_order_number(db)
        if db_type == "sqlite":
            db.execute(
                "INSERT INTO orders (id, order_number, customer_id, date) VALUES (?, ?, ?, ?)",
                (oid, onum, customer_id, date),
            )
        else:
            db_execute(db,
                "INSERT INTO orders (id, order_number, customer_id, date) VALUES (%s, %s, %s, %s)",
                (oid, onum, customer_id, date),
            )
        for item in products:
            pid = item.get("product_id") or item.get("productId")
            qty = item.get("quantity", 1)
            if pid is not None:
                if db_type == "sqlite":
                    db.execute(
                        "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)",
                        (oid, pid, qty),
                    )
                else:
                    db_execute(db,
                        "INSERT INTO order_items (order_id, product_id, quantity) VALUES (%s, %s, %s)",
                        (oid, pid, qty),
                    )
        db.commit()
        row = db_fetchone(
            db,
            """SELECT o.*, c.firstname || ' ' || c.lastname as customer_name
               FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.id = ?""",
            (oid,),
        )
        d = row_to_dict(row)
        items = db_fetchall(db, "SELECT oi.*, p.title, p.price FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = ?", (oid,))
        d["products"] = [row_to_dict(i) for i in items]
        return jsonify(d), 201

    @app.route("/api/orders/<oid>", methods=["DELETE"])
    def delete_order(oid: str):
        db = get_db()
        row = db_fetchone(db, "SELECT * FROM orders WHERE id = ?", (oid,))
        if row is None:
            return jsonify({"error": "Order not found"}), 404
        db_execute(db, "DELETE FROM order_items WHERE order_id = ?", (oid,))
        db_execute(db, "DELETE FROM orders WHERE id = ?", (oid,))
        db.commit()
        return jsonify(row_to_dict(row))

    # ------------------------------------------------------------------
    # API: Products (read-only)
    # ------------------------------------------------------------------

    @app.route("/api/products", methods=["GET"])
    def list_products():
        rows = db_fetchall(get_db(), "SELECT * FROM products ORDER BY category, title")
        return jsonify([row_to_dict(r) for r in rows])

    @app.route("/api/products/<int:pid>", methods=["GET"])
    def get_product(pid: int):
        row = db_fetchone(get_db(), "SELECT * FROM products WHERE id = ?", (pid,))
        if row is None:
            return jsonify({"error": "Product not found"}), 404
        return jsonify(row_to_dict(row))

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @app.route("/api/stats", methods=["GET"])
    def stats():
        db = get_db()
        def count_rows(table):
            row = db_fetchone(db, f"SELECT COUNT(*) as cnt FROM {table}")
            d = row_to_dict(row)
            return list(d.values())[0] if d else 0
        return jsonify({
            "customers": count_rows("customers"),
            "orders": count_rows("orders"),
            "products": count_rows("products"),
            "order_items": count_rows("order_items"),
        })

    # ------------------------------------------------------------------
    # Reseed / bulk delete
    # ------------------------------------------------------------------

    @app.route("/api/reseed", methods=["POST"])
    def reseed():
        db = get_db()
        db_type = get_db_type()
        if db_type == "sqlite":
            db.executescript("DELETE FROM order_items; DELETE FROM orders; DELETE FROM customers; DELETE FROM products;")
        else:
            cur = db.cursor()
            cur.execute("DELETE FROM order_items")
            cur.execute("DELETE FROM orders")
            cur.execute("DELETE FROM customers")
            cur.execute("DELETE FROM products")
        db.commit()
        seed_if_empty()
        return jsonify({"status": "ok"})

    @app.route("/api/orders/delete-all", methods=["POST"])
    def delete_all_orders():
        db = get_db()
        db_type = get_db_type()
        if db_type == "sqlite":
            count = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            db.execute("DELETE FROM order_items")
            db.execute("DELETE FROM orders")
        else:
            cur = db.cursor()
            cur.execute("SELECT COUNT(*) FROM orders")
            count = cur.fetchone()[0]
            cur.execute("DELETE FROM order_items")
            cur.execute("DELETE FROM orders")
        db.commit()
        return jsonify({"deleted": count})

    @app.route("/api/customers/delete-all", methods=["POST"])
    def delete_all_customers():
        db = get_db()
        db_type = get_db_type()
        if db_type == "sqlite":
            count = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
            db.execute("DELETE FROM order_items")
            db.execute("DELETE FROM orders")
            db.execute("DELETE FROM customers")
        else:
            cur = db.cursor()
            cur.execute("SELECT COUNT(*) FROM customers")
            count = cur.fetchone()[0]
            cur.execute("DELETE FROM order_items")
            cur.execute("DELETE FROM orders")
            cur.execute("DELETE FROM customers")
        db.commit()
        return jsonify({"deleted": count})

    # ------------------------------------------------------------------
    # Frontend
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        from flask import render_template
        return render_template("index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5001))
    print(f"🛒 Fake Store running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)