"""A.C.E. Layer 2 — Dynamic Menu Engineering Engine (Working Paper §3.3).

Computes actual food cost percentage per menu item from the current recorded
ingredient costs, and generates a price recommendation when an item exceeds
the configured threshold (default 32%, §3.3).

Every recommendation carries a plain-language rationale naming the ingredient
that moved, the resulting food cost percentage, the threshold it breached,
and the arithmetic behind the suggested price. A recommendation a manager
cannot interrogate is not usable under the Human-in-the-Loop model in §3.1.

ADVISORY ONLY. This module never writes a menu price. Working Paper §3.3
permits bounded autonomous adjustment in Phase 3; `ACEConfig` refuses to
enable it below Phase 3, and nothing in this file performs such a write.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ace import db

logger = logging.getLogger(__name__)


def engine_version() -> str:
    """Git commit hash, so a stored recommendation is reproducible."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent.parent,
            text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "untracked"


@dataclass
class IngredientContribution:
    sku: str
    name: str
    qty_per_serving: float
    unit_price: float

    @property
    def cost(self) -> float:
        return self.qty_per_serving * self.unit_price


@dataclass
class ItemCostAnalysis:
    recipe_id: str
    item_name: str
    menu_price: float
    contributions: List[IngredientContribution] = field(default_factory=list)
    threshold_pct: float = 0.32
    target_pct: float = 0.28
    suggested_price: Optional[float] = None
    rationale: str = ""

    @property
    def recipe_cost(self) -> float:
        return sum(c.cost for c in self.contributions)

    @property
    def food_cost_pct(self) -> float:
        return self.recipe_cost / self.menu_price if self.menu_price > 0 else 0.0

    @property
    def above_threshold(self) -> bool:
        return self.food_cost_pct > self.threshold_pct

    @property
    def top_driver(self) -> Optional[IngredientContribution]:
        return max(self.contributions, key=lambda c: c.cost, default=None)

    def to_dict(self) -> Dict:
        return {
            "recipe_id": self.recipe_id,
            "item_name": self.item_name,
            "menu_price": round(self.menu_price, 2),
            "recipe_cost": round(self.recipe_cost, 4),
            "food_cost_pct": round(self.food_cost_pct * 100, 1),
            "threshold_pct": round(self.threshold_pct * 100, 1),
            "target_pct": round(self.target_pct * 100, 1),
            "above_threshold": self.above_threshold,
            "suggested_price": (round(self.suggested_price, 2)
                                if self.suggested_price is not None else None),
            "price_delta": (round(self.suggested_price - self.menu_price, 2)
                            if self.suggested_price is not None else None),
            "rationale": self.rationale,
            "cost_breakdown": [
                {"sku": c.sku, "name": c.name,
                 "qty_per_serving": c.qty_per_serving,
                 "unit_price": round(c.unit_price, 2),
                 "cost": round(c.cost, 4),
                 # Same formatting as the rationale text, so the dashboard
                 # never shows a different cent value for the same cost.
                 "cost_display": f"${c.cost:.2f}"}
                for c in sorted(self.contributions, key=lambda c: c.cost, reverse=True)
            ],
        }


class MenuEngine:
    """Layer 2: recipe cost model -> food cost % -> price recommendation."""

    def __init__(self, config, conn=None):
        self.config = config
        self.conn = conn or db.connect()

    def analyze(self, restaurant_id: str) -> List[ItemCostAnalysis]:
        """Cost every menu item against current recorded ingredient prices."""
        recipes = self.conn.execute(
            "SELECT recipe_id, item_name, menu_price FROM recipes "
            "WHERE restaurant_id = ? ORDER BY item_name", (restaurant_id,)
        ).fetchall()

        analyses: List[ItemCostAnalysis] = []
        for r in recipes:
            rows = self.conn.execute(
                "SELECT ri.sku, ri.qty_per_serving, s.name, s.last_unit_price "
                "FROM recipe_ingredients ri JOIN inventory_skus s ON s.sku = ri.sku "
                "WHERE ri.recipe_id = ?", (r["recipe_id"],)
            ).fetchall()

            analysis = ItemCostAnalysis(
                recipe_id=r["recipe_id"],
                item_name=r["item_name"],
                menu_price=r["menu_price"],
                contributions=[
                    IngredientContribution(
                        sku=row["sku"], name=row["name"],
                        qty_per_serving=row["qty_per_serving"],
                        unit_price=row["last_unit_price"] or 0.0)
                    for row in rows
                ],
                threshold_pct=self.config.food_cost_alert_threshold,
                target_pct=self.config.target_food_cost_pct,
            )
            self._build_recommendation(analysis)
            analyses.append(analysis)

        analyses.sort(key=lambda a: a.food_cost_pct, reverse=True)
        return analyses

    def _build_recommendation(self, a: ItemCostAnalysis) -> None:
        """Attach a suggested price and a human-readable 'why'."""
        driver = a.top_driver
        driver_txt = (
            f"{driver.name} at ${driver.unit_price:.2f}/unit contributes "
            f"${driver.cost:.2f} of the ${a.recipe_cost:.2f} plate cost"
            if driver else "no ingredients are recorded for this item"
        )

        if not a.above_threshold:
            a.rationale = (
                f"Food cost is {a.food_cost_pct * 100:.1f}%, within the "
                f"{a.threshold_pct * 100:.0f}% threshold. No action required. "
                f"Largest cost driver: {driver_txt}."
            )
            return

        # Price that restores the target food cost percentage:
        #   suggested = recipe_cost / target_pct
        a.suggested_price = a.recipe_cost / a.target_pct
        delta = a.suggested_price - a.menu_price
        a.rationale = (
            f"{driver_txt}. Total plate cost ${a.recipe_cost:.2f} against a "
            f"${a.menu_price:.2f} menu price puts food cost at "
            f"{a.food_cost_pct * 100:.1f}%, above the "
            f"{a.threshold_pct * 100:.0f}% threshold. Repricing to "
            f"${a.suggested_price:.2f} ({delta:+.2f}) restores the "
            f"{a.target_pct * 100:.0f}% target "
            f"(${a.recipe_cost:.2f} / {a.target_pct:.2f}). "
            f"Advisory only - manager approval required before any price change."
        )

    def recommendations(self, restaurant_id: str, *, persist: bool = True,
                        actor: str = "system") -> Dict:
        """Full Layer 2 output. Persists flagged items to price_recommendations."""
        analyses = self.analyze(restaurant_id)
        flagged = [a for a in analyses if a.above_threshold]

        if persist and flagged:
            version = engine_version()
            for a in flagged:
                self.conn.execute(
                    "INSERT INTO price_recommendations (recommendation_id, recipe_id, "
                    "current_price, recipe_cost, food_cost_pct, threshold_pct, "
                    "suggested_price, rationale, engine_version, generated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (db.new_id(), a.recipe_id, a.menu_price, a.recipe_cost,
                     a.food_cost_pct, a.threshold_pct, a.suggested_price,
                     a.rationale, version, db.now_iso()),
                )
            self.conn.commit()
            db.audit(self.conn, actor=actor, action="PRICE_RECOMMENDATIONS_GENERATED",
                     payload={"flagged": len(flagged), "engine_version": version})

        return {
            "total_menu_items": len(analyses),
            "items_above_threshold": len(flagged),
            "items_within_threshold": len(analyses) - len(flagged),
            "threshold_pct": round(self.config.food_cost_alert_threshold * 100, 1),
            "target_pct": round(self.config.target_food_cost_pct * 100, 1),
            "autonomous_execution_enabled": self.config.autonomous_pricing_change_enabled,
            "governance_note": (
                "All recommendations are advisory. A.C.E. does not change menu "
                "prices without manager confirmation (Working Paper §3.1, §3.3)."
            ),
            "items": [a.to_dict() for a in analyses],
        }
