"""A.C.E. test suite.

One test per claim the working paper or the code makes.

  T1   Layer 1 parses line items out of real invoice text (nothing hardcoded)
  T2   header fields (supplier, invoice no., date) are read from the document
  T3   non-line-item rows (headers, totals, banners) are not mistaken for items
  T4   >5% price increase routes to manager_confirmation      (WP §3.2, §5.2)
  T5   the gate is strictly >5%: exactly 5.0% still auto-syncs (WP §3.2)
  T6   >5% price DECREASE also requires confirmation (gate is symmetric)
  T7   <80% match confidence routes to manual_review          (WP §3.2)
  T8   an exact supplier item code short-circuits matching at confidence 1.0
  T9   upper-case invoice text still fuzzy-matches mixed-case SKU names
       (regression: rapidfuzz is case-sensitive without default_process)
  T10  auto_sync writes the new cost; manager_confirmation does NOT
  T11  food cost % = recipe cost / menu price, and >32% is flagged (WP §3.3)
  T12  the suggested price restores the configured target food cost %
  T13  a price recommendation always carries a non-empty rationale (WP §3.1)
  T14  ACEConfig refuses autonomous execution below Phase 3   (WP §3.3, §4.1)
  T15  labor baseline returns exactly the configured horizon  (WP §3.4)
  T16  the day-of-week index reflects the trailing window, and no accuracy
       figure is claimed for the untrained baseline
  T17  the minimum staffing floor is applied and disclosed    (WP §3.4)
  T18  labor forecasting consumes no worker-level data        (WP §5.2)
  T19  audit_log is append-only (UPDATE/DELETE rejected)
  T20  seeding twice does not duplicate rows (idempotency)
  T21  demo data is flagged is_demo so it cannot pass as pilot data
  T22  API contract: health, process, pricing, approval round-trip
  T26  stored source paths are repo-relative — no local username or absolute
       path reaches the database, the API, or the published dashboard
  T27  author-added staffing ratios are disclosed as a structured field, not
       only in prose, so every consumer surfaces them
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ace import db
from ace.config import ACEConfig
from ace.ingestion import seed_data
from ace.ingestion.invoice_loader import (
    InvoiceLoader, parse_invoice_text, portable_source_path,
)
from ace.pricing.menu_engine import MenuEngine
from ace.scheduling.labor_optimizer import CoverRecord, LaborForecaster, load_history

DEMO = Path(__file__).resolve().parent.parent / "data" / "demo"
USFOODS = DEMO / "invoice_usfoods_2026-03-14.txt"
SYSCO = DEMO / "invoice_sysco_2026-03-21.txt"
LOCAL = DEMO / "invoice_localproduce_2026-03-28.txt"


@pytest.fixture()
def conn(tmp_path):
    """Isolated database per test — never touches data/ace.db."""
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture()
def cfg():
    return ACEConfig()


@pytest.fixture()
def seeded(conn):
    return seed_data.load(conn)


# ── Layer 1: parsing ────────────────────────────────────────────────────
def test_t1_parser_extracts_line_items():
    _header, items = parse_invoice_text(USFOODS.read_text(encoding="utf-8"))
    assert len(items) == 5
    chicken = next(i for i in items if "CHICKEN" in i.ingredient_name)
    assert chicken.unit_price == 22.50
    assert chicken.quantity == 4.0
    assert chicken.unit == "CS"
    assert chicken.total_price == 90.00
    assert chicken.supplier_code == "CHK-BREAST-5LB"


def test_t2_parser_reads_header_fields():
    header, _ = parse_invoice_text(USFOODS.read_text(encoding="utf-8"))
    assert header["supplier_name"] == "US Foods"
    assert header["invoice_number"] == "DEMO-4471902"
    assert header["invoice_date"] == "2026-03-14"


def test_t3_non_line_items_are_ignored():
    _h, items = parse_invoice_text(USFOODS.read_text(encoding="utf-8"))
    blob = " ".join(i.ingredient_name.upper() for i in items)
    # The banner, the column header row, and the INVOICE TOTAL line must not
    # be parsed as products.
    assert "DESCRIPTION" not in blob
    assert "INVOICE TOTAL" not in blob
    assert "DEMO DATA" not in blob
    assert all(i.unit_price > 0 for i in items)


# ── Layer 1: routing (White Paper §3.2) ─────────────────────────────────
def test_t4_price_increase_over_5pct_requires_confirmation(cfg, conn, seeded):
    result = InvoiceLoader(cfg, conn).process(USFOODS, seeded, is_demo=True)
    chicken = next(li for li in result.line_items
                   if li.matched_sku == "CHK-BREAST-5LB")
    assert chicken.routing == "manager_confirmation"
    assert chicken.price_change_pct == pytest.approx((22.50 - 18.99) / 18.99)
    assert "18.5%" in chicken.routing_reason


def test_t5_exactly_5pct_still_auto_syncs(cfg):
    loader = InvoiceLoader.__new__(InvoiceLoader)  # no DB needed for route()
    loader.config = cfg
    routing, _reason, change = loader.route(
        confidence=1.0, unit_price=10.50, previous_price=10.00)
    assert change == pytest.approx(0.05)
    assert routing == "auto_sync", "gate is '>5%', so exactly 5% must pass"


def test_t6_price_decrease_over_5pct_also_requires_confirmation(cfg, conn, seeded):
    result = InvoiceLoader(cfg, conn).process(SYSCO, seeded, is_demo=True)
    beef = next(li for li in result.line_items
                if li.matched_sku == "PRO-BEEF-GRND-10")
    assert beef.price_change_pct < 0
    assert beef.routing == "manager_confirmation"
    assert "decrease" in beef.routing_reason


def test_t7_low_confidence_routes_to_manual_review(cfg, conn, seeded):
    result = InvoiceLoader(cfg, conn).process(USFOODS, seeded, is_demo=True)
    saffron = next(li for li in result.line_items
                   if "SAFFRON" in li.parsed.ingredient_name)
    assert saffron.match_confidence < cfg.sku_match_confidence_threshold
    assert saffron.routing == "manual_review"
    assert saffron.matched_sku is None, "a rejected match must not be recorded"


def test_t8_supplier_code_short_circuits_matching(cfg, conn, seeded):
    loader = InvoiceLoader(cfg, conn)
    catalogue = loader._sku_catalogue(seeded)
    sku, confidence = loader.match_sku(
        "TOTALLY UNRECOGNISABLE TEXT", catalogue, supplier_code="CHK-BREAST-5LB")
    assert (sku, confidence) == ("CHK-BREAST-5LB", 1.0)


def test_t9_uppercase_invoice_matches_mixed_case_sku(cfg, conn, seeded):
    """Regression: rapidfuzz scorers are case-sensitive unless a processor is
    supplied. Without default_process, 'ROMA TOMATOES 25LB CASE' scored 0.35
    against 'Roma Tomatoes 25lb Case' and every code-less line was dumped
    into manual review."""
    loader = InvoiceLoader(cfg, conn)
    catalogue = loader._sku_catalogue(seeded)
    sku, confidence = loader.match_sku("ROMA TOMATOES 25LB CASE", catalogue)
    assert sku == "VEG-TOMATO-ROMA"
    assert confidence >= 0.80

    result = loader.process(LOCAL, seeded, is_demo=True)
    matched = [li for li in result.line_items if li.matched_sku]
    assert len(matched) == 3, "three of four code-less lines should match"


def test_t10_auto_sync_writes_cost_but_confirmation_does_not(cfg, conn, seeded):
    before = {r["sku"]: r["last_unit_price"] for r in
              conn.execute("SELECT sku, last_unit_price FROM inventory_skus")}
    InvoiceLoader(cfg, conn).process(USFOODS, seeded, is_demo=True)
    after = {r["sku"]: r["last_unit_price"] for r in
             conn.execute("SELECT sku, last_unit_price FROM inventory_skus")}

    # Tomatoes moved +2.6% -> auto-synced.
    assert after["VEG-TOMATO-ROMA"] == 18.99 != before["VEG-TOMATO-ROMA"]
    # Chicken moved +18.5% -> held pending a manager decision.
    assert after["CHK-BREAST-5LB"] == before["CHK-BREAST-5LB"] == 18.99


# ── Layer 2: menu engineering (White Paper §3.3) ────────────────────────
def test_t11_food_cost_pct_and_threshold_flagging(cfg, conn, seeded):
    engine = MenuEngine(cfg, conn)
    analyses = engine.analyze(seeded)
    assert len(analyses) == len(seed_data.RECIPES)

    for a in analyses:
        expected = sum(c.qty_per_serving * c.unit_price for c in a.contributions)
        assert a.recipe_cost == pytest.approx(expected)
        assert a.food_cost_pct == pytest.approx(a.recipe_cost / a.menu_price)
        assert a.above_threshold == (a.food_cost_pct > cfg.food_cost_alert_threshold)

    # At seeded prices nothing breaches 32%; confirming the chicken rise
    # pushes the three chicken-led items over it.
    assert all(not a.above_threshold for a in analyses)
    InvoiceLoader(cfg, conn).apply_confirmed_price("CHK-BREAST-5LB", 22.50, "test")
    flagged = [a for a in engine.analyze(seeded) if a.above_threshold]
    assert {a.item_name for a in flagged} == {
        "Chicken Parmigiana", "Grilled Chicken Sandwich", "Chicken Pesto Pasta"}


def test_t12_suggested_price_restores_target(cfg, conn, seeded):
    InvoiceLoader(cfg, conn).apply_confirmed_price("CHK-BREAST-5LB", 22.50, "test")
    for a in MenuEngine(cfg, conn).analyze(seeded):
        if not a.above_threshold:
            assert a.suggested_price is None
            continue
        assert a.suggested_price > a.menu_price
        # Repricing to the suggestion yields exactly the target percentage.
        assert a.recipe_cost / a.suggested_price == pytest.approx(cfg.target_food_cost_pct)


def test_t13_every_recommendation_explains_itself(cfg, conn, seeded):
    InvoiceLoader(cfg, conn).apply_confirmed_price("CHK-BREAST-5LB", 22.50, "test")
    out = MenuEngine(cfg, conn).recommendations(seeded)
    flagged = [i for i in out["items"] if i["above_threshold"]]
    assert flagged
    for item in flagged:
        r = item["rationale"]
        assert "32%" in r and "above" in r
        assert "Advisory only" in r
        assert item["cost_breakdown"], "the cost breakdown backs the rationale"
    assert out["autonomous_execution_enabled"] is False


def test_t14_autonomous_execution_blocked_below_phase_3():
    with pytest.raises(ValueError, match="Phase-3"):
        ACEConfig(autonomous_pricing_change_enabled=True, deployment_phase=1)
    with pytest.raises(ValueError, match="Phase-3"):
        ACEConfig(autonomous_scheduling_enabled=True, deployment_phase=2)
    ok = ACEConfig(autonomous_pricing_change_enabled=True, deployment_phase=3)
    assert ok.autonomous_pricing_change_enabled is True


# ── Layer 3: labor baseline (White Paper §3.4) ──────────────────────────
def test_t15_forecast_horizon_matches_config(cfg, conn, seeded):
    out = LaborForecaster(cfg, conn).recommendations(seeded)
    assert len(out["daily"]) == cfg.scheduling_horizon_days == 7
    days = [d["date"] for d in out["daily"]]
    assert days == sorted(days) and len(set(days)) == 7


def test_t16_dow_index_reflects_history_and_no_accuracy_is_claimed(cfg, conn, seeded):
    history = load_history()
    out = LaborForecaster(cfg, conn).recommendations(seeded, history=history)

    sat = next(d for d in out["daily"] if d["day_of_week"] == "Saturday")
    mon = next(d for d in out["daily"] if d["day_of_week"] == "Monday")
    assert sat["forecast_covers"] > mon["forecast_covers"]
    assert sat["dow_index"] > 1.0 > mon["dow_index"]

    # The forecast must equal the trailing same-weekday mean, not a fitted value.
    sat_actuals = [r.covers for r in history[-56:]
                   if r.day.strftime("%A") == "Saturday"]
    assert sat["forecast_covers"] == round(sum(sat_actuals) / len(sat_actuals))

    assert out["model_type"] == "seasonal-naive baseline (untrained)"
    assert out["external_signals_used"] == []
    assert "None." in out["accuracy_claim"]


def test_t17_minimum_staffing_floor_applied_and_disclosed(cfg, conn):
    quiet = [CoverRecord(day=date(2026, 1, 5) + timedelta(days=i), covers=4)
             for i in range(28)]
    out = LaborForecaster(cfg, conn).forecast(quiet)
    for f in out:
        assert f.recommended_foh == cfg.min_front_of_house_staff
        assert f.recommended_boh == cfg.min_back_of_house_staff
        assert f.floor_applied is True
        assert "minimum staffing floor" in f.rationale


def test_t18_labor_model_sees_no_worker_data(cfg, conn, seeded):
    out = LaborForecaster(cfg, conn).recommendations(seeded)
    assert "aggregate daily cover counts only" in out["fairness_note"]
    # CoverRecord carries a date and a count — there is no field a worker
    # attribute could occupy.
    assert set(CoverRecord.__dataclass_fields__) == {"day", "covers"}


def test_t19_forecast_rejects_insufficient_history(cfg, conn):
    with pytest.raises(ValueError, match="at least 7 days"):
        LaborForecaster(cfg, conn).forecast(
            [CoverRecord(day=date(2026, 1, 1), covers=100)])
    with pytest.raises(ValueError, match="empty history"):
        LaborForecaster(cfg, conn).forecast([])


# ── Governance and data hygiene ─────────────────────────────────────────
def test_t20_audit_log_is_append_only(conn):
    db.audit(conn, actor="test", action="PROBE")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE audit_log SET action='tampered' WHERE action='PROBE'")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM audit_log WHERE action='PROBE'")


def test_t21_seeding_is_idempotent(conn):
    first = seed_data.load(conn)
    second = seed_data.load(conn)
    assert first == second
    counts = {
        t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
        for t in ("restaurants", "inventory_skus", "recipes",
                  "recipe_ingredients", "pos_connections")
    }
    assert counts["restaurants"] == 1
    assert counts["pos_connections"] == 1
    assert counts["inventory_skus"] == len(seed_data.SKUS)
    assert counts["recipes"] == len(seed_data.RECIPES)
    assert counts["recipe_ingredients"] == sum(len(r[3]) for r in seed_data.RECIPES)


def test_t22_demo_data_is_flagged_as_demo(cfg, conn, seeded):
    row = conn.execute("SELECT name, is_demo FROM restaurants WHERE restaurant_id = ?",
                       (seeded,)).fetchone()
    assert row["is_demo"] == 1
    assert "DEMO" in row["name"]

    InvoiceLoader(cfg, conn).process(USFOODS, seeded, is_demo=True)
    inv = conn.execute("SELECT is_demo, extraction_method FROM invoices").fetchone()
    assert inv["is_demo"] == 1
    # Provenance is recorded: this is a text layer, not an OCR result.
    assert inv["extraction_method"] == "text_layer"


def test_t23_manager_approval_is_recorded_before_cost_write(cfg, conn, seeded):
    loader = InvoiceLoader(cfg, conn)
    loader.process(USFOODS, seeded, is_demo=True)
    line = conn.execute(
        "SELECT line_item_id FROM invoice_line_items WHERE matched_sku = ?",
        ("CHK-BREAST-5LB",)).fetchone()

    db.record_approval(conn, subject_type="invoice_line_item",
                       subject_id=line["line_item_id"], decision="approved",
                       decided_by="gm@demo", note="verified against supplier")
    loader.apply_confirmed_price("CHK-BREAST-5LB", 22.50, "gm@demo")

    price = conn.execute(
        "SELECT last_unit_price p FROM inventory_skus WHERE sku = ?",
        ("CHK-BREAST-5LB",)).fetchone()["p"]
    assert price == 22.50

    actions = [r["action"] for r in
               conn.execute("SELECT action FROM audit_log ORDER BY log_id")]
    assert "APPROVAL_APPROVED" in actions
    assert "SKU_PRICE_UPDATED" in actions


# ── API ─────────────────────────────────────────────────────────────────
def test_t24_api_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DEFAULT_DB", tmp_path / "api.db")
    from ace.api import endpoints
    client = TestClient(endpoints.app)

    assert client.get("/health").json()["status"] == "ok"

    cfg_body = client.get("/config").json()
    assert cfg_body["price_change_confirmation_threshold"] == 0.05
    assert cfg_body["food_cost_alert_threshold"] == 0.32
    assert "engineering choice" in cfg_body["provenance"]["target_food_cost_pct"]

    rid = client.post("/demo/seed").json()["restaurant_id"]

    inv = client.post("/invoices/process", json={
        "filename": "invoice_usfoods_2026-03-14.txt", "restaurant_id": rid}).json()
    assert inv["items_extracted"] == 5
    assert inv["routing_counts"]["manager_confirmation"] == 1
    assert inv["routing_counts"]["manual_review"] == 1
    assert inv["is_demo"] is True

    line = next(li for li in inv["line_items"]
                if li["matched_sku"] == "CHK-BREAST-5LB")
    assert client.get("/pricing/recommendations",
                      params={"restaurant_id": rid}).json()[
                          "items_above_threshold"] == 0

    approved = client.post("/approvals", json={
        "subject_type": "invoice_line_item", "subject_id": inv["invoice_id"],
        "decision": "approved", "decided_by": "gm@demo",
        "sku": line["matched_sku"],
        "confirmed_unit_price": line["unit_price"]}).json()
    assert approved["cost_synced"]["sku"] == "CHK-BREAST-5LB"

    after = client.get("/pricing/recommendations",
                       params={"restaurant_id": rid}).json()
    assert after["items_above_threshold"] == 3
    assert after["autonomous_execution_enabled"] is False

    labor = client.get("/labor/forecast", params={"restaurant_id": rid}).json()
    assert len(labor["daily"]) == 7
    assert labor["external_signals_used"] == []

    actions = [e["action"] for e in client.get("/audit/export").json()["entries"]]
    assert "APPROVAL_APPROVED" in actions and "INVOICE_PROCESSED" in actions


def test_t26_source_path_is_repo_relative(cfg, conn, seeded):
    """Regression: the builder embedded absolute paths in the published
    dashboard, leaking the operating user's name and directory layout."""
    result = InvoiceLoader(cfg, conn).process(USFOODS, seeded, is_demo=True)
    assert result.source_path == "data/demo/invoice_usfoods_2026-03-14.txt"

    stored = conn.execute("SELECT source_path FROM invoices").fetchone()["source_path"]
    for leak in ("C:", "/home/", "/Users/", "\\", str(Path.home())):
        assert leak not in stored, f"absolute path component {leak!r} leaked"

    # A file outside the repository degrades to its bare name, never a path.
    outside = portable_source_path(Path.home() / "secret" / "invoice.txt")
    assert outside == "invoice.txt"


def test_t27_staffing_assumptions_are_disclosed(cfg, conn, seeded):
    out = LaborForecaster(cfg, conn).recommendations(seeded)
    sa = out["staffing_assumptions"]
    assert sa["covers_per_foh_staff_hour"] == 7.0
    assert sa["covers_per_boh_staff_hour"] == 15.0
    assert "not specified in the working" in sa["provenance"]
    assert "not measured" in sa["provenance"]

    # The disclosure must track the actual values in use, not a fixed string.
    custom = LaborForecaster(cfg, conn, covers_per_foh=9.0, covers_per_boh=20.0)
    assert custom.recommendations(seeded, persist=False)[
        "staffing_assumptions"]["covers_per_foh_staff_hour"] == 9.0


def test_t25_api_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DEFAULT_DB", tmp_path / "api2.db")
    from ace.api import endpoints
    client = TestClient(endpoints.app)
    r = client.post("/invoices/process",
                    json={"filename": "../../../../etc/passwd"})
    assert r.status_code == 404
