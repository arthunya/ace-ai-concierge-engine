"""
A.C.E. Layer 2: Dynamic Menu Engineering Engine

Translates real-time ingredient cost data — updated by Layer 1 — into
actionable menu pricing intelligence. Monitors food cost percentage for
every menu item and surfaces pricing recommendations when margins erode
beyond the configured threshold.

Human-in-the-Loop design: ALL pricing recommendations are advisory only.
The system never autonomously changes menu prices. Manager confirmation
is required before any price adjustment is implemented. This is non-negotiable
and satisfies both the vicarious liability mitigation requirement and the
Human-in-the-Loop principle established in the A.C.E. working paper.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MenuItemCostAnalysis:
    """Cost analysis for a single menu item."""
    item_id: str
    item_name: str
    current_menu_price: float
    recipe_cost: float
    food_cost_pct: float
    target_food_cost_pct: float
    is_above_threshold: bool
    suggested_price: Optional[float] = None
    price_change_required: Optional[float] = None
    confidence: float = 0.0
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return {
            "item_id": self.item_id,
            "item_name": self.item_name,
            "current_price": round(self.current_menu_price, 2),
            "recipe_cost": round(self.recipe_cost, 2),
            "food_cost_pct": round(self.food_cost_pct * 100, 1),
            "target_food_cost_pct": round(self.target_food_cost_pct * 100, 1),
            "above_threshold": self.is_above_threshold,
            "suggested_price": round(self.suggested_price, 2) if self.suggested_price else None,
            "price_change_required": round(self.price_change_required, 2) if self.price_change_required else None,
            "action": "Manager review recommended" if self.is_above_threshold else "No action required",
            "last_updated": self.last_updated,
        }


class MenuEngine:
    """
    A.C.E. Layer 2 — Dynamic menu pricing intelligence.

    Continuously monitors food cost percentage for every menu item.
    When ingredient costs change (updated by Layer 1), recalculates
    food cost % and flags items that exceed the threshold for manager review.

    The financial governance logic in this engine draws directly from
    practitioner experience in financial analysis and internal audit,
    where margin monitoring and cost variance analysis were core functions.

    Usage:
        engine = MenuEngine(config)
        engine.initialize()
        recommendations = engine.get_recommendations()
    """

    def __init__(self, config):
        self.config = config
        self._menu_items: Dict[str, Dict] = {}
        self._current_costs: Dict[str, float] = {}
        self._initialized = False

    def initialize(self) -> None:
        """Load menu items and current ingredient costs."""
        self._load_sample_menu()
        self._load_current_costs()
        self._initialized = True
        logger.info(f"MenuEngine initialized with {len(self._menu_items)} menu items")

    def get_recommendations(self) -> Dict:
        """
        Analyze all menu items and return pricing recommendations.

        Returns advisory recommendations only — no prices are changed
        without explicit manager confirmation.
        """
        if not self._initialized:
            self.initialize()

        analyses = []
        items_above_threshold = 0

        for item_id, item_data in self._menu_items.items():
            analysis = self._analyze_item(item_id, item_data)
            analyses.append(analysis)
            if analysis.is_above_threshold:
                items_above_threshold += 1

        # Sort: items needing attention first
        analyses.sort(key=lambda x: x.food_cost_pct, reverse=True)

        return {
            "total_menu_items": len(analyses),
            "items_above_threshold": items_above_threshold,
            "items_healthy": len(analyses) - items_above_threshold,
            "threshold_pct": round(self.config.food_cost_alert_threshold * 100, 1),
            "recommendations": [a.to_dict() for a in analyses if a.is_above_threshold],
            "healthy_items": [a.to_dict() for a in analyses if not a.is_above_threshold],
            "generated_at": datetime.utcnow().isoformat(),
            "note": "All recommendations require manager confirmation before implementation.",
        }

    def update_ingredient_cost(self, sku: str, new_unit_price: float) -> List[str]:
        """
        Update cost for an ingredient SKU and return affected menu items.
        Called by Layer 1 after manager confirms a price change.
        """
        self._current_costs[sku] = new_unit_price
        affected_items = []

        for item_id, item_data in self._menu_items.items():
            recipe = item_data.get("recipe", {})
            if sku in recipe:
                affected_items.append(item_id)
                logger.info(f"Cost update for {sku} affects menu item: {item_data['name']}")

        return affected_items

    def _analyze_item(
        self, item_id: str, item_data: Dict
    ) -> MenuItemCostAnalysis:
        """Calculate food cost % and generate pricing recommendation if needed."""
        current_price = item_data["price"]
        recipe = item_data.get("recipe", {})

        # Calculate recipe cost from current ingredient prices
        recipe_cost = sum(
            self._current_costs.get(sku, 0) * qty_per_serving
            for sku, qty_per_serving in recipe.items()
        )

        food_cost_pct = recipe_cost / current_price if current_price > 0 else 0
        is_above = food_cost_pct > self.config.food_cost_alert_threshold

        suggested_price = None
        price_change = None

        if is_above:
            # Calculate price needed to hit target food cost %
            # Using 28% as target (below 32% threshold with margin)
            target_pct = 0.28
            suggested_price = recipe_cost / target_pct
            price_change = suggested_price - current_price

        return MenuItemCostAnalysis(
            item_id=item_id,
            item_name=item_data["name"],
            current_menu_price=current_price,
            recipe_cost=recipe_cost,
            food_cost_pct=food_cost_pct,
            target_food_cost_pct=self.config.food_cost_alert_threshold,
            is_above_threshold=is_above,
            suggested_price=suggested_price,
            price_change_required=price_change,
            confidence=0.85 if recipe_cost > 0 else 0.0,
        )

    def _load_sample_menu(self) -> None:
        """
        Sample menu with recipes linking to inventory SKUs.
        In Phase 2, this loads from the live POS menu API.
        """
        self._menu_items = {
            "ITEM-001": {
                "name": "Grilled Chicken Sandwich",
                "price": 14.99,
                "category": "entrees",
                "recipe": {
                    "CHK-BREAST-5LB": 0.35,   # 0.35 CS equivalent per serving
                    "VEG-TOMATO-ROMA": 0.04,
                }
            },
            "ITEM-002": {
                "name": "Margherita Pizza (10\")",
                "price": 16.99,
                "category": "entrees",
                "recipe": {
                    "DRY-FLOUR-AP-50": 0.03,
                    "VEG-TOMATO-ROMA": 0.06,
                    "OIL-EVOO-1GAL": 0.02,
                }
            },
            "ITEM-003": {
                "name": "Caesar Salad",
                "price": 11.99,
                "category": "starters",
                "recipe": {
                    "VEG-TOMATO-ROMA": 0.05,
                    "OIL-EVOO-1GAL": 0.015,
                }
            },
            "ITEM-004": {
                "name": "Chicken Pasta",
                "price": 17.99,
                "category": "entrees",
                "recipe": {
                    "CHK-BREAST-5LB": 0.40,
                    "OIL-EVOO-1GAL": 0.025,
                    "VEG-TOMATO-ROMA": 0.05,
                }
            },
        }

    def _load_current_costs(self) -> None:
        """Load current ingredient costs (Phase 1: sample data)."""
        self._current_costs = {
            "CHK-BREAST-5LB": 22.50,    # Updated price from sample invoice
            "VEG-TOMATO-ROMA": 18.99,
            "OIL-EVOO-1GAL": 24.99,
            "DRY-FLOUR-AP-50": 19.50,
        }
