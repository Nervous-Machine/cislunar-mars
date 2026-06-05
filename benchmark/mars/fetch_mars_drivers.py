"""
Mars regime — fetch real public driver data (no ground truth yet — see
generate_rad_synthetic.py for that gap).

Pulls:
  - CelesTrak SW-All (F10.7 daily, Ap daily, going back to 1957) — the
    long-baseline solar/geomagnetic archive already used by the LEO benchmark
  - SWPC alerts.json (rolling 1-day) — SEP/CME event triggers; for skeleton
    we extract event timestamps to seed synthetic SEP injections at real
    recent event times
  - SWPC Kp index history (rolling) — 3-hour Kp

Skeleton scope: covers a 1-Earth-year window so Mars voxelization (4 Ls bins
of 90° each ~ 172 Earth days) can exercise multiple voxels. Real MSL/RAD
ground truth would come from PDS — see README's "Deferred" for the path.
"""

import csv
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests

RAW = Path(__file__).parent / "raw"
RAW.mkdir(exist_ok=True)

SW_ALL_LOCAL = Path("/tmp/sw-all.csv")          # already cached from LEO work
SW_ALL_URL = "https://celestrak.org/SpaceData/SW-All.csv"
SWPC_ALERTS = "https://services.swpc.noaa.gov/products/alerts.json"
SWPC_KP = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"

# Skeleton window: last 1 Earth year (covers ~190° of Ls — exercises 2-3 voxels)
WINDOW_END = datetime(2026, 5, 22, tzinfo=timezone.utc)
WINDOW_START = WINDOW_END - timedelta(days=365)


def fetch_sw_all(manifest):
    out = RAW / "sw-all.csv"
    if SW_ALL_LOCAL.exists():
        out.write_bytes(SW_ALL_LOCAL.read_bytes())
        manifest["endpoints"]["sw_all"] = {"url": str(SW_ALL_LOCAL), "bytes": out.stat().st_size, "status": "ok (cached)"}
        print(f"  ok   sw-all.csv  (copied from {SW_ALL_LOCAL}, {out.stat().st_size:,} bytes)")
        return
    try:
        r = requests.get(SW_ALL_URL, timeout=60); r.raise_for_status()
        out.write_bytes(r.content)
        manifest["endpoints"]["sw_all"] = {"url": SW_ALL_URL, "bytes": len(r.content), "status": "ok"}
        print(f"  ok   sw-all.csv  (fetched, {len(r.content):,} bytes)")
    except Exception as e:
        manifest["endpoints"]["sw_all"] = {"url": SW_ALL_URL, "status": f"error: {e}"}
        print(f"  FAIL sw-all.csv  {e}")


def _fetch(manifest, name, url, fname):
    out = RAW / fname
    try:
        r = requests.get(url, timeout=30); r.raise_for_status()
        out.write_bytes(r.content)
        manifest["endpoints"][name] = {"url": url, "bytes": len(r.content), "status": "ok"}
        print(f"  ok   {fname}  ({len(r.content):,} bytes)")
    except Exception as e:
        manifest["endpoints"][name] = {"url": url, "status": f"error: {e}"}
        print(f"  FAIL {fname}  {e}")


def fetch_swpc_alerts(manifest):
    _fetch(manifest, "swpc_alerts", SWPC_ALERTS, "swpc_alerts.json")


def fetch_swpc_kp(manifest):
    _fetch(manifest, "swpc_kp", SWPC_KP, "swpc_kp.json")


def summarize_window():
    """Quick check that SW-All covers the skeleton window."""
    rows = []
    with (RAW / "sw-all.csv").open() as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                d = datetime.fromisoformat(r["DATE"]).replace(tzinfo=timezone.utc)
                if WINDOW_START <= d <= WINDOW_END:
                    rows.append((d, float(r["F10.7_OBS"]), float(r["AP_AVG"]) if r["AP_AVG"] else 0))
            except (ValueError, KeyError):
                continue
    if rows:
        print(f"  SW-All window: {rows[0][0].date()} → {rows[-1][0].date()}  ({len(rows)} days)")
        f107s = [r[1] for r in rows]
        aps = [r[2] for r in rows]
        print(f"  F10.7 range: {min(f107s):.0f}–{max(f107s):.0f}    Ap range: {min(aps):.0f}–{max(aps):.0f}")


def main():
    print(f"fetching Mars-regime drivers → {RAW}/")
    print(f"window: {WINDOW_START.date()} → {WINDOW_END.date()}  (365 days)")
    manifest = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "endpoints": {},
    }
    fetch_sw_all(manifest)
    fetch_swpc_alerts(manifest)
    fetch_swpc_kp(manifest)
    summarize_window()
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
