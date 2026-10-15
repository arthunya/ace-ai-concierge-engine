"""A.C.E. REST API (FastAPI).

Exposes the three layers plus the manager approval gate and the audit trail.
Nothing here can change a menu price or publish a schedule: the only
state-changing endpoint is /approvals, which records an explicit human
decision, and /approvals is what unlocks a cost write.

Run locally:
    uvicorn ace.api.endpoints:app --reload --port 8001
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ace import __version__, db
from ace.config import ACEConfig
from ace.ingestion import seed_data
from ace.ingestion.invoice_loader import InvoiceLoader
from ace.pricing.menu_engine import MenuEngine, engine_version
from ace.scheduling.labor_optimizer import LaborForecaster

app = FastAPI(
    title="A.C.E. — AI Concierge & Engine",
    version=__version__,
    description=(
        "Phase-1 proof of concept. All demo data is synthetic and labelled; "
        "no pilot deployment has taken place."
    ),
)

CONFIG = ACEConfig()
DEMO_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "demo"


def _conn():
    return db.connect()


class ProcessInvoiceRequest(BaseModel):
    filename: str = Field(..., description="File name inside data/demo/")
    restaurant_id: Optional[str] = None


class ApprovalRequest(BaseModel):
    subject_type: Literal["invoice_line_item", "price_recommendation", "labor_forecast"]
    subject_id: str
    decision: Literal["approved", "rejected"]
    decided_by: str
    note: Optional[str] = None
    # Only meaningful for an approved invoice_line_item: the confirmed cost
    # to write through to the SKU record.
    sku: Optional[str] = None
    confirmed_unit_price: Optional[float] = None


@app.get("/health")
def health():
    conn = _conn()
    counts = {
        t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
        for t in ("restaurants", "inventory_skus", "recipes", "invoices",
                  "invoice_line_items", "audit_log")
    }
    conn.close()
    return {"status": "ok", "version": __version__,
            "engine_version": engine_version(), "counts": counts}


@app.get("/config")
def read_config():
    """Thresholds in force, each traceable to a Working Paper section."""
    return {
        "sku_match_confidence_threshold": CONFIG.sku_match_confidence_threshold,
        "price_change_confirmation_threshold": CONFIG.price_change_confirmation_threshold,
        "food_cost_alert_threshold": CONFIG.food_cost_alert_threshold,
        "target_food_cost_pct": CONFIG.target_food_cost_pct,
        "scheduling_horizon_days": CONFIG.scheduling_horizon_days,
        "deployment_phase": CONFIG.deployment_phase,
        "autonomous_pricing_change_enabled": CONFIG.autonomous_pricing_change_enabled,
        "autonomous_scheduling_enabled": CONFIG.autonomous_scheduling_enabled,
        "provenance": {
            "sku_match_confidence_threshold": "Working Paper §3.2",
            "price_change_confirmation_threshold": "Working Paper §3.2, §5.2",
            "food_cost_alert_threshold": "Working Paper §3.3",
            "target_food_cost_pct": "engineering choice — not specified in the paper",
            "scheduling_horizon_days": "Working Paper §3.4",
        },
    }


@app.post("/demo/seed")
def seed():
    conn = _conn()
    rid = seed_data.load(conn)
    conn.close()
    return {"restaurant_id": rid, "synthetic": True,
            "note": "Demo data is illustrative only, not pilot data."}


@app.get("/demo/invoices")
def list_demo_invoices():
    return {"invoices": sorted(p.name for p in DEMO_DIR.glob("invoice_*.txt"))}


@app.post("/invoices/process")
def process_invoice(req: ProcessInvoiceRequest):
    path = (DEMO_DIR / req.filename).resolve()
    if not path.is_file() or DEMO_DIR.resolve() not in path.parents:
        raise HTTPException(404, f"demo invoice not found: {req.filename}")

    conn = _conn()
    rid = req.restaurant_id or seed_data.load(conn)
    result = InvoiceLoader(CONFIG, conn).process(path, rid, is_demo=True,
                                                 actor="api")
    conn.close()
    return result.to_dict()


@app.get("/pricing/recommendations")
def pricing(restaurant_id: Optional[str] = None):
    conn = _conn()
    rid = restaurant_id or seed_data.load(conn)
    out = MenuEngine(CONFIG, conn).recommendations(rid, actor="api")
    conn.close()
    return out


@app.get("/labor/forecast")
def labor(restaurant_id: Optional[str] = None, days_ahead: Optional[int] = None):
    conn = _conn()
    rid = restaurant_id or seed_data.load(conn)
    out = LaborForecaster(CONFIG, conn).recommendations(
        rid, days_ahead=days_ahead, actor="api")
    conn.close()
    return out


@app.post("/approvals")
def approve(req: ApprovalRequest):
    """Record a manager decision — the Human-in-the-Loop gate (§3.1)."""
    conn = _conn()
    approval_id = db.record_approval(
        conn, subject_type=req.subject_type, subject_id=req.subject_id,
        decision=req.decision, decided_by=req.decided_by, note=req.note)

    synced = None
    if (req.decision == "approved" and req.subject_type == "invoice_line_item"
            and req.sku and req.confirmed_unit_price is not None):
        InvoiceLoader(CONFIG, conn).apply_confirmed_price(
            req.sku, req.confirmed_unit_price, req.decided_by)
        synced = {"sku": req.sku, "unit_price": req.confirmed_unit_price}
    conn.close()
    return {"approval_id": approval_id, "decision": req.decision,
            "cost_synced": synced}


@app.get("/audit/export")
def audit_export(limit: int = 200):
    conn = _conn()
    rows = conn.execute(
        "SELECT log_id, ts, actor, action, payload FROM audit_log "
        "ORDER BY log_id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return {"entries": [dict(r) for r in rows]}
