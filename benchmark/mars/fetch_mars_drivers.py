"""
Mars regime — fetch real public driver data over the RAD-aligned window.

Pulls:
  - CelesTrak SW-All (F10.7 daily, Ap daily) — long-baseline solar /
    geomagnetic archive
  - SWPC alerts.json (rolling 30-day) — SEP/CME event triggers; kept for
    skeleton continuity but does NOT overlap the historical RAD window
    (see fetch_goes_protons.py for the archive-grade SEP source)
  - SWPC Kp index history (rolling)

Window: defaults to the same range as fetch_rad.py (2025-05-22 →
2025-11-04, the most recent 166 days of MSL/RAD PDS coverage). The
historical archives (SW-All, OMNI, GOES SGPS) cover this window. The
SWPC alerts feed does not — sep_proton driver is supplied by
fetch_goes_protons.py for the historical window instead.
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

# Window: matches fetch_rad.py default (recent ~166 days of MSL/RAD coverage).
WINDOW_END = datetime(2025, 11, 4, tzinfo=timezone.utc)
WINDOW_START = WINDOW_END - timedelta(days=166)


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
    days = (WINDOW_END - WINDOW_START).days
    print(f"window: {WINDOW_START.date()} → {WINDOW_END.date()}  ({days} days)")
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
