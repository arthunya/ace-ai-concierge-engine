"""
A.C.E. Quick Demo — Run this to see all three layers in action.

Usage:
    python demo.py

Demonstrates the Phase 1 proof-of-concept pipeline:
  Layer 1: Invoice ingestion with cost change detection
  Layer 2: Menu pricing recommendations based on updated costs
  Layer 3: 7-day labor scheduling forecast
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from ace import ACEEngine
from ace.config import ACEConfig


def run_demo():
    print("=" * 65)
    print("A.C.E. — AI Concierge & Engine")
    print("Phase 1 Proof-of-Concept Demo")
    print(f"DOI: 10.13140/RG.2.2.33391.60326")
    print("=" * 65)
    print()

    config = ACEConfig()
    engine = ACEEngine(config=config)
    engine.initialize()

    # ── LAYER 1: Invoice Processing ──────────────────────────────────
    print("LAYER 1 — Automated Invoice Ingestion")
    print("-" * 45)

    result = engine.process_invoice("sample_invoice_usfoods_april2026.pdf")

    print(f"Supplier:          {result.supplier_name}")
    print(f"Items extracted:   {result.items_extracted}")
    print(f"Items mapped:      {result.items_mapped}")
    print(f"Requiring review:  {result.items_requiring_review}")
    print(f"Total cost:        ${result.total_invoice_cost:,.2f}")
    print()

    if result.cost_changes_flagged:
        print("⚠️  Cost Changes Requiring Manager Confirmation:")
        for change in result.cost_changes_flagged:
            arrow = "↑" if change["direction"] == "increase" else "↓"
            print(f"   {arrow} {change['ingredient']}")
            print(f"     ${change['old_price']} → ${change['new_price']} "
                  f"({change['change_pct']:+.1f}%)")
            print(f"     {change['action_required']}")
    else:
        print("✅ No significant cost changes detected.")
    print()

    # ── LAYER 2: Menu Pricing ─────────────────────────────────────────
    print("LAYER 2 — Dynamic Menu Engineering")
    print("-" * 45)

    pricing = engine.get_pricing_recommendations()

    print(f"Menu items analyzed:    {pricing['total_menu_items']}")
    print(f"Above threshold ({pricing['threshold_pct']}%): {pricing['items_above_threshold']}")
    print(f"Healthy items:          {pricing['items_healthy']}")
    print()

    if pricing["recommendations"]:
        print("Pricing Recommendations (advisory — manager approval required):")
        for rec in pricing["recommendations"]:
            print(f"\n   📋 {rec['item_name']}")
            print(f"      Current price:     ${rec['current_price']:.2f}")
            print(f"      Recipe cost:       ${rec['recipe_cost']:.2f}")
            print(f"      Food cost %:       {rec['food_cost_pct']:.1f}% "
                  f"(threshold: {rec['target_food_cost_pct']:.1f}%)")
            if rec["suggested_price"]:
                print(f"      Suggested price:   ${rec['suggested_price']:.2f} "
                      f"(+${rec['price_change_required']:.2f})")
            print(f"      Status:            {rec['action']}")
    else:
        print("✅ All menu items within acceptable food cost %.")
    print()

    # ── LAYER 3: Labor Scheduling ─────────────────────────────────────
    print("LAYER 3 — Predictive Labor Scheduling (7-day forecast)")
    print("-" * 45)
    print("⚠️  Advisory only — manager confirmation required for all changes")
    print()

    schedule = engine.get_labor_recommendations(days_ahead=7)

    print(f"{'Date':<14} {'Day':<12} {'Covers':>7} {'Revenue':>10} "
          f"{'FOH':>5} {'BOH':>5} {'Conf':>6}")
    print("-" * 65)

    for day in schedule["daily_forecasts"]:
        sr = day["staffing_recommendation"]
        print(f"{day['date']:<14} {day['day_of_week']:<12} "
              f"{day['forecasted_covers']:>7} "
              f"${day['forecasted_revenue']:>9,.0f} "
              f"{sr['front_of_house']:>5} "
              f"{sr['back_of_house']:>5} "
              f"{day['confidence']:>5.0%}")

    print()
    print(f"Total recommended labor hours: {schedule['total_recommended_labor_hours']}")
    print()

    # ── FOOTER ────────────────────────────────────────────────────────
    print("=" * 65)
    print("Demo complete.")
    print()
    print("Research paper:  https://doi.org/10.13140/RG.2.2.33391.60326")
    print("GitHub:          https://github.com/arthunya/ace-ai-concierge-engine")
    print("Companion (V.E.T.): https://github.com/arthunya/vet-vendor-threat-detection")


if __name__ == "__main__":
    run_demo()
