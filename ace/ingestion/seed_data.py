"""Demo dataset for the A.C.E. Phase-1 proof of concept.

EVERYTHING IN THIS MODULE IS SYNTHETIC AND ILLUSTRATIVE.

"Bella Vista Trattoria" is not a real business. The SKU prices, recipes, and
menu prices were written by hand to exercise the engine across realistic
ranges. They are not observed data from any restaurant, and no pilot
deployment has taken place — White Paper §4.1 and §7 describe the 10-location
Early Adopter pilot as future work.

The restaurant row is flagged `is_demo = 1` in the database, and the demo
name carries an explicit marker, so demo output can never be mistaken for a
pilot result.
"""
from __future__ import annotations

from ace import db

DEMO_RESTAURANT = "Bella Vista Trattoria [DEMO - NOT A REAL BUSINESS]"

# (sku, name, unit, last_unit_price, category)
# last_unit_price is the cost on record *before* the demo invoices are
# processed, so that Layer 1 has a baseline to compute variance against.
SKUS = [
    ("CHK-BREAST-5LB",   "Chicken Breast Boneless Skinless 5lb", "CS", 18.99, "protein"),
    ("PRO-BEEF-GRND-10", "Ground Beef 80/20 10lb",               "CS", 42.00, "protein"),
    ("PRO-PANCETTA-2LB", "Pancetta Diced 2lb",                   "EA", 24.00, "protein"),
    ("SEA-SHRIMP-2LB",   "Shrimp 16/20 Peeled Deveined 2lb",     "EA", 27.50, "protein"),
    ("VEG-TOMATO-ROMA",  "Roma Tomatoes 25lb Case",              "CS", 18.50, "produce"),
    ("VEG-ROMAINE-24",   "Romaine Hearts 24ct Case",             "CS", 32.00, "produce"),
    ("VEG-BASIL-1LB",    "Fresh Basil 1lb",                      "EA", 12.00, "produce"),
    ("CHZ-MOZZ-5LB",     "Mozzarella Whole Milk 5lb",            "CS", 21.00, "dairy"),
    ("CHZ-PARM-2LB",     "Parmigiano Reggiano 2lb",              "EA", 28.00, "dairy"),
    ("OIL-EVOO-1GAL",    "Extra Virgin Olive Oil 1 Gallon",      "EA", 24.99, "dry_goods"),
    ("DRY-FLOUR-AP-50",  "All Purpose Flour 50lb Bag",           "EA", 19.00, "dry_goods"),
    ("DRY-PASTA-20LB",   "Dry Pasta Assorted 20lb",              "EA", 22.00, "dry_goods"),
]

# (item_name, menu_price, category, {sku: qty_per_serving})
# qty_per_serving is expressed as a fraction of the purchase unit above.
RECIPES = [
    # The three chicken-led items sit just under the 32% threshold at seeded
    # prices. They cross it only once the +18.5% chicken increase on the
    # US Foods demo invoice is confirmed by a manager — which is the
    # Human-in-the-Loop path the demo walks through end to end.
    ("Grilled Chicken Sandwich", 14.99, "entrees", {
        "CHK-BREAST-5LB": 0.210, "VEG-TOMATO-ROMA": 0.012, "DRY-FLOUR-AP-50": 0.010}),
    ("Chicken Parmigiana", 21.99, "entrees", {
        "CHK-BREAST-5LB": 0.250, "CHZ-MOZZ-5LB": 0.055, "VEG-TOMATO-ROMA": 0.030,
        "CHZ-PARM-2LB": 0.020}),
    ("Chicken Pesto Pasta", 18.99, "entrees", {
        "CHK-BREAST-5LB": 0.223, "DRY-PASTA-20LB": 0.035, "VEG-BASIL-1LB": 0.030,
        "OIL-EVOO-1GAL": 0.012}),
    ("Margherita Pizza 10in", 15.99, "entrees", {
        "DRY-FLOUR-AP-50": 0.022, "CHZ-MOZZ-5LB": 0.070, "VEG-TOMATO-ROMA": 0.035,
        "VEG-BASIL-1LB": 0.010, "OIL-EVOO-1GAL": 0.006}),
    ("Classic Cheeseburger", 16.49, "entrees", {
        "PRO-BEEF-GRND-10": 0.075, "CHZ-MOZZ-5LB": 0.030, "VEG-TOMATO-ROMA": 0.015,
        "DRY-FLOUR-AP-50": 0.010}),
    ("Bolognese Rigatoni", 19.49, "entrees", {
        "PRO-BEEF-GRND-10": 0.070, "DRY-PASTA-20LB": 0.040, "VEG-TOMATO-ROMA": 0.040,
        "CHZ-PARM-2LB": 0.018}),
    ("Shrimp Scampi", 24.99, "entrees", {
        "SEA-SHRIMP-2LB": 0.180, "DRY-PASTA-20LB": 0.035, "OIL-EVOO-1GAL": 0.018,
        "VEG-BASIL-1LB": 0.008}),
    ("Carbonara", 19.99, "entrees", {
        "PRO-PANCETTA-2LB": 0.105, "DRY-PASTA-20LB": 0.038, "CHZ-PARM-2LB": 0.030}),
    ("Caesar Salad", 11.99, "starters", {
        "VEG-ROMAINE-24": 0.055, "CHZ-PARM-2LB": 0.015, "OIL-EVOO-1GAL": 0.008}),
    ("Caprese Salad", 13.49, "starters", {
        "VEG-TOMATO-ROMA": 0.055, "CHZ-MOZZ-5LB": 0.060, "VEG-BASIL-1LB": 0.020,
        "OIL-EVOO-1GAL": 0.010}),
    ("Garlic Focaccia", 7.99, "starters", {
        "DRY-FLOUR-AP-50": 0.018, "OIL-EVOO-1GAL": 0.014}),
    ("Side Caesar", 6.49, "sides", {
        "VEG-ROMAINE-24": 0.030, "CHZ-PARM-2LB": 0.008}),
]


def load(conn=None) -> str:
    """Create the demo restaurant, SKUs, and recipes. Idempotent.

    Returns the restaurant_id. Safe to call repeatedly: rows are keyed on
    natural identifiers and re-running will not duplicate them.
    """
    conn = conn or db.connect()
    rid = db.upsert_restaurant(conn, DEMO_RESTAURANT, is_demo=True)

    existing_conn = conn.execute(
        "SELECT 1 FROM pos_connections WHERE restaurant_id = ?", (rid,)
    ).fetchone()
    if not existing_conn:
        conn.execute(
            "INSERT INTO pos_connections (connection_id, restaurant_id, pos_vendor, "
            "mode, connected_at) VALUES (?,?,?,?,?)",
            (db.new_id(), rid, "csv_export", "file", db.now_iso()),
        )

    for sku, name, unit, price, category in SKUS:
        db.upsert_sku(conn, sku=sku, restaurant_id=rid, name=name, unit=unit,
                      last_unit_price=price, category=category)

    for item_name, menu_price, category, ingredients in RECIPES:
        row = conn.execute(
            "SELECT recipe_id FROM recipes WHERE restaurant_id = ? AND item_name = ?",
            (rid, item_name),
        ).fetchone()
        if row:
            continue
        recipe_id = db.new_id()
        conn.execute(
            "INSERT INTO recipes (recipe_id, restaurant_id, item_name, menu_price, "
            "category) VALUES (?,?,?,?,?)",
            (recipe_id, rid, item_name, menu_price, category),
        )
        for sku, qty in ingredients.items():
            conn.execute(
                "INSERT INTO recipe_ingredients (recipe_ingredient_id, recipe_id, "
                "sku, qty_per_serving) VALUES (?,?,?,?)",
                (db.new_id(), recipe_id, sku, qty),
            )

    conn.commit()
    db.audit(conn, actor="seed", action="DEMO_DATA_LOADED",
             payload={"restaurant_id": rid, "skus": len(SKUS), "recipes": len(RECIPES),
                      "synthetic": True})
    return rid


def reset_sku_prices(conn, restaurant_id: str) -> None:
    """Restore SKU prices to their seeded baseline.

    Needed because processing a demo invoice mutates recorded costs. Without
    this, re-running the demo would compare against already-updated prices and
    the variance gate would stop firing — the idempotency bug this guards.
    """
    for sku, _name, _unit, price, _cat in SKUS:
        conn.execute(
            "UPDATE inventory_skus SET last_unit_price = ?, updated_at = ? "
            "WHERE sku = ? AND restaurant_id = ?",
            (price, db.now_iso(), sku, restaurant_id),
        )
    conn.commit()


if __name__ == "__main__":
    rid = load()
    print(f"Demo data loaded. restaurant_id={rid}")
