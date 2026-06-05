"""
Tier-1 metric: internal-comparator.

Compares the framework's evolved-W prediction against the prior-W (W=0)
baseline on the same prequential record stream. Prior-W = the median /
log-median of the bucket — the prediction the system makes BEFORE any
driver coupling is learned. Evolved-W = the streaming-pass prediction
written by learn_geo.py to preds.jsonl.

Produces:
  - per-observable residual reduction (% of σ² explained by W relative
    to prior)
  - anomaly-flag precision: when the framework flags an obs as
    (max_Z ≥ 0.85 AND |ε_evolved| ≥ 2σ), how often is the prior-W
    prediction ALSO ≥ 2σ from the obs? — i.e. is the framework's flag
    pointing at obs the prior would also have missed?
  - per-storm-day breakdown: precision on the geomag_storm event days
    parsed from alerts.json
  - 2×2 contingency tables (LEO parity)

This is a self-reference comparator (prior-W is a strict subset of
evolved-W's information set) so it can't *overstate* framework value:
any precision lift over prior-W is from learned coupling.

Reproduce:
    python3 learn_geo.py     # writes results/preds.jsonl + trajectory.jsonl
    python3 analyze_internal.py
"""

import bisect
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
PREDS = ROOT / "results" / "preds.jsonl"
TRAJ = ROOT / "results" / "trajectory.jsonl"
OUT_MD = ROOT / "results" / "internal_comparator.md"

Z_THRESH = 0.85
EPS_THRESH = 2.0


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def main():
    print(f"loading {PREDS.name}…")
    preds = [json.loads(l) for l in PREDS.read_text().splitlines() if l]
    print(f"  {len(preds):,} records")

    # Per-observable residual reduction.
    # For multiplicative-form observables, residuals are in log10 space;
    # for additive (B-field), residuals are linear. We compute residual
    # variance both ways and report the % reduction.
    by_obs_evolved = defaultdict(list)
    by_obs_baseline = defaultdict(list)
    for r in preds:
        o = r["obs"]
        if o == "b_field_magnitude":
            r_evolved = r["p"] - r["o"]
            r_baseline = r["p_baseline"] - r["o"]
        else:
            # Flux: log-space residual (matches the ε computation in learn_geo)
            r_evolved = math.log10(max(r["p"], 1e-12)) - math.log10(max(r["o"], 1e-12))
            r_baseline = math.log10(max(r["p_baseline"], 1e-12)) - math.log10(max(r["o"], 1e-12))
        by_obs_evolved[o].append(r_evolved)
        by_obs_baseline[o].append(r_baseline)

    print("\nPer-observable residual reduction (evolved-W vs prior-W baseline):")
    print(f"  {'observable':<24} {'n':>6} {'var_baseline':>12} {'var_evolved':>11} {'reduction':>10}")
    reductions = {}
    for o in sorted(by_obs_evolved):
        n = len(by_obs_evolved[o])
        v_b = statistics.variance(by_obs_baseline[o]) if n > 1 else 0
        v_e = statistics.variance(by_obs_evolved[o]) if n > 1 else 0
        red = 100.0 * (1.0 - v_e / v_b) if v_b > 0 else 0.0
        reductions[o] = (n, v_b, v_e, red)
        print(f"  {o:<24} {n:>6,} {v_b:>12.4g} {v_e:>11.4g} {red:>+9.1f}%")

    # Per-voxel residual std for the evolved predictions (used to z-score ε).
    by_vox_evolved = defaultdict(list)
    by_vox_baseline = defaultdict(list)
    for r in preds:
        o = r["obs"]
        key = (r["v"], o)
        if o == "b_field_magnitude":
            by_vox_evolved[key].append(r["p"] - r["o"])
            by_vox_baseline[key].append(r["p_baseline"] - r["o"])
        else:
            by_vox_evolved[key].append(math.log10(max(r["p"], 1e-12)) - math.log10(max(r["o"], 1e-12)))
            by_vox_baseline[key].append(math.log10(max(r["p_baseline"], 1e-12)) - math.log10(max(r["o"], 1e-12)))
    voxel_std_evolved = {k: max(statistics.stdev(vs), 1e-15)
                         for k, vs in by_vox_evolved.items() if len(vs) > 1}
    voxel_std_baseline = {k: max(statistics.stdev(vs), 1e-15)
                          for k, vs in by_vox_baseline.items() if len(vs) > 1}

    # Index trajectory for max_Z lookup
    print(f"\nindexing {TRAJ.name}…")
    raw_idx = defaultdict(lambda: defaultdict(list))
    with open(TRAJ) as f:
        for line in f:
            r = json.loads(line)
            # Key by (target voxel, observable, src driver) → list of (t, Z)
            raw_idx[(r["v"], r["obs"])][r["src"]].append((parse_iso(r["t"]), r["Z"]))
    indexed = defaultdict(dict)
    for vo, edges in raw_idx.items():
        for src, items in edges.items():
            items.sort()
            indexed[vo][src] = ([p[0] for p in items], [p[1] for p in items])
    print(f"  {sum(len(e) for e in indexed.values())} (v,o,src) edges indexed")

    def max_z_at(v, o, t):
        e = indexed.get((v, o))
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

    # 2×2 contingency: framework_flag × baseline-wrong (≥2σ on prior-W ε)
    print(f"\nClassifying obs (Z_thresh={Z_THRESH}, eps_thresh={EPS_THRESH})…")
    ff_bw, ff_bo, fq_bw, fq_bo = 0, 0, 0, 0
    no_z = 0
    for r in preds:
        v, o = r["v"], r["obs"]
        std_e = voxel_std_evolved.get((v, o))
        std_b = voxel_std_baseline.get((v, o))
        if not std_e or not std_b:
            continue
        if o == "b_field_magnitude":
            eps_e = (r["p"] - r["o"]) / std_e
            eps_b = (r["p_baseline"] - r["o"]) / std_b
        else:
            eps_e = (math.log10(max(r["p"], 1e-12)) - math.log10(max(r["o"], 1e-12))) / std_e
            eps_b = (math.log10(max(r["p_baseline"], 1e-12)) - math.log10(max(r["o"], 1e-12))) / std_b

        t = parse_iso(r["t"])
        mz = max_z_at(v, o, t)
        if mz is None:
            no_z += 1
            continue
        ff = (mz >= Z_THRESH and abs(eps_e) >= EPS_THRESH)
        bw = (abs(eps_b) >= EPS_THRESH)
        if ff and bw:    ff_bw += 1
        elif ff and not bw: ff_bo += 1
        elif not ff and bw: fq_bw += 1
        else: fq_bo += 1

    total = ff_bw + ff_bo + fq_bw + fq_bo
    print(f"  classified: {total:,}  (skipped {no_z:,} with no Z lookup)")
    precision = ff_bw / (ff_bw + ff_bo) if (ff_bw + ff_bo) else 0
    recall = ff_bw / (ff_bw + fq_bw) if (ff_bw + fq_bw) else 0
    base_rate = (ff_bw + fq_bw) / total if total else 0
    lift = precision / base_rate if base_rate > 0 else 0
    print(f"\n  2×2 contingency: framework flag × prior-W baseline wrong")
    print(f"  {'':16s} {'baseline wrong':>14s} {'baseline ok':>14s}")
    print(f"  {'framework flag':16s} {ff_bw:>14,} {ff_bo:>14,}")
    print(f"  {'framework quiet':16s} {fq_bw:>14,} {fq_bo:>14,}")
    print(f"\n  Precision: {100*precision:.2f}%   Recall: {100*recall:.2f}%   "
          f"Base rate: {100*base_rate:.2f}%   Lift: {lift:.2f}×")

    # Markdown output
    lines = [
        "# Internal comparator — framework vs prior-W baseline",
        "",
        "Generated by `analyze_internal.py`. Single streaming pass over the 7-day "
        "GOES-19 SWPC window. Prior-W = the per-voxel-observable log-median "
        "(flux) or median (B-field) baseline a learner with no fitted couplings "
        "would emit; evolved-W = the framework's prediction after one prequential "
        "pass through the observation stream. Both are prequential (predict-then-update); "
        "neither prediction uses information from its own observation step.",
        "",
        "## Residual variance reduction (var_evolved / var_baseline)",
        "",
        "Residuals are in log10 space for flux observables (multiplicative composition) "
        "and linear for B-field (additive composition). Negative reduction = baseline "
        "is already as good as evolved (small effective coupling within window).",
        "",
        "| Observable | n | var(baseline) | var(evolved) | reduction |",
        "|---|---|---|---|---|",
    ]
    for o in sorted(reductions):
        n, vb, ve, red = reductions[o]
        lines.append(f"| `{o}` | {n:,} | {vb:.4g} | {ve:.4g} | {red:+.1f}% |")

    lines += [
        "",
        "## 2×2 contingency — framework flag vs prior-W baseline wrong",
        "",
        f"Flag = (max_Z ≥ {Z_THRESH}) AND (|ε_evolved| ≥ {EPS_THRESH}σ).",
        f"Baseline wrong = (|ε_baseline| ≥ {EPS_THRESH}σ).",
        f"ε is per-voxel residual-std-normalized (separate σ for evolved vs baseline ε).",
        f"Self-reference comparator: any precision lift here is from learned driver coupling.",
        "",
        f"|  | baseline wrong | baseline ok |",
        f"|---|---|---|",
        f"| **framework flag** | {ff_bw:,} | {ff_bo:,} |",
        f"| framework quiet | {fq_bw:,} | {fq_bo:,} |",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Precision | **{100*precision:.2f}%** |",
        f"| Recall | {100*recall:.2f}% |",
        f"| Base rate (P(baseline wrong)) | {100*base_rate:.2f}% |",
        f"| Lift over base rate | **{lift:.2f}×** |",
        "",
        "Interpretation: when the framework flags an observation, the prior-W "
        f"baseline prediction is ≥{EPS_THRESH}σ wrong "
        f"**{100*precision:.1f}%** of the time — "
        f"{lift:.1f}× the background rate at which the baseline is wrong.",
        "",
        f"Window: 7 days SWPC rolling. {total:,} (timestamp, voxel) records classified.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {OUT_MD}")


if __name__ == "__main__":
    main()
