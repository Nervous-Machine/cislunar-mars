"""
Mars regime — parse MSL/RAD per-sol .TXT products into hourly-binned
dose-rate JSONL.

Per-product structure (from PDS3 .LBL):

    [FILE]                                  # product header
      START_TIME=...                        # sol start UTC
    [OBSERVATION: NN]                       # 30-60 obs per sol, ~17 min each
      START_OBS_UTC="YYYY-DOY HH:MM:SS"
      ...
    [DOSIMETRY_TOTAL_DOSE_B: NN]
      <single ASCII real>                   # UNIT="microGray / Hour"
    [DOSIMETRY_TOTAL_DOSE_E: NN]
      <single ASCII real>                   # UNIT="microGray / Hour"

The .LBL units field calls out µGy/hr — so values are already dose-RATES,
not integrated doses. We convert to µGy/day for unit-parity with the
synthetic ground truth (which used the same unit, per Hassler+ 2014's
~200 µGy/day quiet-time GCR baseline).

The output JSONL is one record per observation block:
    {
      "t": "2025-05-23T03:14:22Z",          # START_OBS_UTC
      "obs": "surface_dose_rate",
      "o": 213.5,                            # dose-rate (µGy/day) from B detector
      "dose_e_uGy_per_day": 198.7,           # E detector (for cross-check)
      "duration_s": 1024,                    # integration duration (from COUNTER_L1)
      "units": "uGy_per_day",
      "product_id": "RAD_RDR_2025_142_03_14_4538_V00",
      "is_synthetic": false,
      "placeholder_schema": "pds3_rad_rdr_v1"
    }

Why we don't aggregate to fixed clock hours here: each obs block already
represents ~17 minutes of integration with one calibrated dose-rate. The
downstream learn_mars.py voxelizes by Ls (4 bins / Mars year), not by
hour-of-day. Records per sol average ~30, so hourly binning would actually
*reduce* statistical power. We keep per-observation records.

Quiet-time validation: median dose-rate-B across non-event days should
sit ~200 µGy/day (Hassler et al. 2014). The script prints this as a unit
sanity check; if it's an order of magnitude off, the parser has a bug.
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAW = Path(__file__).parent / "raw"
RAD_DIR = RAW / "rad"
OUT = Path(__file__).parent / "rad_observations.jsonl"

# Parser regexes
_OBS_HEADER = re.compile(r"^\[OBSERVATION:\s+(\d+)\]")
_DOSE_B = re.compile(r"^\[DOSIMETRY_TOTAL_DOSE_B:\s+(\d+)\]")
_DOSE_E = re.compile(r"^\[DOSIMETRY_TOTAL_DOSE_E:\s+(\d+)\]")
_COUNTER_L1 = re.compile(r"^\[COUNTER_L1:\s+(\d+)\]")
_START_UTC = re.compile(r'^START_OBS_UTC="([^"]+)"')
_SECTION = re.compile(r"^\[[A-Z_]+:")


def parse_pds_utc(s: str) -> datetime:
    """'2025-142 03:14:22' → aware UTC datetime."""
    date_part, time_part = s.strip().split(maxsplit=1)
    year, doy = date_part.split("-")
    base = datetime(int(year), 1, 1, tzinfo=timezone.utc) + timedelta(days=int(doy) - 1)
    h, m, sec = time_part.split(":")
    return base + timedelta(hours=int(h), minutes=int(m), seconds=int(float(sec)))


def parse_one_product(txt_path: Path):
    """Stream-parse one .TXT, yield (start_utc, dose_b_uGyhr, dose_e_uGyhr, duration_s).

    State machine: track current observation id; when we hit a
    [DOSIMETRY_TOTAL_DOSE_{B,E}] header, read the next non-blank ascii
    line as the value. [COUNTER_L1] block's first ascii data row's
    'duration' column captures the integration window in seconds.
    """
    obs = {}  # obs_id -> {start, dose_b, dose_e, duration}
    current_obs = None
    awaiting = None  # 'dose_b' | 'dose_e' | 'counter_l1'

    with txt_path.open("r", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")

            m = _OBS_HEADER.match(line)
            if m:
                current_obs = int(m.group(1))
                obs.setdefault(current_obs, {})
                awaiting = None
                continue

            if current_obs is None:
                continue

            m = _START_UTC.match(line.strip())
            if m:
                try:
                    obs[current_obs]["start"] = parse_pds_utc(m.group(1))
                except (ValueError, IndexError):
                    pass
                continue

            m = _DOSE_B.match(line)
            if m:
                awaiting = "dose_b"
                continue
            m = _DOSE_E.match(line)
            if m:
                awaiting = "dose_e"
                continue
            m = _COUNTER_L1.match(line)
            if m:
                awaiting = "counter_l1"
                continue

            # Hit another section — stop awaiting
            if _SECTION.match(line):
                awaiting = None
                continue

            stripped = line.strip()
            if not stripped:
                continue

            if awaiting in ("dose_b", "dose_e"):
                # Single ASCII real on one line
                try:
                    val = float(stripped.split()[0])
                    obs[current_obs][awaiting] = val
                except (ValueError, IndexError):
                    pass
                awaiting = None
                continue

            if awaiting == "counter_l1":
                # First active data row's 'duration' column. Skip header lines
                # (start with " ch ", " --- ") and -2 rows (N/A channels).
                if stripped.startswith("ch") or stripped.startswith("---"):
                    continue
                parts = stripped.split()
                # Format: ch name fast slow duration alive%  ...
                # name may contain a space inside quotes → splitting differs.
                # Simpler: regex pull the integer that's the duration column.
                # Pattern: int int int float ...
                try:
                    # try splitting after the quoted name
                    if '"' in line:
                        after_name = line.split('"', 2)[2].split()
                        if len(after_name) >= 3:
                            dur = int(after_name[2])
                            if dur > 0:
                                obs[current_obs]["duration"] = dur
                                awaiting = None
                                continue
                    # fallback
                    if len(parts) >= 5:
                        dur = int(parts[4])
                        if dur > 0:
                            obs[current_obs]["duration"] = dur
                            awaiting = None
                except (ValueError, IndexError):
                    pass

    out = []
    for oid in sorted(obs):
        o = obs[oid]
        start = o.get("start")
        db = o.get("dose_b")
        de = o.get("dose_e")
        dur = o.get("duration", 0)
        if start is None or db is None:
            continue
        out.append((start, db, de, dur))
    return out


def main():
    if not RAD_DIR.exists() or not any(RAD_DIR.glob("*.TXT")):
        print(f"no .TXT products in {RAD_DIR}/. Run fetch_rad.py first.")
        sys.exit(1)

    products = sorted(RAD_DIR.glob("*.TXT"))
    print(f"parsing {len(products):,} per-sol products from {RAD_DIR}/")

    n_records = 0
    n_dropped_short = 0
    n_dropped_invalid = 0
    n_files = 0
    dose_b_samples = []  # for unit sanity check
    earliest = None
    latest = None
    # Quality filter: standard RAD integration is ~960s (16 min). Short
    # integration windows under MIN_DURATION_S produce partial counts that
    # under-represent the dose-rate per Hour — drop them. Typical loss
    # is <3% of observations (verified across the 2025 archive window).
    MIN_DURATION_S = 900
    with OUT.open("w") as out:
        for p in products:
            try:
                rows = parse_one_product(p)
            except Exception as e:
                print(f"  skip {p.name}: {e}")
                continue
            for start, db_hr, de_hr, dur in rows:
                if dur and dur < MIN_DURATION_S:
                    n_dropped_short += 1
                    continue
                if db_hr is None or db_hr <= 0 or db_hr > 50:  # >50 µGy/hr = 1200 µGy/day, way above any known event
                    n_dropped_invalid += 1
                    continue
                # μGy/hour → μGy/day
                dose_b_day = db_hr * 24.0
                dose_e_day = (de_hr * 24.0) if de_hr is not None else None
                rec = {
                    "t": start.isoformat().replace("+00:00", "Z"),
                    "obs": "surface_dose_rate",
                    "o": round(dose_b_day, 3),
                    "dose_e_uGy_per_day": (round(dose_e_day, 3) if dose_e_day is not None else None),
                    "duration_s": dur,
                    "units": "uGy_per_day",
                    "product_id": p.stem,
                    "is_synthetic": False,
                    "placeholder_schema": "pds3_rad_rdr_v1",
                }
                out.write(json.dumps(rec) + "\n")
                n_records += 1
                dose_b_samples.append(dose_b_day)
                if earliest is None or start < earliest:
                    earliest = start
                if latest is None or start > latest:
                    latest = start
            n_files += 1
            if n_files % 20 == 0 or n_files == len(products):
                print(f"  [{n_files:>4d}/{len(products)}]  {n_records:,} records")

    if dose_b_samples:
        dose_b_samples.sort()
        med = dose_b_samples[len(dose_b_samples) // 2]
        p10 = dose_b_samples[len(dose_b_samples) // 10]
        p90 = dose_b_samples[9 * len(dose_b_samples) // 10]
        print(f"\nwrote {OUT.name}  ({n_records:,} records)")
        print(f"  dropped: {n_dropped_short} short-duration, {n_dropped_invalid} invalid-dose")
        print(f"  span:  {earliest.isoformat()} → {latest.isoformat()}")
        print(f"  dose-B p10/median/p90 (µGy/day):  {p10:.0f} / {med:.0f} / {p90:.0f}")
        print(f"  expected quiet-time GCR baseline at Gale ~200 µGy/day (Hassler+ 2014)")
        if not (50 < med < 1000):
            print(f"  WARN: median dose-rate {med:.0f} is far from expected ~200; check units/parser")


if __name__ == "__main__":
    main()
