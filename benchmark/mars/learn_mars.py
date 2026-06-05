"""
Mars regime — streaming learn pass + tier-1 internal comparator.

24 edges (4 Ls voxels × 1 observable × 6 drivers — f107, ap, kp_index,
sep_proton, flare_xclass, geomag_storm). The framework primitives in
nm_primitives.py are unmodified across regimes; this pass demonstrates
they operate on Mars-shaped data without changes.

Two artifacts:
  1. results/training_summary.md   — per-edge final Z, W, n updates
  2. results/internal_comparator.md — prequential prior-W vs evolved-W
                                       per-voxel ε statistics + anomaly
                                       flag precision under self-reference

The prequential comparator is the LEO benchmark's tier-1 metric pattern,
adapted for the Mars regime where no operational MSIS-equivalent baseline
exists (NAIRAS-Mars and Badhwar-O'Neill exist but no time-aligned public
archive — see README's "External-comparator gap"). The internal
comparator answers: does the substrate's evolved per-edge state actually
predict held-out residual better than the prior?

Falsifiable architecture test (expected on REAL MSL/RAD data):
  - F10.7 edges → NEGATIVE W (solar activity suppresses GCRs reaching surface)
  - sep_proton edges → POSITIVE W (SEP events drive dose spikes when active)
  - ap / kp_index → null contribution (Mars has no global magnetic field
                    deflecting GCRs the way Earth's geomagnetic field does)
  - flare_xclass / geomag_storm → null over the historical RAD window
                    (their driver values are derived from SWPC alerts.json,
                    which is rolling 30-day and does not cover historical
                    RAD data — these are documented gaps, not bugs)
"""

import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from nm_primitives import apply_learning_feedback_in_memory

OBS_JSONL = Path(__file__).parent / "obs.jsonl"
EDGES_OUT = Path(__file__).parent / "results" / "edges_state.json"
SUMMARY_OUT = Path(__file__).parent / "results" / "training_summary.md"
COMPARATOR_OUT = Path(__file__).parent / "results" / "internal_comparator.md"

W_STEP_ZSCORE = 0.02
Z_BIAS_TOL_ZSCORE = 0.30
Z_STD_TOL_ZSCORE = 1.00
ACTIVITY_THRESH_DEFAULT = 0.10
ACTIVITY_THRESH = {
    "sep_proton": 0.01, "flare_xclass": 0.01, "geomag_storm": 0.01,
}

DRIVERS = ["f107", "ap", "kp_index",
           "sep_proton", "flare_xclass", "geomag_storm"]
VOXELS = ["ls_0_90", "ls_90_180", "ls_180_270", "ls_270_360"]
OBSERVABLES = ["surface_dose_rate"]

# Driver normalization → typical |d| ~ 1.
DRIVER_NORM = {
    "f107": ("linear", 100.0),
    "ap": ("linear", 20.0),
    "kp_index": ("linear", 5.0),
    "sep_proton": ("passthrough", 1.0),
    "flare_xclass": ("passthrough", 1.0),
    "geomag_storm": ("passthrough", 1.0),
}


def normalize(name, raw, center=0.0):
    """Linear drivers are centered (so d ~ 0 at typical values), then scaled.
    Passthrough drivers (SEP-like in [0, 1]) are left as-is — they're already
    impulsive (zero outside events) and centering would inject negative state
    during quiet periods.

    Centering is essential under multiplicative-on-baseline composition:
    without it, a large learned |W| inflates or deflates the prediction
    even at "typical" driver values, biasing residuals system-wide.
    """
    if raw is None: return 0.0
    kind, scale = DRIVER_NORM[name]
    if kind == "passthrough":
        return raw
    return (raw - center) / scale


def edge_key(d, v, o):
    return f"{d}|{v}|{o}"


def init_edge():
    return {"certainty": 0.30, "weight": 0.0, "validation_history": []}


def prediction(bl, edges, d_norm, v, o):
    """Compute prediction = baseline × (1 + Σ d_n · W_n) using only
    drivers that pass the activity gate."""
    adjust = sum(
        d_norm[n] * edges[edge_key(n, v, o)]["weight"]
        for n in DRIVERS
        if abs(d_norm[n]) >= ACTIVITY_THRESH.get(n, ACTIVITY_THRESH_DEFAULT)
    )
    return bl * (1.0 + adjust)


def main():
    obs = [json.loads(line) for line in OBS_JSONL.read_text().splitlines() if line]
    obs.sort(key=lambda r: r["t"])
    is_synth = obs[0].get("is_synthetic", False) if obs else False
    schema = obs[0].get("placeholder_schema", "?") if obs else "?"
    print(f"loaded {len(obs):,} records  (synthetic={is_synth}, schema={schema})")

    bucket = defaultdict(list)
    for r in obs:
        bucket[(r["v"], r["obs"])].append(r["o"])
    baseline = {k: statistics.median(vs) for k, vs in bucket.items()}
    voxel_std = {k: max(statistics.stdev(vs), 1e-15) if len(vs) > 1 else 1.0
                 for k, vs in bucket.items()}

    # Driver centers: median of each linear driver across the obs stream.
    # SEP-like passthrough drivers are not centered (see normalize()).
    driver_centers = {}
    for n in DRIVERS:
        kind, _ = DRIVER_NORM[n]
        if kind == "linear":
            vals = [r["d"].get(n) for r in obs if r["d"].get(n) is not None]
            driver_centers[n] = statistics.median(vals) if vals else 0.0
        else:
            driver_centers[n] = 0.0
    print(f"driver centers (linear): "
          + " ".join(f"{n}={driver_centers[n]:.2f}"
                     for n in DRIVERS if DRIVER_NORM[n][0] == "linear"))

    edges = {edge_key(d, v, o): init_edge() for d in DRIVERS for v in VOXELS for o in OBSERVABLES}
    print(f"{len(edges)} edges initialized")

    # Tier-1 comparator state: predict at PRIOR-W (zero) vs evolved-W
    # before each update, then update. Prequential.
    eps_prior = defaultdict(list)     # (v, o) -> list of ε under prior-W baseline
    eps_evolved = defaultdict(list)   # (v, o) -> list of ε under evolved-W
    flag_state = defaultdict(list)    # (v, o) -> list of (eps_evolved, max_Z_at_record)

    # Warm-up: the substrate starts at Z=0.30, W=0. The first ~20% of the
    # stream is spent climbing Z and approaching the fixed-point W. The LEO
    # benchmark's published numbers are computed AFTER the substrate has
    # converged (Z saturated, W stationary); we mirror that here by reserving
    # the first N records for warm-up and only including the remainder in
    # the comparator statistics.
    warmup_n = len(obs) // 5  # 20% warm-up
    print(f"warm-up: first {warmup_n:,} records (state evolves but metrics excluded)")

    n_updates = 0
    for i, r in enumerate(obs):
        v, o = r["v"], r["obs"]
        bl = baseline.get((v, o))
        std = voxel_std.get((v, o))
        if bl is None: continue
        d_norm = {n: normalize(n, r["d"].get(n), driver_centers.get(n, 0.0))
                  for n in DRIVERS}

        # Tier-1: capture prior-W and evolved-W predictions BEFORE update
        p_evolved = prediction(bl, edges, d_norm, v, o)
        # Prior-W = zero-W prediction = the baseline (no learned correction)
        p_prior = bl

        e_prior = (p_prior - r["o"]) / std
        e_evolved = (p_evolved - r["o"]) / std

        # Only record metrics AFTER warm-up. State still evolves before then.
        if i >= warmup_n:
            eps_prior[(v, o)].append(e_prior)
            eps_evolved[(v, o)].append(e_evolved)

            # max_Z across active edges for this record (for tier-1 flag)
            active_zs = [
                edges[edge_key(n, v, o)]["certainty"]
                for n in DRIVERS
                if abs(d_norm[n]) >= ACTIVITY_THRESH.get(n, ACTIVITY_THRESH_DEFAULT)
            ]
            max_z = max(active_zs) if active_zs else 0.0
            flag_state[(v, o)].append((e_evolved, max_z))

        # Apply learning update (uses evolved-W ε signal)
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

    gt_label = ("**REAL** (MSL/RAD detector B, μGy/day)" if not is_synth
                else "**SYNTHETIC PLACEHOLDER**")
    lines = [
        "# Mars benchmark — training summary",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()}",
        f"Window: {obs[0]['t']} → {obs[-1]['t']}",
        f"Observable: surface_dose_rate ({gt_label})",
        f"Schema: `{schema}`",
        f"Voxels: {len(VOXELS)} Ls bins · Drivers: {len(DRIVERS)} · Edges: {len(edges)}",
        f"Updates applied: {n_updates:,}",
        "",
        "## Falsifiable architecture test",
        "",
        ("On real MSL/RAD data we expect:" if not is_synth else
         "On synthetic data we expect:"),
        "  - **f107**: NEGATIVE W (solar activity suppresses GCR access to Mars)",
        "  - **sep_proton**: POSITIVE W (SEP events drive dose spikes when active)",
        "  - **ap, kp_index**: near null (Mars has no global B-field deflecting GCRs)",
        "  - **flare_xclass, geomag_storm**: null over historical RAD window — their",
        "    driver values come from SWPC alerts.json (rolling 30-day) and so are",
        "    zero outside that window; this is a documented gap, not a bug.",
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

    lines += [
        "",
        "## Per-edge state",
        "",
        "| Driver | Voxel | Z | W | n updates |",
        "|---|---|---|---|---|",
    ]
    for k in sorted(final):
        d, v, _ = k.split("|")
        e = final[k]
        lines.append(f"| {d} | {v} | {e['Z']:.3f} | {e['W']:+.4f} | {e['n']} |")

    SUMMARY_OUT.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {SUMMARY_OUT.name}")
    print("\n  median Z and W by driver:")
    for d in DRIVERS:
        rows = by_driver[d]
        med_z = statistics.median(e["Z"] for e in rows)
        med_w = statistics.median(e["W"] for e in rows)
        print(f"    {d:10s}  median Z={med_z:.3f}  median W={med_w:+.4f}")

    # --- internal_comparator.md (tier-1) ---
    comp_lines = [
        "# Tier-1 internal comparator — prior-W vs evolved-W (prequential)",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()}",
        f"Window: {obs[0]['t']} → {obs[-1]['t']}",
        f"Records: {len(obs):,} · Voxels: {len(VOXELS)} · Drivers: {len(DRIVERS)}",
        "",
        "**What this measures.** A single streaming pass over the obs records;",
        "at each step we compute two predictions BEFORE applying the learning",
        "update: `p_prior` (uses W=0 for all edges — the prior-only baseline)",
        "and `p_evolved` (uses the substrate's current W state). ε is",
        "(prediction − observation) / per-voxel residual std. Statistics are",
        "computed across the prequential trajectory; lower |ε| under evolved-W",
        "is the substrate beating its own prior on held-out residual.",
        "",
        "Why this is tier-1: the LEO benchmark uses additive-residual",
        "composition on MSIS as its prediction baseline. The Mars regime has",
        "no time-aligned operational MSIS-equivalent (see README §",
        "External-comparator gap), so the substrate's prior-W prediction is",
        "the only honest self-comparator we can produce today.",
        "",
        "## Per-voxel ε statistics",
        "",
        "| Voxel | n | mean(\\|ε_prior\\|) | mean(\\|ε_evolved\\|) | residual reduction |",
        "|---|---|---|---|---|",
    ]
    overall_prior, overall_evolved, overall_n = [], [], 0
    for v in VOXELS:
        for o in OBSERVABLES:
            ep = eps_prior.get((v, o), [])
            ee = eps_evolved.get((v, o), [])
            if not ep:
                continue
            mp = sum(abs(x) for x in ep) / len(ep)
            me = sum(abs(x) for x in ee) / len(ee)
            reduction_pct = 100.0 * (mp - me) / mp if mp > 0 else 0.0
            comp_lines.append(
                f"| {v} | {len(ep):,} | {mp:.4f} | {me:.4f} | {reduction_pct:+.2f}% |"
            )
            overall_prior.extend(ep); overall_evolved.extend(ee); overall_n += len(ep)
    if overall_prior:
        mp = sum(abs(x) for x in overall_prior) / overall_n
        me = sum(abs(x) for x in overall_evolved) / overall_n
        reduction = 100.0 * (mp - me) / mp if mp > 0 else 0.0
        comp_lines.append(
            f"| **overall** | **{overall_n:,}** | **{mp:.4f}** | **{me:.4f}** | **{reduction:+.2f}%** |"
        )

    # Median variant — robust to Forbush-event outliers (single records
    # can have |ε| ≥ 10σ when dose drops to ~30 µGy/day during SEP-driven
    # solar wind disturbances; the mean is sensitive to these even after warm-up).
    def med_abs(xs):
        sxs = sorted(abs(x) for x in xs)
        return sxs[len(sxs) // 2] if sxs else 0.0
    comp_lines += [
        "",
        "Median variant (robust to Forbush-event outliers):",
        "",
        "| Voxel | n | median(\\|ε_prior\\|) | median(\\|ε_evolved\\|) | residual reduction |",
        "|---|---|---|---|---|",
    ]
    for v in VOXELS:
        for o in OBSERVABLES:
            ep = eps_prior.get((v, o), [])
            ee = eps_evolved.get((v, o), [])
            if not ep:
                continue
            mp = med_abs(ep); me = med_abs(ee)
            red = 100.0 * (mp - me) / mp if mp > 0 else 0.0
            comp_lines.append(
                f"| {v} | {len(ep):,} | {mp:.4f} | {me:.4f} | {red:+.2f}% |"
            )
    mp_med = med_abs(overall_prior); me_med = med_abs(overall_evolved)
    reduction_med = 100.0 * (mp_med - me_med) / mp_med if mp_med > 0 else 0.0
    comp_lines.append(
        f"| **overall** | **{overall_n:,}** | **{mp_med:.4f}** | **{me_med:.4f}** | **{reduction_med:+.2f}%** |"
    )

    # --- Anomaly-flag precision under self-reference ---
    comp_lines += [
        "",
        "## Anomaly-flag precision (self-referenced contingency)",
        "",
        "Flag definition: (max_Z ≥ 0.85) AND (|ε_evolved| ≥ 2σ). \"Anomaly\" =",
        "|ε_prior| ≥ 2σ — i.e., a record where the prior-only baseline would",
        "have substantial residual error. The contingency table answers:",
        "*when the substrate flags a record, is the prior actually wrong?*",
        "",
    ]
    # Self-referenced contingency: substrate flag vs prior-error proxy
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
        "Interpretation: when the substrate flags a record as anomalous (high",
        "Z + large evolved-W residual), the prior-only baseline is also",
        "substantially wrong this fraction of the time. Lift is the precision",
        "divided by the base rate of records where the prior is wrong; >1× means",
        "the substrate's flags are non-random.",
    ]

    COMPARATOR_OUT.write_text("\n".join(comp_lines) + "\n")
    print(f"wrote {COMPARATOR_OUT.name}")

    print(f"\n  tier-1 prequential:")
    print(f"    n records:                  {overall_n:,}")
    print(f"    mean |ε| at prior-W:        {sum(abs(x) for x in overall_prior)/overall_n:.4f}")
    print(f"    mean |ε| at evolved-W:      {sum(abs(x) for x in overall_evolved)/overall_n:.4f}")
    print(f"    residual reduction:         {100*(1 - sum(abs(x) for x in overall_evolved)/sum(abs(x) for x in overall_prior)):+.2f}%")
    print(f"    anomaly-flag precision:     {precision*100:.2f}%  (lift {lift:.2f}× over base rate)")


if __name__ == "__main__":
    main()
