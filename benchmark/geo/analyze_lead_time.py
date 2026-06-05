"""
LEO-parity lead-time analysis.

For each operational event parsed from SWPC alerts during the obs window,
find the first record where the framework flag fires at each severity
tier, and report lead time (hours before event onset).

  flag at tier τ  =  (max_Z ≥ Z_THRESH) AND (|ε_evolved| ≥ τ)
                     on at least one observable at the event timestamp.

Tiers mirror the LEO benchmark (analyze_lead_time.py at the repo root):
  MILD ≥ 2σ
  MODERATE ≥ 3σ
  SEVERE ≥ 5σ
  CRITICAL ≥ 10σ

The GEO obs window is 7 days, so lookback caps at 7d (168h). Event onset =
"Begin Time" from SWPC alerts where present, else issue datetime.

Reproduce:
    python3 learn_geo.py
    python3 analyze_lead_time.py
"""

import bisect
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent))
from sep_alerts import parse_alerts

PREDS = ROOT / "results" / "preds.jsonl"
TRAJ = ROOT / "results" / "trajectory.jsonl"
RAW_ALERTS = ROOT / "raw" / "alerts.json"
OUT_MD = ROOT / "results" / "lead_time_by_severity.md"

Z_THRESH = 0.85
LOOKBACK_H = 168
SEVERITY_TIERS = [(2.0, "MILD"), (3.0, "MODERATE"), (5.0, "SEVERE"), (10.0, "CRITICAL")]


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def main():
    print(f"loading {PREDS.name}…")
    preds = [json.loads(l) for l in PREDS.read_text().splitlines() if l]
    print(f"  {len(preds):,} records")

    # Per-voxel-observable residual std for ε z-scoring
    by_v = defaultdict(list)
    for r in preds:
        if r["obs"] == "b_field_magnitude":
            by_v[(r["v"], r["obs"])].append(r["p"] - r["o"])
        else:
            by_v[(r["v"], r["obs"])].append(math.log10(max(r["p"], 1e-12))
                                            - math.log10(max(r["o"], 1e-12)))
    voxel_std = {k: max(statistics.stdev(vs), 1e-15)
                 for k, vs in by_v.items() if len(vs) > 1}

    print(f"indexing trajectory…")
    raw_idx = defaultdict(lambda: defaultdict(list))
    with open(TRAJ) as f:
        for line in f:
            r = json.loads(line)
            raw_idx[(r["v"], r["obs"])][r["src"]].append((parse_iso(r["t"]), r["Z"]))
    indexed = defaultdict(dict)
    for vo, edges in raw_idx.items():
        for src, items in edges.items():
            items.sort()
            indexed[vo][src] = ([p[0] for p in items], [p[1] for p in items])

    def max_z_at(v, o, t):
        e = indexed.get((v, o))
        if not e: return None
        mz = None
        for src, (ts, zs) in e.items():
            i = bisect.bisect_right(ts, t) - 1
            if i < 0: continue
            if mz is None or zs[i] > mz:
                mz = zs[i]
        return mz

    # Parse alerts (events).
    print(f"parsing alerts…")
    timeline = parse_alerts(RAW_ALERTS)
    events = []
    for cat, rows in timeline.items():
        for onset, tier in rows:
            events.append({"cat": cat, "onset": onset, "tier": tier})
    events.sort(key=lambda e: e["onset"])
    # Dedupe within 6h within category
    dedup = []
    last_per_cat = {}
    for e in events:
        last = last_per_cat.get(e["cat"])
        if last and (e["onset"] - last["onset"]).total_seconds() < 6 * 3600:
            if e["tier"] > last["tier"]:
                last["tier"] = e["tier"]
                last["onset"] = e["onset"]
            continue
        dedup.append(e)
        last_per_cat[e["cat"]] = e
    print(f"  {len(dedup)} deduped events")

    # Sort preds by time for per-step ε z-scoring
    preds_sorted = sorted(preds, key=lambda r: r["t"])
    # Precompute ε z-score per pred record
    for r in preds_sorted:
        std = voxel_std.get((r["v"], r["obs"]))
        if not std:
            r["_eps_z"] = None
            continue
        if r["obs"] == "b_field_magnitude":
            r["_eps_z"] = (r["p"] - r["o"]) / std
        else:
            r["_eps_z"] = (math.log10(max(r["p"], 1e-12))
                          - math.log10(max(r["o"], 1e-12))) / std

    # Compute first-flag-at-tier per event
    def first_flag(event_t, eps_thresh):
        lo = event_t - timedelta(hours=LOOKBACK_H)
        first = None
        for r in preds_sorted:
            t = parse_iso(r["t"])
            if t < lo:
                continue
            if t >= event_t:
                break
            ez = r["_eps_z"]
            if ez is None or abs(ez) < eps_thresh:
                continue
            mz = max_z_at(r["v"], r["obs"], t)
            if mz is None or mz < Z_THRESH:
                continue
            if first is None or t < first:
                first = t
        return first

    rows = []
    only_obs_window_events = []
    pred_t_min = parse_iso(preds_sorted[0]["t"])
    pred_t_max = parse_iso(preds_sorted[-1]["t"])
    for e in dedup:
        # Skip events entirely outside the obs window — no flag computable
        if e["onset"] < pred_t_min or e["onset"] > pred_t_max:
            continue
        leads = []
        for eps, _ in SEVERITY_TIERS:
            ff = first_flag(e["onset"], eps)
            leads.append((e["onset"] - ff).total_seconds() / 3600 if ff else None)
        rows.append({"event": e, "leads": leads})
        only_obs_window_events.append(e)

    print(f"\n  events within obs window: {len(rows)}")

    # Per-tier summary
    print(f"\nLead time by severity (lookback {LOOKBACK_H}h):")
    header = "  {:24s} {:>5s}  ".format("cat / onset", "tier") + "  ".join(
        f"{tier:>8s}" for _, tier in SEVERITY_TIERS)
    print(header)
    # Show top 20 events by tier (then by onset desc)
    rows_sorted = sorted(rows, key=lambda r: (-r["event"]["tier"], r["event"]["onset"]))
    for r in rows_sorted[:20]:
        ev = r["event"]
        cells = "  ".join(f"{('+%.1fh' % x) if x is not None else '—':>8s}" for x in r["leads"])
        print(f"  {ev['cat'][:16]:16s} {ev['onset'].strftime('%m-%d %H:%M'):14s} {ev['tier']:>4.2f}  {cells}")

    print(f"\nSummary by tier:")
    for i, (eps, tier) in enumerate(SEVERITY_TIERS):
        vals = sorted(r["leads"][i] for r in rows if r["leads"][i] is not None)
        if vals:
            n = len(vals); med = vals[n // 2]
            print(f"  {tier:>10s}  {n:>2d}/{len(rows):<3d}  min=+{vals[0]:.1f}h  "
                  f"median=+{med:.1f}h  mean=+{sum(vals)/n:.1f}h  max=+{vals[-1]:.1f}h")
        else:
            print(f"  {tier:>10s}  0/{len(rows)} — no detections")

    # Markdown report
    lines = [
        "# Lead time before event onset, by flag severity tier",
        "",
        f"All SWPC operational alerts ({len(rows)}) onset within the 7-day "
        f"GOES-19 obs window, lookback {LOOKBACK_H}h. Each row shows the lead "
        "time between the framework's first flag at that tier and the event's "
        "alert onset. ε is per-voxel-observable residual-std-normalized.",
        "",
        f"Flag at tier τ = (max_Z ≥ {Z_THRESH}) AND (|ε_evolved| ≥ τσ) on "
        "at least one observable.",
        "",
        "## Per-event lead time (hours before alert onset)",
        "",
        "| Category | Onset (UTC) | Alert tier | MILD ≥2σ | MOD ≥3σ | SEV ≥5σ | CRIT ≥10σ |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows_sorted[:30]:
        ev = r["event"]
        cells = " | ".join(f"+{x:.1f}h" if x is not None else "—" for x in r["leads"])
        lines.append(f"| {ev['cat']} | {ev['onset'].strftime('%Y-%m-%d %H:%M')} | "
                     f"{ev['tier']:.2f} | {cells} |")

    lines += [
        "",
        "## Summary by tier",
        "",
        "| Tier | n events flagged pre-onset | Min | Median | Mean | Max |",
        "|---|---|---|---|---|---|",
    ]
    for i, (eps, tier) in enumerate(SEVERITY_TIERS):
        vals = sorted(r["leads"][i] for r in rows if r["leads"][i] is not None)
        if vals:
            n = len(vals); med = vals[n // 2]
            lines.append(f"| {tier} (≥{eps}σ) | {n}/{len(rows)} | "
                         f"+{vals[0]:.1f}h | +{med:.1f}h | +{sum(vals)/n:.1f}h | +{vals[-1]:.1f}h |")
        else:
            lines.append(f"| {tier} (≥{eps}σ) | 0/{len(rows)} | — | — | — | — |")

    lines += [
        "",
        "## Window context",
        "",
        f"- Obs window: 7 days SWPC rolling ({pred_t_min.date()} to {pred_t_max.date()})",
        f"- Total events within window: {len(rows)} (deduped within 6h × category)",
        "- The LEO benchmark publishes this table at 240h lookback over 7+ "
        "  years of GRACE-FO data (21 major storms). The 7-day GEO window is "
        "  proof-of-method; NCEI multi-year backfill is the prerequisite for "
        "  parity-scale storm coverage.",
        "- Event onset is `Begin Time` from the alert body if present, else "
        "  issue datetime. SWPC alert tiers are 0.33 / 0.67 / 1.00 per "
        "  `sep_alerts.py` mapping of Space Weather Message Codes.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {OUT_MD}")


if __name__ == "__main__":
    main()
