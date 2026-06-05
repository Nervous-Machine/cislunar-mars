"""
Tier-2 external comparator — substrate vs naive ballistic L1→lunar IMF
propagation.

The natural cislunar tier-2 comparator is: does the learned per-voxel
substrate beat a naive Parker-spiral / ballistic propagation of L1 IMF
to lunar distance?

Naive ballistic propagation:
  Bz_at_lunar(t) ≈ Bz_at_L1(t - Δt)
  Bt_at_lunar(t) ≈ Bt_at_L1(t - Δt)

where Δt = (X_L1 - X_Moon) / V_sw ≈ 9 minutes typical (V_sw=400 km/s,
distance ~220 RE from L1 to Moon at first-quarter orbit position). For
this hourly benchmark we use Δt = 0 (within rounding to the hour) since
9 min is much less than the 60-min cadence.

This is the LEO-equivalent of substrate-vs-MSIS. It is *unique to
cislunar* — the L1-to-target propagation distance is large enough to
make naive ballistic propagation a non-trivial baseline.

Method:
  1. For each obs record, compute naive prediction:
       p_naive(imf_bz_at_lunar)   = imf_bz_l1
       p_naive(imf_btot_at_lunar) = imf_bt_l1
  2. Compare to substrate prediction p_evolved (loaded from learn_cislunar
     trajectory) and observed o.
  3. Report per-voxel-observable residual MAE/RMSE for {naive, evolved}.

Output: results/tier2_l1_propagation.md
"""

import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from nm_primitives import apply_learning_feedback_in_memory

ROOT = Path(__file__).parent
OBS_JSONL = ROOT / "obs.jsonl"
EDGES_IN = ROOT / "results" / "edges_state.json"
OUT_MD = ROOT / "results" / "tier2_l1_propagation.md"

# Mirror learn_cislunar.py settings
DRIVER_NORM = {
    "imf_bz_l1":            ("linear", 5.0),
    "imf_bt_l1":            ("linear", 5.0),
    "sw_speed":             ("linear", 100.0),
    "sw_density":           ("linear", 5.0),
    "sw_dynamic_pressure":  ("linear", 2.0),
    "sep_proton":           ("passthrough", 1.0),
    "kp_index":             ("linear", 2.0),
    "dst_index":            ("linear", 30.0),
    "f107":                 ("linear", 50.0),
    "ap":                   ("linear", 15.0),
    "flare_xclass":         ("passthrough", 1.0),
    "geomag_storm":         ("passthrough", 1.0),
}
DRIVERS = list(DRIVER_NORM.keys())
ACTIVITY_THRESH_DEFAULT = 0.10
ACTIVITY_THRESH = {"sep_proton": 0.01, "flare_xclass": 0.01, "geomag_storm": 0.01}


def normalize(name, raw, center=0.0):
    if raw is None: return 0.0
    kind, scale = DRIVER_NORM[name]
    if kind == "passthrough":
        return raw
    return (raw - center) / scale


def main():
    obs = [json.loads(line) for line in OBS_JSONL.read_text().splitlines() if line]
    obs.sort(key=lambda r: r["t"])
    edges = json.load(open(EDGES_IN))
    print(f"loaded {len(obs):,} obs records and {len(edges)} final edges")

    # Per-voxel-observable baseline (median) + std — must match learn_cislunar
    bucket = defaultdict(list)
    for r in obs:
        bucket[(r["v"], r["obs"])].append(r["o"])
    baseline = {k: statistics.median(vs) for k, vs in bucket.items()}
    voxel_std = {k: max(statistics.stdev(vs), 1e-15) if len(vs) > 1 else 1.0
                 for k, vs in bucket.items()}
    driver_centers = {}
    for n in DRIVERS:
        kind, _ = DRIVER_NORM[n]
        if kind == "linear":
            vals = [r["d"].get(n) for r in obs if r["d"].get(n) is not None]
            driver_centers[n] = statistics.median(vals) if vals else 0.0
        else:
            driver_centers[n] = 0.0

    def edge_key(d, v, o):
        return f"{d}|{v}|{o}"

    # Compute three predictions per record:
    #   p_naive    = direct L1 propagation (imf_bz_l1 or imf_bt_l1 as-is)
    #   p_prior    = baseline (W=0 for all)
    #   p_evolved  = baseline + (Σ d·W)·σ using FINAL edge state
    n_skipped_no_l1 = 0
    per = defaultdict(lambda: {"naive_abs": [], "prior_abs": [], "evolved_abs": [], "n": 0})
    for r in obs:
        v, o = r["v"], r["obs"]
        bl = baseline.get((v, o)); std = voxel_std.get((v, o))
        if bl is None: continue

        # naive: identity L1 → lunar
        if o == "imf_bz_at_lunar_distance":
            d_l1 = r["d"].get("imf_bz_l1")
        elif o == "imf_btot_at_lunar_distance":
            d_l1 = r["d"].get("imf_bt_l1")
        else:
            d_l1 = None
        if d_l1 is None:
            n_skipped_no_l1 += 1
            continue
        p_naive = d_l1

        # prior + evolved
        d_norm = {n: normalize(n, r["d"].get(n), driver_centers.get(n, 0.0))
                  for n in DRIVERS}
        p_prior = bl
        adjust = sum(
            d_norm[n] * edges[edge_key(n, v, o)]["W"]
            for n in DRIVERS
            if abs(d_norm[n]) >= ACTIVITY_THRESH.get(n, ACTIVITY_THRESH_DEFAULT)
        )
        p_evolved = bl + adjust * std

        ob = r["o"]
        per[(v, o)]["naive_abs"].append(abs(p_naive - ob))
        per[(v, o)]["prior_abs"].append(abs(p_prior - ob))
        per[(v, o)]["evolved_abs"].append(abs(p_evolved - ob))
        per[(v, o)]["n"] += 1

    print(f"skipped {n_skipped_no_l1} records lacking L1 driver")

    # Report
    lines = [
        "# Tier-2 external comparator — substrate vs naive L1→lunar propagation",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()}",
        f"Window: {obs[0]['t']} → {obs[-1]['t']}",
        "",
        "**What this measures.** The natural external baseline for the",
        "cislunar regime is naive ballistic propagation of L1 IMF to the",
        "Moon: identity coupling between L1 measurement and lunar-distance",
        "prediction.  This is operational physics — Parker-spiral and",
        "ballistic propagation are how cislunar forecasts have been done",
        "in the absence of a learned correction.",
        "",
        "Three predictions per record:",
        "  - `p_naive`   = direct L1 measurement (imf_bz_l1 or imf_bt_l1 as-is)",
        "  - `p_prior`   = per-voxel median baseline (substrate at W=0)",
        "  - `p_evolved` = baseline + (Σ d·W)·σ using the substrate's final",
        "                  edge state (uses the converged W from a single",
        "                  prequential pass; this is in-sample evaluation,",
        "                  the standard for substrate-vs-baseline comparisons",
        "                  in the LEO benchmark)",
        "",
        "Reported metric: mean absolute residual |p − o|, in the observable's",
        "native units (nT for both observables).",
        "",
        "## Per-voxel × observable absolute residual (nT)",
        "",
        "| Voxel | Observable | n | naive_L1 | prior_W | evolved_W | substrate vs naive |",
        "|---|---|---|---|---|---|---|",
    ]
    overall_n = 0
    overall_naive = []
    overall_prior = []
    overall_evolved = []
    for (v, o), s in sorted(per.items()):
        n = s["n"]
        if n == 0: continue
        mn = sum(s["naive_abs"]) / n
        mp = sum(s["prior_abs"]) / n
        me = sum(s["evolved_abs"]) / n
        reduction = 100.0 * (mn - me) / mn if mn > 0 else 0.0
        lines.append(
            f"| {v} | {o} | {n:,} | {mn:.3f} | {mp:.3f} | {me:.3f} | {reduction:+.2f}% |"
        )
        overall_naive.extend(s["naive_abs"])
        overall_prior.extend(s["prior_abs"])
        overall_evolved.extend(s["evolved_abs"])
        overall_n += n
    if overall_n:
        mn = sum(overall_naive) / overall_n
        mp = sum(overall_prior) / overall_n
        me = sum(overall_evolved) / overall_n
        red = 100.0 * (mn - me) / mn if mn > 0 else 0.0
        lines.append(
            f"| **overall** |  | **{overall_n:,}** | **{mn:.3f}** | **{mp:.3f}** | **{me:.3f}** | **{red:+.2f}%** |"
        )

    # Median variant
    def med(xs):
        s = sorted(xs); return s[len(s)//2] if s else 0.0
    lines += [
        "",
        "Median absolute residual (robust to storm-time outliers):",
        "",
        "| Voxel | Observable | n | naive_L1 | prior_W | evolved_W | substrate vs naive |",
        "|---|---|---|---|---|---|---|",
    ]
    for (v, o), s in sorted(per.items()):
        n = s["n"]
        if n == 0: continue
        mn = med(s["naive_abs"])
        mp = med(s["prior_abs"])
        me = med(s["evolved_abs"])
        red = 100.0 * (mn - me) / mn if mn > 0 else 0.0
        lines.append(
            f"| {v} | {o} | {n:,} | {mn:.3f} | {mp:.3f} | {me:.3f} | {red:+.2f}% |"
        )
    if overall_n:
        mn = med(overall_naive); mp = med(overall_prior); me = med(overall_evolved)
        red = 100.0 * (mn - me) / mn if mn > 0 else 0.0
        lines.append(
            f"| **overall** |  | **{overall_n:,}** | **{mn:.3f}** | **{mp:.3f}** | **{me:.3f}** | **{red:+.2f}%** |"
        )

    # Interpretation
    lines += [
        "",
        "## Interpretation",
        "",
        "The naive ballistic predictor is the standard operational forecast for",
        "lunar-distance IMF in the absence of a learned correction: take what",
        "L1 measures, assume the field convects to the Moon unchanged. This is",
        "decent in *outer_lunar_vicinity* where the Moon is in the solar wind,",
        "and DEGRADES in *magnetotail_transit* where the magnetospheric field",
        "decouples from the upstream IMF.",
        "",
        "The substrate's per-voxel learning is structurally what's required:",
        "the same L1 driver should propagate ~directly when the Moon is in the",
        "solar wind, but ~not at all when the Moon is in the magnetotail. A",
        "single-coupling forecaster (naive_L1) cannot represent this; the",
        "substrate's per-voxel W naturally does.",
        "",
        "The W-magnitudes that show this (from `results/edges_state.json`):",
    ]
    # Show 4 key edges to make this concrete
    interest = [
        ("imf_bz_l1|outer_lunar_vicinity|imf_bz_at_lunar_distance",
         "L1 Bz → lunar Bz in solar wind: large positive (direct propagation)"),
        ("imf_bz_l1|magnetotail_transit|imf_bz_at_lunar_distance",
         "L1 Bz → lunar Bz in magnetotail: smaller positive (partial decoupling)"),
        ("imf_bt_l1|outer_lunar_vicinity|imf_btot_at_lunar_distance",
         "L1 |B| → lunar |B| in solar wind: large positive"),
        ("imf_bt_l1|magnetotail_transit|imf_btot_at_lunar_distance",
         "L1 |B| → lunar |B| in magnetotail: NEAR-NULL (lobe field decoupled from L1)"),
    ]
    for k, why in interest:
        e = json.load(open(EDGES_IN)).get(k)
        if e is None: continue
        lines.append(f"  - `{k}`")
        lines.append(f"    Z={e['Z']:.2f}  W={e['W']:+.4f}  n={e['n']}")
        lines.append(f"    → {why}")

    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {OUT_MD}")

    # Console summary
    print(f"\n  tier-2 substrate vs naive L1 propagation:")
    if overall_n:
        mn = sum(overall_naive) / overall_n
        me = sum(overall_evolved) / overall_n
        red = 100.0 * (mn - me) / mn
        print(f"    overall mean |residual|:  naive={mn:.3f} nT  evolved={me:.3f} nT  ({red:+.2f}%)")
        mn_med = med(overall_naive); me_med = med(overall_evolved)
        red_med = 100.0 * (mn_med - me_med) / mn_med
        print(f"    overall median |residual|: naive={mn_med:.3f} nT  evolved={me_med:.3f} nT  ({red_med:+.2f}%)")


if __name__ == "__main__":
    main()
