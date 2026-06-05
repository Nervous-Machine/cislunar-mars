"""
Mars regime — fetch real MSL/RAD per-sol product files from PDS-PPI.

Pulls the master INDEX.TAB for the MSL-M-RAD-3-RDR-V1.0 volume and a
per-sol .TXT product for every sol whose START_TIME falls in the target
date window. Each .TXT carries 30-60 ~17-minute observation blocks with
Total Dose B and E values (units: μGy/hour, per the .LBL declaration).

Why download whole .TXTs (~18-35 MB each): the dose values are interleaved
with histograms across the file (obs N's dose-B at byte ~N×430 KB), so
batched-range fetches would be 60 requests per sol × N sols. A 6-month
window is ~180 sols × ~25 MB avg = ~4.5 GB total; bandwidth not the issue,
disk is. Files land in raw/rad/, manifest in raw/rad_manifest.json.

The parser (parse_rad.py) reads each .TXT, emits hourly-binned dose-rate
JSONL, then the raw .TXT can be safely deleted (the JSONL is the
permanent artifact).

Default window: 2025-05-22 → 2025-11-04, the most recent ~166 days of
RAD coverage (archive ends 2025-308). This matches the drivers window
pulled by fetch_mars_drivers.py.

Reproduce:
    python3 fetch_rad.py                              # default window
    python3 fetch_rad.py 2025-01-01 2025-11-04        # custom window
"""

import csv
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

RAW = Path(__file__).parent / "raw"
RAD_DIR = RAW / "rad"
RAW.mkdir(exist_ok=True)
RAD_DIR.mkdir(exist_ok=True)

PDS_BASE = "https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0"
INDEX_URL = f"{PDS_BASE}/INDEX/INDEX.TAB"

# Default window — RAD coverage ends 2025-308 (2025-11-04). We use the
# last ~166 days of coverage to maximize Mars-year overlap and seasonal
# spread while staying within available data.
DEFAULT_END = datetime(2025, 11, 4, tzinfo=timezone.utc)
DEFAULT_START = DEFAULT_END - timedelta(days=166)


def parse_pds_doy(s: str) -> datetime:
    """Parse PDS3 'YYYY-DOYTHH:MM:SS' format → aware UTC datetime."""
    s = s.strip().strip('"')
    if "T" in s:
        date_part, time_part = s.split("T", 1)
    else:
        parts = s.split()
        date_part, time_part = parts[0], parts[1] if len(parts) > 1 else "00:00:00"
    year, doy = date_part.split("-")
    base = datetime(int(year), 1, 1, tzinfo=timezone.utc) + timedelta(days=int(doy) - 1)
    h, m, sec = time_part.split(":")
    return base + timedelta(hours=int(h), minutes=int(m), seconds=int(float(sec)))


def fetch_index(manifest):
    """Pull the master index. ~1 MB, refresh every run for currency."""
    out = RAW / "rad_index.tab"
    t0 = time.time()
    r = requests.get(INDEX_URL, timeout=120)
    r.raise_for_status()
    out.write_bytes(r.content)
    elapsed = time.time() - t0
    manifest["index"] = {
        "url": INDEX_URL, "bytes": len(r.content),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(elapsed, 2),
    }
    print(f"  index    {len(r.content):,} bytes  ({elapsed:.1f}s)")
    return out


def parse_index(index_path: Path, start: datetime, end: datetime):
    """Filter index to sols in [start, end]. Returns list of dicts:
    {start_time, product_id, lbl_rel_path, txt_url}.

    Note: INDEX.TAB column headers are space-padded to fixed width — we
    strip them on read so 'START_TIME       ' becomes 'START_TIME'.
    """
    rows = []
    text = index_path.read_text()
    reader = csv.DictReader(text.splitlines())
    fmap = {k: k.strip() for k in reader.fieldnames}
    for raw in reader:
        r = {fmap[k]: (v.strip().strip('"') if v else "") for k, v in raw.items()}
        try:
            st = parse_pds_doy(r["START_TIME"])
        except (ValueError, KeyError):
            continue
        if not (start <= st <= end):
            continue
        lbl_rel = r["FILE_SPECIFICATION_NAME"]
        # /DATA/SOL_XXXXX_XXXXX/RAD_RDR_YYYY_DOY_HH_MM_NNNN_V00.LBL
        txt_rel = lbl_rel.rsplit(".", 1)[0] + ".TXT"
        rows.append({
            "start_time": st.isoformat(),
            "product_id": r["PRODUCT_ID"],
            "lbl_path": lbl_rel,
            "txt_url": f"{PDS_BASE}{txt_rel}",
        })
    rows.sort(key=lambda r: r["start_time"])
    return rows


def fetch_product(prod, manifest_entry):
    """Download one per-sol .TXT into RAD_DIR. Skip if already on disk."""
    out = RAD_DIR / (prod["product_id"] + ".TXT")
    if out.exists() and out.stat().st_size > 1000:
        manifest_entry["status"] = "cached"
        manifest_entry["bytes"] = out.stat().st_size
        return True
    try:
        t0 = time.time()
        r = requests.get(prod["txt_url"], timeout=120, stream=True)
        r.raise_for_status()
        with out.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        manifest_entry["status"] = "ok"
        manifest_entry["bytes"] = out.stat().st_size
        manifest_entry["elapsed_s"] = round(time.time() - t0, 2)
        return True
    except Exception as e:
        manifest_entry["status"] = f"error: {e}"
        if out.exists():
            out.unlink()
        return False


def main():
    if len(sys.argv) >= 3:
        start = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=timezone.utc)
    else:
        start, end = DEFAULT_START, DEFAULT_END

    print(f"fetching MSL/RAD products for {start.date()} → {end.date()}")
    print(f"  base: {PDS_BASE}")
    print(f"  out:  {RAD_DIR}")
    manifest = {
        "base_url": PDS_BASE,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    index_path = fetch_index(manifest)
    products = parse_index(index_path, start, end)
    print(f"  {len(products):,} per-sol products in window")
    if not products:
        print("  (no products — check window bounds vs PDS coverage)")
        (RAW / "rad_manifest.json").write_text(json.dumps(manifest, indent=2))
        return

    print(f"  span: {products[0]['start_time']} → {products[-1]['start_time']}")
    manifest["products"] = []

    n_ok = n_cached = n_fail = 0
    total_bytes = 0
    t_start = time.time()
    for i, p in enumerate(products, 1):
        entry = {"product_id": p["product_id"], "start_time": p["start_time"]}
        ok = fetch_product(p, entry)
        manifest["products"].append(entry)
        total_bytes += entry.get("bytes", 0)
        if entry["status"] == "ok":
            n_ok += 1
        elif entry["status"] == "cached":
            n_cached += 1
        else:
            n_fail += 1
        if i % 20 == 0 or i == len(products):
            elapsed = time.time() - t_start
            rate_mb = total_bytes / 1e6 / max(elapsed, 1)
            print(f"  [{i:>4d}/{len(products)}]  ok={n_ok}  cached={n_cached}  fail={n_fail}  "
                  f"({total_bytes/1e9:.2f} GB total, {rate_mb:.1f} MB/s avg)")

    manifest["summary"] = {
        "total_products": len(products),
        "ok": n_ok, "cached": n_cached, "failed": n_fail,
        "total_bytes": total_bytes,
        "elapsed_s": round(time.time() - t_start, 1),
    }
    (RAW / "rad_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nwrote rad_manifest.json")
    print(f"  total: {total_bytes/1e9:.2f} GB across {n_ok + n_cached:,} products")


if __name__ == "__main__":
    main()
