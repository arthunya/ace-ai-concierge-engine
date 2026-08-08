"""A.C.E. — AI Concierge & Engine.

An AI-Driven Financial Intelligence Framework for U.S. SME Restaurant
Resilience. Phase-1 proof of concept.

Reference:
    Kanoklertwongse, A. (2026). A.C.E. — AI Concierge & Engine.
    ResearchGate Working Paper. DOI: 10.13140/RG.2.2.33391.60326

See README.md for the Honest Scope Statement describing what in this
repository is built and verified versus what remains future work.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from ace.config import ACEConfig

__version__ = "0.2.0"
__author__ = "Arthunya Kanoklertwongse"
__doi__ = "10.13140/RG.2.2.33391.60326"


class ACEEngine:
    """Orchestrates the three layers over a shared database connection.

    Usage:
        from ace import ACEEngine
        engine = ACEEngine()
        rid = engine.load_demo_data()
        engine.process_invoice("data/demo/invoice_usfoods_2026-03-14.txt", rid,
                               is_demo=True)
        engine.pricing_recommendations(rid)
        engine.labor_recommendations(rid)
    """

    def __init__(self, config: Optional[ACEConfig] = None, db_path=None):
        from ace import db
        from ace.ingestion.invoice_loader import InvoiceLoader
        from ace.pricing.menu_engine import MenuEngine
        from ace.scheduling.labor_optimizer import LaborForecaster

        self.config = config or ACEConfig()
        self.conn = db.connect(db_path) if db_path else db.connect()
        self.invoices = InvoiceLoader(self.config, self.conn)
        self.menu = MenuEngine(self.config, self.conn)
        self.labor = LaborForecaster(self.config, self.conn)

    def load_demo_data(self) -> str:
        """Load the synthetic demo restaurant. Returns its restaurant_id."""
        from ace.ingestion import seed_data
        return seed_data.load(self.conn)

    def process_invoice(self, path: str | Path, restaurant_id: str, **kw):
        return self.invoices.process(path, restaurant_id, **kw)

    def pricing_recommendations(self, restaurant_id: str, **kw) -> Dict:
        return self.menu.recommendations(restaurant_id, **kw)

    def labor_recommendations(self, restaurant_id: str, **kw) -> Dict:
        return self.labor.recommendations(restaurant_id, **kw)

    def close(self) -> None:
        self.conn.close()


__all__ = ["ACEEngine", "ACEConfig", "__version__", "__doi__"]
