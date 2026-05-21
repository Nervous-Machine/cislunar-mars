"""
Run NRLMSISE-00 against the same 89k GRACE-FO observations our framework
was benchmarked on, with REAL F10.7/Ap from the CelesTrak archive.

Outputs JSONL in the same shape that benchmark-gracefo-obs.js consumes.

Fairness:
  - MSIS gets voxel-center lat/lon/alt (matches our framework's resolution)
  - Time is per-obs (hourly)
  - F10.7 and Ap are real daily values from CelesTrak SW-Last5Years.csv
  - Both models share the same observation set and ground truth
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from nrlmsise00 import msise_model

OBS_LOG = Path.home() / "space-waze" / "results" / "learn-gracefo-obs-multiyear.jsonl"
OUT_PATH = Path.home() / "space-waze" / "results" / "msis-preds-multiyear.jsonl"
SW_CSV = Path("/tmp/sw-all.csv")

LAT_BIN_MID = {
    "0-30N": 15, "30-60N": 45, "60-90N": 75,
    "0-30S": -15, "30-60S": -45, "60-90S": -75,
}
LT_BIN_MID = {"midnight": 0, "dawn": 6, "noon": 12, "dusk": 18}
ALT_MID_KM = 485


def parse_voxel(v):
    parts = v.replace("voxel_gracefo_", "").split("_")
    return LAT_BIN_MID[parts[0]], LT_BIN_MID[parts[1]]


def load_space_weather():
    """
    Returns dict: date_str ('YYYY-MM-DD') → (f107_obs, f107_81day, ap_avg).
    """
    sw = {}
    with open(SW_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                sw[row["DATE"]] = (
                    float(row["F10.7_OBS"]),
                    float(row["F10.7_OBS_CENTER81"]),
                    float(row["AP_AVG"]),
                )
            except (KeyError, ValueError):
                continue
    return sw


def main():
    sw = load_space_weather()
    print(f"Loaded {len(sw)} days of F10.7/Ap from CelesTrak archive")

    out = open(OUT_PATH, "w")
    n_written = 0
    n_failed = 0
    n_missing_sw = 0
    t0 = datetime.utcnow()

    with open(OBS_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)

            t = datetime.fromisoformat(o["t"].replace("Z", "+00:00")).replace(tzinfo=None)
            date_str = t.strftime("%Y-%m-%d")
            sw_today = sw.get(date_str)
            if sw_today is None:
                # Fall back to nearest available day
                n_missing_sw += 1
                # Use reasonable solar-max default
                f107_d, f107_81, ap = 160.0, 165.0, 15.0
            else:
                f107_d, f107_81, ap = sw_today

            lat, lt_h = parse_voxel(o["v"])
            utc_h = t.hour + t.minute / 60.0
            lon = (lt_h - utc_h) * 15.0
            while lon > 180:
                lon -= 360
            while lon < -180:
                lon += 360

            try:
                densities, _temps = msise_model(t, ALT_MID_KM, lat, lon,
                                                f107_81, f107_d, ap, lst=lt_h)
                pred_kgm3 = densities[5] * 1000.0
            except Exception as e:
                n_failed += 1
                continue

            out.write(json.dumps({
                "t": o["t"],
                "v": o["v"],
                "b": o["b"],
                "o": o["o"],
                "p": pred_kgm3,
                "dst": o.get("dst"),
                "bz": o.get("bz"),
                "f107": f107_d,
                "ap": ap,
            }) + "\n")
            n_written += 1
            if n_written % 20000 == 0:
                elapsed = (datetime.utcnow() - t0).total_seconds()
                print(f"  {n_written} predictions  ({n_written/elapsed:.0f}/s)")

    out.close()
    elapsed = (datetime.utcnow() - t0).total_seconds()
    print(f"\nDone. {n_written} written, {n_failed} failed, "
          f"{n_missing_sw} obs without SW data (default-filled).")
    print(f"Output: {OUT_PATH}")


if __name__ == "__main__":
    main()
