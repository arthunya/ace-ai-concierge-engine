"""A.C.E. database layer.

Development/PoC backend: SQLite (zero-config, file-based).
Production backend: PostgreSQL 16 (see schema/postgres_schema.sql).
The table structure is kept 1:1 so migration is a connection-string change
plus type widening, not a rewrite.

The audit log is append-only at the database layer — triggers in development,
revoked UPDATE/DELETE grants in production. Every manager approval and every
recommendation is written here, which is what makes the Human-in-the-Loop
claim in White Paper §3.1 auditable rather than merely asserted.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "ace.db"

DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS restaurants (
    restaurant_id TEXT PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    is_demo       INTEGER NOT NULL DEFAULT 0,  -- 1 = illustrative, not a real site
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pos_connections (
    connection_id TEXT PRIMARY KEY,
    restaurant_id TEXT NOT NULL REFERENCES restaurants(restaurant_id),
    pos_vendor    TEXT NOT NULL CHECK (pos_vendor IN ('toast','clover','csv_export')),
    -- Phase 1 is file-based; 'live' is reserved for future REST/webhook work.
    mode          TEXT NOT NULL CHECK (mode IN ('file','live')) DEFAULT 'file',
    connected_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_skus (
    sku              TEXT PRIMARY KEY,
    restaurant_id    TEXT NOT NULL REFERENCES restaurants(restaurant_id),
    name             TEXT NOT NULL,
    unit             TEXT NOT NULL,
    last_unit_price  REAL,
    category         TEXT,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id     TEXT PRIMARY KEY,
    restaurant_id  TEXT NOT NULL REFERENCES restaurants(restaurant_id),
    supplier_name  TEXT NOT NULL,
    invoice_number TEXT,
    invoice_date   TEXT,
    source_path    TEXT NOT NULL,
    extraction_method TEXT NOT NULL,   -- how the text was obtained; see §3.2
    total_extracted   REAL NOT NULL,
    is_demo        INTEGER NOT NULL DEFAULT 0,
    processed_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoice_line_items (
    line_item_id   TEXT PRIMARY KEY,
    invoice_id     TEXT NOT NULL REFERENCES invoices(invoice_id),
    raw_text       TEXT NOT NULL,
    ingredient_name TEXT NOT NULL,
    quantity       REAL NOT NULL,
    unit           TEXT NOT NULL,
    unit_price     REAL NOT NULL,
    total_price    REAL NOT NULL,
    supplier_code  TEXT,
    matched_sku    TEXT REFERENCES inventory_skus(sku),
    match_confidence REAL NOT NULL,
    -- Routing outcome per §3.2: auto-sync, price-variance gate, or review queue.
    routing        TEXT NOT NULL CHECK (routing IN
                   ('auto_sync','manager_confirmation','manual_review')),
    routing_reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipes (
    recipe_id     TEXT PRIMARY KEY,
    restaurant_id TEXT NOT NULL REFERENCES restaurants(restaurant_id),
    item_name     TEXT NOT NULL,
    menu_price    REAL NOT NULL,
    category      TEXT
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    recipe_ingredient_id TEXT PRIMARY KEY,
    recipe_id   TEXT NOT NULL REFERENCES recipes(recipe_id),
    sku         TEXT NOT NULL REFERENCES inventory_skus(sku),
    qty_per_serving REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS price_recommendations (
    recommendation_id TEXT PRIMARY KEY,
    recipe_id       TEXT NOT NULL REFERENCES recipes(recipe_id),
    current_price   REAL NOT NULL,
    recipe_cost     REAL NOT NULL,
    food_cost_pct   REAL NOT NULL,
    threshold_pct   REAL NOT NULL,
    suggested_price REAL,
    rationale       TEXT NOT NULL,     -- the "why", shown in the dashboard
    engine_version  TEXT NOT NULL,
    generated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS labor_forecasts (
    forecast_id     TEXT PRIMARY KEY,
    restaurant_id   TEXT NOT NULL REFERENCES restaurants(restaurant_id),
    forecast_date   TEXT NOT NULL,
    day_of_week     TEXT NOT NULL,
    forecast_covers INTEGER NOT NULL,
    method          TEXT NOT NULL,     -- baseline identifier, not a trained model
    rationale       TEXT NOT NULL,
    recommended_foh INTEGER NOT NULL,
    recommended_boh INTEGER NOT NULL,
    generated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS manager_approvals (
    approval_id  TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL CHECK (subject_type IN
                 ('invoice_line_item','price_recommendation','labor_forecast')),
    subject_id   TEXT NOT NULL,
    decision     TEXT NOT NULL CHECK (decision IN ('approved','rejected')),
    decided_by   TEXT NOT NULL,
    note         TEXT,
    decided_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    payload TEXT
);

-- Append-only enforcement for the audit log.
CREATE TRIGGER IF NOT EXISTS audit_no_update
BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TRIGGER IF NOT EXISTS audit_no_delete
BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    return conn


def audit(conn: sqlite3.Connection, actor: str, action: str,
          payload: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (ts, actor, action, payload) VALUES (?,?,?,?)",
        (now_iso(), actor, action, json.dumps(payload or {})),
    )
    conn.commit()


def upsert_restaurant(conn: sqlite3.Connection, name: str, *,
                      is_demo: bool = False) -> str:
    row = conn.execute(
        "SELECT restaurant_id FROM restaurants WHERE name = ?", (name,)
    ).fetchone()
    if row:
        return row["restaurant_id"]
    rid = new_id()
    conn.execute(
        "INSERT INTO restaurants (restaurant_id, name, is_demo, created_at) "
        "VALUES (?,?,?,?)",
        (rid, name, int(is_demo), now_iso()),
    )
    conn.commit()
    return rid


def upsert_sku(conn: sqlite3.Connection, *, sku: str, restaurant_id: str, name: str,
               unit: str, last_unit_price: float | None = None,
               category: str | None = None) -> str:
    """Insert a SKU, or update its last recorded unit price if it exists.

    Idempotent: re-running seed data must not duplicate rows or silently
    reset a price that a later invoice legitimately updated.
    """
    existing = conn.execute(
        "SELECT sku FROM inventory_skus WHERE sku = ?", (sku,)
    ).fetchone()
    if existing:
        if last_unit_price is not None:
            conn.execute(
                "UPDATE inventory_skus SET last_unit_price = ?, updated_at = ? "
                "WHERE sku = ?",
                (last_unit_price, now_iso(), sku),
            )
            conn.commit()
        return sku
    conn.execute(
        "INSERT INTO inventory_skus (sku, restaurant_id, name, unit, "
        "last_unit_price, category, updated_at) VALUES (?,?,?,?,?,?,?)",
        (sku, restaurant_id, name, unit, last_unit_price, category, now_iso()),
    )
    conn.commit()
    return sku


def record_approval(conn: sqlite3.Connection, *, subject_type: str, subject_id: str,
                    decision: str, decided_by: str, note: str | None = None) -> str:
    """Record a manager decision. This is the Human-in-the-Loop gate (§3.1)."""
    aid = new_id()
    conn.execute(
        "INSERT INTO manager_approvals (approval_id, subject_type, subject_id, "
        "decision, decided_by, note, decided_at) VALUES (?,?,?,?,?,?,?)",
        (aid, subject_type, subject_id, decision, decided_by, note, now_iso()),
    )
    conn.commit()
    audit(conn, actor=decided_by, action=f"APPROVAL_{decision.upper()}",
          payload={"subject_type": subject_type, "subject_id": subject_id,
                   "note": note})
    return aid
