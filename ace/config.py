"""
A.C.E. Configuration Management
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class ACEConfig:
    """
    Central configuration for the A.C.E. pipeline.

    Thresholds are calibrated for the U.S. SME restaurant context
    based on industry benchmarks from the National Restaurant Association (2025).
    """

    # ── Layer 1: Invoice Ingestion ────────────────────────────────────
    # OCR confidence threshold — items below this go to manual review queue
    ocr_confidence_threshold: float = 0.80

    # Price change threshold — changes above this require manager confirmation
    # Satisfies Human-in-the-Loop requirement for financial decisions
    price_change_confirmation_threshold: float = 0.05  # 5%

    # ── Layer 2: Menu Engineering ─────────────────────────────────────
    # Food cost % threshold — items above this trigger pricing recommendation
    # 32% is the standard industry benchmark for full-service restaurants
    food_cost_alert_threshold: float = 0.32

    # Minimum price recommendation confidence before surfacing to manager
    pricing_recommendation_confidence: float = 0.75

    # Supported POS systems for API integration
    supported_pos_systems: List[str] = field(default_factory=lambda: [
        "toast", "clover", "square", "csv_export"
    ])

    # ── Layer 3: Labor Scheduling ─────────────────────────────────────
    # Days ahead to generate staffing recommendations
    scheduling_horizon_days: int = 7

    # Minimum staffing level — never recommend below this regardless of forecast
    min_front_of_house_staff: int = 2
    min_back_of_house_staff: int = 1

    # External signals to incorporate in demand forecast
    use_weather_data: bool = True
    use_local_events: bool = True

    # ── Human-in-the-Loop Controls ────────────────────────────────────
    # All decisions above these thresholds require explicit manager confirmation
    # This is non-negotiable — addresses vicarious liability risk
    autonomous_invoice_sync_max_change: float = 0.05
    autonomous_pricing_change_enabled: bool = False  # Phase 3 only
    autonomous_scheduling_enabled: bool = False       # Phase 3 only

    # ── API Configuration ─────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8001

    # ── Phase tracking ────────────────────────────────────────────────
    # Phase 1 (current): advisory mode, CSV/JSON POS integration
    # Phase 2: live POS API integration, accuracy validation
    # Phase 3: selective automation within pre-approved parameters
    deployment_phase: int = 1
