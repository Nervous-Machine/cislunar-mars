"""
GEO regime — fetch GOES + DSCOVR + indices from public SWPC JSON endpoints.

Skeleton scope: pulls a 1-day rolling snapshot of every endpoint declared in
geo/validate.yaml. This is plumbing-proof, not multi-year backfill. For real
multi-year benchmark, swap the SWPC 1-day URLs for NCEI archive pulls (the
NOAA NGDC / NCEI archive at https://www.ncei.noaa.gov/data/goes-space-environment-monitor/access/full/
holds historical GOES-R data on the same field schema).

GOES X-Ray Sensor (XRS) and Extreme-Ultraviolet Sensor (EUVS) on EXIS are
included as solar-input drivers — XRS for flare onset (precursor to SEP),
EUVS for EUV / Mg II index (thermospheric / ionospheric driving).

Outputs to ./raw/<source>.json — re-runnable.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

import requests   # certifi-backed; same convention as ~/NM-learning-loop/mcp_validation.py

RAW = Path(__file__).parent / "raw"
RAW.mkdir(exist_ok=True)

ENDPOINTS = {
    # Direct error signals (target observables)
    "integral_electrons":      "https://services.swpc.noaa.gov/json/goes/primary/integral-electrons-1-day.json",
    "integral_protons":        "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json",
    "differential_electrons":  "https://services.swpc.noaa.gov/json/goes/primary/differential-electrons-1-day.json",
    "magnetometers":           "https://services.swpc.noaa.gov/json/goes/primary/magnetometers-1-day.json",
    # Solar inputs (drivers)
    "xrays":                   "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json",
    "euvs":                    "https://services.swpc.noaa.gov/json/goes/primary/euvs-1-day.json",
    # L1 drivers
    "dscovr_plasma":           "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json",
    "dscovr_mag":              "https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json",
    # State indices
    "kp":                      "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
    "dst":                     "https://services.swpc.noaa.gov/products/kyoto-dst.json",
    # Event triggers
    "alerts":                  "https://services.swpc.noaa.gov/products/alerts.json",
}


def fetch(name: str, url: str) -> int:
    out = RAW / f"{name}.json"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    out.write_bytes(r.content)
    return len(r.content)


def main():
    print(f"fetching {len(ENDPOINTS)} endpoints → {RAW}/")
    manifest = {"fetched_at": datetime.now(timezone.utc).isoformat(), "endpoints": {}}
    for name, url in ENDPOINTS.items():
        try:
            n = fetch(name, url)
            manifest["endpoints"][name] = {"url": url, "bytes": n, "status": "ok"}
            print(f"  ok   {name:24s} {n:>10,} bytes")
        except Exception as e:
            manifest["endpoints"][name] = {"url": url, "status": f"error: {e}"}
            print(f"  FAIL {name:24s} {e}")
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
