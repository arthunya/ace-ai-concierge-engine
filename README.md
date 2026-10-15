# A.C.E. — AI Concierge & Engine

**An AI-Driven Financial Intelligence Framework for U.S. SME Restaurant Resilience**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![ResearchGate DOI](https://img.shields.io/badge/DOI-10.13140%2FRG.2.2.33391.60326-blue)](https://doi.org/10.13140/RG.2.2.33391.60326)
[![Status: Active Development](https://img.shields.io/badge/Status-Active%20Development-green.svg)](#project-status)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-Dashboard-orange.svg)](https://arthunya.github.io/ace-ai-concierge-engine/dashboard/ACE_Dashboard.html)

Repository created April 2026 · actively maintained.

---

## Overview

A.C.E. (AI Concierge & Engine) is an open-source framework addressing the
**"Financial Blindness"** problem in U.S. small and medium-sized enterprise
(SME) restaurants: the lag between cost data arriving and pricing decisions
being made, caused by manual invoice processing and fragmented data systems.

In the U.S. Accommodation and Food Services sector, **572,464 small employer
firms** — 99.6% of all employer firms in the sector — employ **more than
8.6 million workers** ([U.S. Small Business Administration Office of Advocacy,
2025 Small Business Profile: United States](https://advocacy.sba.gov)).
The working paper estimates that owners and managers spend **15 or more hours
per week** on manual data entry (§1.2). Figures are as cited in the working
paper (§1.1, §1.2); none was independently re-verified in this repository.

This repository contains the runnable **Phase-1 implementation** of the
architecture described in:

> Kanoklertwongse, A. (2026). *A.C.E. — AI Concierge & Engine: An AI-Driven
> Financial Intelligence Framework for U.S. SME Restaurant Resilience*.
> ResearchGate Working Paper. DOI: [10.13140/RG.2.2.33391.60326](https://doi.org/10.13140/RG.2.2.33391.60326)

**Companion repository (supply chain security):**
> V.E.T. — Vendor Entity Threat Detection: [github.com/arthunya/vet-vendor-threat-detection](https://github.com/arthunya/vet-vendor-threat-detection) | DOI: [10.13140/RG.2.2.33961.76641](https://doi.org/10.13140/RG.2.2.33961.76641)

---

## Project Status

| Component | Status |
|---|---|
| Invoice text parsing, fuzzy SKU matching, three routing gates (§3.2) | **Built & verified** (this repo) |
| Recipe cost model, food cost %, price recommendation with rationale (§3.3) | **Built & verified** (this repo) |
| Seasonal-naive 7-day labor baseline (§3.4, partial) | **Built & verified** (this repo) |
| Manager approval gate, append-only audit log (§3.1) | **Built & verified** (this repo) |
| REST API, SQLite/PostgreSQL schema, 27-test suite, standalone dashboard | **Built & verified** (this repo) |
| AI-OCR of scanned PDF invoices (§3.2) | **Not built** — no model trained |
| Live Toast / Clover API integration (§3.1) | **Not built** — Phase 1 is file-based |
| Trained time-series forecaster with event + weather signals (§3.4) | **Not built** — future work |
| 10-location Early Adopter pilot (§4.1, §7) | **Not started** — no pilot data exists |

## Honest Scope Statement

**No pilot deployment has taken place.** The working paper describes the
10-location Early Adopter pilot as future work (§4.1, §7). This repository
therefore contains **no pilot metrics, no measured time savings, and no OCR
accuracy figure** — any such number would be fabricated. The paper's targets
("near-elimination of manual invoice data entry", "15+ hours saved per week")
are stated in the paper as *targets*, and are not results claimed here.

What this repository is and is not:

- **Is:** a runnable end-to-end pipeline — invoice parsing, SKU matching, the
  three §3.2 routing gates, recipe costing, price recommendation, the manager
  approval gate, a labor baseline, a REST API, an append-only audit log, and a
  self-contained dashboard.
- **Is:** exercised on **3 synthetic demo invoices (14 line items)** against a
  **12-item demo menu** and **84 days of generated cover history**. Every one
  of those numbers is produced by code in this repository, and all of that data
  is clearly labelled synthetic — the demo restaurant is named
  `Bella Vista Trattoria [DEMO - NOT A REAL BUSINESS]` and its database row
  carries `is_demo = 1`.
- **Is not:** an OCR system. §3.2 specifies "a fine-tuned transformer model for
  restaurant invoice format recognition." No such model is trained or invoked.
  Phase 1 parses a **text layer**, and each invoice records how its text was
  obtained in `extraction_method` so a fixture can never be mistaken for a live
  OCR result. Character- and field-level accuracy are measurable only against a
  labelled corpus of real supplier invoices, which does not exist in this project.
- **Is not:** the trained forecaster of §3.4. Layer 3 is a **seasonal-naive
  baseline** — trailing mean × day-of-week index. Nothing is fitted, no external
  signal is consumed, and **no accuracy is claimed** because no backtest has been
  run. A seasonal-naive model is the standard reference any trained forecaster
  must beat, so it also serves as the benchmark for that future work.

---

## Architecture

### Target architecture (working paper §3.2–§3.4)

```
Layer 1  Automated Invoice Ingestion (AI-OCR pipeline)
         PDF invoices -> OCR + entity extraction -> SKU mapping -> POS sync
              |
Layer 2  Dynamic Menu Engineering Engine
         Recipe cost model -> food cost % -> price recommendation
              |
Layer 3  Predictive Labor Scheduling
         POS history + events + weather -> 7-day staffing recommendation
```

### What is actually built and verified right now (Phase 1, this repo)

```
  invoice text file
        |
   parse_invoice_text()          regex line-item extraction + header fields
        |
   match_sku()                   rapidfuzz token-set, case-folded;
        |                        exact supplier code short-circuits at 1.0
   route()                       gate 1: confidence  < 80%  -> manual_review
        |                        gate 2: |price change| > 5% -> manager_confirmation
        |                        else                        -> auto_sync (cost written)
        |
   [manager approval]            record_approval() -> apply_confirmed_price()
        |                        nothing reaches pricing without this
        |
   MenuEngine.analyze()          plate cost -> food cost % -> >32% flagged
        |                        suggested price = plate cost / target %
        |                        every recommendation carries its rationale
        |
   LaborForecaster.forecast()    trailing mean x day-of-week index -> FOH/BOH
        |
   FastAPI + audit_log (append-only, enforced by DB trigger)
```

Production DDL: [`schema/postgres_schema.sql`](schema/postgres_schema.sql). The
development backend is SQLite with an identical table layout
([`ace/db.py`](ace/db.py)); the audit log is append-only at the database layer
(triggers in development, revoked grants in production).

---

## Thresholds and their provenance

Every threshold is traceable. Where a value is an engineering choice rather
than a paper parameter, it says so — in the code, in `/config`, and here.

| Parameter | Value | Source |
|---|---|---|
| SKU match confidence floor | 80% | White Paper §3.2 |
| Price variance confirmation gate | 5% | White Paper §3.2, §5.2 |
| Food cost alert threshold | 32% | White Paper §3.3 ("configurable, defaulting to 32%") |
| Repricing target food cost | 28% | **Engineering choice — not in the paper.** §3.3 says a recommendation "maintains target margin" without giving a number. Repricing exactly to 32% would re-flag the item on any further cost rise, so the target sits below the alert line. Configurable. |
| Forecast horizon | 7 days | White Paper §3.4 |
| Covers per FOH / BOH staff-hour | 7 / 15 | **Engineering assumption — not in the paper, not measured.** Constructor arguments, since service styles differ enormously. |
| Minimum staffing floor | 2 FOH / 1 BOH | Operator-set. §3.4 requires configurable minimums but sets no number. |

The variance gate is **symmetric**: a cost *decrease* over 5% also requires
confirmation. A supplier credit or a keying error is as material to margin as
an increase, and §5.2 frames the gate as an error-containment control.

---

## Quick Start

```bash
git clone https://github.com/arthunya/ace-ai-concierge-engine.git
cd ace-ai-concierge-engine
pip install -r requirements.txt
python demo.py
```

`demo.py` walks the full Human-in-the-Loop path and prints only values computed
during that run. Abridged, from an actual run:

```
  invoice_usfoods_2026-03-14.txt
    supplier US Foods | invoice DEMO-4471902 | 2026-03-14
    5 line items parsed, $425.42 extracted
    auto-synced 3 | awaiting confirmation 1 | manual review 1
      [CONFIRM] CHICKEN BREAST BNLS SKNLS 5LB
                Unit price increase of 18.5% ($18.99 -> $22.50) exceeds the 5%
                variance gate (White Paper §3.2, §5.2).
      [REVIEW ] SAFFRON THREADS SPANISH GRADE A 1OZ
                SKU match confidence 41.4% is below the 80% threshold (§3.2).
```

After the manager confirms that held cost, Layer 2 recomputes:

```
  Chicken Parmigiana  ($21.99 -> $28.36, +6.37)
    Chicken Breast Boneless Skinless 5lb at $22.50/unit contributes $5.62 of
    the $7.94 plate cost. Total plate cost $7.94 against a $21.99 menu price
    puts food cost at 36.1%, above the 32% threshold. Repricing to $28.36
    (+6.37) restores the 28% target ($7.94 / 0.28). Advisory only - manager
    approval required before any price change.
```

### Other entry points

```bash
python -m pytest tests/ -q              # 27 tests
python scripts/build_dashboard.py       # rebuild dashboard/ACE_Dashboard.html
uvicorn ace.api.endpoints:app --port 8001
```

### Dashboard

**[Open the live interactive dashboard →](https://arthunya.github.io/ace-ai-concierge-engine/dashboard/ACE_Dashboard.html)** (hosted via GitHub Pages;
GitHub does not render HTML files inline, so clicking the file in the repository
shows its source code instead).

Or download [`dashboard/ACE_Dashboard.html`](dashboard/ACE_Dashboard.html) and open it in any
browser — a single self-contained file, no server and no network access
required. Select a demo invoice to see extracted line items with the routing
decision and its stated reason, toggle Layer 2 between before and after manager
confirmation, and read the 7-day labor baseline with the reasoning behind each
day. It is regenerated by `scripts/build_dashboard.py`, which runs the engine
and embeds the real computed output — the page contains no hand-written numbers.

---

## Ethical Governance

Human-in-the-Loop validation at every decision point with financial or
operational consequences (White Paper §3.1, §5.2):

| Decision | Automation | Human override |
|---|---|---|
| Cost recording, change ≤5%, match ≥80% | Automatic | Always available |
| Cost recording, change >5% | Requires confirmation | Required |
| Cost recording, match <80% | Routed to manual review | Required |
| Menu price recommendations | Advisory only | Always required |
| Labor schedule recommendations | Advisory only | Always required |

This is enforced in code, not just documented: `ACEConfig` raises if autonomous
execution is enabled below deployment Phase 3 (§3.3, §4.1), and a held cost
cannot reach the pricing engine without a recorded approval. The labor model
consumes aggregate daily cover counts only — it holds no worker-level or
demographic data, addressing the scheduling-bias risk in §5.2.

---

## Repository Structure

This tree reflects the files that actually exist, not an aspirational layout.

```
ace-ai-concierge-engine/
├── README.md
├── LICENSE                              MIT
├── requirements.txt
├── demo.py                              full walkthrough — run this first
├── ace/
│   ├── __init__.py                      ACEEngine orchestrator
│   ├── config.py                        thresholds, each traced to a §
│   ├── db.py                            SQLite dev layer + append-only audit
│   ├── ingestion/
│   │   ├── invoice_loader.py            Layer 1: parse, match, route
│   │   └── seed_data.py                 synthetic demo dataset
│   ├── pricing/menu_engine.py           Layer 2: food cost % + recommendation
│   ├── scheduling/labor_optimizer.py    Layer 3: seasonal-naive baseline
│   └── api/endpoints.py                 FastAPI surface
├── schema/postgres_schema.sql           production DDL
├── data/demo/                           3 synthetic invoices + cover history
├── dashboard/
│   ├── ace_dashboard_template.html
│   └── ACE_Dashboard.html               assembled, self-contained
├── scripts/
│   ├── build_dashboard.py
│   └── generate_demo_pos_history.py
└── tests/test_ace.py                    27 tests, one per claim
```

---

## Research Paper

| Platform | Link |
|---|---|
| **ResearchGate** | [DOI: 10.13140/RG.2.2.33391.60326](https://doi.org/10.13140/rg.2.2.33391.60326) |
| **SSRN (Elsevier)** | [Abstract ID: 6774983](https://ssrn.com/abstract=6774983) (posted May 22, 2026) |

License: CC BY 4.0 · Published: April 2026

---

## Author

**Arthunya Kanoklertwongse**
M.S. Computer Science (AI Concentration) — Westcliff University, San Francisco
MSc Financial Technology (Merit; partial merit scholarship) — University of the West of England, Bristol
14 years: Financial analysis · Internal audit · Cross-border counterparty coordination

**Background:** A.C.E. emerges from 14 years of practitioner experience in
financial analysis, internal audit, and cross-border counterparty coordination —
where the manual data integration problems this system addresses were
encountered firsthand. The framework translates financial governance expertise
into AI system design, applying audit-grade precision to automated financial
intelligence.

---

## License

MIT License — see [LICENSE](LICENSE).
