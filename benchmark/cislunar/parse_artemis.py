"""
Cislunar regime — parse THEMIS-ARTEMIS L2 FGM + L1 STATE CDFs to hourly
JSONL with per-record (timestamp, voxel-determining position, observables).

For each (probe, day) we:
  1. Read STATE → time series of GSE position (km). Resample to hourly.
  2. Read FGM  → time series of B-vector (nT, GSE), reduce to hourly:
        imf_btot   = hourly mean |B|
        imf_bz     = hourly mean Bz_GSE
     (Hourly mean is the standard reduction for cislunar driver coupling
     at synoptic timescales; the FGM 3 s data is averaged over 1200
     samples per hour, suppressing noise on Bz to ~σ/√1200.)
  3. Join position to B by hourly key; drop hours missing either side.
  4. Compute voxel membership from position (see voxelize()).

Output: artemis_hourly.jsonl
    {"t": ISO,
     "probe": "thb"|"thc",
     "obs": "imf_btot_at_lunar_distance"|"imf_bz_at_lunar_distance",
     "v":  voxel,
     "o":  scalar value,
     "units": "nT",
     "pos_gse_km": [x, y, z],
     "r_re": geocentric distance in Earth radii}

Voxelization (see voxelize() docstring):
    inner_magnetospheric    — r ≤ 10 RE
    outer_lunar_vicinity    — Moon outside the Shue-1998 magnetopause
                              (the typical case; ~75% of the time at lunar
                              distance)
    free_solar_wind         — synonym for outer_lunar_vicinity in the
                              cislunar/prior.yaml taxonomy; we use a
                              SUBDIVISION via the magnetotail mask:
                              inside_magnetotail vs outside_magnetotail

Note: prior.yaml declares three regions
    inner_magnetospheric, magnetotail_transit, outer_lunar_vicinity
We use those three IDs verbatim. magnetotail_transit is between 10 RE
and the magnetopause/bow shock on the nightside.
"""

import bisect
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cdflib
import numpy as np

RAW = Path(__file__).parent / "raw"
ARTEMIS_DIR = RAW / "artemis"
OUT = Path(__file__).parent / "artemis_hourly.jsonl"

RE_KM = 6378.137


# --- Voxelization --------------------------------------------------------
# Voxel membership is determined by spacecraft position relative to
# magnetospheric structures (geocentric distance + Shue-1998 magnetopause).
#
# inner_magnetospheric : r ≤ 10 RE — inside Earth's magnetosphere all the
#                        time regardless of solar wind state; trapped
#                        radiation belt geometry dominates here. ARTEMIS
#                        does not loiter here at lunar orbit; this voxel
#                        sees data only during apogee-to-perigee passes
#                        (when applicable) or near phasing-orbit periods.
#
# magnetotail_transit  : x_GSE < -10 RE AND r > 10 RE AND inside the
#                        magnetotail (|y_GSE| < tail_radius(x_GSE)).
#                        Variable shielding regime; Moon spends ~3-5 days
#                        per lunar month here near full Moon (depending
#                        on solar wind state and tail flaring).
#
# outer_lunar_vicinity : everything else at r > 10 RE (the dayside or
#                        flanks of the magnetosphere, or in the upstream
#                        solar wind). Dominant ARTEMIS regime.
#
# We DO NOT use the Shue-1998 self-consistent magnetopause here (which
# would require concurrent solar-wind state); we use a fixed geometric
# proxy for the magnetotail:
#   tail_radius(x) ≈ 25 RE * (1 + 0.001 * (-x_RE - 10))  for x < -10 RE
# i.e. a ~25 RE half-width tail flaring modestly with distance. This is
# a static-geometry proxy; substrate learning compensates for the
# resulting residual when actual magnetopause position varies.

def voxelize(x_km: float, y_km: float, z_km: float) -> str:
    x_re = x_km / RE_KM
    y_re = y_km / RE_KM
    z_re = z_km / RE_KM
    r_re = math.sqrt(x_re**2 + y_re**2 + z_re**2)
    if r_re <= 10.0:
        return "inner_magnetospheric"
    if x_re < -10.0:
        # nightside — check if inside tail
        tail_half_width = 25.0 * (1.0 + 0.001 * (-x_re - 10.0))
        rho = math.sqrt(y_re**2 + z_re**2)
        if rho < tail_half_width:
            return "magnetotail_transit"
    return "outer_lunar_vicinity"


# --- CDF parsing helpers -------------------------------------------------

def epoch_seconds_to_utc(epoch_sec: float) -> datetime:
    return datetime.fromtimestamp(float(epoch_sec), tz=timezone.utc)


def hourly_floor(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def parse_state(state_path: Path):
    """Return {hour_dt -> (x_km, y_km, z_km)} mean of state samples in that hour."""
    try:
        c = cdflib.CDF(str(state_path))
        t = c.varget("thb_state_time" if "thb" in state_path.name else "thc_state_time")
        pos = c.varget("thb_pos_gse" if "thb" in state_path.name else "thc_pos_gse")
    except Exception as e:
        print(f"  state parse fail {state_path.name}: {e}")
        return {}
    bucket = {}
    for i in range(len(t)):
        dt = epoch_seconds_to_utc(t[i])
        h = hourly_floor(dt)
        bucket.setdefault(h, []).append((float(pos[i, 0]), float(pos[i, 1]), float(pos[i, 2])))
    out = {}
    for h, vs in bucket.items():
        xs = [v[0] for v in vs]
        ys = [v[1] for v in vs]
        zs = [v[2] for v in vs]
        out[h] = (sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs))
    return out


def parse_fgm(fgm_path: Path):
    """Return {hour_dt -> (btot_mean, bz_mean, n_samples)} from FGS (3 s) data."""
    probe = "thb" if "thb" in fgm_path.name else "thc"
    try:
        c = cdflib.CDF(str(fgm_path))
        t = c.varget(f"{probe}_fgs_time")
        btot = c.varget(f"{probe}_fgs_btotal")
        gse = c.varget(f"{probe}_fgs_gse")
    except Exception as e:
        print(f"  fgm parse fail {fgm_path.name}: {e}")
        return {}
    bucket = {}
    for i in range(len(t)):
        b = float(btot[i])
        bz = float(gse[i, 2])
        if not (math.isfinite(b) and math.isfinite(bz)):
            continue
        dt = epoch_seconds_to_utc(t[i])
        h = hourly_floor(dt)
        bucket.setdefault(h, [[], []])
        bucket[h][0].append(b)
        bucket[h][1].append(bz)
    out = {}
    for h, (bs, bzs) in bucket.items():
        if not bs:
            continue
        out[h] = (sum(bs)/len(bs), sum(bzs)/len(bzs), len(bs))
    return out


# --- Main pipeline -------------------------------------------------------

def main():
    state_files = sorted(ARTEMIS_DIR.glob("th?_l1_state_*.cdf"))
    fgm_files = sorted(ARTEMIS_DIR.glob("th?_l2_fgm_*.cdf"))
    print(f"state files: {len(state_files)}    fgm files: {len(fgm_files)}")
    if not state_files or not fgm_files:
        sys.exit("no CDFs found — run fetch_artemis.py first")

    # Group by (probe, date)
    def key(p):
        # tha_l2_fgm_YYYYMMDD.cdf  →  ("thb", "YYYYMMDD")
        parts = p.stem.split("_")
        return (parts[0], parts[-1])

    state_by = {key(p): p for p in state_files}
    fgm_by = {key(p): p for p in fgm_files}
    common = sorted(set(state_by.keys()) & set(fgm_by.keys()))
    print(f"paired (state ∩ fgm): {len(common)} (probe, day) combos")

    records = []
    voxel_counts = {"inner_magnetospheric": 0,
                    "magnetotail_transit": 0,
                    "outer_lunar_vicinity": 0}
    for (probe, ymd) in common:
        state_path = state_by[(probe, ymd)]
        fgm_path = fgm_by[(probe, ymd)]
        state_hour = parse_state(state_path)
        fgm_hour = parse_fgm(fgm_path)
        # join on hour
        for h in sorted(set(state_hour.keys()) & set(fgm_hour.keys())):
            x, y, z = state_hour[h]
            btot, bz, n = fgm_hour[h]
            voxel = voxelize(x, y, z)
            voxel_counts[voxel] += 1
            r_re = math.sqrt(x*x + y*y + z*z) / RE_KM
            iso = h.isoformat().replace("+00:00", "Z")
            # Emit ONE record per (t, probe, observable). The framework's
            # learner expects per-(t, voxel, observable) records; we emit
            # both observables for this hour from this probe.
            records.append({
                "t": iso, "probe": probe, "obs": "imf_btot_at_lunar_distance",
                "v": voxel, "o": btot, "units": "nT",
                "pos_gse_km": [x, y, z], "r_re": r_re,
                "n_samples": n,
            })
            records.append({
                "t": iso, "probe": probe, "obs": "imf_bz_at_lunar_distance",
                "v": voxel, "o": bz, "units": "nT",
                "pos_gse_km": [x, y, z], "r_re": r_re,
                "n_samples": n,
            })

    records.sort(key=lambda r: (r["t"], r["probe"], r["obs"]))
    OUT.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    n_hours = len({(r["t"], r["probe"]) for r in records})
    print(f"\nwrote {OUT.name}  ({len(records):,} obs records, {n_hours:,} probe-hours)")
    print("voxel coverage (per obs-record):")
    total = sum(voxel_counts.values())
    for k, v in voxel_counts.items():
        bar = "█" * (v * 40 // max(total, 1))
        print(f"  {k:24s} {v:>6d}  {100*v/max(total,1):4.1f}%  {bar}")

    # Sanity stats
    btots = [r["o"] for r in records if r["obs"] == "imf_btot_at_lunar_distance"]
    bzs = [r["o"] for r in records if r["obs"] == "imf_bz_at_lunar_distance"]
    if btots:
        print(f"\nimf_btot: n={len(btots)}  min={min(btots):.2f}  median={sorted(btots)[len(btots)//2]:.2f}  max={max(btots):.2f}  nT")
    if bzs:
        print(f"imf_bz:   n={len(bzs)}  min={min(bzs):.2f}  median={sorted(bzs)[len(bzs)//2]:+.2f}  max={max(bzs):.2f}  nT")
    print(f"r geocentric (RE): min={min(r['r_re'] for r in records):.2f}  max={max(r['r_re'] for r in records):.2f}")


if __name__ == "__main__":
    main()
