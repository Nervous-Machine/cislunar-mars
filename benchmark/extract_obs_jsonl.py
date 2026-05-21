"""
Extract per-obs JSONL from raw GRACE-FO TU Delft text files, ready for
consumption by learn_gracefo_full_year.py.

Output schema matches the existing obs JSONL:
  t        ISO timestamp of hourly bucket
  v        voxel_id (voxel_gracefo_<lat>_<lt>_<alt>)
  b        static quiet-time per-voxel median (fallback baseline)
  o        hourly-averaged observed density (kg/m^3)
  dst      Dst index at the hour
  bz       IMF Bz at the hour
  rawN     number of raw 10s samples in this hourly bucket

Lighter than re-running learn-from-grace-fo.js (which does parse + learn).
Just parse + hourly-bucket + voxel-map + write.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient

DATA_DIR = Path.home() / "space-waze" / "data" / "grace-fo" / "raw"
OUT_PATH = Path.home() / "space-waze" / "results" / "learn-gracefo-obs-multiyear.jsonl"
HOUR_S = 3600

# Voxel binning (matches voxels-v3 LATITUDE_BINS, LOCAL_TIME_BINS, GRACEFO_ALT_BIN)
LAT_BINS = [
    ("0-30N", 0, 30), ("0-30S", -30, 0),
    ("30-60N", 30, 60), ("30-60S", -60, -30),
    ("60-90N", 60, 90), ("60-90S", -90, -60),
]
# Local-time bins: dawn 3-9, noon 9-15, dusk 15-21, midnight 21-3 (wrap)
LT_BINS = [("dawn", 3, 9), ("noon", 9, 15), ("dusk", 15, 21), ("midnight", 21, 3)]
ALT_BIN_ID = "460-510"
ALT_MIN, ALT_MAX = 460.0, 510.0


def map_voxel(lat, lst, alt_km):
    if alt_km < ALT_MIN or alt_km >= ALT_MAX:
        return None
    lat_id = None
    for bid, lo, hi in LAT_BINS:
        if lat >= lo and lat < hi:
            lat_id = bid
            break
        if lat == 90 and hi == 90:
            lat_id = bid
            break
        if lat == -90 and lo == -90:
            lat_id = bid
            break
    lt_id = None
    for bid, lo, hi in LT_BINS:
        if lo < hi:
            if lst >= lo and lst < hi:
                lt_id = bid
                break
        else:
            if lst >= lo or lst < hi:
                lt_id = bid
                break
    if lat_id is None or lt_id is None:
        return None
    return f"voxel_gracefo_{lat_id}_{lt_id}_{ALT_BIN_ID}"


def parse_file(path):
    """Yields (timestamp, lat, lst, alt_km, density) records."""
    with open(path) as f:
        for line in f:
            line = line.rstrip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 12:
                continue
            try:
                t = datetime.fromisoformat(f"{parts[0]}T{parts[1]}")
            except ValueError:
                continue
            try:
                alt_m = float(parts[3])
                lon = float(parts[4])
                lat = float(parts[5])
                lst = float(parts[6])
                density = float(parts[8])
                flag = float(parts[10])
            except (ValueError, IndexError):
                continue
            if flag != 0 or density <= 0:
                continue
            yield t, lat, lst, alt_m / 1000.0, density


def main():
    files = sorted(p for p in DATA_DIR.iterdir() if p.name.startswith("GC_DNS_ACC_") and p.suffix == ".txt")
    print(f"Found {len(files)} GRACE-FO files in {DATA_DIR}")

    # Bucket by (voxel, hour_key)
    buckets = defaultdict(list)
    n_raw = 0
    n_mapped = 0
    t0 = datetime.utcnow()

    for fpath in files:
        n_file_records = 0
        for t, lat, lst, alt_km, density in parse_file(fpath):
            n_raw += 1
            voxel = map_voxel(lat, lst, alt_km)
            if voxel is None:
                continue
            hk = int(t.replace(tzinfo=timezone.utc).timestamp() // HOUR_S)
            buckets[(voxel, hk)].append(density)
            n_mapped += 1
            n_file_records += 1
        elapsed = (datetime.utcnow() - t0).total_seconds()
        print(f"  {fpath.name}: {n_file_records} mapped  "
              f"(cumulative raw={n_raw:_}, mapped={n_mapped:_}, t={elapsed:.0f}s)")

    print(f"\nHourly buckets: {len(buckets):_}  (from {n_raw:_} raw records, "
          f"{n_mapped:_} mapped)")

    # Hourly averages
    obs = []
    for (voxel, hk), densities in buckets.items():
        avg_d = sum(densities) / len(densities)
        obs.append({
            "voxel": voxel,
            "hk": hk,
            "timestamp": datetime.fromtimestamp(hk * HOUR_S, tz=timezone.utc),
            "density": avg_d,
            "rawN": len(densities),
        })
    obs.sort(key=lambda o: o["hk"])
    print(f"After hourly aggregation: {len(obs):_} hourly observations")

    # Per-voxel quiet-time median (fallback baseline `b` for JSONL)
    # We don't know quiet times yet without joining weather. Use overall median
    # per voxel — the framework's rolling causal baseline overrides this anyway.
    by_voxel = defaultdict(list)
    for o in obs:
        by_voxel[o["voxel"]].append(o["density"])
    voxel_median = {}
    for v, ds in by_voxel.items():
        s = sorted(ds)
        voxel_median[v] = s[len(s) // 2]
    print(f"Computed per-voxel medians for {len(voxel_median)} voxels")

    # Load weather_hourly from prod for dst/bz fields
    load_dotenv(Path.home() / "context-os" / ".env")
    client = MongoClient(os.getenv("MONGO_URI"), tlsCAFile=certifi.where())
    weather = {}
    for w in client["space-waze"]["weather_hourly"].find({}, {"_id": 0}):
        hk = int(w["timestamp"].replace(tzinfo=timezone.utc).timestamp() // HOUR_S)
        weather[hk] = w
    print(f"Loaded {len(weather):_} hours of weather (dst/bz lookup)")

    # Write JSONL
    print(f"\nWriting {OUT_PATH}...")
    with open(OUT_PATH, "w") as f:
        for o in obs:
            w = weather.get(o["hk"]) or weather.get(o["hk"] - 1) or weather.get(o["hk"] + 1)
            f.write(json.dumps({
                "t": o["timestamp"].isoformat().replace("+00:00", "Z").replace(".000000", ".000"),
                "v": o["voxel"],
                "b": voxel_median[o["voxel"]],
                "o": o["density"],
                "dst": w.get("dst") if w else None,
                "bz": w.get("imf_bz") if w else None,
                "rawN": o["rawN"],
            }) + "\n")
    print(f"Done. {OUT_PATH}")


if __name__ == "__main__":
    main()
