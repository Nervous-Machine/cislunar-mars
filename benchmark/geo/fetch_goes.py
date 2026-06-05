"""
GEO regime — fetch GOES + DSCOVR + indices from public SWPC JSON endpoints.

Pulls a 7-day rolling window of every observable + driver declared in
geo/validate.yaml. SWPC publishes both -1-day.json and -7-day.json snapshots
on the same field schema; the latter is a drop-in 7x widener.

Multi-year backfill path (deferred from this benchmark): NOAA NCEI's
`goes-r-series-l2-operational-space-weather-products/access/<sat>/<inst>/`
tree was created but is empty as of 2026-06; full-fidelity historical
data lives in the GOES-R AWS S3 buckets (e.g. noaa-goes16) as L1b
NetCDF at 30s–1min cadence. Wiring that requires netCDF4 + a dedicated
ingest layer; out-of-scope for this commit.

External operational comparator: SWPC REFM (Relativistic Electron Forecast
Model), pulled here as text. REFM publishes daily observed >2 MeV
electron fluence + Day 1/2/3 forecasts on ~60-day rolling history, with
its own published skill scores. This is the tier-2 baseline that
e_flux_gt_2mev edge predictions get scored against.

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

# 7-day rolling windows where available. Indices (Kp/Dst) and DSCOVR remain
# at their published cadence (Kp 30-day, Dst 7-day, DSCOVR 7-day).
ENDPOINTS = {
    # Direct error signals (target observables) — 7-day SWPC windows
    "integral_electrons":      "https://services.swpc.noaa.gov/json/goes/primary/integral-electrons-7-day.json",
    "integral_protons":        "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-7-day.json",
    "differential_electrons":  "https://services.swpc.noaa.gov/json/goes/primary/differential-electrons-7-day.json",
    "magnetometers":           "https://services.swpc.noaa.gov/json/goes/primary/magnetometers-7-day.json",
    # Solar inputs (drivers)
    "xrays":                   "https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json",
    "euvs":                    "https://services.swpc.noaa.gov/json/goes/primary/euvs-7-day.json",
    # L1 drivers (DSCOVR is 7-day natively from the SWPC products feed)
    "dscovr_plasma":           "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json",
    "dscovr_mag":              "https://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json",
    # State indices (Kp 30-day; Dst 7-day)
    "kp":                      "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
    "dst":                     "https://services.swpc.noaa.gov/products/kyoto-dst.json",
    # Event triggers
    "alerts":                  "https://services.swpc.noaa.gov/products/alerts.json",
}

# Operational comparator: REFM tabular (observed + Day-1/2/3 forecast, ~60-day
# rolling). Stored alongside JSON for the analysis stage.
TEXT_ENDPOINTS = {
    "refm":                    "https://services.swpc.noaa.gov/text/relativistic-electron-fluence-tabular.txt",
    "refm_stats":              "https://services.swpc.noaa.gov/text/relativistic-electron-fluence-statistics.txt",
    "daily_geomag":            "https://services.swpc.noaa.gov/text/daily-geomagnetic-indices.txt",
}


def fetch(name: str, url: str) -> int:
    out_ext = ".txt" if name in TEXT_ENDPOINTS else ".json"
    out = RAW / f"{name}{out_ext}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    out.write_bytes(r.content)
    return len(r.content)


def main():
    total = len(ENDPOINTS) + len(TEXT_ENDPOINTS)
    print(f"fetching {total} endpoints → {RAW}/")
    manifest = {"fetched_at": datetime.now(timezone.utc).isoformat(), "endpoints": {}}
    for name, url in {**ENDPOINTS, **TEXT_ENDPOINTS}.items():
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
