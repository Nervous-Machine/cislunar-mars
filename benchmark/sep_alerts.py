"""
Shared SWPC alerts parser — used by both the GEO and Mars benchmarks to
derive event-driven binary/graded drivers from the rolling
`https://services.swpc.noaa.gov/products/alerts.json` feed.

Why a shared module: both benchmarks pull the same alerts.json and both
need the same event categorization. Keeping this in one file avoids the
"copy then drift" pattern the framework constants ran into.

Source schema (per SWPC alert):
    { "product_id": "EF3A",
      "issue_datetime": "2026-05-22 05:07:16.083",
      "message": "Space Weather Message Code: ALTEF3\\r\\n... " }

The Space Weather Message Code is embedded in the message body, not in a
top-level field — we parse it out. Codes are grouped into event categories
that map to substrate driver edges.

Output API: timeline -> intensity(t) per category, with exponential decay
from each onset. Intensity is in [0, 1] graded by storm severity tier.
"""

import json
import re
import math
from datetime import datetime, timezone
from pathlib import Path


# SWPC Space Weather Message Codes, grouped by physical event category.
# Both legacy ALTPX* and current ALTTP* are included where applicable —
# SWPC has migrated some codes over the years and rolling feeds may mix
# old and new in a single archive pull.
#
# Magnitude tier is the graded intensity assigned at onset (0..1):
#   0.33 = S1 / G1 / M-flare         (minor)
#   0.67 = S2 / G2 / X-flare         (moderate)
#   1.00 = S3+ / G3+ / extreme       (strong)

EVENT_CATEGORIES = {
    "sep_proton": {
        # 10/100/1000 pfu proton flux alerts — SEP S-scale onset.
        # ALTPX1/2/3 (legacy), ALTTP2/4 (current 100/10000 pfu)
        "codes": {
            "ALTPX1": 0.33, "ALTPX2": 0.67, "ALTPX3": 1.00,
            "ALTTP1": 0.33, "ALTTP2": 0.67, "ALTTP4": 1.00,
            "SUMPX1": 0.33, "SUMPX2": 0.67, "SUMPX3": 1.00,
        },
        "decay_hours": 48.0,
        "description": "Solar Energetic Particle event (S-scale)",
    },
    "relativistic_electron": {
        # GEO-relevant; ≥2 MeV electron integral flux ≥1000 pfu
        "codes": {"ALTEF3": 1.00},
        "decay_hours": 24.0,
        "description": "Relativistic electron enhancement (GEO charging)",
    },
    "flare_xclass": {
        # X-ray flare alerts — solar input precursor
        "codes": {"ALTXMF": 0.67, "SUMX01": 0.67, "SUMXM5": 0.67,
                  "WARK10": 1.00},
        "decay_hours": 6.0,
        "description": "X-class X-ray flare",
    },
    "geomag_storm": {
        # G-scale storm watches/alerts
        "codes": {
            "WATA20": 0.33, "WATA30": 0.67, "WATA40": 1.00, "WATA50": 1.00,
            "ALTK04": 0.33, "ALTK05": 0.33, "ALTK06": 0.67, "ALTK07": 0.67,
            "ALTK08": 1.00, "ALTK09": 1.00,
            "WARK04": 0.33, "WARK05": 0.33, "WARK06": 0.67,
            "WARK07": 0.67, "WARK08": 1.00, "WARK09": 1.00,
        },
        "decay_hours": 24.0,
        "description": "Geomagnetic storm watch/alert (G-scale)",
    },
}


_CODE_RE = re.compile(r"Space Weather Message Code:\s*(\S+)")
_BEGIN_RE = re.compile(r"Begin Time:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})")


def _parse_issue_datetime(s: str) -> datetime:
    # SWPC format: "2026-05-22 05:07:16.083" — naive UTC; force tz
    s = s.strip().split(".")[0]
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def _parse_begin_time(msg: str):
    m = _BEGIN_RE.search(msg)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_alerts(alerts_path: Path) -> dict:
    """
    Parse alerts.json into {category -> [(onset_dt, magnitude_tier)]}.

    Onset is `Begin Time` from the alert body when present, else
    `issue_datetime`. Continuation alerts (same Begin Time as a prior one)
    are deduped — we take the *first* onset per category at a given
    Begin Time, keeping the max magnitude_tier seen.
    """
    raw = json.loads(alerts_path.read_text())
    code_to_category = {
        code: (cat, tier)
        for cat, spec in EVENT_CATEGORIES.items()
        for code, tier in spec["codes"].items()
    }

    timeline = {cat: {} for cat in EVENT_CATEGORIES}
    for a in raw:
        msg = a.get("message", "")
        m = _CODE_RE.search(msg)
        if not m:
            continue
        code = m.group(1)
        if code not in code_to_category:
            continue
        cat, tier = code_to_category[code]

        onset = _parse_begin_time(msg)
        if onset is None:
            try:
                onset = _parse_issue_datetime(a["issue_datetime"])
            except (KeyError, ValueError):
                continue

        # Dedupe by (category, onset minute), keeping max tier
        key = (cat, onset.replace(second=0, microsecond=0))
        timeline[cat][key] = max(timeline[cat].get(key, 0.0), tier)

    out = {}
    for cat, evs in timeline.items():
        rows = sorted([(k[1], tier) for k, tier in evs.items()], key=lambda x: x[0])
        out[cat] = rows
    return out


def intensity_at(timeline_cat: list, t: datetime, decay_hours: float) -> float:
    """
    Return graded activity of one category at time t: max over all events of
    tier * exp(-Δt / τ) where Δt is hours since onset (and 0 if t < onset).
    """
    if not timeline_cat:
        return 0.0
    val = 0.0
    for onset, tier in timeline_cat:
        if t < onset:
            continue
        dt_hours = (t - onset).total_seconds() / 3600.0
        if dt_hours > 6.0 * decay_hours:
            continue
        val = max(val, tier * math.exp(-dt_hours / decay_hours))
    return val


def driver_state(timeline: dict, t: datetime) -> dict:
    """Return {category: intensity_in_[0,1]} for all configured categories."""
    return {
        cat: intensity_at(timeline[cat], t, EVENT_CATEGORIES[cat]["decay_hours"])
        for cat in EVENT_CATEGORIES
    }


def summarize(timeline: dict) -> str:
    """Human-readable summary of what was parsed; useful for benchmark logs."""
    lines = []
    for cat, rows in timeline.items():
        if not rows:
            continue
        first = rows[0][0].isoformat()
        last = rows[-1][0].isoformat()
        lines.append(f"  {cat:24s} {len(rows):>3d} events  {first} … {last}")
    return "\n".join(lines) if lines else "  (no events parsed)"


if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("geo/raw/alerts.json")
    tl = parse_alerts(p)
    print(f"parsed {p}:")
    print(summarize(tl))
    print()
    # Show driver state at the latest event onset, if any
    latest = None
    for cat, rows in tl.items():
        for onset, _ in rows:
            if latest is None or onset > latest:
                latest = onset
    if latest:
        print(f"driver state at {latest.isoformat()}:")
        for k, v in driver_state(tl, latest).items():
            print(f"  {k:24s} {v:.3f}")
