"""Assemble the standalone A.C.E. dashboard.

Runs the engine over the demo invoices, captures the real computed output at
each stage, and injects it into the HTML template as JSON. The resulting
dashboard/ACE_Dashboard.html is a single self-contained file with no network
dependencies — every number in it was produced by the code in this repo
during this build.

    python scripts/build_dashboard.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # allow `python scripts/build_dashboard.py`

from ace import ACEEngine, __doi__, __version__, db  # noqa: E402
from ace.pricing.menu_engine import engine_version   # noqa: E402

DEMO_DIR = ROOT / "data" / "demo"
BUILD_DB = ROOT / "data" / "dashboard_build.db"
TEMPLATE = ROOT / "dashboard" / "ace_dashboard_template.html"
OUTPUT = ROOT / "dashboard" / "ACE_Dashboard.html"

INVOICES = [
    "invoice_usfoods_2026-03-14.txt",
    "invoice_sysco_2026-03-21.txt",
    "invoice_localproduce_2026-03-28.txt",
]


def build_payload() -> dict:
    BUILD_DB.unlink(missing_ok=True)
    engine = ACEEngine(db_path=BUILD_DB)
    rid = engine.load_demo_data()

    invoices, pending = [], []
    for name in INVOICES:
        result = engine.process_invoice(DEMO_DIR / name, rid, is_demo=True,
                                        actor="dashboard_build")
        payload = result.to_dict()
        payload["filename"] = name
        payload["source_text"] = (DEMO_DIR / name).read_text(encoding="utf-8")
        invoices.append(payload)
        for li in result.line_items:
            if li.routing == "manager_confirmation" and li.matched_sku:
                pending.append({
                    "sku": li.matched_sku,
                    "ingredient": li.parsed.ingredient_name,
                    "previous_unit_price": li.previous_unit_price,
                    "new_unit_price": li.parsed.unit_price,
                    "change_pct": round((li.price_change_pct or 0) * 100, 1),
                    "reason": li.routing_reason,
                })

    pricing_before = engine.pricing_recommendations(rid, persist=False)

    for item in pending:
        row = engine.conn.execute(
            "SELECT line_item_id FROM invoice_line_items WHERE matched_sku = ? "
            "AND routing = 'manager_confirmation' ORDER BY rowid DESC LIMIT 1",
            (item["sku"],)).fetchone()
        db.record_approval(engine.conn, subject_type="invoice_line_item",
                           subject_id=row["line_item_id"], decision="approved",
                           decided_by="demo_manager@example",
                           note="Dashboard build: approved to show downstream effect.")
        engine.invoices.apply_confirmed_price(
            item["sku"], item["new_unit_price"], "demo_manager@example")

    pricing_after = engine.pricing_recommendations(rid, actor="dashboard_build")
    labor = engine.labor_recommendations(rid, actor="dashboard_build")

    audit = [dict(r) for r in engine.conn.execute(
        "SELECT ts, actor, action FROM audit_log ORDER BY log_id")]

    history = [
        {"date": r["forecast_date"], "covers": r["forecast_covers"]}
        for r in engine.conn.execute(
            "SELECT forecast_date, forecast_covers FROM labor_forecasts "
            "ORDER BY forecast_date")
    ]
    engine.close()

    return {
        "meta": {
            "version": __version__,
            "doi": __doi__,
            "engine_version": engine_version(),
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "synthetic": True,
        },
        "thresholds": {
            "match_confidence": 0.80,
            "price_variance": 0.05,
            "food_cost_alert": pricing_after["threshold_pct"] / 100,
            "food_cost_target": pricing_after["target_pct"] / 100,
        },
        "invoices": invoices,
        "pending_confirmations": pending,
        "pricing_before": pricing_before,
        "pricing_after": pricing_after,
        "labor": labor,
        "labor_series": history,
        "audit": audit,
    }


def main() -> None:
    payload = build_payload()
    template = TEMPLATE.read_text(encoding="utf-8")
    token = '"__ACE_DATA__"'
    if token not in template:
        raise SystemExit(f"template is missing the {token} placeholder")
    # A literal "</script>" inside any JSON string value would close the tag
    # early and break the page, so neutralise it before injection.
    blob = json.dumps(payload, indent=None).replace("</", "<\\/")
    out = template.replace(token, blob)
    OUTPUT.write_text(out, encoding="utf-8")
    size_kb = OUTPUT.stat().st_size // 1024
    print(f"{OUTPUT} ({size_kb} KB)")
    print(f"  invoices: {len(payload['invoices'])}")
    print(f"  flagged before approval: {payload['pricing_before']['items_above_threshold']}")
    print(f"  flagged after approval:  {payload['pricing_after']['items_above_threshold']}")
    print(f"  labor days: {len(payload['labor']['daily'])}")
    print(f"  audit entries: {len(payload['audit'])}")


if __name__ == "__main__":
    main()
