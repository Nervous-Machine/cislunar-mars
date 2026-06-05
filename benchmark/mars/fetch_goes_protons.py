"""
Mars regime — fetch GOES-18 SGPS proton flux (5-minute averages) over the
benchmark window and reduce to hourly >=10 MeV integral flux.

Why we need this: the SWPC alerts.json feed is rolling 30-day only. For
a real-data RAD benchmark window of 2025-05-22 → 2025-11-04, alerts.json
covers nothing. The actual GOES proton sensor data is in NOAA's NGDC
archive (sgps-l2-avg5m, daily netCDF files, ~600 KB each).

We extract:
  >=10 MeV integral flux  = sum of diff channels with effective energy
                           >= 10 MeV, multiplied by their bin widths
                           (Σ flux_i × ΔE_i over channels ≥10 MeV)
  Units: protons / (cm^2 s sr)  — same as the SWPC SEP alert threshold
         (10 pfu @ ≥10 MeV triggers S1)

For each hour, we take the max 5-minute >=10 MeV flux in the hour
(SEP detection is impulse-driven, not time-averaged-driven).

Cadence reduction: 12 × 5-min samples per hour → 1 hourly max value.
Output: raw/goes_protons_hourly.jsonl

Reproduce: python3 fetch_goes_protons.py
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import netCDF4 as nc
import numpy as np
import requests

RAW = Path(__file__).parent / "raw"
PROTON_DIR = RAW / "goes_protons"
RAW.mkdir(exist_ok=True)
PROTON_DIR.mkdir(exist_ok=True)
OUT = RAW / "goes_protons_hourly.jsonl"

# Match the RAD window
DEFAULT_END = datetime(2025, 11, 4, tzinfo=timezone.utc)
DEFAULT_START = DEFAULT_END - timedelta(days=166)

GOES_BASE = ("https://data.ngdc.noaa.gov/platforms/"
             "solar-space-observing-satellites/goes/goes18/l2/data/"
             "sgps-l2-avg5m")

THRESHOLD_KEV = 10_000   # >=10 MeV per SWPC SEP S-scale


def url_for(date_utc: datetime) -> str:
    return (f"{GOES_BASE}/{date_utc.year:04d}/{date_utc.month:02d}/"
            f"sci_sgps-l2-avg5m_g18_d{date_utc.strftime('%Y%m%d')}_v3-0-2.nc")


def fetch_day(date_utc: datetime, manifest_entry):
    out = PROTON_DIR / f"g18_{date_utc.strftime('%Y%m%d')}.nc"
    if out.exists() and out.stat().st_size > 1000:
        manifest_entry["status"] = "cached"
        manifest_entry["bytes"] = out.stat().st_size
        return out
    url = url_for(date_utc)
    try:
        r = requests.get(url, timeout=60)
        if r.status_code != 200:
            manifest_entry["status"] = f"http {r.status_code}"
            return None
        out.write_bytes(r.content)
        manifest_entry["status"] = "ok"
        manifest_entry["bytes"] = len(r.content)
        return out
    except Exception as e:
        manifest_entry["status"] = f"error: {e}"
        return None


def integral_above_threshold(diff_flux, lower_kev, upper_kev, threshold_kev):
    """Σ flux_i × ΔE_i for channels with effective energy ≥ threshold.

    diff_flux shape (sensor_units=2, diff_channels=13).
    Take mean across sensor_units for robustness.

    Returns flux in protons/(cm^2 s sr) — effectively summed differential
    flux × channel widths over included channels.
    """
    # mean across the two HEPAD sensors
    flux = np.nanmean(diff_flux, axis=0)  # shape (13,)
    lower = np.nanmean(lower_kev, axis=0)
    upper = np.nanmean(upper_kev, axis=0)
    widths_mev = (upper - lower) / 1000.0
    centers_kev = (upper + lower) / 2.0
    mask = centers_kev >= threshold_kev
    # diff flux is in protons/(cm^2 s sr keV) — multiply by width to get integral
    # (the SGPS diff flux unit is protons/(cm^2 s sr keV))
    # 1 MeV = 1000 keV
    contributions = flux * (widths_mev * 1000.0)  # back to keV widths
    return float(np.nansum(contributions[mask]))


def parse_day(nc_path: Path):
    """Read one day's SGPS file → list of (utc_dt, integral_flux_ge_10mev)."""
    out = []
    ds = nc.Dataset(nc_path)
    times = ds.variables["time"][:]
    time_units = ds.variables["time"].units  # "seconds since 2000-01-01 12:00:00 UTC"
    epoch = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    diff = ds.variables["AvgDiffProtonFlux"][:]            # (time, sensor_units, channels)
    lower = ds.variables["DiffProtonLowerEnergy"][:]       # (sensor_units, channels)
    upper = ds.variables["DiffProtonUpperEnergy"][:]
    fill = ds.variables["AvgDiffProtonFlux"]._FillValue

    diff = np.where(diff == fill, np.nan, diff)

    for i, t_sec in enumerate(times):
        dt = epoch + timedelta(seconds=float(t_sec))
        flux = integral_above_threshold(diff[i], lower, upper, THRESHOLD_KEV)
        out.append((dt, flux))
    ds.close()
    return out


def hourly_max(samples):
    """Reduce 5-min samples → max per UTC hour.
    samples: list of (datetime, flux). Returns {hour_dt -> max_flux}."""
    bucket = {}
    for dt, fl in samples:
        if not np.isfinite(fl):
            continue
        h = dt.replace(minute=0, second=0, microsecond=0)
        if h not in bucket or fl > bucket[h]:
            bucket[h] = fl
    return bucket


def main():
    if len(sys.argv) >= 3:
        start = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=timezone.utc)
    else:
        start, end = DEFAULT_START, DEFAULT_END

    print(f"fetching GOES-18 SGPS proton archive for {start.date()} → {end.date()}")
    print(f"  base: {GOES_BASE}")
    print(f"  out:  {PROTON_DIR}")

    manifest = {
        "base_url": GOES_BASE,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "threshold_kev": THRESHOLD_KEV,
        "days": [],
    }
    day = start
    n_ok = n_cached = n_fail = 0
    nc_paths = []
    t0 = time.time()
    while day <= end:
        entry = {"date": day.date().isoformat()}
        path = fetch_day(day, entry)
        manifest["days"].append(entry)
        if path:
            nc_paths.append(path)
            if entry["status"] == "ok":
                n_ok += 1
            else:
                n_cached += 1
        else:
            n_fail += 1
        day += timedelta(days=1)
    print(f"  fetched: ok={n_ok}  cached={n_cached}  fail={n_fail}  ({time.time()-t0:.1f}s)")

    # Parse all days, build hourly series
    all_samples = []
    for p in nc_paths:
        try:
            all_samples.extend(parse_day(p))
        except Exception as e:
            print(f"  parse fail {p.name}: {e}")

    hourly = hourly_max(all_samples)
    print(f"  {len(all_samples):,} 5-min samples → {len(hourly):,} hourly max records")

    # Write JSONL
    with OUT.open("w") as f:
        for h in sorted(hourly):
            f.write(json.dumps({
                "t": h.isoformat().replace("+00:00", "Z"),
                "flux_ge_10mev": hourly[h],
                "units": "protons/(cm^2 s sr)",
                "source": "goes18_sgps_l2_avg5m",
                "reduction": "hourly_max",
            }) + "\n")

    # Quick stats: identify SEP events (>=10 pfu sustained)
    vals = sorted(hourly.values())
    n = len(vals)
    if n:
        p50 = vals[n // 2]
        p90 = vals[9 * n // 10]
        p99 = vals[99 * n // 100]
        n_sep = sum(1 for v in vals if v >= 10)
        print(f"\n>=10 MeV integral flux distribution (protons/cm^2/s/sr):")
        print(f"  p50: {p50:.3g}    p90: {p90:.3g}    p99: {p99:.3g}    max: {vals[-1]:.3g}")
        print(f"  hours with flux >= 10 pfu (S1 threshold): {n_sep} / {n}")

    (RAW / "goes_protons_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nwrote {OUT.name}")


if __name__ == "__main__":
    main()
