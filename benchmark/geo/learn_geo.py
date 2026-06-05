"""
GEO regime — minimal learning pipeline that streams observations through the
framework primitives in nm_primitives.py. Skeleton scope: prove the LEO
architecture transfers to GEO data with no MCP-server changes.

Per geo/prior.yaml: 6 LT voxels × 4 target observables × 8 drivers.

NOT skeleton-scope (intentionally deferred):
  - AE9/AP9 baseline integration (additive_residual on a real comparator)
  - NCEI multi-year backfill
  - e_flux_hot_plasma (needs an MPS-LO feed, not in primary SWPC JSON)
  - Per-regime z-bias/std/W_STEP retuning vs LEO defaults

ε convention is z-score per learn_gracefo_full_year.py: |ε| ~ 1σ.
The framework's magnitude tolerances rescale together — see
~/space-waze/math_functions.md §3.1.
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
# Per-step prediction trajectory (used by tier-1/tier-2 analyses).
PREDS_OUT = Path(__file__).parent / "results" / "preds.jsonl"
# Per-edge Z evolution snapshots (used by analyze_lead_time-style code).
TRAJ_OUT = Path(__file__).parent / "results" / "trajectory.jsonl"

# z-score ε rescale (matches the LEO pipeline override of MCP defaults)
W_STEP_ZSCORE = 0.02
Z_BIAS_TOL_ZSCORE = 0.30
Z_STD_TOL_ZSCORE = 1.00
# Per-driver activity floor. Physical drivers use 0.10 as a noise gate
# (sw_speed deviation > 50 km/s, B-field > 0.5 nT, etc). SWPC-alert-derived
# drivers come from sep_alerts.py already in [0, 1] with no instrument noise —
# any nonzero value is real residual activity from a recent event, so we
# gate them at 0.01 (admit decay tails but reject pure zeros).
ACTIVITY_THRESH_DEFAULT = 0.10
ACTIVITY_THRESH = {
    "sep_proton": 0.01, "relativistic_electron": 0.01,
    "flare_xclass": 0.01, "geomag_storm": 0.01,
}

DRIVERS = ["sw_speed", "sw_density", "imf_bz", "imf_bt", "xrs_long",
           "mgii_index", "kp_index", "dst",
           "sep_proton", "relativistic_electron", "flare_xclass", "geomag_storm"]
VOXELS = ["lt_0_4", "lt_4_8", "lt_8_12", "lt_12_16", "lt_16_20", "lt_20_24"]
OBSERVABLES = ["e_flux_gt_2mev", "p_flux_gt_10mev", "p_flux_gt_50mev",
               "b_field_magnitude", "e_flux_warm_plasma"]

# Per-observable prediction composition. "multiplicative" suits flux observables
# whose driver-driven range spans factors (storm enhancements 10×–10000×).
# "additive_residual" suits signed/bounded observables (B-field magnitude at GEO
# varies ~±30 nT around ~100 nT — multiplicative coupling with 8+ active drivers
# saturated W at ±1 in the original skeleton). Form: p = bl + (Σ d·W)·σ.
PREDICTION_FORM = {
    "e_flux_gt_2mev":   "multiplicative",
    "p_flux_gt_10mev":  "multiplicative",
    "p_flux_gt_50mev":  "multiplicative",
    "b_field_magnitude": "additive_residual",
    "e_flux_warm_plasma": "multiplicative",
}

# Driver normalization (target |d|~1 in typical conditions; rough physical scales).
# SWPC-alert-derived drivers are already in [0, 1] — pass through.
DRIVER_NORM = {
    "sw_speed":             ("linear", 500.0),     # km/s
    "sw_density":           ("linear", 5.0),       # cm^-3
    "imf_bz":               ("linear", 5.0),       # nT
    "imf_bt":               ("linear", 8.0),       # nT
    "xrs_long":             ("log10",  1e-7),      # W/m^2 — log-scaled, flare regime
    "mgii_index":           ("linear", 0.27),      # MgII core/wing baseline ratio
    "kp_index":             ("linear", 5.0),       # Kp
    "dst":                  ("linear", -50.0),     # nT (negative scale: storm → +1)
    "sep_proton":           ("passthrough", 1.0),  # already [0, 1] from sep_alerts
    "relativistic_electron":("passthrough", 1.0),
    "flare_xclass":         ("passthrough", 1.0),
    "geomag_storm":         ("passthrough", 1.0),
}


def normalize(name, raw):
    if raw is None: return 0.0
    kind, scale = DRIVER_NORM[name]
    if kind == "log10":
        if raw <= 0: return 0.0
        return math.log10(max(raw, 1e-12) / scale)
    if kind == "passthrough":
        return raw
    return raw / scale


def edge_key(d, v, o):
    return f"{d}|{v}|{o}"


def init_edge(initial_z=0.30, initial_w=0.0):
    return {"certainty": initial_z, "weight": initial_w, "validation_history": []}


def main():
    print(f"loading {OBS_JSONL.name}…")
    obs = [json.loads(line) for line in OBS_JSONL.read_text().splitlines() if line]
    obs.sort(key=lambda r: r["t"])
    print(f"  {len(obs)} records")

    # Per-(voxel, observable) baseline (median) and residual std.
    # For flux observables (multiplicative composition), the std is computed
    # in log10 space because flux distributions are heavy-tailed and the
    # multiplicative-coupling residual ε = (p − o) / σ is meaningful only when
    # σ is set on a scale where σ ≈ typical (p − o). For B-field (additive),
    # std stays in linear space.
    bucket = defaultdict(list)
    for r in obs:
        bucket[(r["v"], r["obs"])].append(r["o"])
    baseline = {}
    voxel_std = {}
    for (v, o), vs in bucket.items():
        if PREDICTION_FORM[o] == "additive_residual":
            baseline[(v, o)] = statistics.median(vs)
            voxel_std[(v, o)] = max(statistics.stdev(vs), 1e-15) if len(vs) > 1 else 1.0
        else:
            # log10 baseline + log10 residual std; flux observables span OOM
            logs = [math.log10(max(x, 1e-12)) for x in vs]
            baseline[(v, o)] = 10 ** statistics.median(logs)
            voxel_std[(v, o)] = max(statistics.stdev(logs), 1e-3) if len(logs) > 1 else 1.0
    print(f"  {len(baseline)} (voxel, observable) prediction buckets")

    # Initialize 12 × 6 × 5 = 360 edges, all at the default prior
    edges = {}
    for d in DRIVERS:
        for v in VOXELS:
            for o in OBSERVABLES:
                edges[edge_key(d, v, o)] = init_edge()
    print(f"  {len(edges)} edges initialized at Z={0.30}, W=0.0")

    # ε is dimensionless across observables:
    #   - additive_residual:  ε = (p − o) / σ_linear
    #   - multiplicative:     ε = (log10 p − log10 o) / σ_log10
    # This lets us reuse the same Z-tolerance constants across observable types.

    preds_f = open(PREDS_OUT, "w")
    traj_f = open(TRAJ_OUT, "w")
    # Snapshot edge Z to trajectory every N records (keep file small).
    # At 200/record stride and ~18K obs, file is ~4MB.
    TRAJ_EVERY = 200

    # Streaming training pass
    n_updates = 0
    n_skipped_inactive = 0
    for idx, r in enumerate(obs):
        v, o = r["v"], r["obs"]
        bl = baseline.get((v, o))
        std = voxel_std.get((v, o))
        if bl is None or std is None: continue

        d_norm = {name: normalize(name, r["d"].get(name)) for name in DRIVERS}

        # Joint prediction. Composition mode is per-observable (see PREDICTION_FORM
        # comment above for why B-field uses additive_residual to avoid multi-driver
        # saturation on a quantity with naturally bounded relative variation).
        adjust = 0.0
        for name in DRIVERS:
            if abs(d_norm[name]) < ACTIVITY_THRESH.get(name, ACTIVITY_THRESH_DEFAULT): continue
            adjust += d_norm[name] * edges[edge_key(name, v, o)]["weight"]
        if PREDICTION_FORM[o] == "additive_residual":
            p = bl + adjust * std
            eps_joint = (p - r["o"]) / std
            # Prior-W (W=0) baseline prediction = bl (no driver coupling)
            p_baseline = bl
        else:
            # Log-space multiplicative composition; bounded coupling per
            # OOM scale so 8+ active drivers don't accumulate to ±∞ in linear
            # space. p = bl * 10^(adjust * std_log).
            log_adjust = adjust * std  # adjust is unitless, std is in log10 units
            # Clamp log_adjust to ±3 OOM (factor 1000) to prevent runaway during
            # transient storm onsets — physical fluxes don't move 5+ OOM in
            # one step, and this preserves Z-update sign without W-saturation.
            if log_adjust > 3.0: log_adjust = 3.0
            if log_adjust < -3.0: log_adjust = -3.0
            p = bl * (10 ** log_adjust)
            # ε in log10 space
            eps_joint = (math.log10(max(p, 1e-12)) - math.log10(max(r["o"], 1e-12))) / std
            p_baseline = bl

        preds_f.write(json.dumps({
            "t": r["t"], "v": v, "obs": o,
            "o": r["o"], "p": p, "p_baseline": p_baseline,
            "eps": eps_joint,
        }) + "\n")

        for name in DRIVERS:
            if abs(d_norm[name]) < ACTIVITY_THRESH.get(name, ACTIVITY_THRESH_DEFAULT):
                n_skipped_inactive += 1
                continue
            k = edge_key(name, v, o)
            # OLS-gradient attribution: pass d_i * eps to the primitive
            updated = apply_learning_feedback_in_memory(
                edges[k], d_norm[name] * eps_joint,
                w_step=W_STEP_ZSCORE,
                z_bias_tol=Z_BIAS_TOL_ZSCORE,
                z_std_tol=Z_STD_TOL_ZSCORE,
            )
            edges[k] = updated
            n_updates += 1

        if idx % TRAJ_EVERY == 0:
            # Snapshot ALL edges' Z/W at this timestamp (kept small via stride).
            for k, e in edges.items():
                traj_f.write(json.dumps({
                    "t": r["t"], "src": k.split("|")[0], "v": k.split("|")[1],
                    "obs": k.split("|")[2],
                    "Z": e["certainty"], "W": e["weight"],
                }) + "\n")

    # Final trajectory snapshot
    for k, e in edges.items():
        traj_f.write(json.dumps({
            "t": obs[-1]["t"], "src": k.split("|")[0], "v": k.split("|")[1],
            "obs": k.split("|")[2],
            "Z": e["certainty"], "W": e["weight"],
        }) + "\n")
    preds_f.close()
    traj_f.close()

    print(f"  {n_updates:,} edge updates applied, {n_skipped_inactive:,} skipped (driver inactive)")

    # ---- summarize ----
    final = {k: {"Z": e["certainty"], "W": e["weight"], "n": len(e["validation_history"])}
             for k, e in edges.items()}
    EDGES_OUT.parent.mkdir(exist_ok=True)
    EDGES_OUT.write_text(json.dumps(final, indent=2))

    zs = [e["Z"] for e in final.values()]
    ws = [e["W"] for e in final.values()]
    z_above_85 = sum(1 for z in zs if z >= 0.85)
    z_below_30 = sum(1 for z in zs if z < 0.30)
    by_obs = defaultdict(list)
    for k, e in final.items():
        obs_name = k.split("|")[-1]
        by_obs[obs_name].append(e["Z"])

    lines = [
        "# GEO benchmark — training summary",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()}",
        f"Window: {obs[0]['t']} → {obs[-1]['t']}  (7-day SWPC primary feed, GOES-19)",
        f"Voxels: {len(VOXELS)} LT bins  ·  Observables: {len(OBSERVABLES)}  ·  Drivers: {len(DRIVERS)}",
        f"Edges initialized: {len(edges)}  ·  Updates applied: {n_updates:,}",
        "",
        "## Z distribution after one streaming pass",
        "",
        f"| Statistic | Value |",
        f"|---|---|",
        f"| Edges Z ≥ 0.85 (curiosity-converged) | {z_above_85} / {len(zs)} |",
        f"| Edges Z < 0.30 (below initial prior) | {z_below_30} / {len(zs)} |",
        f"| Median Z | {statistics.median(zs):.3f} |",
        f"| W range (min … max) | {min(ws):+.3f} … {max(ws):+.3f} |",
        "",
        "## Per-observable Z (median across voxels × drivers)",
        "",
        "| Observable | n edges | median Z |",
        "|---|---|---|",
    ]
    for o in OBSERVABLES:
        if by_obs[o]:
            lines.append(f"| {o} | {len(by_obs[o])} | {statistics.median(by_obs[o]):.3f} |")
    lines += [
        "",
        "## Next-stage analyses",
        "",
        "- **Tier-1 internal comparator:** `python3 analyze_internal.py` → "
        "  `results/internal_comparator.md`",
        "- **Tier-2 external comparator (REFM):** `python3 analyze_refm.py` → "
        "  `results/tier2_refm_comparison.md`",
        "- **Tier-3 falsifiable architecture test:** `python3 analyze_sign_convergence.py` "
        "  → `results/tier3_sign_convergence.md`",
        "- **Lead-time analysis (LEO parity):** `python3 analyze_lead_time.py` → "
        "  `results/lead_time_by_severity.md`",
        "",
        "## Window-coverage caveat",
        "",
        f"This summary covers a 7-day SWPC rolling window. The 5/5 observables × "
        f"{len(VOXELS)} voxels × {len(DRIVERS)} drivers = {len(edges)} edges saturate "
        "Z=1 for the drivers that have evidence in window (high-cadence DSCOVR / "
        "GOES-XRS / Dst); the SEP/CME alert-derived drivers carry decay-tail "
        "intensity only because no actively-rising SEP events occurred in the obs "
        "window (see `tier3_sign_convergence.md` for the falsifiable test result and "
        "scope notes). Multi-month NCEI backfill is the prerequisite for events-"
        "in-window evidential convergence of the SEP/CME edges.",
    ]
    SUMMARY_OUT.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {EDGES_OUT.name}")
    print(f"wrote {SUMMARY_OUT.name}")
    print(f"\n  Z ≥ 0.85: {z_above_85}/{len(zs)}    Z < 0.30: {z_below_30}/{len(zs)}    "
          f"median Z: {statistics.median(zs):.3f}    W range: {min(ws):+.3f}..{max(ws):+.3f}")


if __name__ == "__main__":
    main()
