"""
Mars regime — SYNTHETIC MSL/RAD dose-rate placeholder.

REAL ground-truth data is not yet wired (PDS-PPI URL in mars/validate.yaml
currently 404s; data likely moved to PDS Geosciences or MSL Analyst's
Notebook — see README for the resolution path). This file generates a
clearly-labeled synthetic dose-rate time series with realistic morphology
so the skeleton pipeline can be exercised end-to-end.

Morphology (per Hassler et al. 2014 and follow-on RAD papers):
  - Quiet baseline ~ 200 µGy/day at Gale Crater
  - GCR modulation by F10.7 (anticorrelated; high solar suppresses dose)
  - Small annual cycle (~ ±10 µGy/day; Mars dust-storm season modulation)
  - SEP-event spikes at major historical storm onsets, exponential decay
    with amplitudes 20-100 µGy/day
  - Gaussian measurement noise σ ~ 3 µGy/day

EVERY record carries `"is_synthetic": true` and `"placeholder_schema": "v0.1"`
so downstream consumers cannot mistake this for real PDS data.
"""

import csv
import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sep_alerts import parse_alerts

RAW = Path(__file__).parent / "raw"
OUT = Path(__file__).parent / "rad_synthetic.jsonl"

# Skeleton window (matches fetch_mars_drivers.py)
WINDOW_END = datetime(2026, 5, 22, tzinfo=timezone.utc)
WINDOW_START = WINDOW_END - timedelta(days=365)

QUIET_DOSE = 200.0          # µGy/day, Hassler+ 2014 quiet-time baseline
F107_MODULATION = -0.40     # µGy/day per unit F10.7 above 100 sfu
ANNUAL_AMP = 10.0           # µGy/day, peak-to-peak annual cycle
NOISE_SIGMA = 3.0           # µGy/day, measurement noise

# SEP injection times are derived from SWPC alerts.json (sep_proton + flare_xclass
# categories — see sep_alerts.EVENT_CATEGORIES). Amplitudes are scaled by the
# parsed event tier (S1/S2/S3 → 0.33/0.67/1.00) × a peak-amplitude constant.
# This makes the synthetic ground truth share an onset basis with the
# real driver feed: when sep_alerts also drives the substrate (as a real driver),
# the framework should converge that edge's W to a high positive value, closing
# the "missing physics" curiosity gap the original skeleton's flat F10.7-only
# prior could only point at.
PEAK_SEP_AMPLITUDE = 60.0   # µGy/day at tier 1.00 (S3 / extreme)
DEFAULT_DECAY_DAYS = 1.5


def load_f107_daily():
    """Return dict: date_obj -> F10.7_obs over the skeleton window."""
    out = {}
    with (RAW / "sw-all.csv").open() as f:
        for r in csv.DictReader(f):
            try:
                d = datetime.fromisoformat(r["DATE"]).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if WINDOW_START <= d <= WINDOW_END:
                try:
                    out[d.date()] = float(r["F10.7_OBS"])
                except (ValueError, KeyError):
                    pass
    return out


def lerp_f107(f107_daily, t):
    d = t.date()
    return f107_daily.get(d, 150.0)


def load_sep_events():
    """Read sep_proton + flare_xclass onsets from SWPC alerts → (onset, amp, decay)."""
    alerts_path = RAW / "swpc_alerts.json"
    if not alerts_path.exists():
        return []
    tl = parse_alerts(alerts_path)
    events = []
    for cat in ("sep_proton", "flare_xclass"):
        for onset, tier in tl.get(cat, []):
            events.append((onset, tier * PEAK_SEP_AMPLITUDE, DEFAULT_DECAY_DAYS))
    return events


def sep_contribution(t, events):
    dose = 0.0
    for onset, amp, decay_days in events:
        if t < onset:
            continue
        dt_days = (t - onset).total_seconds() / 86400.0
        if dt_days > 6 * decay_days:
            continue
        dose += amp * math.exp(-dt_days / decay_days)
    return dose


def annual_cycle(t):
    # Day of Mars year is irrelevant here — small Earth-year proxy
    doy = (t - datetime(t.year, 1, 1, tzinfo=timezone.utc)).total_seconds() / 86400.0
    return 0.5 * ANNUAL_AMP * math.sin(2 * math.pi * doy / 365.25)


def main():
    print("loading real F10.7 daily…")
    f107 = load_f107_daily()
    print(f"  {len(f107)} daily F10.7 values in window")

    print("loading SEP events from SWPC alerts…")
    sep_events = load_sep_events()
    in_window = [e for e in sep_events if WINDOW_START <= e[0] <= WINDOW_END]
    print(f"  {len(sep_events)} parsed total, {len(in_window)} in skeleton window")

    print("generating hourly synthetic dose-rate…")
    random.seed(42)
    n = 0
    t = WINDOW_START
    with OUT.open("w") as f:
        while t <= WINDOW_END:
            f107_t = lerp_f107(f107, t)
            base = QUIET_DOSE + F107_MODULATION * (f107_t - 100.0)
            dose = base + annual_cycle(t) + sep_contribution(t, sep_events) + random.gauss(0, NOISE_SIGMA)
            dose = max(dose, 1.0)
            f.write(json.dumps({
                "t": t.isoformat().replace("+00:00", "Z"),
                "obs": "surface_dose_rate",
                "o": round(dose, 3),
                "units": "uGy_per_day",
                "is_synthetic": True,
                "placeholder_schema": "v0.2",
            }) + "\n")
            n += 1
            t += timedelta(hours=1)
    print(f"  {n:,} hourly records → {OUT.name}")
    print(f"  schema marker: is_synthetic=True, placeholder_schema=v0.2")
    print(f"  quiet baseline ~ {QUIET_DOSE:.0f} µGy/day; SEP injections derived from SWPC alerts")


if __name__ == "__main__":
    main()
