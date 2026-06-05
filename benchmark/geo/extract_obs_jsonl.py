"""
GEO regime — extract per-(timestamp, voxel, observable) JSONL records with
aligned driver state.

Voxelization: 6 LT bins per geo/prior.yaml (lt_0_4, lt_4_8, lt_8_12, lt_12_16,
lt_16_20, lt_20_24). GOES-19 is the primary in 2026 at ~75.2°W; its local
time follows UTC − 5.01h and sweeps all 6 voxels every 24h.

Observables (target observables in geo/prior.yaml):
    e_flux_gt_2mev      ← integral_electrons (>=2 MeV channel)
    p_flux_gt_10mev     ← integral_protons (>=10 MeV channel)
    p_flux_gt_50mev     ← integral_protons (>=50 MeV channel)
    b_field_magnitude   ← magnetometers (total)
    e_flux_warm_plasma  ← differential_electrons (79 keV channel) — proxy
                          for the MPS-LO 1-50 keV target in prior.yaml.
                          SWPC primary differential feed starts at 79 keV;
                          the true 1-50 keV band requires L1b MPS-LO ingest
                          which is deferred (see README "Hot-plasma gap").
                          79 keV is the closest available proxy and still
                          measures substorm-injection signature.

Drivers (aligned by nearest-time lookup):
    sw_speed, sw_density (DSCOVR plasma)
    imf_bz, imf_bt (DSCOVR mag)
    xrs_long (GOES-XRS B channel 0.1-0.8 nm — flare proxy / SEP precursor)
    mgii_index (GOES-EUVS — solar EUV proxy)
    kp_index (3-hour Kp)
    dst (1-hour Dst)
"""

import bisect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Shared SWPC alerts parser lives one directory up (used by GEO + Mars).
sys.path.insert(0, str(Path(__file__).parent.parent))
from sep_alerts import parse_alerts, driver_state as sep_driver_state, summarize as sep_summarize

RAW = Path(__file__).parent / "raw"
OUT = Path(__file__).parent / "obs.jsonl"

GOES_LONGITUDE_DEG = -75.2          # GOES-19 east position (negative = west)
LT_OFFSET_HOURS = GOES_LONGITUDE_DEG / 15.0


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def lt_voxel(t: datetime) -> str:
    lt = (t.hour + t.minute / 60 + t.second / 3600 + LT_OFFSET_HOURS) % 24
    if lt < 4:  return "lt_0_4"
    if lt < 8:  return "lt_4_8"
    if lt < 12: return "lt_8_12"
    if lt < 16: return "lt_12_16"
    if lt < 20: return "lt_16_20"
    return "lt_20_24"


def load(name: str):
    return json.loads((RAW / f"{name}.json").read_text())


def header_table(rows):
    """SWPC plasma/mag JSON is [header, *data_rows]; convert to list of dicts."""
    if not rows:
        return []
    hdr = rows[0]
    out = []
    for row in rows[1:]:
        d = dict(zip(hdr, row))
        out.append(d)
    return out


def build_driver_series():
    """Return dict: driver_name -> (sorted_ts, values).  Used for nearest-time lookup."""
    series = {}

    plasma = header_table(load("dscovr_plasma"))
    series["sw_speed"]   = ([parse_iso(r["time_tag"]) for r in plasma if r.get("speed")  not in (None,"")],
                            [float(r["speed"])   for r in plasma if r.get("speed")  not in (None,"")])
    series["sw_density"] = ([parse_iso(r["time_tag"]) for r in plasma if r.get("density") not in (None,"")],
                            [float(r["density"]) for r in plasma if r.get("density") not in (None,"")])

    mag = header_table(load("dscovr_mag"))
    # DSCOVR mag schema: time_tag, bx_gsm, by_gsm, bz_gsm, lon_gsm, lat_gsm, bt
    bz_idx = "bz_gsm"; bt_idx = "bt"
    series["imf_bz"] = ([parse_iso(r["time_tag"]) for r in mag if r.get(bz_idx) not in (None,"")],
                        [float(r[bz_idx]) for r in mag if r.get(bz_idx) not in (None,"")])
    series["imf_bt"] = ([parse_iso(r["time_tag"]) for r in mag if r.get(bt_idx) not in (None,"")],
                        [float(r[bt_idx]) for r in mag if r.get(bt_idx) not in (None,"")])

    xrays = load("xrays")
    xb = [r for r in xrays if r.get("energy") == "0.1-0.8nm"]
    series["xrs_long"] = ([parse_iso(r["time_tag"]) for r in xb],
                          [float(r["observed_flux"]) for r in xb])

    euvs = load("euvs")
    mg = [r for r in euvs if r.get("line") == "mgii_index" and r.get("value") is not None]
    series["mgii_index"] = ([parse_iso(r["time_tag"]) for r in mg],
                            [float(r["value"]) for r in mg])

    kp = load("kp")
    series["kp_index"] = ([parse_iso(r["time_tag"].replace(" ", "T") + "Z" if "T" not in r["time_tag"] else r["time_tag"]) for r in kp],
                          [float(r["Kp"]) for r in kp])

    dst = load("dst")
    series["dst"] = ([parse_iso(r["time_tag"].replace(" ", "T") + "Z" if "T" not in r["time_tag"] else r["time_tag"]) for r in dst],
                     [float(r["dst"]) for r in dst])

    return series


def nearest(series, t):
    ts, vs = series
    if not ts:
        return None
    i = bisect.bisect_left(ts, t)
    if i == 0: return vs[0]
    if i >= len(ts): return vs[-1]
    return vs[i] if (ts[i] - t) < (t - ts[i-1]) else vs[i-1]


def driver_state(drivers, t, sep_timeline=None):
    state = {k: nearest(v, t) for k, v in drivers.items()}
    if sep_timeline is not None:
        state.update(sep_driver_state(sep_timeline, t))
    return state


# --- Observable extractors ----
def extract_electrons(drivers, sep_timeline):
    rows = load("integral_electrons")
    out = []
    for r in rows:
        if r.get("energy") != ">=2 MeV": continue
        t = parse_iso(r["time_tag"])
        out.append({
            "t": r["time_tag"], "v": lt_voxel(t),
            "obs": "e_flux_gt_2mev", "o": float(r["flux"]),
            "satellite": r["satellite"], "d": driver_state(drivers, t, sep_timeline),
        })
    return out


def extract_protons(drivers, channel: str, obs_name: str, sep_timeline):
    rows = load("integral_protons")
    out = []
    for r in rows:
        if r.get("energy") != channel: continue
        t = parse_iso(r["time_tag"])
        out.append({
            "t": r["time_tag"], "v": lt_voxel(t),
            "obs": obs_name, "o": float(r["flux"]),
            "satellite": r["satellite"], "d": driver_state(drivers, t, sep_timeline),
        })
    return out


def extract_mag(drivers, sep_timeline):
    rows = load("magnetometers")
    out = []
    for r in rows:
        t = parse_iso(r["time_tag"])
        out.append({
            "t": r["time_tag"], "v": lt_voxel(t),
            "obs": "b_field_magnitude", "o": float(r["total"]),
            "satellite": r["satellite"], "d": driver_state(drivers, t, sep_timeline),
        })
    return out


def extract_warm_plasma(drivers, sep_timeline):
    """79 keV differential electron channel as a proxy for the 1-50 keV
    MPS-LO band declared in prior.yaml. 79 keV is the lowest channel in
    SWPC's primary differential-electrons feed."""
    rows = load("differential_electrons")
    out = []
    for r in rows:
        if r.get("energy") != "79 keV": continue
        flux = r.get("flux")
        if flux is None or flux <= 0: continue
        t = parse_iso(r["time_tag"])
        out.append({
            "t": r["time_tag"], "v": lt_voxel(t),
            "obs": "e_flux_warm_plasma", "o": float(flux),
            "satellite": r["satellite"], "d": driver_state(drivers, t, sep_timeline),
        })
    return out


def main():
    print("building driver series from raw/…")
    drivers = build_driver_series()
    for k, (ts, vs) in drivers.items():
        span_h = (ts[-1] - ts[0]).total_seconds() / 3600 if ts else 0
        print(f"  {k:14s} {len(ts):>5d} points, {span_h:>5.1f}h span")

    print("parsing SWPC alerts…")
    sep_timeline = parse_alerts(RAW / "alerts.json")
    print(sep_summarize(sep_timeline))

    print("extracting observations…")
    obs = []
    obs += extract_electrons(drivers, sep_timeline)
    obs += extract_protons(drivers, ">=10 MeV", "p_flux_gt_10mev", sep_timeline)
    obs += extract_protons(drivers, ">=50 MeV", "p_flux_gt_50mev", sep_timeline)
    obs += extract_mag(drivers, sep_timeline)
    obs += extract_warm_plasma(drivers, sep_timeline)
    print(f"  {len(obs)} total records")

    by_obs = {}
    for r in obs:
        by_obs.setdefault(r["obs"], 0)
        by_obs[r["obs"]] += 1
    for k, n in sorted(by_obs.items()):
        print(f"    {k:24s} {n:>6d}")

    by_vox = {}
    for r in obs:
        by_vox.setdefault(r["v"], 0); by_vox[r["v"]] += 1
    print("  voxel coverage:")
    for v in ["lt_0_4","lt_4_8","lt_8_12","lt_12_16","lt_16_20","lt_20_24"]:
        print(f"    {v:10s} {by_vox.get(v,0):>5d}")

    with OUT.open("w") as f:
        for r in obs:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
