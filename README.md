# A.C.E. — AI Concierge & Engine

**An AI-Driven Financial Intelligence Framework for U.S. SME Restaurant Resilience**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![ResearchGate DOI](https://img.shields.io/badge/DOI-10.13140%2FRG.2.2.33391.60326-blue)](https://doi.org/10.13140/RG.2.2.33391.60326)
[![Status: Active Development](https://img.shields.io/badge/Status-Active%20Development-green.svg)]()

---

## Overview

A.C.E. (AI Concierge & Engine) is an open-source AI framework designed to eliminate the **"Financial Blindness"** crisis afflicting U.S. small and medium-sized enterprise (SME) restaurant operators — the dangerous lag between cost data arrival and pricing decisions caused by manual invoice processing and fragmented data systems.

The U.S. restaurant industry generates **$1.1 trillion** in annual sales and employs **8.6 million Americans**. Yet the SME segment operates at a severe informational disadvantage relative to corporate chains that deploy proprietary AI analytics. A.C.E. democratizes access to enterprise-grade financial intelligence by integrating directly with existing POS infrastructure — no hardware replacement required.

This repository contains the **proof-of-concept implementation** of the A.C.E. Intelligent Neural Network architecture described in:

> Kanoklertwongse, A. (2026). *A.C.E. — AI Concierge & Engine: An AI-Driven Financial Intelligence Framework for U.S. SME Restaurant Resilience*. ResearchGate Working Paper. DOI: [10.13140/RG.2.2.33391.60326](https://doi.org/10.13140/RG.2.2.33391.60326)

**Companion repository (supply chain security):**
> V.E.T. — Vendor Entity Threat Detection: [github.com/arthunya/vet-vendor-threat-detection](https://github.com/arthunya/vet-vendor-threat-detection) | DOI: [10.13140/RG.2.2.33961.76641](https://doi.org/10.13140/RG.2.2.33961.76641)

---

## The Problem: Financial Blindness

Current SME restaurant operations rely on a **Hub-and-Spoke** data model where the POS system is a passive data repository:

```
Supplier Invoices (PDF) ──► Manual Data Entry ──► POS / Spreadsheet
                                   ↑
                          15+ hours/week of
                          administrative burden
```

Three structural failures drive SME market exit:

1. **Data Silos** — Sales data in POS JSON, cost data in PDF invoices, inventory in spreadsheets — never combined in real time
2. **Data Latency** — Batch-sync integrations mean financial data is historically accurate but strategically obsolete
3. **Pricing Lag** — During 2022–2024 inflation, SMEs adjusted menu prices weeks after cost increases — by which point margin erosion was unrecoverable

---

## A.C.E. Architecture: The Intelligent Neural Network

A.C.E. transforms the passive Hub-and-Spoke model into a proactive intelligence layer:

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Automated Invoice Ingestion (AI-OCR Pipeline)     │
│  PDF invoices → OCR extraction → SKU mapping → POS sync     │
│  Target: 100% elimination of manual invoice data entry      │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Layer 2: Dynamic Menu Engineering Engine                   │
│  Real-time food cost % monitoring → price recommendations   │
│  Threshold: flag items when food cost % exceeds 32%         │
│  Human-in-the-Loop: manager confirmation required           │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Layer 3: Predictive Labor Scheduling                       │
│  Historical POS data + events + weather → demand forecast   │
│  Output: 7-day staffing recommendations                     │
│  Always advisory — manager approval required                │
└─────────────────────────────────────────────────────────────┘
```

**Design principles:**
- **Non-invasive:** Connects via standard REST APIs — no hardware replacement, no downtime
- **Human-in-the-Loop by default:** All recommendations require manager confirmation
- **Progressive automation:** Advisory mode first, automated execution only after accuracy validation

---

## Repository Structure

```
ace-ai-concierge-engine/
├── README.md                      # This file
├── LICENSE                        # MIT License
├── requirements.txt               # Python dependencies
├── demo.py                        # Quick demo — run this first
│
├── ace/                           # Core package
│   ├── __init__.py
│   ├── config.py                  # Configuration and thresholds
│   │
│   ├── ingestion/                 # Layer 1: Invoice processing
│   │   ├── __init__.py
│   │   ├── invoice_loader.py      # PDF invoice ingestion + OCR
│   │   └── pos_connector.py       # POS API integration (Toast/Clover)
│   │
│   ├── pricing/                   # Layer 2: Menu engineering
│   │   ├── __init__.py
│   │   ├── menu_engine.py         # Dynamic pricing recommendations
│   │   └── cost_tracker.py        # Real-time food cost % monitoring
│   │
│   ├── scheduling/                # Layer 3: Labor optimization
│   │   ├── __init__.py
│   │   ├── demand_forecaster.py   # Time-series demand prediction
│   │   └── labor_optimizer.py     # Staffing recommendation engine
│   │
│   └── api/                       # REST API interface
│       ├── __init__.py
│       └── endpoints.py           # FastAPI endpoints
│
├── notebooks/                     # Jupyter exploration notebooks
│   ├── 01_invoice_processing_demo.ipynb
│   ├── 02_menu_engineering_demo.ipynb
│   └── 03_labor_scheduling_demo.ipynb
│
├── tests/                         # Unit tests
│   ├── test_invoice_loader.py
│   ├── test_menu_engine.py
│   └── test_labor_optimizer.py
│
└── docs/                          # Documentation
    ├── architecture.md
    └── pos_integration_guide.md
```

---

## Quick Start

### Installation

```bash
git clone https://github.com/arthunya/ace-ai-concierge-engine.git
cd ace-ai-concierge-engine
pip install -r requirements.txt
```

### Basic Usage

```python
from ace import ACEEngine

# Initialize the engine
engine = ACEEngine()
engine.initialize()

# Process a supplier invoice
invoice_result = engine.process_invoice("path/to/invoice.pdf")
print(invoice_result)
# {
#   "supplier": "US Foods",
#   "items_extracted": 24,
#   "items_mapped": 23,
#   "items_requiring_review": 1,
#   "total_cost": 1847.50,
#   "cost_changes_flagged": [
#     {"sku": "CHICKEN-BREAST-5LB", "old_price": 18.99, "new_price": 22.50, "change_pct": 18.5}
#   ]
# }

# Get menu pricing recommendations
pricing = engine.get_pricing_recommendations()
print(pricing)
# {
#   "items_above_threshold": 3,
#   "recommendations": [
#     {"item": "Grilled Chicken Sandwich", "current_price": 14.99,
#      "suggested_price": 16.99, "current_food_cost_pct": 36.2}
#   ]
# }

# Get labor scheduling recommendations
schedule = engine.get_labor_recommendations(days_ahead=7)
```

### Run Demo

```bash
python demo.py
```

---

## POS Integration

A.C.E. connects to existing POS systems via standard APIs:

| POS System | Integration Method | Status |
|------------|-------------------|--------|
| Toast | REST API + Webhooks | Phase 1 target |
| Clover | REST API | Phase 1 target |
| Square | REST API | Phase 2 |
| Generic | CSV/JSON export | Phase 1 (fallback) |

*Phase 1 proof-of-concept uses CSV/JSON export for POS integration. Live API integration is the Phase 2 milestone.*

---

## Ethical Governance

A.C.E. is designed with **Human-in-the-Loop** validation at every decision point with financial or operational consequences:

| Decision Type | Automation Level | Human Override |
|--------------|-----------------|----------------|
| Invoice cost recording (change ≤5%) | Automatic | Always available |
| Invoice cost recording (change >5%) | Requires confirmation | Required |
| Menu price recommendations | Advisory only | Always required |
| Labor schedule recommendations | Advisory only | Always required |
| Tax-relevant financial data | Never automatic | Always required |

This design directly addresses the vicarious liability risk identified in the working paper (Castro & Sainati, 2024).

---

## Research Paper

Kanoklertwongse, A. (2026). A.C.E. — AI Concierge & Engine: An AI-Driven 
Financial Intelligence Framework for U.S. SME Restaurant Resilience. 
ResearchGate Working Paper.

| Platform | Link |
|---|---|
| **ResearchGate** | [DOI: 10.13140/RG.2.2.33391.60326](https://doi.org/10.13140/rg.2.2.33391.60326) |
| **SSRN (Elsevier)** | [Abstract ID: 6774983](https://ssrn.com/abstract=6774983) (posted May 22, 2026)|

License: CC BY 4.0 · Published: April 2026

---

## Author

**Arthunya Kanoklertwongse**
M.S. Computer Science (AI Concentration) — Westcliff University, San Francisco
MSc Financial Technology (Merit, academic merit scholarship) — University of the West of England, Bristol
14 years: Financial analysis · Enterprise operations · KYC/AML compliance

**Background:** A.C.E. emerges from 14 years of practitioner experience in financial analysis and internal audit — where the manual data integration problems this system addresses were encountered firsthand. The framework translates financial governance expertise into AI system design, applying audit-grade precision to automated financial intelligence.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
