"""
Mars regime — SEP event response analysis.

The LEO benchmark's headline lead-time table reports per-storm flag
severity ahead of peak Dst, across 21 Dst≤−100nT storms. Mars analog:
for each GOES SGPS-identified SEP event in the benchmark window, report
the substrate's flag response in the RAD dose record near the event.

This is the Mars equivalent of LEO's storm-replay table. Differences:
  - Mars triggering event = SEP (GOES proton onset), not geomagnetic storm
  - "Flag" = substrate-determined anomaly in MSL RAD dose
  - Lead-time framing inverted: we report dose response IN the event
    window relative to baseline, not flag-time relative to peak

We define an "SEP event" as a GOES-18 SGPS >=10 MeV integral flux that
crosses 10 pfu and stays above 1 pfu for at least 2 hours. Event window
is onset → onset+48h (matches the SEP-driver decay constant).

For each event, report:
  - peak proton flux at GOES (pfu)
  - peak Mars dose-rate observed (MSL RAD) and Δ vs voxel baseline
  - max framework |ε_evolved| in the event window
  - whether the substrate flagged (max_Z ≥ 0.85 AND |ε| ≥ 2σ)

Reproduce: python3 analyze_sep_events.py
"""

import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nm_primitives import apply_learning_feedback_in_memory

OBS_JSONL = Path(__file__).parent / "obs.jsonl"
PROTONS_JSONL = Path(__file__).parent / "raw" / "goes_protons_hourly.jsonl"
EDGES_OUT = Path(__file__).parent / "results" / "edges_state.json"
OUT = Path(__file__).parent / "results" / "sep_event_response.md"

# Constants — must match learn_mars.py
DRIVERS = ["f107", "ap", "kp_index", "sep_proton", "flare_xclass", "geomag_storm"]
DRIVER_NORM = {"f107": ("linear", 100.0), "ap": ("linear", 20.0),
               "kp_index": ("linear", 5.0), "sep_proton": ("passthrough", 1.0),
               "flare_xclass": ("passthrough", 1.0), "geomag_storm": ("passthrough", 1.0)}
ACTIVITY_THRESH = {"sep_proton": 0.01, "flare_xclass": 0.01, "geomag_storm": 0.01}
ACTIVITY_DEFAULT = 0.10
W_STEP = 0.02; ZBT = 0.30; ZST = 1.00


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def identify_sep_events(proton_path, onset_threshold=10.0, sustain_threshold=1.0,
                         min_duration_h=2):
    """Find SEP events: hourly flux crosses 10 pfu, stays above 1 pfu.
    Returns list of (onset_dt, peak_dt, peak_flux, end_dt)."""
    prot = sorted([json.loads(l) for l in Path(proton_path).read_text().splitlines() if l],
                  key=lambda r: r["t"])
    events = []
    in_event = False
    onset = peak_t = end_t = None
    peak_flux = 0.0
    sustain_count = 0
    for r in prot:
        t = parse_iso(r["t"])
        f = r["flux_ge_10mev"]
        if not in_event:
            if f >= onset_threshold:
                in_event = True
                onset = t
                peak_t = t
                peak_flux = f
                sustain_count = 1
        else:
            if f > peak_flux:
                peak_flux = f
                peak_t = t
            if f >= sustain_threshold:
                sustain_count += 1
                end_t = t
            else:
                if sustain_count >= min_duration_h:
                    events.append((onset, peak_t, peak_flux, end_t))
                in_event = False
                sustain_count = 0
    if in_event and sustain_count >= min_duration_h:
        events.append((onset, peak_t, peak_flux, end_t or peak_t))
    return events


def normalize(name, raw, center=0.0):
    if raw is None: return 0.0
    kind, scale = DRIVER_NORM[name]
    if kind == "passthrough":
        return raw
    return (raw - center) / scale


def edge_key(d, v, o):
    return f"{d}|{v}|{o}"


def replay_substrate(obs):
    """Re-run learning, return per-record (t, v, eps_evolved, max_z, dose).
    Mirrors learn_mars.py main loop exactly."""
    bucket = defaultdict(list)
    for r in obs:
        bucket[(r["v"], r["obs"])].append(r["o"])
    baseline = {k: statistics.median(vs) for k, vs in bucket.items()}
    voxel_std = {k: max(statistics.stdev(vs), 1e-15) if len(vs) > 1 else 1.0
                 for k, vs in bucket.items()}
    centers = {}
    for n in DRIVERS:
        kind, _ = DRIVER_NORM[n]
        if kind == "linear":
            vals = [r["d"].get(n) for r in obs if r["d"].get(n) is not None]
            centers[n] = statistics.median(vals) if vals else 0.0
        else:
            centers[n] = 0.0
    edges = {edge_key(d, v, o): dict(certainty=0.30, weight=0.0, validation_history=[])
             for d in DRIVERS for v in ["ls_0_90","ls_90_180","ls_180_270","ls_270_360"]
             for o in ["surface_dose_rate"]}
    trace = []
    for r in obs:
        v, o = r["v"], r["obs"]
        bl = baseline.get((v, o)); std = voxel_std.get((v, o))
        if bl is None: continue
        d_norm = {n: normalize(n, r["d"].get(n), centers.get(n, 0.0)) for n in DRIVERS}
        adjust = sum(d_norm[n] * edges[edge_key(n, v, o)]["weight"] for n in DRIVERS
                     if abs(d_norm[n]) >= ACTIVITY_THRESH.get(n, ACTIVITY_DEFAULT))
        p_evolved = bl * (1.0 + adjust)
        eps = (p_evolved - r["o"]) / std
        active_zs = [edges[edge_key(n, v, o)]["certainty"] for n in DRIVERS
                     if abs(d_norm[n]) >= ACTIVITY_THRESH.get(n, ACTIVITY_DEFAULT)]
        max_z = max(active_zs) if active_zs else 0.0
        trace.append({
            "t": parse_iso(r["t"]), "v": v, "o": r["o"], "bl": bl, "std": std,
            "eps": eps, "max_z": max_z,
            "sep_driver": r["d"].get("sep_proton", 0.0),
        })
        for n in DRIVERS:
            if abs(d_norm[n]) < ACTIVITY_THRESH.get(n, ACTIVITY_DEFAULT): continue
            k = edge_key(n, v, o)
            edges[k] = apply_learning_feedback_in_memory(
                edges[k], d_norm[n] * eps,
                w_step=W_STEP, z_bias_tol=ZBT, z_std_tol=ZST,
            )
    return trace, baseline, voxel_std


def main():
    obs = [json.loads(l) for l in OBS_JSONL.read_text().splitlines() if l]
    obs.sort(key=lambda r: r["t"])
    print(f"loaded {len(obs):,} records")

    events = identify_sep_events(PROTONS_JSONL)
    print(f"identified {len(events)} SEP events (≥10 pfu onset, ≥1 pfu sustained for ≥2 hours)")

    trace, baseline, voxel_std = replay_substrate(obs)
    print(f"replayed substrate, {len(trace):,} records in trace")

    # For each SEP event, look at trace records in [onset, onset+48h]
    lines = [
        "# Mars SEP event response",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()}",
        f"Window: {obs[0]['t']} → {obs[-1]['t']}",
        f"Records: {len(obs):,} · SEP events identified: {len(events)}",
        "",
        "**Identification rule.** A SEP event is a GOES-18 SGPS >=10 MeV",
        "integral proton flux that crosses 10 pfu and remains above 1 pfu",
        "for at least 2 hours. Event window for response analysis is",
        "[onset, onset + 48h] — matches the substrate's sep_proton",
        "exponential-decay time constant.",
        "",
        "**\"Substrate flag\"** = within the event window, at least one record",
        "with max_Z ≥ 0.85 AND |ε_evolved| ≥ 2σ. \"Dose response\" = peak",
        "RAD dose-rate in the window minus the in-voxel baseline median,",
        "expressed in μGy/day.",
        "",
        "## Per-event response",
        "",
        "| Onset (UTC) | Peak GOES (pfu) | Voxel | Baseline (µGy/day) | Peak RAD (µGy/day) | Δ dose | Max \\|ε\\| (σ) | Flag? |",
        "|---|---|---|---|---|---|---|---|",
    ]
    n_flagged = 0
    n_dose_enhanced = 0
    n_dose_suppressed = 0
    for (onset, peak_t, peak_flux, end_t) in events:
        window_end = onset + timedelta(hours=48)
        records_in = [r for r in trace if onset <= r["t"] <= window_end]
        if not records_in:
            lines.append(f"| {onset.isoformat()} | {peak_flux:.1f} | — | — | — | — | — | (no RAD records in window) |")
            continue
        peak_dose = max(r["o"] for r in records_in)
        baseline_at = records_in[0]["bl"]
        delta_dose = peak_dose - baseline_at
        max_eps = max(abs(r["eps"]) for r in records_in)
        flagged = any(r["max_z"] >= 0.85 and abs(r["eps"]) >= 2.0 for r in records_in)
        if flagged: n_flagged += 1
        if delta_dose > 5: n_dose_enhanced += 1
        elif delta_dose < -5: n_dose_suppressed += 1
        voxel = records_in[0]["v"]
        lines.append(
            f"| {onset.strftime('%Y-%m-%d %H:%M')} | {peak_flux:.1f} | "
            f"{voxel} | {baseline_at:.1f} | {peak_dose:.1f} | "
            f"{delta_dose:+.1f} | {max_eps:.2f} | "
            f"{'**YES**' if flagged else 'no'} |"
        )

    lines += [
        "",
        "## Summary",
        "",
        f"- SEP events with substrate anomaly flag fired: **{n_flagged} / {len(events)}**",
        f"- SEP events with positive RAD dose enhancement (Δ > +5 µGy/day): **{n_dose_enhanced}**",
        f"- SEP events with dose suppression (Δ < −5 µGy/day): **{n_dose_suppressed}**",
        "",
        "**Interpretation.** Whether a SEP event drives a dose enhancement",
        "or suppression at the Mars surface depends on the event's energy",
        "spectrum and Mars atmospheric column at the time. High-energy SEPs",
        "(>~100 MeV) drive surface enhancement; lower-energy events plus",
        "Forbush-decrease GCR suppression can produce a net dose drop.",
        "The substrate learns this voxel-by-voxel — see edge state for",
        "sep_proton|ls_*_* in training_summary.md.",
    ]

    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.name}")
    print(f"  flagged {n_flagged}/{len(events)} SEP events")
    print(f"  {n_dose_enhanced} enhancement, {n_dose_suppressed} suppression")


if __name__ == "__main__":
    main()
