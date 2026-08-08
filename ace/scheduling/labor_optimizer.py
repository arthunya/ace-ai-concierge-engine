"""A.C.E. Layer 3 — Predictive Labor Scheduling (White Paper §3.4).

WHAT IS ACTUALLY IMPLEMENTED (Phase-1 baseline)
    A seasonal-naive forecast: for each target date, the model multiplies the
    trailing mean daily covers by a day-of-week index computed from the same
    trailing window.

        forecast(d) = trailing_mean * (dow_mean(weekday(d)) / trailing_mean)
                    = dow_mean(weekday(d))    over the trailing window

    Written in the first form because the two factors are what the operator
    actually reads: "your recent average is N covers, Fridays run X% above
    that." It is arithmetic over observed history — nothing is trained, no
    parameters are fitted, and no accuracy claim is made.

WHAT IS NOT IMPLEMENTED
    White Paper §3.4 specifies "a time-series forecasting model trained on
    the restaurant's historical POS transaction data, incorporating external
    signals including local event calendars, weather forecasts, and seasonal
    patterns." No model is trained here and no external signal is consumed —
    there is no event or weather feed in this repository. Those remain future
    work, and this module must not be described as satisfying §3.4 in full.

    A seasonal-naive baseline is the honest Phase-1 choice: it is the
    standard reference point any trained forecaster must beat, so it also
    doubles as the benchmark for that future work.

GOVERNANCE
    Output is always advisory. §3.4: "the scheduling output is always
    presented as a recommendation requiring manager approval — not an
    autonomous decision." This addresses the algorithmic-management and
    scheduling-bias risk in §5.2; the model consumes only aggregate cover
    counts and holds no worker-level or demographic data.
"""
from __future__ import annotations

import csv
import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from ace import db

logger = logging.getLogger(__name__)

METHOD_ID = "seasonal_naive_dow_trailing_v1"

DEFAULT_HISTORY = (
    Path(__file__).resolve().parent.parent.parent / "data" / "demo" / "pos_covers_history.csv"
)

# ENGINEERING ASSUMPTIONS — not from the working paper, not measured.
# Covers one staff member can handle per hour of service, used to convert a
# cover forecast into headcount. Real sites differ enormously by service
# style, so these are constructor arguments rather than constants: a counter
# service operation and a white-tablecloth room do not share a ratio.
# They exist to make the demo concrete, not to assert an industry standard.
DEFAULT_COVERS_PER_FOH_HOUR = 7.0
DEFAULT_COVERS_PER_BOH_HOUR = 15.0
DEFAULT_SERVICE_HOURS = 6.0


@dataclass
class DayForecast:
    forecast_date: str
    day_of_week: str
    forecast_covers: int
    trailing_mean: float
    dow_index: float
    recommended_foh: int
    recommended_boh: int
    rationale: str
    floor_applied: bool = False

    def to_dict(self) -> Dict:
        return {
            "date": self.forecast_date,
            "day_of_week": self.day_of_week,
            "forecast_covers": self.forecast_covers,
            "trailing_mean_covers": round(self.trailing_mean, 1),
            "dow_index": round(self.dow_index, 3),
            "staffing": {
                "front_of_house": self.recommended_foh,
                "back_of_house": self.recommended_boh,
                "total": self.recommended_foh + self.recommended_boh,
            },
            "minimum_staffing_floor_applied": self.floor_applied,
            "rationale": self.rationale,
            "status": "Advisory - manager approval required (White Paper §3.4)",
        }


@dataclass
class CoverRecord:
    day: date
    covers: int


def load_history(path: Path | str = DEFAULT_HISTORY) -> List[CoverRecord]:
    with Path(path).open(encoding="utf-8") as f:
        return [
            CoverRecord(day=date.fromisoformat(r["date"]), covers=int(r["covers"]))
            for r in csv.DictReader(f)
        ]


class LaborForecaster:
    """Layer 3 seasonal-naive baseline."""

    def __init__(self, config, conn=None, *,
                 covers_per_foh: float = DEFAULT_COVERS_PER_FOH_HOUR,
                 covers_per_boh: float = DEFAULT_COVERS_PER_BOH_HOUR,
                 service_hours: float = DEFAULT_SERVICE_HOURS):
        self.config = config
        self.conn = conn or db.connect()
        self.covers_per_foh = covers_per_foh
        self.covers_per_boh = covers_per_boh
        self.service_hours = service_hours

    def forecast(self, history: List[CoverRecord], *, days_ahead: Optional[int] = None,
                 trailing_weeks: int = 8) -> List[DayForecast]:
        """Produce a staffing recommendation per day for the coming horizon."""
        days_ahead = days_ahead or self.config.scheduling_horizon_days
        if not history:
            raise ValueError("cannot forecast from empty history")

        history = sorted(history, key=lambda r: r.day)
        window = history[-(trailing_weeks * 7):]
        if len(window) < 7:
            raise ValueError(
                f"need at least 7 days of history to derive a day-of-week "
                f"index; got {len(window)}"
            )

        trailing_mean = statistics.fmean(r.covers for r in window)
        by_dow: Dict[str, List[int]] = {}
        for r in window:
            by_dow.setdefault(r.day.strftime("%A"), []).append(r.covers)

        last_day = history[-1].day
        out: List[DayForecast] = []
        for offset in range(1, days_ahead + 1):
            target = last_day + timedelta(days=offset)
            dow = target.strftime("%A")
            samples = by_dow.get(dow)
            if not samples:
                # No same-weekday observation in the window: fall back to the
                # overall mean rather than inventing a seasonal factor.
                dow_mean, dow_index = trailing_mean, 1.0
                basis = (f"no {dow} observed in the trailing window, so the "
                         f"overall mean was used unadjusted")
            else:
                dow_mean = statistics.fmean(samples)
                dow_index = dow_mean / trailing_mean if trailing_mean else 1.0
                basis = (f"{len(samples)} {dow}s in the trailing "
                         f"{len(window)}-day window averaged {dow_mean:.0f} covers, "
                         f"{(dow_index - 1) * 100:+.0f}% versus the "
                         f"{trailing_mean:.0f}-cover overall average")

            covers = max(0, round(dow_mean))
            foh_raw = math.ceil(covers / self.service_hours / self.covers_per_foh)
            boh_raw = math.ceil(covers / self.service_hours / self.covers_per_boh)
            foh = max(foh_raw, self.config.min_front_of_house_staff)
            boh = max(boh_raw, self.config.min_back_of_house_staff)
            floored = (foh > foh_raw) or (boh > boh_raw)

            rationale = (
                f"Forecast {covers} covers: {basis}. Staffing from a "
                f"{self.service_hours:.0f}-hour service window at "
                f"{self.covers_per_foh:.0f} covers/FOH and "
                f"{self.covers_per_boh:.0f} covers/BOH per hour gives "
                f"{foh_raw} FOH / {boh_raw} BOH"
            )
            if floored:
                rationale += (
                    f", raised to {foh} FOH / {boh} BOH by the configured "
                    f"minimum staffing floor"
                )
            rationale += (
                ". Baseline is day-of-week averaging only - no event, weather, "
                "or holiday signal is used (see module docstring)."
            )

            out.append(DayForecast(
                forecast_date=target.isoformat(), day_of_week=dow,
                forecast_covers=covers, trailing_mean=trailing_mean,
                dow_index=dow_index, recommended_foh=foh, recommended_boh=boh,
                rationale=rationale, floor_applied=floored,
            ))
        return out

    def recommendations(self, restaurant_id: str, *,
                        history: Optional[List[CoverRecord]] = None,
                        days_ahead: Optional[int] = None,
                        persist: bool = True, actor: str = "system") -> Dict:
        history = history if history is not None else load_history()
        forecasts = self.forecast(history, days_ahead=days_ahead)

        if persist:
            for f in forecasts:
                self.conn.execute(
                    "INSERT INTO labor_forecasts (forecast_id, restaurant_id, "
                    "forecast_date, day_of_week, forecast_covers, method, rationale, "
                    "recommended_foh, recommended_boh, generated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (db.new_id(), restaurant_id, f.forecast_date, f.day_of_week,
                     f.forecast_covers, METHOD_ID, f.rationale,
                     f.recommended_foh, f.recommended_boh, db.now_iso()),
                )
            self.conn.commit()
            db.audit(self.conn, actor=actor, action="LABOR_FORECAST_GENERATED",
                     payload={"method": METHOD_ID, "days": len(forecasts)})

        return {
            "method": METHOD_ID,
            "model_type": "seasonal-naive baseline (untrained)",
            "horizon_days": len(forecasts),
            "history_days_used": len(history),
            "external_signals_used": [],
            "accuracy_claim": (
                "None. No backtest against held-out data has been run and no "
                "accuracy figure is claimed for this baseline."
            ),
            # Surfaced as a first-class field so every consumer — API, dashboard,
            # demo — discloses it, rather than it living only in per-day prose.
            "staffing_assumptions": {
                "covers_per_foh_staff_hour": self.covers_per_foh,
                "covers_per_boh_staff_hour": self.covers_per_boh,
                "service_hours": self.service_hours,
                "min_front_of_house_staff": self.config.min_front_of_house_staff,
                "min_back_of_house_staff": self.config.min_back_of_house_staff,
                "provenance": (
                    "Engineering assumption - not specified in the working "
                    "paper and not measured. Service styles differ enormously, "
                    "so these are configurable inputs, not industry constants."
                ),
            },
            "governance_note": (
                "Advisory only. A.C.E. does not publish or modify staff "
                "schedules (White Paper §3.4, §5.2)."
            ),
            "fairness_note": (
                "The model consumes aggregate daily cover counts only. No "
                "worker-level or demographic data is used (White Paper §5.2)."
            ),
            "daily": [f.to_dict() for f in forecasts],
        }
