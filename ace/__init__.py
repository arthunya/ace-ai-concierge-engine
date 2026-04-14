"""
A.C.E. — AI Concierge & Engine
An AI-Driven Financial Intelligence Framework for U.S. SME Restaurant Resilience

Author: Arthunya Kanoklertwongse
DOI: 10.13140/RG.2.2.33391.60326
License: MIT
"""

from .config import ACEConfig

__version__ = "0.1.0-alpha"
__author__ = "Arthunya Kanoklertwongse"
__doi__ = "10.13140/RG.2.2.33391.60326"


class ACEEngine:
    """
    A.C.E. primary interface — orchestrates all three layers:
      Layer 1: Automated Invoice Ingestion (AI-OCR Pipeline)
      Layer 2: Dynamic Menu Engineering Engine
      Layer 3: Predictive Labor Scheduling

    Usage:
        engine = ACEEngine()
        engine.initialize()
        result = engine.process_invoice("invoice.pdf")
    """

    def __init__(self, config: "ACEConfig" = None):
        from .ingestion.invoice_loader import InvoiceLoader
        from .pricing.menu_engine import MenuEngine
        from .scheduling.labor_optimizer import LaborOptimizer

        self.config = config or ACEConfig()
        self._invoice_loader = InvoiceLoader(self.config)
        self._menu_engine = MenuEngine(self.config)
        self._labor_optimizer = LaborOptimizer(self.config)
        self._initialized = False

    def initialize(self) -> None:
        """Load all models and connect to data sources."""
        self._invoice_loader.initialize()
        self._menu_engine.initialize()
        self._labor_optimizer.initialize()
        self._initialized = True

    def process_invoice(self, invoice_path: str) -> dict:
        """Layer 1: Process a supplier invoice PDF and sync to inventory."""
        if not self._initialized:
            self.initialize()
        return self._invoice_loader.process(invoice_path)

    def get_pricing_recommendations(self) -> dict:
        """Layer 2: Get menu pricing recommendations based on current costs."""
        if not self._initialized:
            self.initialize()
        return self._menu_engine.get_recommendations()

    def get_labor_recommendations(self, days_ahead: int = 7) -> dict:
        """Layer 3: Get staffing recommendations for the next N days."""
        if not self._initialized:
            self.initialize()
        return self._labor_optimizer.recommend(days_ahead=days_ahead)


__all__ = ["ACEEngine", "ACEConfig"]
