"""
Cislunar regime — streaming learn pass + tier-1 internal comparator.

Observables (2):
  imf_btot_at_lunar_distance  — total field magnitude at lunar distance (nT)
                                from ARTEMIS THB/THC FGM hourly mean
  imf_bz_at_lunar_distance    — GSE Bz at lunar distance (nT)
                                from ARTEMIS THB/THC FGM hourly mean

Voxels (3 declared in cislunar/prior.yaml):
  inner_magnetospheric  — r ≤ 10 RE (ARTEMIS at ~56 RE → empty in this window)
  magnetotail_transit   — nightside inside the magnetotail (lunar transit phase)
  outer_lunar_vicinity  — everything else at r > 10 RE (dominant ARTEMIS regime)

Drivers (12, mirroring GEO+ adding cislunar-specific upstream IMF):
  imf_bz_l1, imf_bt_l1     — OMNI L1-propagated upstream IMF
  sw_speed, sw_density,
  sw_dynamic_pressure       — OMNI L1 plasma
  sep_proton                — GOES SGPS-derived graded SEP intensity
  kp_index, dst_index       — geomag state indices (Kp + OMNI SYM/H)
  f107, ap                  — CelesTrak daily activity
  flare_xclass, geomag_storm — SWPC alerts (rolling, may be zero in window)

Two artifacts:
  results/training_summary.md   — per-edge Z, W, n
  results/internal_comparator.md — prequential prior-W vs evolved-W
                                    per-voxel ε statistics + anomaly flag

Composition: additive residual (same as LEO: p = baseline + (Σ d·W)·σ).
The cislunar IMF observables vary ~ ±tens of nT around a small mean
(~5 nT median |B|, ~0 nT median Bz). A multiplicative form would diverge
when baseline ≈ 0 for Bz. We use the LEO additive-residual prediction
form throughout.
"""

import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from nm_primitives import apply_learning_feedback_in_memory

ROOT = Path(__file__).parent
OBS_JSONL = ROOT / "obs.jsonl"
EDGES_OUT = ROOT / "results" / "edges_state.json"
SUMMARY_OUT = ROOT / "results" / "training_summary.md"
COMPARATOR_OUT = ROOT / "results" / "internal_comparator.md"

# Z-scale framework rescale (same magnitudes as LEO and Mars)
W_STEP_ZSCORE = 0.02
Z_BIAS_TOL_ZSCORE = 0.30
Z_STD_TOL_ZSCORE = 1.00
ACTIVITY_THRESH_DEFAULT = 0.10
ACTIVITY_THRESH = {
    # SEP-like impulsive drivers fire on tiny graded intensity
    "sep_proton": 0.01, "flare_xclass": 0.01, "geomag_storm": 0.01,
}

DRIVERS = [
    "imf_bz_l1", "imf_bt_l1", "sw_speed", "sw_density",
    "sw_dynamic_pressure", "sep_proton", "kp_index", "dst_index",
    "f107", "ap", "flare_xclass", "geomag_storm",
]
VOXELS = ["inner_magnetospheric", "magnetotail_transit", "outer_lunar_vicinity"]
OBSERVABLES = ["imf_btot_at_lunar_distance", "imf_bz_at_lunar_distance"]

# Driver normalization → typical |d| ~ 1 around the centered value.
# Linear drivers are centered at the window median (computed at runtime
# from the obs stream). The values below are scales (units per σ).
DRIVER_NORM = {
    "imf_bz_l1":            ("linear", 5.0),     # nT, typical |Bz_L1| ~5 nT
    "imf_bt_l1":            ("linear", 5.0),     # nT, typical |B_L1| ~5 nT
    "sw_speed":             ("linear", 100.0),   # km/s, typical SW ±100 km/s
    "sw_density":           ("linear", 5.0),     # n/cc
    "sw_dynamic_pressure":  ("linear", 2.0),     # nPa
    "sep_proton":           ("passthrough", 1.0),
    "kp_index":             ("linear", 2.0),
    "dst_index":            ("linear", 30.0),    # SYM/H in nT, sign convention preserved
    "f107":                 ("linear", 50.0),
    "ap":                   ("linear", 15.0),
    "flare_xclass":         ("passthrough", 1.0),
    "geomag_storm":         ("passthrough", 1.0),
}


def normalize(name, raw, center=0.0):
    if raw is None: return 0.0
    kind, scale = DRIVER_NORM[name]
    if kind == "passthrough":
        return raw
    return (raw - center) / scale


def edge_key(d, v, o):
    return f"{d}|{v}|{o}"


def init_edge():
    return {"certainty": 0.30, "weight": 0.0, "validation_history": []}


def prediction(bl, std, edges, d_norm, v, o):
    """Additive-residual: p = baseline + (Σ d·W)·σ (only active drivers)."""
    adjust = sum(
        d_norm[n] * edges[edge_key(n, v, o)]["weight"]
        for n in DRIVERS
        if abs(d_norm[n]) >= ACTIVITY_THRESH.get(n, ACTIVITY_THRESH_DEFAULT)
    )
    return bl + adjust * std


def main():
    obs = [json.loads(line) for line in OBS_JSONL.read_text().splitlines() if line]
    obs.sort(key=lambda r: r["t"])
    print(f"loaded {len(obs):,} obs records")

    # Per-voxel-observable baseline + std (window medians/stdevs)
    bucket = defaultdict(list)
    for r in obs:
        bucket[(r["v"], r["obs"])].append(r["o"])
    baseline = {k: statistics.median(vs) for k, vs in bucket.items()}
    voxel_std = {k: max(statistics.stdev(vs), 1e-15) if len(vs) > 1 else 1.0
                 for k, vs in bucket.items()}
    print(f"baselines (median):")
    for (v, o), bl in sorted(baseline.items()):
        std = voxel_std[(v, o)]
        n = len(bucket[(v, o)])
        print(f"  ({o:32s}, {v:24s})  n={n:>4d}  bl={bl:+7.2f}  σ={std:.2f}")

    # Driver centers (medians) for linear drivers across the obs stream
    driver_centers = {}
    for n in DRIVERS:
        kind, _ = DRIVER_NORM[n]
        if kind == "linear":
            vals = [r["d"].get(n) for r in obs if r["d"].get(n) is not None]
            driver_centers[n] = statistics.median(vals) if vals else 0.0
        else:
            driver_centers[n] = 0.0
    print("driver centers (linear): "
          + " ".join(f"{n}={driver_centers[n]:.2f}"
                     for n in DRIVERS if DRIVER_NORM[n][0] == "linear"))

    # Initialize edges over (driver, voxel, observable)
    edges = {edge_key(d, v, o): init_edge()
             for d in DRIVERS for v in VOXELS for o in OBSERVABLES}
    print(f"{len(edges)} edges initialized")

    # Tier-1 prequential state
    eps_prior = defaultdict(list)
    eps_evolved = defaultdict(list)
    flag_state = defaultdict(list)

    warmup_n = len(obs) // 5
    print(f"warm-up: first {warmup_n:,} records (state evolves but metrics excluded)")

    n_updates = 0
    for i, r in enumerate(obs):
        v, o = r["v"], r["obs"]
        bl = baseline.get((v, o))
        std = voxel_std.get((v, o))
        if bl is None: continue
        d_norm = {n: normalize(n, r["d"].get(n), driver_centers.get(n, 0.0))
                  for n in DRIVERS}

        p_evolved = prediction(bl, std, edges, d_norm, v, o)
        p_prior = bl   # zero-W baseline

        e_prior = (p_prior - r["o"]) / std
        e_evolved = (p_evolved - r["o"]) / std

        if i >= warmup_n:
            eps_prior[(v, o)].append(e_prior)
            eps_evolved[(v, o)].append(e_evolved)
            active_zs = [
                edges[edge_key(n, v, o)]["certainty"]
                for n in DRIVERS
                if abs(d_norm[n]) >= ACTIVITY_THRESH.get(n, ACTIVITY_THRESH_DEFAULT)
            ]
            max_z = max(active_zs) if active_zs else 0.0
            flag_state[(v, o)].append((e_evolved, max_z))

        eps = e_evolved
        for n in DRIVERS:
            if abs(d_norm[n]) < ACTIVITY_THRESH.get(n, ACTIVITY_THRESH_DEFAULT): continue
            k = edge_key(n, v, o)
            edges[k] = apply_learning_feedback_in_memory(
                edges[k], d_norm[n] * eps,
                w_step=W_STEP_ZSCORE,
                z_bias_tol=Z_BIAS_TOL_ZSCORE,
                z_std_tol=Z_STD_TOL_ZSCORE,
            )
            n_updates += 1

    print(f"{n_updates:,} edge updates")

    final = {k: {"Z": round(e["certainty"], 3), "W": round(e["weight"], 4),
                 "n": len(e["validation_history"])}
             for k, e in edges.items()}
    EDGES_OUT.parent.mkdir(exist_ok=True)
    EDGES_OUT.write_text(json.dumps(final, indent=2))

    # --- training_summary.md ---
    by_driver = defaultdict(list)
    for k, e in final.items():
        d = k.split("|")[0]
        by_driver[d].append(e)
    by_observable = defaultdict(list)
    for k, e in final.items():
        d, v, ob = k.split("|")
        by_observable[ob].append((d, v, e))

    lines = [
        "# Cislunar benchmark — training summary",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()}",
        f"Window: {obs[0]['t']} → {obs[-1]['t']}",
        f"Observables: {OBSERVABLES} (THB+THC FGM hourly mean, nT)",
        f"Voxels: {len(VOXELS)} physics regions · Drivers: {len(DRIVERS)} · Edges: {len(edges)}",
        f"Updates applied: {n_updates:,}",
        "",
        "## Falsifiable architecture predictions",
        "",
        "Expected sign + magnitude under known cislunar physics:",
        "  - **imf_bz_l1 → imf_bz_at_lunar_distance**: positive, converging toward",
        "    +1 (direct L1→lunar propagation; Bz_GSE preserved to leading order).",
        "  - **imf_bt_l1 → imf_btot_at_lunar_distance**: positive (same reasoning).",
        "  - **sw_dynamic_pressure → imf_btot**: positive when Moon outside",
        "    magnetopause (compression of nearby IMF), null inside magnetopause.",
        "    The voxel-dependent sign IS the architecture test, mirroring Mars's",
        "    voxel-dependent sep_proton W.",
        "  - **sep_proton → imf_btot**: near-null (SEP events arrive with their own",
        "    IMF disturbance, but the SEP intensity is not the field-magnitude driver).",
        "  - **null drivers** (flare_xclass, geomag_storm, kp_index when its rolling",
        "    feed misses the window): stay near W = 0 at low Z.",
        "",
        "| Driver | n edges | median Z | median W | W sign pattern |",
        "|---|---|---|---|---|",
    ]
    for d in DRIVERS:
        rows = by_driver[d]
        med_z = statistics.median(e["Z"] for e in rows)
        med_w = statistics.median(e["W"] for e in rows)
        signs = [("−" if e["W"] < -0.005 else "+" if e["W"] > 0.005 else "·") for e in rows]
        lines.append(f"| {d} | {len(rows)} | {med_z:.3f} | {med_w:+.4f} | {''.join(signs)} |")

    lines += ["", "## Per-edge state",
              "",
              "| Driver | Voxel | Observable | Z | W | n updates |",
              "|---|---|---|---|---|---|"]
    for k in sorted(final):
        d, v, ob = k.split("|")
        e = final[k]
        lines.append(f"| {d} | {v} | {ob} | {e['Z']:.3f} | {e['W']:+.4f} | {e['n']} |")

    SUMMARY_OUT.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {SUMMARY_OUT.name}")
    print("\n  median Z / median W by driver:")
    for d in DRIVERS:
        rows = by_driver[d]
        med_z = statistics.median(e["Z"] for e in rows)
        med_w = statistics.median(e["W"] for e in rows)
        print(f"    {d:24s}  med Z={med_z:.3f}  med W={med_w:+.4f}  (n={len(rows)} edges)")

    # --- internal_comparator.md (tier-1) ---
    comp_lines = [
        "# Tier-1 internal comparator — prior-W vs evolved-W (prequential)",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()}",
        f"Window: {obs[0]['t']} → {obs[-1]['t']}",
        f"Records: {len(obs):,} · Voxels: {len(VOXELS)} · Observables: {len(OBSERVABLES)} · Drivers: {len(DRIVERS)}",
        "",
        "**What this measures.** Single streaming pass; at each record we",
        "compute two predictions before applying the learning update:",
        "`p_prior` (uses W=0 everywhere → prediction is the per-voxel-observable",
        "median) and `p_evolved` (uses the substrate's current W state with",
        "additive residual composition). ε = (prediction − observation) / std.",
        "Statistics are computed across the prequential trajectory.",
        "",
        "Why this is tier-1: the cislunar regime has no operational SWPC-equivalent",
        "for IMF at lunar distance (REFM exists for ≥2 MeV electrons at GEO;",
        "MSIS exists for LEO density; no public-archive operational baseline",
        "exists for Bz at lunar distance). Tier-2 is the substrate-vs-naive-L1",
        "comparator in `analyze_l1_propagation.py`; tier-3 is the falsifiable",
        "architecture test in `analyze_sign_convergence.py`.",
        "",
        "## Per-voxel × observable ε statistics",
        "",
        "| Voxel | Observable | n | mean(\\|ε_prior\\|) | mean(\\|ε_evolved\\|) | residual reduction |",
        "|---|---|---|---|---|---|",
    ]
    overall_prior, overall_evolved, overall_n = [], [], 0
    for v in VOXELS:
        for o in OBSERVABLES:
            ep = eps_prior.get((v, o), [])
            ee = eps_evolved.get((v, o), [])
            if not ep:
                comp_lines.append(f"| {v} | {o} | 0 | — | — | (empty in window) |")
                continue
            mp = sum(abs(x) for x in ep) / len(ep)
            me = sum(abs(x) for x in ee) / len(ee)
            red = 100.0 * (mp - me) / mp if mp > 0 else 0.0
            comp_lines.append(f"| {v} | {o} | {len(ep):,} | {mp:.4f} | {me:.4f} | {red:+.2f}% |")
            overall_prior.extend(ep); overall_evolved.extend(ee); overall_n += len(ep)
    if overall_prior:
        mp = sum(abs(x) for x in overall_prior) / overall_n
        me = sum(abs(x) for x in overall_evolved) / overall_n
        red = 100.0 * (mp - me) / mp if mp > 0 else 0.0
        comp_lines.append(f"| **overall** |  | **{overall_n:,}** | **{mp:.4f}** | **{me:.4f}** | **{red:+.2f}%** |")

    # Median variant
    def med_abs(xs):
        s = sorted(abs(x) for x in xs)
        return s[len(s)//2] if s else 0.0
    comp_lines += [
        "",
        "Median variant (robust to event-driven outliers):",
        "",
        "| Voxel | Observable | n | median(\\|ε_prior\\|) | median(\\|ε_evolved\\|) | residual reduction |",
        "|---|---|---|---|---|---|",
    ]
    for v in VOXELS:
        for o in OBSERVABLES:
            ep = eps_prior.get((v, o), [])
            ee = eps_evolved.get((v, o), [])
            if not ep: continue
            mp = med_abs(ep); me = med_abs(ee)
            red = 100.0 * (mp - me) / mp if mp > 0 else 0.0
            comp_lines.append(f"| {v} | {o} | {len(ep):,} | {mp:.4f} | {me:.4f} | {red:+.2f}% |")
    mp_med = med_abs(overall_prior); me_med = med_abs(overall_evolved)
    red_med = 100.0 * (mp_med - me_med) / mp_med if mp_med > 0 else 0.0
    comp_lines.append(f"| **overall** |  | **{overall_n:,}** | **{mp_med:.4f}** | **{me_med:.4f}** | **{red_med:+.2f}%** |")

    # Anomaly-flag precision (self-referenced)
    comp_lines += [
        "",
        "## Anomaly-flag precision (self-referenced contingency)",
        "",
        "Flag: (max_Z ≥ 0.85) AND (|ε_evolved| ≥ 2σ). \"Anomaly\" = |ε_prior| ≥ 2σ.",
        "Answers: *when the substrate flags an IMF record, was the prior-only baseline*",
        "*also substantially wrong?*",
        "",
    ]
    flag_pos_anom = flag_pos_ok = flag_neg_anom = flag_neg_ok = 0
    for (v, o), rows in flag_state.items():
        eps_p = eps_prior[(v, o)]
        for (e_ev, mz), e_p in zip(rows, eps_p):
            substrate_flag = (mz >= 0.85) and (abs(e_ev) >= 2.0)
            prior_anom = abs(e_p) >= 2.0
            if substrate_flag and prior_anom:
                flag_pos_anom += 1
            elif substrate_flag and not prior_anom:
                flag_pos_ok += 1
            elif not substrate_flag and prior_anom:
                flag_neg_anom += 1
            else:
                flag_neg_ok += 1
    n_total = flag_pos_anom + flag_pos_ok + flag_neg_anom + flag_neg_ok
    n_anom = flag_pos_anom + flag_neg_anom
    n_flag = flag_pos_anom + flag_pos_ok
    precision = (flag_pos_anom / n_flag) if n_flag > 0 else 0.0
    recall = (flag_pos_anom / n_anom) if n_anom > 0 else 0.0
    base_rate = (n_anom / n_total) if n_total > 0 else 0.0
    lift = (precision / base_rate) if base_rate > 0 else float("inf")
    comp_lines += [
        f"|  | prior anom (|ε_prior|≥2σ) | prior OK |",
        f"|---|---|---|",
        f"| **substrate flag** | {flag_pos_anom:,} | {flag_pos_ok:,} |",
        f"| substrate quiet | {flag_neg_anom:,} | {flag_neg_ok:,} |",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Precision | {precision*100:.2f}% |",
        f"| Recall | {recall*100:.2f}% |",
        f"| Base rate | {base_rate*100:.2f}% |",
        f"| Lift over base rate | {lift:.2f}× |",
        "",
        "Interpretation: precision is *the fraction of substrate flags that*",
        "*correspond to a real prior-baseline anomaly*; lift > 1× means the",
        "substrate's anomaly flags are non-random under self-reference.",
    ]
    COMPARATOR_OUT.write_text("\n".join(comp_lines) + "\n")
    print(f"wrote {COMPARATOR_OUT.name}")

    print(f"\n  tier-1 prequential:")
    print(f"    n records:               {overall_n:,}")
    print(f"    mean |ε| at prior-W:     {sum(abs(x) for x in overall_prior)/overall_n:.4f}")
    print(f"    mean |ε| at evolved-W:   {sum(abs(x) for x in overall_evolved)/overall_n:.4f}")
    red_pct = 100*(1 - sum(abs(x) for x in overall_evolved)/sum(abs(x) for x in overall_prior))
    print(f"    residual reduction:      {red_pct:+.2f}%")
    print(f"    anomaly-flag precision:  {precision*100:.2f}%  (lift {lift:.2f}× over base rate)")


if __name__ == "__main__":
    main()
