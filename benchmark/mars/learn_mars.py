"""
Mars regime — minimal streaming learn pass.

12 edges (4 Ls voxels × 1 observable × 3 drivers). Demonstrates that the
LEO/GEO framework primitives operate on Mars-shaped data with no
modifications.

Expected behavior on synthetic ground truth (which was generated with
F10.7-anticorrelated baseline + SEP injections + noise):
  - F10.7 edges: should converge with NEGATIVE W (high solar → low dose)
  - Ap edges: should stay near prior or collapse (no causal Mars relation)
  - Kp edges: should stay near prior or collapse (geomagnetic, not Mars)

This is a falsifiable test of the framework's ability to separate a real
causal driver from spurious ones — even on a single observable, single
site, with sparse driver dimensionality.
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
# sep_* and other SWPC-alert drivers come from sep_alerts.py already in [0, 1].
DRIVER_NORM = {
    "f107": ("linear", 100.0),
    "ap": ("linear", 20.0),
    "kp_index": ("linear", 5.0),
    "sep_proton": ("passthrough", 1.0),
    "flare_xclass": ("passthrough", 1.0),
    "geomag_storm": ("passthrough", 1.0),
}


def normalize(name, raw):
    if raw is None: return 0.0
    kind, scale = DRIVER_NORM[name]
    if kind == "passthrough":
        return raw
    return raw / scale


def edge_key(d, v, o):
    return f"{d}|{v}|{o}"


def init_edge():
    return {"certainty": 0.30, "weight": 0.0, "validation_history": []}


def main():
    obs = [json.loads(line) for line in OBS_JSONL.read_text().splitlines() if line]
    obs.sort(key=lambda r: r["t"])
    print(f"loaded {len(obs):,} records")

    bucket = defaultdict(list)
    for r in obs:
        bucket[(r["v"], r["obs"])].append(r["o"])
    baseline = {k: statistics.median(vs) for k, vs in bucket.items()}
    voxel_std = {k: max(statistics.stdev(vs), 1e-15) if len(vs) > 1 else 1.0
                 for k, vs in bucket.items()}

    edges = {edge_key(d, v, o): init_edge() for d in DRIVERS for v in VOXELS for o in OBSERVABLES}
    print(f"{len(edges)} edges initialized")

    n_updates = 0
    for r in obs:
        v, o = r["v"], r["obs"]
        bl = baseline.get((v, o))
        std = voxel_std.get((v, o))
        if bl is None: continue
        d_norm = {n: normalize(n, r["d"].get(n)) for n in DRIVERS}
        adjust = sum(d_norm[n] * edges[edge_key(n, v, o)]["weight"]
                     for n in DRIVERS
                     if abs(d_norm[n]) >= ACTIVITY_THRESH.get(n, ACTIVITY_THRESH_DEFAULT))
        p = bl * (1.0 + adjust)
        eps = (p - r["o"]) / std
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

    # Group by driver to see the falsifiable test outcome
    by_driver = defaultdict(list)
    for k, e in final.items():
        d = k.split("|")[0]
        by_driver[d].append(e)

    lines = [
        "# Mars skeleton — training summary",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()}",
        f"Window: {obs[0]['t']} → {obs[-1]['t']} (1 Earth year)",
        f"Observable: surface_dose_rate (**SYNTHETIC PLACEHOLDER** — see README)",
        f"Voxels: {len(VOXELS)} Ls bins · Drivers: {len(DRIVERS)} · Edges: {len(edges)}",
        f"Updates applied: {n_updates:,}",
        "",
        "## Falsifiable test outcome",
        "",
        "Synthetic ground truth was generated with F10.7-anticorrelated baseline + SEP",
        "spikes. F10.7 has a real causal relationship with the synthetic observable;",
        "Ap and Kp do not. We expect F10.7 edges to converge with negative W and",
        "Ap/Kp edges to stay near prior.",
        "",
        "| Driver | n edges | median Z | median W | W sign pattern |",
        "|---|---|---|---|---|",
    ]
    for d in DRIVERS:
        rows = by_driver[d]
        med_z = statistics.median(e["Z"] for e in rows)
        med_w = statistics.median(e["W"] for e in rows)
        signs = [("−" if e["W"] < -0.05 else "+" if e["W"] > 0.05 else "·") for e in rows]
        lines.append(f"| {d} | {len(rows)} | {med_z:.3f} | {med_w:+.3f} | {''.join(signs)} |")

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


if __name__ == "__main__":
    main()
