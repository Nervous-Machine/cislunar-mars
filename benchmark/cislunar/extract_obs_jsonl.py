"""
Cislunar regime — extract per-(t, voxel, observable) JSONL records with
aligned drivers.

Sources joined here:
  - artemis_hourly.jsonl     : ARTEMIS B-field observables (THB+THC, hourly)
  - raw/omni/omni_min*.asc   : OMNI 1-min L1-propagated solar wind / IMF
                                → aggregated to hourly
  - raw/goes_protons_hourly.jsonl : GOES SGPS ≥10 MeV proton hourly max
                                → SEP driver (graded by SWPC S-scale)
  - raw/sw-all.csv           : CelesTrak daily F10.7, Ap, daily Kp
  - raw/swpc_alerts.json     : Rolling 30-day SWPC alert events
  - raw/swpc_kp.json         : Rolling Kp index history

Drivers exposed to the substrate (12, mirroring GEO with cislunar specialization):
  imf_bz_l1            — Bz_GSE at L1 from OMNI (the "should-converge to +1
                         on imf_bz_at_lunar_distance" architecture test)
  imf_bt_l1            — total field at L1
  sw_speed             — solar wind speed at L1
  sw_density           — solar wind proton density at L1
  sw_dynamic_pressure  — derived 1.6726e-6 * density * speed^2 (nPa)
  sep_proton           — graded ≥10 MeV proton tier from GOES SGPS [0, 1]
  kp_index             — Kp planetary index
  dst_index            — Dst ring-current (from OMNI SYM/H proxy)
  f107                 — F10.7 daily flux
  ap                   — Ap daily geomagnetic
  flare_xclass         — SWPC alerts derived (rolling-30d only)
  geomag_storm         — SWPC alerts derived (rolling-30d only)

Output: obs.jsonl  per-record schema:
  {"t": "...", "v": voxel, "obs": observable_id, "o": value, "units": "nT",
   "probe": "thb"|"thc", "r_re": ..., "pos_gse_km": [...],
   "d": {driver_name: value, ...}}
"""

import bisect
import csv
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sep_alerts import parse_alerts, driver_state as sep_driver_state, summarize as sep_summarize

ROOT = Path(__file__).parent
RAW = ROOT / "raw"
ARTEMIS_JSONL = ROOT / "artemis_hourly.jsonl"
GOES_PROTONS_JSONL = RAW / "goes_protons_hourly.jsonl"
OUT = ROOT / "obs.jsonl"

# SWPC S-scale graded tiers for SEP intensity (pfu ≥10 MeV)
SEP_TIERS = [(10.0, 0.33), (100.0, 0.67), (1000.0, 1.00)]
SEP_DECAY_HOURS = 48.0


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


# --- OMNI HRO 1-min parser -----------------------------------------------
# Per hroformat.txt, the columns are space-separated with fixed widths.
# We need a small subset of columns:
#   col   1: Year                   (I4)
#   col   2: Day-of-year            (I4)
#   col   3: Hour                   (I3)
#   col   4: Minute                 (I3)
#   col  14: Field magnitude        (F8.2)   total |B| in nT
#   col  17: Bz_GSE                 (F8.2)
#   col  22: Flow speed             (F8.1)   sw_speed km/s
#   col  26: Proton density         (F7.2)   n/cc
#   col  29: Flow pressure          (F6.2)   nPa
#   col  43: SYM/H index            (I6)     nT (Dst proxy)
# OMNI uses 9999.99 / 999.99 / 99.99 / 9.99 as fill values; we treat any
# value matching the "all 9's" pattern as missing.

def is_fill(v, threshold):
    return v >= threshold or v <= -threshold


def parse_omni_min(omni_dir: Path):
    """Yield (datetime_utc, {field: value}) per minute. Fields:
       imf_bt, imf_bz, sw_speed, sw_density, sw_dyn_p, sym_h."""
    out = {}
    files = sorted(omni_dir.glob("omni_min*.asc"))
    for fp in files:
        for line in fp.read_text().splitlines():
            parts = line.split()
            if len(parts) < 30:
                continue
            try:
                yr = int(parts[0]); doy = int(parts[1])
                hr = int(parts[2]); mn = int(parts[3])
                bt = float(parts[13])     # field magnitude
                bz = float(parts[16])     # Bz GSE
                vsw = float(parts[21])    # flow speed
                dens = float(parts[25])   # proton density
                pdyn = float(parts[28])   # flow pressure (nPa)
                sym_h = int(parts[42])    # SYM/H index nT
            except (ValueError, IndexError):
                continue
            t = datetime(yr, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy - 1, hours=hr, minutes=mn)
            rec = {}
            if not is_fill(bt, 999.0):  rec["imf_bt"] = bt
            if not is_fill(bz, 999.0):  rec["imf_bz"] = bz
            if not is_fill(vsw, 9999.0): rec["sw_speed"] = vsw
            if not is_fill(dens, 999.0): rec["sw_density"] = dens
            if not is_fill(pdyn, 99.0):  rec["sw_dyn_p"] = pdyn
            if abs(sym_h) < 99999:       rec["sym_h"] = float(sym_h)
            out[t] = rec
    return out


def omni_hourly(omni_min: dict) -> dict:
    """Reduce per-minute OMNI dict → hourly mean (dropping nans)."""
    bucket = {}
    for t, rec in omni_min.items():
        h = t.replace(minute=0, second=0, microsecond=0)
        bucket.setdefault(h, []).append(rec)
    out = {}
    for h, recs in bucket.items():
        merged = {}
        for k in ("imf_bt", "imf_bz", "sw_speed", "sw_density", "sw_dyn_p", "sym_h"):
            vs = [r[k] for r in recs if k in r]
            if vs:
                merged[k] = sum(vs) / len(vs)
        out[h] = merged
    return out


# --- F10.7 / Ap / Kp from SW-All -----------------------------------------

def load_f107_ap_daily():
    rows = []
    p = RAW / "sw-all.csv"
    if not p.exists():
        return rows
    with p.open() as f:
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


def lookup_daily(rows, t, default=(150.0, 5.0)):
    if not rows: return default
    target = t.date()
    lo, hi = 0, len(rows) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if rows[mid][0].date() < target: lo = mid + 1
        else: hi = mid
    return (rows[lo][1], rows[lo][2])


def load_kp_series():
    """SWPC Kp JSON (rolling-window)."""
    p = RAW / "swpc_kp.json"
    if not p.exists():
        return [], []
    data = json.loads(p.read_text())
    ts, kp = [], []
    for r in data:
        try:
            t_raw = r["time_tag"]
            if "T" not in t_raw:
                t_raw = t_raw.replace(" ", "T") + "Z"
            ts.append(parse_iso(t_raw))
            kp.append(float(r["Kp"]))
        except (KeyError, ValueError):
            continue
    return ts, kp


def nearest_kp(ts, kps, t, default=2.0):
    if not ts: return default
    i = bisect.bisect_left(ts, t)
    if i == 0: return kps[0]
    if i >= len(ts): return kps[-1]
    return kps[i] if (ts[i] - t) < (t - ts[i-1]) else kps[i-1]


# --- GOES SGPS proton-derived SEP intensity ------------------------------

def load_goes_protons():
    p = GOES_PROTONS_JSONL
    if not p.exists():
        return [], []
    ts, fluxes = [], []
    for line in p.read_text().splitlines():
        if not line: continue
        r = json.loads(line)
        ts.append(parse_iso(r["t"]))
        fluxes.append(r["flux_ge_10mev"])
    return ts, fluxes


def proton_to_tier(flux_pfu):
    if flux_pfu < SEP_TIERS[0][0]:
        return 0.0
    tier = 0.0
    for thr, t in SEP_TIERS:
        if flux_pfu >= thr:
            tier = t
    return tier


def sep_state_from_protons(proton_ts, proton_flux, t, decay_hours=SEP_DECAY_HOURS):
    if not proton_ts: return 0.0
    i_end = bisect.bisect_right(proton_ts, t)
    val = 0.0
    cutoff = decay_hours * 6.0
    for j in range(i_end - 1, -1, -1):
        dt_h = (t - proton_ts[j]).total_seconds() / 3600.0
        if dt_h > cutoff:
            break
        tier = proton_to_tier(proton_flux[j])
        if tier <= 0:
            continue
        decayed = tier * math.exp(-dt_h / decay_hours)
        if decayed > val:
            val = decayed
    return val


# --- Main extraction -----------------------------------------------------

def main():
    print("loading drivers…")
    daily_f107_ap = load_f107_ap_daily()
    kp_ts, kp_vals = load_kp_series()
    print(f"  SW-All daily: {len(daily_f107_ap)} rows  "
          f"({daily_f107_ap[0][0].date() if daily_f107_ap else '-'} → "
          f"{daily_f107_ap[-1][0].date() if daily_f107_ap else '-'})")
    print(f"  SWPC Kp:      {len(kp_ts)} rows  "
          f"span {((kp_ts[-1]-kp_ts[0]).total_seconds()/86400 if kp_ts else 0):.1f} days")

    omni_min = parse_omni_min(RAW / "omni")
    omni_h = omni_hourly(omni_min)
    print(f"  OMNI 1-min:   {len(omni_min):,} records → {len(omni_h):,} hourly")

    proton_ts, proton_flux = load_goes_protons()
    if proton_ts:
        print(f"  GOES protons: {len(proton_ts):,} hourly rows  "
              f"({proton_ts[0].date()} → {proton_ts[-1].date()})")
    else:
        print(f"  GOES protons: NONE — sep_proton driver will fall back to alerts only")

    sep_timeline = parse_alerts(RAW / "swpc_alerts.json")
    print("parsed SWPC alerts.json:")
    print(sep_summarize(sep_timeline))

    # Load ARTEMIS hourly observable records
    if not ARTEMIS_JSONL.exists():
        sys.exit(f"no {ARTEMIS_JSONL} — run parse_artemis.py first")
    artemis = [json.loads(line) for line in ARTEMIS_JSONL.read_text().splitlines() if line]
    print(f"  ARTEMIS:      {len(artemis):,} obs records")

    # Build per-record joined output
    out_records = []
    voxel_counts = {"inner_magnetospheric": 0, "magnetotail_transit": 0, "outer_lunar_vicinity": 0}
    sep_active = 0
    for r in artemis:
        t = parse_iso(r["t"])
        h = t.replace(minute=0, second=0, microsecond=0)
        omni_rec = omni_h.get(h, {})
        f107, ap = lookup_daily(daily_f107_ap, t)
        kp = nearest_kp(kp_ts, kp_vals, t)
        sep_alerts_state = sep_driver_state(sep_timeline, t)
        sep_from_protons = sep_state_from_protons(proton_ts, proton_flux, t)
        sep = max(sep_alerts_state.get("sep_proton", 0.0), sep_from_protons)
        if sep > 0: sep_active += 1

        d = {
            "imf_bz_l1": omni_rec.get("imf_bz"),
            "imf_bt_l1": omni_rec.get("imf_bt"),
            "sw_speed":  omni_rec.get("sw_speed"),
            "sw_density": omni_rec.get("sw_density"),
            "sw_dynamic_pressure": omni_rec.get("sw_dyn_p"),
            "sep_proton": sep,
            "kp_index":   kp,
            "dst_index":  omni_rec.get("sym_h"),    # SYM/H is the high-cadence Dst
            "f107":       f107,
            "ap":         ap,
            "flare_xclass": sep_alerts_state.get("flare_xclass", 0.0),
            "geomag_storm": sep_alerts_state.get("geomag_storm", 0.0),
        }
        voxel_counts[r["v"]] = voxel_counts.get(r["v"], 0) + 1
        out_records.append({
            "t": r["t"], "v": r["v"], "obs": r["obs"], "o": r["o"],
            "units": r["units"], "probe": r["probe"],
            "pos_gse_km": r["pos_gse_km"], "r_re": r["r_re"],
            "d": d,
        })

    with OUT.open("w") as f:
        for r in out_records:
            f.write(json.dumps(r) + "\n")

    print(f"\nwrote {OUT.name}  ({len(out_records):,} records)")
    print(f"  sep_proton active on {sep_active:,} records ({100*sep_active/max(len(out_records),1):.1f}%)")
    print("voxel coverage:")
    total = sum(voxel_counts.values())
    for k in ("inner_magnetospheric", "magnetotail_transit", "outer_lunar_vicinity"):
        v = voxel_counts.get(k, 0)
        pct = 100*v/max(total,1)
        bar = "█" * (v * 40 // max(total, 1))
        print(f"  {k:24s} {v:>6d}  {pct:5.1f}%  {bar}")

    # Driver coverage report
    cov = {k: 0 for k in ("imf_bz_l1","imf_bt_l1","sw_speed","sw_density",
                          "sw_dynamic_pressure","dst_index","f107","ap")}
    for r in out_records:
        for k in cov:
            if r["d"].get(k) is not None:
                cov[k] += 1
    print("\ndriver coverage (non-null fraction):")
    for k, v in cov.items():
        print(f"  {k:24s} {v:>6d} / {len(out_records):<6d}  ({100*v/len(out_records):4.1f}%)")


if __name__ == "__main__":
    main()
