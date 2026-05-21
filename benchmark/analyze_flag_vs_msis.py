"""
The operational comparison: when the framework's curiosity-channel-1 trigger
fires (high-Z edge + high-|ε|), is MSIS ALSO being wrong at that obs?

For each obs, classify into a 2×2 contingency table:
  framework_flagged  ×  msis_wrong
  (yes/no)              (|MSIS-obs|/std ≥ 2)

Then quantify:
  - Of obs where framework flags: what fraction has MSIS also wrong?
  - Of obs where MSIS is wrong: what fraction did framework catch?
  - Precision/recall of framework-as-MSIS-monitor

Plus a worked example: pick the strongest storm, show side-by-side timeline
of MSIS error magnitude and framework flags.
"""

import bisect
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

TRAJ = Path.home() / "space-waze/results/learn-gracefo-trajectory.jsonl"
NM_PREDS = Path.home() / "space-waze/results/learn-gracefo-full-year-preds.jsonl"
MSIS_PREDS = Path.home() / "space-waze/results/msis-preds-multiyear.jsonl"
OUT_PNG = Path.home() / "space-waze/results/flag_vs_msis_g5.png"

Z_THRESH = 0.85
RES_Z_THRESH = 2.0
MSIS_RES_Z_THRESH = 2.0  # "MSIS is wrong" threshold


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
    msis = {}
    with open(MSIS_PREDS) as f:
        for line in f:
            r = json.loads(line)
            if r["o"] > 0 and r["p"] > 0:
                msis[(r["t"], r["v"])] = r["p"]
    keys = sorted(set(nm) & set(msis))
    print(f"  Overlap: {len(keys):_} (t, voxel) records with both NM and MSIS predictions")

    # Voxel residual stds (using NM residuals — same std basis as the anomaly flagger)
    by_v = defaultdict(list)
    for k in keys:
        r = nm[k]
        by_v[r["v"]].append(r["p"] - r["o"])
    voxel_std = {}
    for v, residuals in by_v.items():
        if len(residuals) > 1:
            voxel_std[v] = max(statistics.stdev(residuals), 1e-15)
    print(f"  Voxel residual stds for {len(voxel_std)} voxels")

    # Load trajectory: per voxel, per edge, sorted (timestamps, Z values).
    # bisect-based lookup gives O(log n) per query instead of O(n) linear scan.
    print("Loading + indexing trajectory (bisect-based per-edge lookup)...")
    raw = defaultdict(lambda: defaultdict(list))
    with open(TRAJ) as f:
        for line in f:
            r = json.loads(line)
            raw[r["tgt"]][r["src"]].append((parse_iso(r["t"]), r["Z"]))
    # Convert to parallel arrays (sorted_ts, sorted_zs) for bisect lookup
    indexed = defaultdict(dict)
    for voxel, edges in raw.items():
        for src, items in edges.items():
            items.sort()
            indexed[voxel][src] = ([p[0] for p in items], [p[1] for p in items])
    raw = None  # release memory
    print(f"  Indexed {sum(len(e) for e in indexed.values())} edge-voxel pairs")

    def max_z_at(voxel, t):
        """Return max Z across edges at this voxel at time t (nearest-prior snapshot per edge)."""
        edges = indexed.get(voxel)
        if not edges:
            return None
        max_z = None
        for src, (ts, zs) in edges.items():
            i = bisect.bisect_right(ts, t) - 1
            if i < 0:
                continue
            z = zs[i]
            if max_z is None or z > max_z:
                max_z = z
        return max_z

    # ============================================================
    # 2×2 contingency: framework_flagged × msis_wrong
    # ============================================================
    print(f"\nClassifying {len(keys):_} obs (Z_thresh={Z_THRESH}, res_z_thresh={RES_Z_THRESH})...")
    fw_flag_msis_wrong = 0
    fw_flag_msis_ok = 0
    fw_quiet_msis_wrong = 0
    fw_quiet_msis_ok = 0
    no_z_lookup = 0
    for k in keys:
        r = nm[k]
        v = r["v"]
        std = voxel_std.get(v)
        if std is None or std <= 0:
            continue
        nm_res_z = (r["p"] - r["o"]) / std
        ms_pred = msis[k]
        msis_res_z = (ms_pred - r["o"]) / std

        t_obs = parse_iso(r["t"])
        max_z = max_z_at(v, t_obs)
        if max_z is None:
            no_z_lookup += 1
            continue

        framework_flagged = (max_z >= Z_THRESH and abs(nm_res_z) >= RES_Z_THRESH)
        msis_wrong = abs(msis_res_z) >= MSIS_RES_Z_THRESH

        if framework_flagged and msis_wrong:
            fw_flag_msis_wrong += 1
        elif framework_flagged and not msis_wrong:
            fw_flag_msis_ok += 1
        elif not framework_flagged and msis_wrong:
            fw_quiet_msis_wrong += 1
        else:
            fw_quiet_msis_ok += 1

    total = fw_flag_msis_wrong + fw_flag_msis_ok + fw_quiet_msis_wrong + fw_quiet_msis_ok
    print(f"  Classified: {total:_}  (skipped {no_z_lookup:_} with no Z lookup)")

    print(f"\n{'=' * 90}")
    print(f"  2×2 CONTINGENCY TABLE — framework flag vs. MSIS being wrong")
    print(f"  (MSIS 'wrong' = |MSIS - obs| / voxel_std ≥ {MSIS_RES_Z_THRESH})")
    print(f"{'=' * 90}")
    print(f"")
    print(f"                          MSIS wrong       MSIS ok")
    print(f"  Framework flag      {fw_flag_msis_wrong:>11,}{fw_flag_msis_ok:>14,}     row total {fw_flag_msis_wrong+fw_flag_msis_ok:,}")
    print(f"  Framework quiet     {fw_quiet_msis_wrong:>11,}{fw_quiet_msis_ok:>14,}     row total {fw_quiet_msis_wrong+fw_quiet_msis_ok:,}")
    print(f"  col total           {fw_flag_msis_wrong+fw_quiet_msis_wrong:>11,}{fw_flag_msis_ok+fw_quiet_msis_ok:>14,}     {total:>15,}")
    print()
    # Metrics
    if fw_flag_msis_wrong + fw_flag_msis_ok > 0:
        precision = fw_flag_msis_wrong / (fw_flag_msis_wrong + fw_flag_msis_ok)
        print(f"  PRECISION  (when framework flags, MSIS is wrong): {100*precision:.2f}%")
    if fw_flag_msis_wrong + fw_quiet_msis_wrong > 0:
        recall = fw_flag_msis_wrong / (fw_flag_msis_wrong + fw_quiet_msis_wrong)
        print(f"  RECALL     (of MSIS errors, framework caught):    {100*recall:.2f}%")
    base_rate_msis_wrong = (fw_flag_msis_wrong + fw_quiet_msis_wrong) / total if total else 0
    print(f"  Base-rate MSIS wrong (P(MSIS wrong) in dataset):   {100*base_rate_msis_wrong:.2f}%")
    # Lift
    if base_rate_msis_wrong > 0:
        lift = precision / base_rate_msis_wrong
        print(f"  LIFT (precision / base rate):                      {lift:.2f}x")
        print(f"  → When framework flags, MSIS is wrong {lift:.1f}x more often than random.")

    # ============================================================
    # Worked example: May 2024 G5 storm
    # ============================================================
    print(f"\n{'='*90}")
    print(f"  Worked example: May 2024 G5 storm (peak 2024-05-11)")
    print(f"{'='*90}")
    peak = datetime(2024, 5, 11, tzinfo=timezone.utc)
    win_lo = peak - timedelta(hours=24)
    win_hi = peak + timedelta(hours=72)
    obs_in_win = [nm[k] for k in keys
                  if win_lo <= parse_iso(nm[k]["t"]) <= win_hi]
    print(f"  Obs in window: {len(obs_in_win)}")

    # Per-hour tallies
    by_hour = defaultdict(lambda: {"flagged": 0, "msis_wrong": 0, "both": 0, "n": 0, "dst": None})
    for r in obs_in_win:
        v = r["v"]
        std = voxel_std.get(v)
        if std is None:
            continue
        t_obs = parse_iso(r["t"])
        hk = int(t_obs.timestamp() // 3600)
        nm_res_z = (r["p"] - r["o"]) / std
        ms_pred = msis[(r["t"], v)]
        ms_res_z = (ms_pred - r["o"]) / std
        max_z = max_z_at(v, t_obs)
        if max_z is None:
            continue
        framework_flagged = (max_z >= Z_THRESH and abs(nm_res_z) >= RES_Z_THRESH)
        msis_wrong = abs(ms_res_z) >= MSIS_RES_Z_THRESH
        b = by_hour[hk]
        b["n"] += 1
        if framework_flagged:
            b["flagged"] += 1
        if msis_wrong:
            b["msis_wrong"] += 1
        if framework_flagged and msis_wrong:
            b["both"] += 1
        b["dst"] = r.get("dst")

    # Plot
    hours_sorted = sorted(by_hour)
    times = [datetime.fromtimestamp(hk * 3600, tz=timezone.utc) for hk in hours_sorted]
    flagged_counts = [by_hour[hk]["flagged"] for hk in hours_sorted]
    msis_wrong_counts = [by_hour[hk]["msis_wrong"] for hk in hours_sorted]
    both_counts = [by_hour[hk]["both"] for hk in hours_sorted]
    dst_vals = [by_hour[hk]["dst"] for hk in hours_sorted]

    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    ax = axes[0]
    ax.bar(times, msis_wrong_counts, width=1.0/24, color="red", alpha=0.4,
           label=f"MSIS wrong (|res_z|≥{MSIS_RES_Z_THRESH})")
    ax.bar(times, both_counts, width=1.0/24, color="darkblue", alpha=0.9,
           label=f"Framework flagged AND MSIS wrong")
    ax.bar(times, flagged_counts, width=1.0/24, color="navy", alpha=0.3,
           label=f"Framework flagged (Z≥{Z_THRESH}, |res_z|≥{RES_Z_THRESH})")
    ax.set_ylabel("count / hour")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_title(f"May 2024 G5 storm: framework anomaly flags + MSIS errors per hour",
                 fontsize=11)
    ax.grid(alpha=0.3)
    ax.axvline(peak, color="k", lw=1, ls=":")

    ax2 = axes[1]
    ax2.plot(times, dst_vals, "r-", lw=1.5, label="Dst (nT)")
    ax2.fill_between(times, dst_vals, 0,
                     where=[d is not None and d <= 0 for d in dst_vals],
                     color="red", alpha=0.1)
    ax2.axhline(-50, color="r", lw=0.5, ls="--", alpha=0.5)
    ax2.axhline(-100, color="r", lw=0.5, ls="--", alpha=0.5)
    ax2.set_ylabel("Dst (nT)", color="r")
    ax2.tick_params(axis="y", labelcolor="r")
    ax2.axvline(peak, color="k", lw=1, ls=":")
    ax2.xaxis.set_major_locator(mdates.HourLocator(interval=12))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %Hh"))
    ax2.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_PNG, dpi=120)
    print(f"\n  Saved {OUT_PNG}")

    # Aggregate during the G5
    sum_flag = sum(flagged_counts)
    sum_msis_w = sum(msis_wrong_counts)
    sum_both = sum(both_counts)
    print(f"\n  G5 storm window totals:")
    print(f"    framework flags:    {sum_flag}")
    print(f"    MSIS wrong:         {sum_msis_w}")
    print(f"    BOTH:               {sum_both}")
    if sum_flag:
        print(f"    P(MSIS wrong | framework flagged) = {100*sum_both/sum_flag:.1f}%")
    if sum_msis_w:
        print(f"    P(framework flagged | MSIS wrong) = {100*sum_both/sum_msis_w:.1f}%")


if __name__ == "__main__":
    main()
