"""A.C.E. Phase-1 demonstration — run this first.

Walks the full Human-in-the-Loop path end to end:

    invoice text -> line items -> SKU match -> routing gates
                 -> manager confirmation -> cost sync
                 -> food cost % -> price recommendation
                 -> 7-day labor baseline

Everything printed is computed live from the files in data/demo/. Nothing is
a stored result and nothing is a pilot metric — no pilot has been run.

    python demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Windows consoles default to cp1252 and will crash on non-Latin-1 output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ace import ACEEngine, __doi__, __version__
from ace.ingestion import seed_data

ROOT = Path(__file__).resolve().parent
DEMO_DB = ROOT / "data" / "demo_run.db"
INVOICES = [
    "invoice_usfoods_2026-03-14.txt",
    "invoice_sysco_2026-03-21.txt",
    "invoice_localproduce_2026-03-28.txt",
]
RULE = "=" * 78


def header(title: str) -> None:
    print(f"\n{RULE}\n  {title}\n{RULE}")


def main() -> None:
    # Start from a clean database so the demo is reproducible: processing an
    # invoice mutates recorded costs, and a stale DB would compare against
    # already-updated prices and stop firing the variance gate.
    DEMO_DB.unlink(missing_ok=True)

    engine = ACEEngine(db_path=DEMO_DB)
    restaurant_id = engine.load_demo_data()

    print(RULE)
    print(f"  A.C.E. - AI Concierge & Engine | Phase-1 proof of concept v{__version__}")
    print(f"  Working paper DOI: {__doi__}")
    print(RULE)
    print("  ALL DATA BELOW IS SYNTHETIC AND ILLUSTRATIVE.")
    print("  No pilot deployment has taken place (White Paper §4.1, §7), so")
    print("  none of these figures is a measured result from a restaurant.")

    # ── Layer 1 ────────────────────────────────────────────────────────
    header("LAYER 1 - Automated invoice ingestion (White Paper §3.2)")
    pending: list[tuple[str, str, float]] = []

    for name in INVOICES:
        result = engine.process_invoice(
            ROOT / "data" / "demo" / name, restaurant_id, is_demo=True,
            actor="demo")
        counts = result.counts()
        print(f"\n  {name}")
        print(f"    supplier {result.supplier_name} | invoice "
              f"{result.invoice_number} | {result.invoice_date}")
        print(f"    {len(result.line_items)} line items parsed, "
              f"${result.total_extracted:,.2f} extracted")
        print(f"    auto-synced {counts['auto_sync']} | "
              f"awaiting confirmation {counts['manager_confirmation']} | "
              f"manual review {counts['manual_review']}")
        for li in result.line_items:
            if li.routing == "auto_sync":
                continue
            marker = "CONFIRM" if li.routing == "manager_confirmation" else "REVIEW "
            print(f"      [{marker}] {li.parsed.ingredient_name[:44]}")
            print(f"                {li.routing_reason}")
            if li.routing == "manager_confirmation" and li.matched_sku:
                pending.append((li.matched_sku, li.parsed.ingredient_name,
                                li.parsed.unit_price))

    # ── Layer 2, before any human decision ─────────────────────────────
    header("LAYER 2 - Menu engineering BEFORE manager confirmation (§3.3)")
    before = engine.pricing_recommendations(restaurant_id, persist=False)
    print(f"  {before['items_above_threshold']} of {before['total_menu_items']} "
          f"items exceed the {before['threshold_pct']}% food cost threshold.")
    print("  Only the small auto-synced movements are reflected here. The large")
    print("  changes held at the gate above have NOT been written to inventory,")
    print("  so they cannot yet influence any recommendation. That is the gate")
    print("  working: an 18.5% cost jump does not reach pricing on its own.\n")
    for item in before["items"][:4]:
        print(f"    {item['food_cost_pct']:5.1f}%  {item['item_name']}")

    # ── The Human-in-the-Loop step ─────────────────────────────────────
    header("HUMAN-IN-THE-LOOP - manager confirms the held cost changes (§3.1)")
    from ace import db
    for sku, name, price in pending:
        line = engine.conn.execute(
            "SELECT line_item_id FROM invoice_line_items WHERE matched_sku = ? "
            "AND routing = 'manager_confirmation' ORDER BY rowid DESC LIMIT 1",
            (sku,)).fetchone()
        db.record_approval(
            engine.conn, subject_type="invoice_line_item",
            subject_id=line["line_item_id"], decision="approved",
            decided_by="demo_manager@example",
            note="Demo: approved to show the downstream effect.")
        engine.invoices.apply_confirmed_price(sku, price, "demo_manager@example")
        print(f"  approved  {sku:18} -> ${price:.2f}   ({name[:34]})")
    print("\n  Each decision is written to manager_approvals and to the")
    print("  append-only audit_log before any cost is allowed through.")

    # ── Layer 2, after ─────────────────────────────────────────────────
    header("LAYER 2 - Menu engineering AFTER confirmation (§3.3)")
    after = engine.pricing_recommendations(restaurant_id, actor="demo")
    print(f"  {after['items_above_threshold']} of {after['total_menu_items']} "
          f"items now exceed the {after['threshold_pct']}% threshold.\n")
    for item in after["items"]:
        if not item["above_threshold"]:
            continue
        print(f"  {item['item_name']}  (${item['menu_price']:.2f} -> "
              f"${item['suggested_price']:.2f}, {item['price_delta']:+.2f})")
        print(f"    {item['rationale']}")
        top = item["cost_breakdown"][0]
        print(f"    largest driver: {top['name']} "
              f"${top['cost']:.2f}/plate at ${top['unit_price']:.2f}/unit\n")
    print(f"  {after['governance_note']}")

    # ── Layer 3 ────────────────────────────────────────────────────────
    header("LAYER 3 - Predictive labor scheduling baseline (§3.4)")
    labor = engine.labor_recommendations(restaurant_id, actor="demo")
    print(f"  method: {labor['method']}  ({labor['model_type']})")
    print(f"  history: {labor['history_days_used']} days of synthetic covers")
    print(f"  external signals used: {labor['external_signals_used'] or 'none'}")
    print(f"  accuracy: {labor['accuracy_claim']}\n")
    print("    date         day        covers   idx    FOH  BOH  total")
    for d in labor["daily"]:
        s = d["staffing"]
        print(f"    {d['date']}   {d['day_of_week']:9}  {d['forecast_covers']:5}  "
              f"{d['dow_index']:.2f}   {s['front_of_house']:3}  "
              f"{s['back_of_house']:3}  {s['total']:4}")
    busiest = max(labor["daily"], key=lambda d: d["forecast_covers"])
    print(f"\n  why {busiest['day_of_week']}: {busiest['rationale']}")
    print(f"\n  {labor['governance_note']}")

    # ── Audit trail ────────────────────────────────────────────────────
    header("AUDIT TRAIL - append-only (White Paper §3.1)")
    rows = engine.conn.execute(
        "SELECT action, COUNT(*) n FROM audit_log GROUP BY action ORDER BY n DESC"
    ).fetchall()
    for r in rows:
        print(f"    {r['n']:3}  {r['action']}")
    print("\n  UPDATE and DELETE on audit_log are rejected by database trigger.")

    header("SCOPE REMINDER")
    print("  Built and verified here: invoice text parsing, fuzzy SKU matching,")
    print("  the three routing gates, recipe costing, price recommendation, the")
    print("  approval gate, the labor baseline, and the audit trail.")
    print()
    print("  NOT built here: OCR of scanned PDFs (§3.2 specifies a fine-tuned")
    print("  transformer - none is trained), live Toast/Clover API integration,")
    print("  a trained time-series forecaster with event and weather signals")
    print("  (§3.4), and any pilot validation (§4.1, §7). See README.md.")
    print()
    print(f"  Database written to: {DEMO_DB}")
    engine.close()


if __name__ == "__main__":
    main()
