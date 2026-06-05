"""
Mars regime — extract per-(t, voxel, observable) JSONL records with aligned
drivers.

Voxelization: 4 Ls bins per mars/prior.yaml (ls_0_90, ls_90_180, ls_180_270,
ls_270_360). Single site (MSL/Curiosity, Gale Crater).

Ls computation: simplified linear from sol → Ls anchored at Curiosity
landing (2012-08-06 UTC, Ls=150.65°), advancing 360°/686.971 days. This
ignores Mars orbital eccentricity (real Ls is non-uniform in time); for
4-bin voxelization the error at bin boundaries is acceptable (~5-10°).
A proper ephemeris (JPL Horizons or astropy.solar_system) would replace
this in production.

Observable: surface_dose_rate (SYNTHETIC — see generate_rad_synthetic.py).

Drivers (REAL):
  f107      ← CelesTrak SW-All daily, lerped to hourly
  ap        ← CelesTrak SW-All daily, lerped to hourly
  kp_index  ← SWPC 3-hour Kp (rolling window — sparse coverage outside
              recent days; outside-window values default to 2.0)
"""

import bisect
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sep_alerts import parse_alerts, driver_state as sep_driver_state, summarize as sep_summarize

RAW = Path(__file__).parent / "raw"
RAD_IN = Path(__file__).parent / "rad_synthetic.jsonl"
OUT = Path(__file__).parent / "obs.jsonl"

# Ls anchor: Curiosity landing 2012-08-06 ~05:17 UTC, Ls=150.65°
LS_ANCHOR_DT = datetime(2012, 8, 6, 5, 17, tzinfo=timezone.utc)
LS_ANCHOR_DEG = 150.65
MARS_YEAR_DAYS = 686.971


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def compute_ls(t):
    dt_days = (t - LS_ANCHOR_DT).total_seconds() / 86400.0
    return (LS_ANCHOR_DEG + 360.0 * dt_days / MARS_YEAR_DAYS) % 360.0


def ls_voxel(ls_deg):
    if ls_deg < 90:  return "ls_0_90"
    if ls_deg < 180: return "ls_90_180"
    if ls_deg < 270: return "ls_180_270"
    return "ls_270_360"


def load_f107_ap_daily():
    """Return list of (date, f107, ap) tuples sorted by date."""
    rows = []
    with (RAW / "sw-all.csv").open() as f:
        for r in csv.DictReader(f):
            try:
                d = datetime.fromisoformat(r["DATE"]).replace(tzinfo=timezone.utc)
                f107 = float(r["F10.7_OBS"])
                ap = float(r["AP_AVG"]) if r["AP_AVG"] else 0.0
                rows.append((d, f107, ap))
            except (ValueError, KeyError):
                continue
    rows.sort(key=lambda x: x[0])
    return rows


def load_kp_series():
    """Return (sorted_ts, kp_values)."""
    data = json.loads((RAW / "swpc_kp.json").read_text())
    ts, kp = [], []
    for r in data:
        try:
            t_raw = r["time_tag"]
            if "T" not in t_raw: t_raw = t_raw.replace(" ", "T") + "Z"
            ts.append(parse_iso(t_raw))
            kp.append(float(r["Kp"]))
        except (KeyError, ValueError):
            continue
    return ts, kp


def lookup_daily(rows, t, default=(150.0, 5.0)):
    """Nearest-day F10.7 and Ap."""
    if not rows: return default
    target = t.date()
    # binary search for date
    lo, hi = 0, len(rows) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if rows[mid][0].date() < target: lo = mid + 1
        else: hi = mid
    return (rows[lo][1], rows[lo][2])


def nearest_kp(ts, kps, t, default=2.0):
    if not ts: return default
    i = bisect.bisect_left(ts, t)
    if i == 0: return kps[0]
    if i >= len(ts): return kps[-1]
    return kps[i] if (ts[i] - t) < (t - ts[i-1]) else kps[i-1]


def main():
    print("loading drivers…")
    daily = load_f107_ap_daily()
    kp_ts, kp_vals = load_kp_series()
    print(f"  {len(daily)} daily F10.7/Ap records")
    print(f"  {len(kp_ts)} Kp records  (span: {(kp_ts[-1]-kp_ts[0]).total_seconds()/86400:.1f} days)" if kp_ts else "  no Kp")

    print("parsing SWPC alerts…")
    sep_timeline = parse_alerts(RAW / "swpc_alerts.json")
    print(sep_summarize(sep_timeline))

    print(f"loading synthetic RAD from {RAD_IN.name}…")
    rad = [json.loads(line) for line in RAD_IN.read_text().splitlines() if line]
    rad.sort(key=lambda r: r["t"])
    print(f"  {len(rad)} synthetic RAD records")

    voxel_counts = {"ls_0_90": 0, "ls_90_180": 0, "ls_180_270": 0, "ls_270_360": 0}
    out_records = []
    for r in rad:
        t = parse_iso(r["t"])
        ls = compute_ls(t)
        v = ls_voxel(ls)
        voxel_counts[v] += 1
        f107, ap = lookup_daily(daily, t)
        kp = nearest_kp(kp_ts, kp_vals, t)
        d = {"f107": f107, "ap": ap, "kp_index": kp}
        d.update(sep_driver_state(sep_timeline, t))
        out_records.append({
            "t": r["t"],
            "v": v,
            "obs": r["obs"],
            "o": r["o"],
            "units": r["units"],
            "is_synthetic": r["is_synthetic"],
            "placeholder_schema": r["placeholder_schema"],
            "ls_deg": round(ls, 2),
            "d": d,
        })

    with OUT.open("w") as f:
        for r in out_records:
            f.write(json.dumps(r) + "\n")

    print(f"\nwrote {OUT.name}  ({len(out_records):,} records)")
    print("voxel coverage:")
    for k in ["ls_0_90", "ls_90_180", "ls_180_270", "ls_270_360"]:
        bar = "█" * (voxel_counts[k] * 40 // max(voxel_counts.values(), default=1))
        print(f"  {k:14s} {voxel_counts[k]:>5d}  {bar}")
    if voxel_counts["ls_0_90"] == 0 or voxel_counts["ls_270_360"] == 0:
        print("\n  Note: 365-day window only covers ~190° of Ls (2 of 4 voxels).")
        print("        Extending to 1 Mars year (687 days) would exercise all four.")


if __name__ == "__main__":
    main()
