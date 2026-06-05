"""
Cislunar regime — fetch THEMIS-ARTEMIS L2 FGM + L1 STATE CDFs for the
benchmark window over both probes (THB = P1, THC = P2).

Endpoint:
    http://themis.ssl.berkeley.edu/data/themis/{probe}/l2/fgm/YYYY/
        {probe}_l2_fgm_YYYYMMDD_v01.cdf       — 3-second FGM (B field GSE/GSM)
    http://themis.ssl.berkeley.edu/data/themis/{probe}/l1/state/YYYY/
        {probe}_l1_state_YYYYMMDD_v02.cdf     — 1-minute spacecraft position
                                                 (GSE, GSM, SEL, SSE)

Per-file size: FGM ~20-25 MB/day; STATE ~600 KB/day. For a 30-day window
over two probes the FGM data set is ~1.5 GB raw; the STATE data is ~36 MB.

Window: defaults to 2024-05-01 → 2024-05-31 (the May 2024 G5 superstorm
window, which contains the largest sustained SEP event of solar cycle 25
and the strongest geomagnetic storm since 2003). This is the cislunar
test window most analogous to LEO's storm-rich training data.

State files are pulled separately (smaller, mandatory for voxel
assignment by spacecraft GSE position). FGM is the primary observable
source.

Reproduce:
    python3 fetch_artemis.py
    python3 fetch_artemis.py 2024-05-01 2024-05-31     # explicit window
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

RAW = Path(__file__).parent / "raw"
ARTEMIS_DIR = RAW / "artemis"
ARTEMIS_DIR.mkdir(parents=True, exist_ok=True)

BASE = "http://themis.ssl.berkeley.edu/data/themis"
PROBES = ["thb", "thc"]   # P1, P2 — both at lunar distance since 2011

DEFAULT_START = datetime(2024, 5, 1, tzinfo=timezone.utc)
DEFAULT_END = datetime(2024, 5, 31, tzinfo=timezone.utc)


def fgm_url(probe: str, d: datetime) -> str:
    return (f"{BASE}/{probe}/l2/fgm/{d.year:04d}/"
            f"{probe}_l2_fgm_{d.strftime('%Y%m%d')}_v01.cdf")


def state_url(probe: str, d: datetime) -> str:
    # Try v02 (definitive) → v01 (definitive older) → no-suffix (current)
    return (f"{BASE}/{probe}/l1/state/{d.year:04d}/"
            f"{probe}_l1_state_{d.strftime('%Y%m%d')}_v02.cdf")


def fetch_file(url: str, out: Path) -> dict:
    if out.exists() and out.stat().st_size > 10_000:
        return {"status": "cached", "bytes": out.stat().st_size, "url": url}
    try:
        r = requests.get(url, timeout=300, allow_redirects=True)
        if r.status_code != 200:
            return {"status": f"http {r.status_code}", "url": url}
        out.write_bytes(r.content)
        return {"status": "ok", "bytes": len(r.content), "url": url}
    except Exception as e:
        return {"status": f"error: {e}", "url": url}


def main():
    if len(sys.argv) >= 3:
        start = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=timezone.utc)
    else:
        start, end = DEFAULT_START, DEFAULT_END

    days = (end - start).days + 1
    print(f"fetching THEMIS-ARTEMIS L2 FGM + L1 STATE for {start.date()} → {end.date()}")
    print(f"  probes: {PROBES} ({len(PROBES)} probes × {days} days × 2 file types = "
          f"{len(PROBES)*days*2} files)")
    print(f"  out: {ARTEMIS_DIR}")
    manifest = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "probes": PROBES,
        "base_url": BASE,
        "files": [],
    }

    t0 = time.time()
    n_ok = n_cached = n_fail = 0
    by_kind = {"fgm": {"ok": 0, "cached": 0, "fail": 0},
               "state": {"ok": 0, "cached": 0, "fail": 0}}
    for probe in PROBES:
        for i in range(days):
            d = start + timedelta(days=i)
            # FGM
            f_out = ARTEMIS_DIR / f"{probe}_l2_fgm_{d.strftime('%Y%m%d')}.cdf"
            entry = fetch_file(fgm_url(probe, d), f_out)
            entry["kind"] = "fgm"
            entry["probe"] = probe
            entry["date"] = d.date().isoformat()
            manifest["files"].append(entry)
            kind_status = "ok" if entry["status"] == "ok" else (
                "cached" if entry["status"] == "cached" else "fail")
            by_kind["fgm"][kind_status] += 1
            if kind_status == "ok": n_ok += 1
            elif kind_status == "cached": n_cached += 1
            else: n_fail += 1

            # STATE
            s_out = ARTEMIS_DIR / f"{probe}_l1_state_{d.strftime('%Y%m%d')}.cdf"
            entry = fetch_file(state_url(probe, d), s_out)
            entry["kind"] = "state"
            entry["probe"] = probe
            entry["date"] = d.date().isoformat()
            manifest["files"].append(entry)
            kind_status = "ok" if entry["status"] == "ok" else (
                "cached" if entry["status"] == "cached" else "fail")
            by_kind["state"][kind_status] += 1
            if kind_status == "ok": n_ok += 1
            elif kind_status == "cached": n_cached += 1
            else: n_fail += 1

            # Heartbeat each probe-day
            if (i + 1) % 5 == 0:
                el = time.time() - t0
                print(f"  {probe} {d.date()}  ok={n_ok} cached={n_cached} fail={n_fail}  ({el:.1f}s)")

    el = time.time() - t0
    print(f"\nfetched: ok={n_ok}  cached={n_cached}  fail={n_fail}  ({el:.1f}s)")
    for k in ("fgm", "state"):
        b = by_kind[k]
        print(f"  {k:5s}: ok={b['ok']:>3d}  cached={b['cached']:>3d}  fail={b['fail']:>3d}")

    (ARTEMIS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    total_bytes = sum(e.get("bytes", 0) for e in manifest["files"])
    print(f"\nmanifest: {ARTEMIS_DIR}/manifest.json   (~{total_bytes/1e9:.2f} GB total)")


if __name__ == "__main__":
    main()
