"""A.C.E. configuration.

Every threshold below is traceable to a specific section of the working paper.
Where a value is an engineering choice NOT specified by the paper, it is
labelled as such rather than presented as a sourced parameter.

Reference:
    Kanoklertwongse, A. (2026). A.C.E. — AI Concierge & Engine: An AI-Driven
    Financial Intelligence Framework for U.S. SME Restaurant Resilience.
    ResearchGate Working Paper. DOI: 10.13140/RG.2.2.33391.60326
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class ACEConfig:
    # ── Layer 1: Automated Invoice Ingestion (Working Paper §3.2) ──────────
    # "Items with <80% match confidence routed to manual review queue" — §3.2
    sku_match_confidence_threshold: float = 0.80

    # "any cost change >5% requires manager confirmation before sync" — §3.2,
    # restated as the AI-hallucination mitigation in §5.2.
    price_change_confirmation_threshold: float = 0.05

    # ── Layer 2: Dynamic Menu Engineering (Working Paper §3.3) ─────────────
    # "exceeded a configurable threshold (defaulting to 32%)" — §3.3
    food_cost_alert_threshold: float = 0.32

    # ENGINEERING CHOICE — not specified in the working paper.
    # §3.3 says a recommendation "maintains target margin" but does not give a
    # numeric target. Repricing exactly to the 32% alert threshold would leave
    # an item re-flagged on any further cost rise, so the recommendation targets
    # a band below it. Exposed here so an operator can set their own target.
    target_food_cost_pct: float = 0.28

    # ── Layer 3: Predictive Labor Scheduling (Working Paper §3.4) ──────────
    # "staffing recommendations 7 days in advance" — §3.4
    scheduling_horizon_days: int = 7

    # "subject to configurable constraints including minimum staffing
    # levels" — §3.4. The specific integers are operator-set, not paper-set.
    min_front_of_house_staff: int = 2
    min_back_of_house_staff: int = 1

    # ── Human-in-the-Loop governance (Working Paper §3.1, §5.2) ───────────
    # "All AI-generated recommendations require manager confirmation before
    # executing financial or operational changes" — §3.1.
    # Phase 3 may enable bounded autonomous pricing (§3.3); it is off by
    # default and Phase 1 must never enable it.
    autonomous_pricing_change_enabled: bool = False
    autonomous_scheduling_enabled: bool = False

    # ── Deployment phase (Working Paper §4.1) ─────────────────────────────
    # 1 = Unfreezing, 2 = Moving (advisory), 3 = Refreezing (bounded autonomy).
    # This repository implements Phase 1/2 advisory behaviour only.
    deployment_phase: int = 1

    # POS systems named in the paper (§ Abstract, §3.1). Phase-1 integration is
    # file-based; live REST/webhook integration is future work.
    supported_pos_systems: List[str] = field(
        default_factory=lambda: ["toast", "clover", "csv_export"]
    )

    api_host: str = "127.0.0.1"
    api_port: int = 8001

    def __post_init__(self) -> None:
        if not 0 < self.target_food_cost_pct <= self.food_cost_alert_threshold:
            raise ValueError(
                "target_food_cost_pct must be >0 and <= food_cost_alert_threshold; "
                f"got target={self.target_food_cost_pct} alert={self.food_cost_alert_threshold}"
            )
        if self.deployment_phase < 3 and (
            self.autonomous_pricing_change_enabled or self.autonomous_scheduling_enabled
        ):
            raise ValueError(
                "Autonomous execution is a Phase-3 capability (Working Paper §3.3, §4.1). "
                f"Cannot enable it at deployment_phase={self.deployment_phase}."
            )
