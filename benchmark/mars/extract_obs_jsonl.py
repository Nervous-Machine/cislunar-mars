"""
Mars regime — extract per-(t, voxel, observable) JSONL records with
aligned drivers, using REAL MSL/RAD ground truth and REAL GOES SGPS
proton flux.

Voxelization: 4 Ls bins per mars/prior.yaml (ls_0_90, ls_90_180,
ls_180_270, ls_270_360). Single site (MSL/Curiosity, Gale Crater).

Ls computation: simplified linear from sol → Ls anchored at Curiosity
landing (2012-08-06 UTC, Ls=150.65°), advancing 360°/686.971 days. For
4-bin voxelization the boundary error from ignoring Mars orbital
eccentricity is ~5-10°, acceptable. JPL Horizons or astropy ephemeris
would replace this in production.

Observable: surface_dose_rate (REAL — MSL/RAD detector B, μGy/day).

Drivers (REAL, all archival):
  f107       — CelesTrak SW-All daily, nearest-day lookup
  ap         — CelesTrak SW-All daily
  kp_index   — SWPC 3-hour Kp (rolling — sparse outside last few days;
               defaults to 2.0 outside the rolling window)
  sep_proton — GOES-18 SGPS >=10 MeV integral proton flux, hourly max,
               from goes_protons_hourly.jsonl. Replaces the SWPC alerts
               feed used by the skeleton (alerts.json is rolling 30-day
               only and does NOT cover the historical RAD window).
               Graded by SWPC S-scale: 0.33 = S1 (10-100 pfu), 0.67 = S2
               (100-1000), 1.00 = S3+ (>=1000).

The synthetic_seeds drivers from the SWPC alerts feed (flare_xclass,
geomag_storm) are still parsed and included if available, but for the
historical RAD window will be all-zero — documented as a falsifiable
null-driver pattern. See README "Falsifiable architecture test".
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
RAD_IN = Path(__file__).parent / "rad_observations.jsonl"           # real RAD parser output
RAD_SYNTH_IN = Path(__file__).parent / "rad_synthetic.jsonl"         # skeleton fallback
PROTON_IN = RAW / "goes_protons_hourly.jsonl"                        # archive-grade SEP source
OUT = Path(__file__).parent / "obs.jsonl"

# Ls anchor: Curiosity landing 2012-08-06 ~05:17 UTC, Ls=150.65°
LS_ANCHOR_DT = datetime(2012, 8, 6, 5, 17, tzinfo=timezone.utc)
LS_ANCHOR_DEG = 150.65
MARS_YEAR_DAYS = 686.971

# SWPC S-scale tier thresholds (pfu @ >=10 MeV)
SEP_TIERS = [(10.0, 0.33), (100.0, 0.67), (1000.0, 1.00)]
SEP_DECAY_HOURS = 48.0  # match sep_alerts EVENT_CATEGORIES['sep_proton']


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


def load_goes_protons():
    """Read GOES SGPS hourly max → list of (t, flux_ge_10mev) sorted by time."""
    if not PROTON_IN.exists():
        return [], []
    ts, fluxes = [], []
    for line in PROTON_IN.read_text().splitlines():
        if not line:
            continue
        r = json.loads(line)
        ts.append(parse_iso(r["t"]))
        fluxes.append(r["flux_ge_10mev"])
    return ts, fluxes


def proton_to_tier(flux_pfu):
    """Map proton flux pfu @ >=10 MeV → SWPC S-scale tier [0, 1]."""
    if flux_pfu < SEP_TIERS[0][0]:
        return 0.0
    tier = 0.0
    for threshold, t in SEP_TIERS:
        if flux_pfu >= threshold:
            tier = t
    return tier


def sep_state_from_protons(proton_ts, proton_flux, t, decay_hours=SEP_DECAY_HOURS):
    """Return graded SEP intensity at t, with exponential decay from the
    latest onset preceding t. Matches sep_alerts.intensity_at API.
    """
    if not proton_ts:
        return 0.0
    # Find all hours up to t (right-search)
    i_end = bisect.bisect_right(proton_ts, t)
    val = 0.0
    # Walk backward from i_end looking for the strongest decayed onset
    # within 6 decay constants
    cutoff = decay_hours * 6.0
    for j in range(i_end - 1, -1, -1):
        dt_hours = (t - proton_ts[j]).total_seconds() / 3600.0
        if dt_hours > cutoff:
            break
        tier = proton_to_tier(proton_flux[j])
        if tier <= 0:
            continue
        import math
        decayed = tier * math.exp(-dt_hours / decay_hours)
        if decayed > val:
            val = decayed
    return val


def main():
    print("loading drivers…")
    daily = load_f107_ap_daily()
    kp_ts, kp_vals = load_kp_series()
    print(f"  {len(daily)} daily F10.7/Ap records")
    print(f"  {len(kp_ts)} Kp records  (span: {(kp_ts[-1]-kp_ts[0]).total_seconds()/86400:.1f} days)" if kp_ts else "  no Kp")

    proton_ts, proton_flux = load_goes_protons()
    print(f"  {len(proton_ts)} hourly GOES proton records  "
          f"(span: {(proton_ts[-1]-proton_ts[0]).total_seconds()/86400:.1f} days)" if proton_ts else "  no GOES protons")

    print("parsing SWPC alerts (for flare_xclass / geomag_storm — likely zero over historical RAD window)…")
    sep_timeline = parse_alerts(RAW / "swpc_alerts.json")
    print(sep_summarize(sep_timeline))

    # Choose RAD source: real if available, else synthetic fallback
    if RAD_IN.exists():
        rad_path = RAD_IN
        synth_mode = False
        print(f"\nloading REAL MSL/RAD from {rad_path.name}…")
    elif RAD_SYNTH_IN.exists():
        rad_path = RAD_SYNTH_IN
        synth_mode = True
        print(f"\nWARN: no real RAD file at {RAD_IN.name}; falling back to {rad_path.name}")
    else:
        sys.exit(f"no RAD source at {RAD_IN} or {RAD_SYNTH_IN}; run fetch_rad.py first")

    rad = [json.loads(line) for line in rad_path.read_text().splitlines() if line]
    rad.sort(key=lambda r: r["t"])
    print(f"  {len(rad):,} RAD records ({'SYNTHETIC' if synth_mode else 'REAL'})")

    voxel_counts = {"ls_0_90": 0, "ls_90_180": 0, "ls_180_270": 0, "ls_270_360": 0}
    out_records = []
    sep_active = 0
    for r in rad:
        t = parse_iso(r["t"])
        ls = compute_ls(t)
        v = ls_voxel(ls)
        voxel_counts[v] += 1
        f107, ap = lookup_daily(daily, t)
        kp = nearest_kp(kp_ts, kp_vals, t)
        d = {"f107": f107, "ap": ap, "kp_index": kp}

        # SEP: prefer GOES SGPS archive over SWPC alerts.json (alerts is
        # rolling 30-day, won't overlap historical window)
        sep_alerts_state = sep_driver_state(sep_timeline, t)
        sep_proton_from_protons = sep_state_from_protons(proton_ts, proton_flux, t)
        # Use max(alerts, archive) so either source contributes
        d["sep_proton"] = max(sep_alerts_state.get("sep_proton", 0.0), sep_proton_from_protons)
        if d["sep_proton"] > 0:
            sep_active += 1
        # Keep the rest of the alert-derived drivers for skeleton continuity
        d["flare_xclass"] = sep_alerts_state.get("flare_xclass", 0.0)
        d["geomag_storm"] = sep_alerts_state.get("geomag_storm", 0.0)
        # Optionally surface the raw proton flux for downstream tier-2 work
        out_records.append({
            "t": r["t"],
            "v": v,
            "obs": r["obs"],
            "o": r["o"],
            "units": r["units"],
            "is_synthetic": r.get("is_synthetic", synth_mode),
            "placeholder_schema": r.get("placeholder_schema", "synthetic" if synth_mode else "pds3_rad_rdr_v1"),
            "ls_deg": round(ls, 2),
            "d": d,
        })

    with OUT.open("w") as f:
        for r in out_records:
            f.write(json.dumps(r) + "\n")

    print(f"\nwrote {OUT.name}  ({len(out_records):,} records)")
    print(f"  sep_proton driver active on {sep_active:,} records ({100*sep_active/max(len(out_records),1):.1f}%)")
    print("voxel coverage:")
    for k in ["ls_0_90", "ls_90_180", "ls_180_270", "ls_270_360"]:
        bar = "█" * (voxel_counts[k] * 40 // max(voxel_counts.values(), default=1))
        print(f"  {k:14s} {voxel_counts[k]:>5d}  {bar}")
    empty = [k for k, c in voxel_counts.items() if c < 20]
    if empty:
        print(f"\n  Note: {len(empty)} voxel(s) under-sampled in this window: {empty}.")
        print(f"        Extending the RAD window backward would cover all four.")


if __name__ == "__main__":
    main()
