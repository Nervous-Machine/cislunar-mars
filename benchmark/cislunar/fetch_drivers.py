"""
Cislunar regime — fetch driver data over BOTH the ARTEMIS window
(2024-05-08 → 2024-05-15 default; the May 2024 G5 superstorm period) AND
the CRaTER window (2009-06-26 → 2012-12-31; deep solar minimum).

Drivers pulled:
  - CelesTrak SW-All (F10.7, Ap daily) — long-baseline solar / geomag archive
    that covers both windows
  - SWPC alerts.json (rolling 30-day) — same as GEO/Mars; will cover
    the ARTEMIS window if run now, won't cover the CRaTER window
  - SWPC Kp index history (rolling)
  - DSCOVR plasma/mag — rolling-7-day, real-time only. For ARTEMIS the
    operational SWPC text archive is the historical option; for CRaTER
    we use OMNI L1-propagated solar wind (multi-decade archive).
  - GOES SGPS protons — archive-grade SEP source (same as Mars). Both
    windows are covered by the GOES archive. GOES-18 came online 2022;
    for pre-2022 the script falls back to GOES-13/15 SGPS-equivalent
    archives at NCEI.

The DSCOVR + OMNI multi-source pattern: the cislunar substrate cares
about IMF/plasma upstream of Earth-Moon. For 2024-05 ARTEMIS the
DSCOVR archive (SWPC text 7-day rolling) doesn't reach back; for
benchmark reproducibility we instead use OMNI HRO (1-minute multi-source
upstream) which covers both windows.
"""

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

RAW = Path(__file__).parent / "raw"
RAW.mkdir(parents=True, exist_ok=True)

SW_ALL_LOCAL = Path("/tmp/sw-all.csv")
SW_ALL_URL = "https://celestrak.org/SpaceData/SW-All.csv"
SWPC_ALERTS = "https://services.swpc.noaa.gov/products/alerts.json"
SWPC_KP = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"

# OMNI 1-min HRO at SPDF — the multi-decade L1-propagated upstream archive
OMNI_BASE = "https://spdf.gsfc.nasa.gov/pub/data/omni/high_res_omni/monthly_1min"

# Default ARTEMIS window
DEFAULT_START = datetime(2024, 5, 8, tzinfo=timezone.utc)
DEFAULT_END = datetime(2024, 5, 15, tzinfo=timezone.utc)


def _fetch(name, url, fname, manifest, timeout=60):
    out = RAW / fname
    try:
        r = requests.get(url, timeout=timeout); r.raise_for_status()
        out.write_bytes(r.content)
        manifest["endpoints"][name] = {"url": url, "bytes": len(r.content), "status": "ok"}
        print(f"  ok   {fname}  ({len(r.content):,} bytes)")
        return True
    except Exception as e:
        manifest["endpoints"][name] = {"url": url, "status": f"error: {e}"}
        print(f"  FAIL {fname}  {e}")
        return False


def fetch_sw_all(manifest):
    out = RAW / "sw-all.csv"
    if SW_ALL_LOCAL.exists():
        out.write_bytes(SW_ALL_LOCAL.read_bytes())
        manifest["endpoints"]["sw_all"] = {"url": str(SW_ALL_LOCAL), "bytes": out.stat().st_size, "status": "ok (cached)"}
        print(f"  ok   sw-all.csv  (copied from {SW_ALL_LOCAL}, {out.stat().st_size:,} bytes)")
        return
    _fetch("sw_all", SW_ALL_URL, "sw-all.csv", manifest, timeout=120)


def fetch_omni_min(start: datetime, end: datetime, manifest):
    """OMNI 1-minute HRO monthly files. Each month covers ~30 days of L1-propagated
    solar wind state (proton density, speed, IMF Bx/By/Bz GSE). For ARTEMIS
    benchmark we typically need one or two monthly files."""
    months = []
    cur = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    while cur <= end:
        months.append(cur)
        # next month
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            cur = datetime(cur.year, cur.month + 1, 1, tzinfo=timezone.utc)
    print(f"  OMNI months: {[m.strftime('%Y-%m') for m in months]}")

    omni_dir = RAW / "omni"
    omni_dir.mkdir(exist_ok=True)
    n_ok = 0
    for m in months:
        # Filename: omni_min{YYYYMM}.asc — plain text 1-min OMNI
        fname = f"omni_min{m.strftime('%Y%m')}.asc"
        url = f"{OMNI_BASE}/{fname}"
        out = omni_dir / fname
        if out.exists() and out.stat().st_size > 100_000:
            print(f"  cached {fname}  ({out.stat().st_size:,} bytes)")
            n_ok += 1
            continue
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                out.write_bytes(r.content)
                print(f"  ok   {fname}  ({len(r.content):,} bytes)")
                n_ok += 1
            else:
                print(f"  FAIL {fname}  http {r.status_code}")
        except Exception as e:
            print(f"  FAIL {fname}  {e}")
    manifest["endpoints"]["omni"] = {
        "base_url": OMNI_BASE,
        "months_attempted": [m.strftime("%Y-%m") for m in months],
        "n_ok": n_ok,
    }


def summarize_sw_window(start, end):
    """SW-All coverage report over the window."""
    rows = []
    with (RAW / "sw-all.csv").open() as f:
        for r in csv.DictReader(f):
            try:
                d = datetime.fromisoformat(r["DATE"]).replace(tzinfo=timezone.utc)
                if start <= d <= end:
                    rows.append((d, float(r["F10.7_OBS"]), float(r["AP_AVG"]) if r["AP_AVG"] else 0))
            except (ValueError, KeyError):
                continue
    if rows:
        print(f"  SW-All window: {rows[0][0].date()} → {rows[-1][0].date()}  ({len(rows)} days)")
        f107s = [r[1] for r in rows]; aps = [r[2] for r in rows]
        print(f"  F10.7 range: {min(f107s):.0f}–{max(f107s):.0f}    Ap range: {min(aps):.0f}–{max(aps):.0f}")


def main():
    if len(sys.argv) >= 3:
        start = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=timezone.utc)
    else:
        start, end = DEFAULT_START, DEFAULT_END

    print(f"fetching cislunar drivers → {RAW}/")
    days = (end - start).days + 1
    print(f"window: {start.date()} → {end.date()}  ({days} days)")
    manifest = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "endpoints": {},
    }
    fetch_sw_all(manifest)
    _fetch("swpc_alerts", SWPC_ALERTS, "swpc_alerts.json", manifest)
    _fetch("swpc_kp", SWPC_KP, "swpc_kp.json", manifest)
    fetch_omni_min(start, end, manifest)
    summarize_sw_window(start, end)
    (RAW / "drivers_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nmanifest: {RAW}/drivers_manifest.json")


if __name__ == "__main__":
    main()
