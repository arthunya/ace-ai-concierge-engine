"""Generate the synthetic POS cover history used by the Layer 3 demo.

The output file is committed to the repository so demo results are
reproducible without re-running this script. Re-running it with the same
seed reproduces the file byte-for-byte.

THIS IS SYNTHETIC DATA. It is generated from a day-of-week pattern plus a
mild upward trend plus seeded noise. It is not transaction data from any
restaurant. Its only purpose is to give the Layer 3 baseline something
realistic to consume.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 20260331
HISTORY_DAYS = 84          # 12 full weeks
HISTORY_END = date(2026, 3, 31)   # fixed anchor -> reproducible demo

# Relative weekday demand shape for a dinner-led independent restaurant.
DOW_SHAPE = {
    "Monday": 0.62, "Tuesday": 0.68, "Wednesday": 0.79, "Thursday": 0.92,
    "Friday": 1.34, "Saturday": 1.48, "Sunday": 1.07,
}
BASE_COVERS = 118
TREND_PER_WEEK = 0.6       # slow growth, so trailing average is not flat
NOISE_SD = 7.0

OUT = Path(__file__).resolve().parent.parent / "data" / "demo" / "pos_covers_history.csv"


def main() -> None:
    rng = random.Random(SEED)
    start = HISTORY_END - timedelta(days=HISTORY_DAYS - 1)
    rows = []
    for i in range(HISTORY_DAYS):
        d = start + timedelta(days=i)
        trend = BASE_COVERS + TREND_PER_WEEK * (i / 7.0)
        covers = trend * DOW_SHAPE[d.strftime("%A")] + rng.gauss(0, NOISE_SD)
        rows.append({
            "date": d.isoformat(),
            "day_of_week": d.strftime("%A"),
            "covers": max(0, round(covers)),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "day_of_week", "covers"])
        w.writeheader()
        w.writerows(rows)
    print(f"{OUT} ({len(rows)} rows, {rows[0]['date']} to {rows[-1]['date']})")


if __name__ == "__main__":
    main()
