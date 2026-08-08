-- A.C.E. — AI Concierge & Engine
-- Production PostgreSQL 16 schema (reference DDL).
-- Development/PoC uses an equivalent SQLite schema (ace/db.py).
--
-- Table structure is kept 1:1 with the SQLite development schema so that
-- migration is a connection-string change plus type widening, not a rewrite.

CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- fuzzy SKU matching at scale
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

CREATE TABLE restaurants (
    restaurant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL UNIQUE,
    is_demo       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE pos_connections (
    connection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(restaurant_id),
    pos_vendor    TEXT NOT NULL CHECK (pos_vendor IN ('toast','clover','csv_export')),
    mode          TEXT NOT NULL DEFAULT 'file' CHECK (mode IN ('file','live')),
    connected_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE inventory_skus (
    sku             TEXT PRIMARY KEY,
    restaurant_id   UUID NOT NULL REFERENCES restaurants(restaurant_id),
    name            TEXT NOT NULL,
    unit            TEXT NOT NULL,
    last_unit_price NUMERIC(12,4),
    category        TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_skus_name_trgm ON inventory_skus USING gin (name gin_trgm_ops);

CREATE TABLE invoices (
    invoice_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id     UUID NOT NULL REFERENCES restaurants(restaurant_id),
    supplier_name     TEXT NOT NULL,
    invoice_number    TEXT,
    invoice_date      DATE,
    source_path       TEXT NOT NULL,
    extraction_method TEXT NOT NULL,       -- White Paper §3.2 provenance
    total_extracted   NUMERIC(12,2) NOT NULL,
    is_demo           BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE invoice_line_items (
    line_item_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id       UUID NOT NULL REFERENCES invoices(invoice_id),
    raw_text         TEXT NOT NULL,
    ingredient_name  TEXT NOT NULL,
    quantity         NUMERIC(12,3) NOT NULL,
    unit             TEXT NOT NULL,
    unit_price       NUMERIC(12,4) NOT NULL,
    total_price      NUMERIC(12,2) NOT NULL,
    supplier_code    TEXT,
    matched_sku      TEXT REFERENCES inventory_skus(sku),
    match_confidence NUMERIC(5,4) NOT NULL,
    routing          TEXT NOT NULL CHECK (routing IN
                     ('auto_sync','manager_confirmation','manual_review')),
    routing_reason   TEXT NOT NULL
);
CREATE INDEX idx_line_items_invoice ON invoice_line_items(invoice_id);

CREATE TABLE recipes (
    recipe_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(restaurant_id),
    item_name     TEXT NOT NULL,
    menu_price    NUMERIC(10,2) NOT NULL,
    category      TEXT
);

CREATE TABLE recipe_ingredients (
    recipe_ingredient_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipe_id            UUID NOT NULL REFERENCES recipes(recipe_id),
    sku                  TEXT NOT NULL REFERENCES inventory_skus(sku),
    qty_per_serving      NUMERIC(12,4) NOT NULL
);
CREATE INDEX idx_recipe_ing_sku ON recipe_ingredients(sku);

CREATE TABLE price_recommendations (
    recommendation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipe_id         UUID NOT NULL REFERENCES recipes(recipe_id),
    current_price     NUMERIC(10,2) NOT NULL,
    recipe_cost       NUMERIC(10,4) NOT NULL,
    food_cost_pct     NUMERIC(6,4) NOT NULL,
    threshold_pct     NUMERIC(6,4) NOT NULL,
    suggested_price   NUMERIC(10,2),
    rationale         TEXT NOT NULL,
    engine_version    TEXT NOT NULL,       -- git commit hash: runs reproducible
    generated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE labor_forecasts (
    forecast_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id   UUID NOT NULL REFERENCES restaurants(restaurant_id),
    forecast_date   DATE NOT NULL,
    day_of_week     TEXT NOT NULL,
    forecast_covers INTEGER NOT NULL,
    method          TEXT NOT NULL,         -- baseline id, not a trained model
    rationale       TEXT NOT NULL,
    recommended_foh INTEGER NOT NULL,
    recommended_boh INTEGER NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE manager_approvals (
    approval_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type TEXT NOT NULL CHECK (subject_type IN
                 ('invoice_line_item','price_recommendation','labor_forecast')),
    subject_id   UUID NOT NULL,
    decision     TEXT NOT NULL CHECK (decision IN ('approved','rejected')),
    decided_by   TEXT NOT NULL,
    note         TEXT,
    decided_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_approvals_subject ON manager_approvals(subject_type, subject_id);

-- Append-only audit log: the application role is granted INSERT/SELECT only.
CREATE TABLE audit_log (
    log_id  BIGSERIAL PRIMARY KEY,
    ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    payload JSONB
);

-- Production append-only enforcement (development uses SQLite triggers):
--   REVOKE UPDATE, DELETE ON audit_log FROM ace_app;
--   GRANT  INSERT, SELECT ON audit_log TO   ace_app;
