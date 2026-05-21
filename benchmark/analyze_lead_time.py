"""
Lead-time analysis: how far before peak Dst does the framework's anomaly flag
fire, stratified by severity tier?

Reproduces results/lead_time_by_severity.md.

For each top storm (Dst <= STORM_DST_THRESHOLD), and each severity tier, find
the first observation in the LOOKBACK_H window before peak where the framework
flags at that tier:
    flag at tier τ  =  (max_Z >= Z_THRESH) AND (|ε_framework| >= τ)
where ε_framework = (pred_framework - obs) / per-voxel residual std.

LOOKBACK_H = 240 (10 days). The earlier 72h cap artificially truncated lead
times; 240h removes the truncation. MILD-tier saturates against the background
flag rate at this lookback (every window contains some MILD flag), so the
SEVERE tier is the most informative "first meaningful flag" measure.
"""

import bisect
import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

NM_PREDS = Path.home() / "space-waze/results/learn-gracefo-full-year-preds.jsonl"
TRAJ = Path.home() / "space-waze/results/learn-gracefo-trajectory.jsonl"
OBS = Path.home() / "space-waze/results/learn-gracefo-obs-multiyear.jsonl"

Z_THRESH = 0.85
STORM_DST_THRESHOLD = -100
LOOKBACK_H = 240
EVENT_GAP_HOURS = 6
SEVERITY_TIERS = [(2.0, "MILD"), (3.0, "MODERATE"), (5.0, "SEVERE"), (10.0, "CRITICAL")]


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def main():
    print("Loading predictions...")
    nm = {}
    with open(NM_PREDS) as f:
        for line in f:
            r = json.loads(line)
            if r["o"] > 0 and r["p"] > 0:
                nm[(r["t"], r["v"])] = r

    by_v = defaultdict(list)
    for r in nm.values():
        by_v[r["v"]].append(r["p"] - r["o"])
    voxel_std = {v: max(statistics.stdev(rs), 1e-15) for v, rs in by_v.items() if len(rs) > 1}

    print("Indexing trajectory...")
    raw = defaultdict(lambda: defaultdict(list))
    with open(TRAJ) as f:
        for line in f:
            r = json.loads(line)
            raw[r["tgt"]][r["src"]].append((parse_iso(r["t"]), r["Z"]))
    indexed = defaultdict(dict)
    for v, edges in raw.items():
        for src, items in edges.items():
            items.sort()
            indexed[v][src] = ([p[0] for p in items], [p[1] for p in items])

    def max_z_at(v, t):
        e = indexed.get(v)
        if not e:
            return None
        mz = None
        for src, (ts, zs) in e.items():
            i = bisect.bisect_right(ts, t) - 1
            if i < 0:
                continue
            if mz is None or zs[i] > mz:
                mz = zs[i]
        return mz

    print(f"Identifying storms (Dst <= {STORM_DST_THRESHOLD})...")
    dst_hourly = {}
    with open(OBS) as f:
        for line in f:
            r = json.loads(line)
            if r.get("dst") is None:
                continue
            t = parse_iso(r["t"])
            dst_hourly[int(t.timestamp() // 3600)] = (t, r["dst"])
    dst_series = sorted(dst_hourly.values())

    events = []
    in_e = False
    cur = None
    last = None
    for t, d in dst_series:
        if d <= STORM_DST_THRESHOLD:
            if not in_e:
                cur = {"peak_t": t, "peak_dst": d}
                in_e = True
            elif d < cur["peak_dst"]:
                cur["peak_dst"] = d
                cur["peak_t"] = t
            last = t
        else:
            if in_e and last and (t - last).total_seconds() > EVENT_GAP_HOURS * 3600:
                events.append(cur)
                in_e = False
                cur = None
    if in_e and cur:
        events.append(cur)
    events.sort(key=lambda e: e["peak_dst"])
    print(f"  {len(events)} storms")

    def first_flag(peak_t, eps_thresh):
        lo = peak_t - timedelta(hours=LOOKBACK_H)
        first = None
        for (t_str, v), r in nm.items():
            t = parse_iso(t_str)
            if not (lo <= t < peak_t):
                continue
            std = voxel_std.get(v)
            if not std:
                continue
            nm_z = (r["p"] - r["o"]) / std
            mz = max_z_at(v, t)
            if mz is None:
                continue
            if mz >= Z_THRESH and abs(nm_z) >= eps_thresh:
                if first is None or t < first:
                    first = t
        return first

    print(f"\nLead time by severity (lookback {LOOKBACK_H}h):\n")
    header = "  {:12s} {:>5s}  ".format("peak", "Dst") + "  ".join(
        f"{tier:>8s}" for _, tier in SEVERITY_TIERS)
    print(header)
    print("  " + "-" * (len(header)))

    rows = []
    for e in events:
        pt = e["peak_t"]
        leads = []
        for eps, _ in SEVERITY_TIERS:
            ff = first_flag(pt, eps)
            leads.append((pt - ff).total_seconds() / 3600 if ff else None)
        rows.append((pt, e["peak_dst"], leads))
        cells = "  ".join(f"{('+%.0fh' % x) if x is not None else '—':>8s}" for x in leads)
        print(f"  {pt.strftime('%Y-%m-%d'):12s} {e['peak_dst']:+5.0f}  {cells}")

    print("\n  Summary by tier:")
    print(f"  {'tier':>10s}  {'n':>6s}  {'min':>6s}  {'median':>7s}  {'mean':>6s}  {'max':>6s}")
    for i, (eps, tier) in enumerate(SEVERITY_TIERS):
        vals = sorted(r[2][i] for r in rows if r[2][i] is not None)
        if vals:
            print(f"  {tier:>10s}  {len(vals):>2d}/{len(rows):<3d}  +{vals[0]:>4.0f}h  "
                  f"+{vals[len(vals)//2]:>5.0f}h  +{sum(vals)/len(vals):>4.0f}h  +{vals[-1]:>4.0f}h")


if __name__ == "__main__":
    main()
