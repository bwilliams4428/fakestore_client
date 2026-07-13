"""Flask backend with SQLite persistence for Fake Store API data.

- Auto-seeds from the live Fake Store API on first run
- Full CRUD for customers and orders
- Batch creation with random Faker data
- REST JSON API at /api/*
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from flask import Flask, g, jsonify, request
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

# Resolve DB path — supports Render persistent disk via DATABASE_URL env var
_DEFAULT_DB = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "data", "store.db")
DB_PATH = os.environ.get("DATABASE_URL", _DEFAULT_DB)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(exc: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        try:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.commit()
        except Exception:
            pass
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    # Migration: add order_number column if missing (existing DBs)
    try:
        db.execute("ALTER TABLE orders ADD COLUMN order_number INTEGER")
    except sqlite3.OperationalError:
        pass  # column already exists
    # Backfill order_number for any existing rows
    rows = db.execute("SELECT id FROM orders WHERE order_number IS NULL ORDER BY created_at").fetchall()
    for i, row in enumerate(rows, 1):
        db.execute("UPDATE orders SET order_number = ? WHERE id = ?", (i, row["id"]))
    db.commit()


SCHEMA = """\
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
"""


def get_next_order_number(db: sqlite3.Connection) -> int:
    """Return the next sequential order number."""
    row = db.execute("SELECT COALESCE(MAX(order_number), 0) + 1 FROM orders").fetchone()
    return row[0]


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


# ---------------------------------------------------------------------------
# Seed from Fake Store API
# ---------------------------------------------------------------------------

def seed_if_empty() -> None:
    """Seed products from the live API if the products table is empty."""
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count > 0:
        return

    import httpx
    client = httpx.Client(base_url="https://fakestoreapi.com", timeout=30)

    # Seed products
    products = client.get("/products").json()
    for p in products:
        db.execute(
            """INSERT OR IGNORE INTO products
               (id, title, price, description, category, image, rate, count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                p["id"],
                p["title"],
                p["price"],
                p.get("description", ""),
                p.get("category", ""),
                p.get("image", ""),
                p.get("rating", {}).get("rate"),
                p.get("rating", {}).get("count"),
            ),
        )

    # Seed customers from users
    users = client.get("/users").json()
    for u in users:
        cid = str(uuid.uuid4())
        db.execute(
            """INSERT OR IGNORE INTO customers
               (id, email, username, password, firstname, lastname, phone,
                city, street, number, zipcode, lat, long)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cid,
                u.get("email", ""),
                u.get("username", ""),
                u.get("password", ""),
                u.get("name", {}).get("firstname", ""),
                u.get("name", {}).get("lastname", ""),
                u.get("phone", ""),
                u.get("address", {}).get("city", ""),
                u.get("address", {}).get("street", ""),
                u.get("address", {}).get("number", 0),
                u.get("address", {}).get("zipcode", ""),
                u.get("address", {}).get("geolocation", {}).get("lat", ""),
                u.get("address", {}).get("geolocation", {}).get("long", ""),
            ),
        )

    # Seed orders from carts
    carts = client.get("/carts").json()
    customers = db.execute("SELECT id FROM customers ORDER BY created_at").fetchall()
    for i, c in enumerate(carts):
        cid = str(uuid.uuid4())
        # Map original userId to our seeded customer
        cust_idx = min((c.get("userId", 1) - 1), len(customers) - 1) if customers else 0
        customer_id = customers[cust_idx]["id"] if customers else str(uuid.uuid4())
        onum = i + 1
        db.execute(
            "INSERT OR IGNORE INTO orders (id, order_number, customer_id, date) VALUES (?, ?, ?, ?)",
            (cid, onum, customer_id, c.get("date", "")),
        )
        for item in c.get("products", []):
            db.execute(
                """INSERT INTO order_items (order_id, product_id, quantity)
                   VALUES (?, ?, ?)""",
                (cid, item["productId"], item["quantity"]),
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
# App factory
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()
        seed_if_empty()

    # ------------------------------------------------------------------
    # API: Customers
    # ------------------------------------------------------------------

    @app.route("/api/customers", methods=["GET"])
    def list_customers():
        db = get_db()
        search = request.args.get("search", "").strip()
        if search:
            rows = db.execute(
                """SELECT c.*, COUNT(o.id) as order_count
                   FROM customers c
                   LEFT JOIN orders o ON c.id = o.customer_id
                   WHERE c.firstname LIKE ? OR c.lastname LIKE ?
                      OR c.email LIKE ? OR c.username LIKE ?
                   GROUP BY c.id
                   ORDER BY c.created_at DESC""",
                (f"%{search}%",) * 4,
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT c.*, COUNT(o.id) as order_count
                   FROM customers c
                   LEFT JOIN orders o ON c.id = o.customer_id
                   GROUP BY c.id
                   ORDER BY c.created_at DESC""",
            ).fetchall()
        return jsonify([row_to_dict(r) for r in rows])

    @app.route("/api/customers/<cid>", methods=["GET"])
    def get_customer(cid: str):
        row = get_db().execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
        if row is None:
            return jsonify({"error": "Customer not found"}), 404
        return jsonify(row_to_dict(row))

    @app.route("/api/customers", methods=["POST"])
    def create_customer():
        data = request.get_json(force=True)
        db = get_db()
        cid = data.get("id") or str(uuid.uuid4())
        db.execute(
            """INSERT INTO customers
               (id, email, username, password, firstname, lastname, phone,
                city, street, number, zipcode, lat, long)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cid,
                data.get("email", ""),
                data.get("username", ""),
                data.get("password", ""),
                data.get("firstname", data.get("name", {}).get("firstname", "")),
                data.get("lastname", data.get("name", {}).get("lastname", "")),
                data.get("phone", ""),
                data.get("city", data.get("address", {}).get("city", "")),
                data.get("street", data.get("address", {}).get("street", "")),
                data.get("number", data.get("address", {}).get("number", 0)),
                data.get("zipcode", data.get("address", {}).get("zipcode", "")),
                data.get("lat", data.get("address", {}).get("geolocation", {}).get("lat", "")),
                data.get("long", data.get("address", {}).get("geolocation", {}).get("long", "")),
            ),
        )
        db.commit()
        row = db.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
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
        # Flatten nested name/address
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
            row = db.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
            return jsonify(row_to_dict(row))
        values.append(cid)
        db.execute(f"UPDATE customers SET {', '.join(fields)} WHERE id = ?", values)
        db.commit()
        row = db.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
        return jsonify(row_to_dict(row))

    @app.route("/api/customers/<cid>", methods=["DELETE"])
    def delete_customer(cid: str):
        db = get_db()
        row = db.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
        if row is None:
            return jsonify({"error": "Customer not found"}), 404
        db.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE customer_id = ?)", (cid,))
        db.execute("DELETE FROM orders WHERE customer_id = ?", (cid,))
        db.execute("DELETE FROM customers WHERE id = ?", (cid,))
        db.commit()
        return jsonify(row_to_dict(row))

    @app.route("/api/customers/batch", methods=["POST"])
    def batch_create_customers():
        count = request.get_json(force=True).get("count", 5)
        count = min(max(count, 1), 100)
        db = get_db()
        created = []
        for _ in range(count):
            c = generate_fake_customer()
            db.execute(
                """INSERT INTO customers
                   (id, email, username, password, firstname, lastname, phone,
                    city, street, number, zipcode, lat, long)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (c["id"], c["email"], c["username"], c["password"],
                 c["firstname"], c["lastname"], c["phone"],
                 c["city"], c["street"], c["number"], c["zipcode"], c["lat"], c["long"]),
            )
            created.append(c)
        db.commit()
        return jsonify(created), 201

    # ------------------------------------------------------------------
    # API: Customer ↔ Order linking
    # ------------------------------------------------------------------

    @app.route("/api/customers/<cid>/orders", methods=["GET"])
    def get_customer_orders(cid: str):
        """Get all orders for a specific customer."""
        db = get_db()
        row = db.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
        if row is None:
            return jsonify({"error": "Customer not found"}), 404
        rows = db.execute(
            """SELECT o.*, c.firstname || ' ' || c.lastname as customer_name
               FROM orders o
               JOIN customers c ON o.customer_id = c.id
               WHERE o.customer_id = ?
               ORDER BY o.created_at DESC""",
            (cid,),
        ).fetchall()
        result = []
        for r in rows:
            d = row_to_dict(r)
            items = db.execute(
                "SELECT oi.*, p.title, p.price FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = ?",
                (d["id"],),
            ).fetchall()
            d["products"] = [row_to_dict(i) for i in items]
            result.append(d)
        return jsonify(result)

    @app.route("/api/orders/<oid>/customer", methods=["PUT"])
    def link_order_to_customer(oid: str):
        """Reassign an order to a different customer."""
        data = request.get_json(force=True)
        customer_id = data.get("customer_id")
        if not customer_id:
            return jsonify({"error": "customer_id is required"}), 400
        db = get_db()
        order = db.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
        if order is None:
            return jsonify({"error": "Order not found"}), 404
        cust = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if cust is None:
            return jsonify({"error": "Customer not found"}), 404
        db.execute("UPDATE orders SET customer_id = ? WHERE id = ?", (customer_id, oid))
        db.commit()
        row = db.execute(
            """SELECT o.*, c.firstname || ' ' || c.lastname as customer_name
               FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.id = ?""",
            (oid,),
        ).fetchone()
        d = row_to_dict(row)
        items = db.execute(
            "SELECT oi.*, p.title, p.price FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = ?",
            (oid,),
        ).fetchall()
        d["products"] = [row_to_dict(i) for i in items]
        return jsonify(d)

    @app.route("/api/orders/batch", methods=["POST"])
    def batch_create_orders():
        body = request.get_json(force=True)
        count = body.get("count", 5)
        count = min(max(count, 1), 100)
        link_to = body.get("link_customer_ids")  # optional: list of customer IDs to assign orders to
        db = get_db()
        customer_ids = [r["id"] for r in db.execute("SELECT id FROM customers").fetchall()]
        product_ids = [r["id"] for r in db.execute("SELECT id FROM products").fetchall()]
        if not customer_ids or not product_ids:
            return jsonify({"error": "Need at least one customer and one product"}), 400
        created = []
        base_onum = get_next_order_number(db)
        for i in range(count):
            o = generate_fake_order(customer_ids, product_ids)
            # If link_to provided, cycle through those customer IDs
            if link_to and len(link_to) > 0:
                o["customer_id"] = link_to[i % len(link_to)]
            o["order_number"] = base_onum + i
            db.execute(
                "INSERT INTO orders (id, order_number, customer_id, date) VALUES (?, ?, ?, ?)",
                (o["id"], o["order_number"], o["customer_id"], o["date"]),
            )
            for item in o["items"]:
                db.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)",
                    (o["id"], item["product_id"], item["quantity"]),
                )
            created.append(o)
        db.commit()
        # Enrich with customer names
        for o in created:
            cust = db.execute("SELECT firstname, lastname FROM customers WHERE id = ?", (o["customer_id"],)).fetchone()
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
            rows = db.execute(
                """SELECT o.*, c.firstname || ' ' || c.lastname as customer_name
                   FROM orders o
                   JOIN customers c ON o.customer_id = c.id
                   WHERE c.firstname LIKE ? OR c.lastname LIKE ?
                      OR (c.firstname || ' ' || c.lastname) LIKE ?
                      OR CAST(o.order_number AS TEXT) LIKE ?
                      OR o.id LIKE ?
                   ORDER BY o.order_number DESC""",
                (f"%{search}%",) * 5,
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT o.*, c.firstname || ' ' || c.lastname as customer_name
                   FROM orders o
                   JOIN customers c ON o.customer_id = c.id
                   ORDER BY o.order_number DESC""",
            ).fetchall()
        result = []
        for row in rows:
            d = row_to_dict(row)
            items = db.execute(
                "SELECT * FROM order_items WHERE order_id = ?", (d["id"],)
            ).fetchall()
            d["products"] = [row_to_dict(i) for i in items]
            result.append(d)
        return jsonify(result)

    @app.route("/api/orders/<oid>", methods=["GET"])
    def get_order(oid: str):
        db = get_db()
        row = db.execute(
            """SELECT o.*, c.firstname || ' ' || c.lastname as customer_name
               FROM orders o
               JOIN customers c ON o.customer_id = c.id
               WHERE o.id = ?""",
            (oid,),
        ).fetchone()
        if row is None:
            return jsonify({"error": "Order not found"}), 404
        d = row_to_dict(row)
        items = db.execute(
            "SELECT oi.*, p.title, p.price FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = ?",
            (d["id"],),
        ).fetchall()
        d["products"] = [row_to_dict(i) for i in items]
        return jsonify(d)

    @app.route("/api/orders", methods=["POST"])
    def create_order():
        data = request.get_json(force=True)
        db = get_db()
        oid = data.get("id") or str(uuid.uuid4())
        customer_id = data.get("customer_id") or data.get("userId")
        if not customer_id:
            return jsonify({"error": "customer_id is required"}), 400
        date = data.get("date") or datetime.now(timezone.utc).isoformat()
        products = data.get("products", data.get("items", []))
        onum = get_next_order_number(db)
        db.execute(
            "INSERT INTO orders (id, order_number, customer_id, date) VALUES (?, ?, ?, ?)",
            (oid, onum, customer_id, date),
        )
        for item in products:
            pid = item.get("product_id") or item.get("productId")
            qty = item.get("quantity", 1)
            if pid is not None:
                db.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)",
                    (oid, pid, qty),
                )
        db.commit()
        row = db.execute(
            """SELECT o.*, c.firstname || ' ' || c.lastname as customer_name
               FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.id = ?""",
            (oid,),
        ).fetchone()
        d = row_to_dict(row)
        items = db.execute(
            "SELECT oi.*, p.title, p.price FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = ?",
            (oid,),
        ).fetchall()
        d["products"] = [row_to_dict(i) for i in items]
        return jsonify(d), 201

    @app.route("/api/orders/<oid>", methods=["DELETE"])
    def delete_order(oid: str):
        db = get_db()
        row = db.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
        if row is None:
            return jsonify({"error": "Order not found"}), 404
        db.execute("DELETE FROM order_items WHERE order_id = ?", (oid,))
        db.execute("DELETE FROM orders WHERE id = ?", (oid,))
        db.commit()
        return jsonify(row_to_dict(row))

    # ------------------------------------------------------------------
    # API: Products (read-only)
    # ------------------------------------------------------------------

    @app.route("/api/products", methods=["GET"])
    def list_products():
        rows = get_db().execute("SELECT * FROM products ORDER BY category, title").fetchall()
        return jsonify([row_to_dict(r) for r in rows])

    @app.route("/api/products/<int:pid>", methods=["GET"])
    def get_product(pid: int):
        row = get_db().execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
        if row is None:
            return jsonify({"error": "Product not found"}), 404
        return jsonify(row_to_dict(row))

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @app.route("/api/stats", methods=["GET"])
    def stats():
        db = get_db()
        return jsonify({
            "customers": db.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
            "orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "products": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "order_items": db.execute("SELECT COUNT(*) FROM order_items").fetchone()[0],
        })

    # ------------------------------------------------------------------
    # Reseed
    # ------------------------------------------------------------------

    @app.route("/api/reseed", methods=["POST"])
    def reseed():
        db = get_db()
        db.executescript(
            "DELETE FROM order_items; DELETE FROM orders; DELETE FROM customers; DELETE FROM products;"
        )
        db.commit()
        seed_if_empty()
        return jsonify({"status": "ok"})

    @app.route("/api/orders/delete-all", methods=["POST"])
    def delete_all_orders():
        db = get_db()
        count = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        db.execute("DELETE FROM order_items")
        db.execute("DELETE FROM orders")
        db.commit()
        return jsonify({"deleted": count})

    @app.route("/api/customers/delete-all", methods=["POST"])
    def delete_all_customers():
        db = get_db()
        count = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        db.execute("DELETE FROM order_items")
        db.execute("DELETE FROM orders")
        db.execute("DELETE FROM customers")
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