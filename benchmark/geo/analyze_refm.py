"""
Tier-2 metric: external operational comparator.

Compares the framework's e_flux_gt_2mev prediction against SWPC REFM
(Relativistic Electron Forecast Model). REFM publishes daily observed
>2 MeV fluence + Day-1/2/3 forecasts at GEO based on ACE solar-wind
speed, on a ~60-day rolling history.

Field alignment:
  REFM "Observed Fluence (>2 MeV)" = daily-integrated >2 MeV electron
    fluence at GEO (electrons / cm² · day · sr).
  SWPC integral_electrons feed = 5-min >=2 MeV flux at GEO
    (electrons / cm² · s · sr).
  Daily fluence ≈ mean(daily flux samples) × 86400.

Method:
  For each UTC day with both REFM and SWPC integral_electrons coverage,
  aggregate observed flux → observed daily fluence (electrons/cm²/d/sr).
  Compute residuals on log10(fluence) for three predictors:
    - REFM Day-1 forecast (operational comparator)
    - Persistence: yesterday's observed fluence
    - Framework: daily-mean of evolved-W predictions written to preds.jsonl

Outputs a contingency table mirroring the LEO benchmark's framework-vs-MSIS
table: 2×2 of (framework flag) × (REFM ≥2σ wrong).

Note on window: REFM history is ~60 days but our framework prediction
window (from learn_geo.py) is only the 7-day SWPC rolling pull. The
contingency table covers only the days of overlap. For a longer
comparison we report REFM's own published Prediction Efficiency from
refm_stats.txt as the operational baseline.

Reproduce:
    python3 fetch_goes.py     # writes raw/refm.txt, raw/refm_stats.txt
    python3 learn_geo.py      # writes results/preds.jsonl
    python3 analyze_refm.py
"""

import bisect
import json
import math
import re
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
REFM = ROOT / "raw" / "refm.txt"
REFM_STATS = ROOT / "raw" / "refm_stats.txt"
PREDS = ROOT / "results" / "preds.jsonl"
OBS = ROOT / "obs.jsonl"
TRAJ = ROOT / "results" / "trajectory.jsonl"
OUT_MD = ROOT / "results" / "tier2_refm_comparison.md"

Z_THRESH = 0.85
EPS_THRESH = 2.0


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def parse_refm(path: Path):
    """Parse REFM tabular into [{date, observed_fluence, sw_speed, fc_d1, fc_d2, fc_d3}]."""
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ":")):
            continue
        parts = line.split()
        if len(parts) != 8:
            continue
        try:
            d = datetime(int(parts[0]), int(parts[1]), int(parts[2]),
                         tzinfo=timezone.utc)
            obs = float(parts[3])
            sws = float(parts[4])
            fc1 = float(parts[5])
            fc2 = float(parts[6])
            fc3 = float(parts[7])
            if obs <= 0 or fc1 <= 0:
                continue
            rows.append({
                "date": d, "observed": obs, "sw_speed": sws,
                "fc_d1": fc1, "fc_d2": fc2, "fc_d3": fc3,
            })
        except (ValueError, IndexError):
            continue
    return rows


def parse_refm_stats(path: Path):
    """Pull the published Prediction Efficiency (PE) for Day-1 forecast."""
    txt = path.read_text()
    pe = {}
    # Lines like "    + 1        0.15        -0.90       0.28       0.42 ..."
    for line in txt.splitlines():
        m = re.match(r"\s*\+\s*(\d+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)", line)
        if m:
            lead, pe_all, ss_p, ss_r, pe_30 = m.groups()
            pe[int(lead)] = {
                "PE_all": float(pe_all), "SS_pers_all": float(ss_p),
                "SS_recur_all": float(ss_r), "PE_30d": float(pe_30),
            }
    return pe


def aggregate_daily(preds_or_obs, key="o"):
    """Aggregate flux records to daily mean (proxy for daily fluence).
    Returns {utc_date -> mean_flux}."""
    by_day = defaultdict(list)
    for r in preds_or_obs:
        if r.get("obs") != "e_flux_gt_2mev":
            continue
        t = parse_iso(r["t"])
        day = datetime(t.year, t.month, t.day, tzinfo=timezone.utc)
        v = r.get(key)
        if v is None or v <= 0:
            continue
        by_day[day].append(v)
    return {d: statistics.mean(vs) for d, vs in by_day.items() if vs}


def main():
    print(f"parsing {REFM.name}…")
    refm = parse_refm(REFM)
    print(f"  {len(refm)} days, {refm[0]['date'].date()} … {refm[-1]['date'].date()}")

    print(f"parsing {REFM_STATS.name}…")
    refm_pe = parse_refm_stats(REFM_STATS)
    if refm_pe:
        print(f"  REFM Day-1 PE (all-time): {refm_pe[1]['PE_all']}  "
              f"(30-day: {refm_pe[1]['PE_30d']})")

    print(f"loading {PREDS.name} and {OBS.name}…")
    preds = [json.loads(l) for l in PREDS.read_text().splitlines() if l]
    obs = [json.loads(l) for l in OBS.read_text().splitlines() if l]

    daily_obs_flux = aggregate_daily(obs, key="o")
    daily_pred_flux = aggregate_daily(preds, key="p")
    daily_baseline_flux = aggregate_daily(preds, key="p_baseline")

    # Convert mean flux (e/cm²/s/sr) → daily fluence (e/cm²/d/sr) = mean × 86400
    daily_obs = {d: v * 86400 for d, v in daily_obs_flux.items()}
    daily_pred = {d: v * 86400 for d, v in daily_pred_flux.items()}
    daily_baseline = {d: v * 86400 for d, v in daily_baseline_flux.items()}

    refm_by_day = {r["date"]: r for r in refm}
    common = sorted(set(daily_obs) & set(refm_by_day))
    print(f"  overlap window: {len(common)} days")
    if common:
        print(f"  range: {common[0].date()} … {common[-1].date()}")

    # Persistence baseline (yesterday's observed)
    obs_sorted = sorted(daily_obs.items())
    persistence = {}
    for i in range(1, len(obs_sorted)):
        persistence[obs_sorted[i][0]] = obs_sorted[i-1][1]

    # Log10-residuals
    def log10(x): return math.log10(max(x, 1e-12))

    res_framework = []
    res_refm = []
    res_persistence = []
    res_baseline = []  # prior-W baseline
    rows = []
    for d in common:
        obs_d = daily_obs[d]
        pred_d = daily_pred.get(d)
        base_d = daily_baseline.get(d)
        refm_fc = refm_by_day[d]["fc_d1"]
        pers = persistence.get(d)
        if not (pred_d and base_d and refm_fc > 0):
            continue
        r_f = log10(pred_d) - log10(obs_d)
        r_r = log10(refm_fc) - log10(obs_d)
        r_b = log10(base_d) - log10(obs_d)
        res_framework.append(r_f); res_refm.append(r_r); res_baseline.append(r_b)
        if pers and pers > 0:
            r_p = log10(pers) - log10(obs_d)
            res_persistence.append(r_p)
        rows.append({"date": d.date().isoformat(),
                     "obs": obs_d, "framework": pred_d, "baseline": base_d,
                     "refm": refm_fc, "persistence": pers})

    def stat(name, rs):
        if not rs:
            return f"{name:<18} (no overlap)"
        mae = sum(abs(x) for x in rs) / len(rs)
        var = statistics.variance(rs) if len(rs) > 1 else 0
        return f"{name:<18} n={len(rs)}  log10-MAE={mae:.3f}  var={var:.3f}"

    print(f"\nDaily-fluence prediction skill (log10 residual, lower is better):")
    print(f"  {stat('framework', res_framework)}")
    print(f"  {stat('REFM Day-1', res_refm)}")
    print(f"  {stat('persistence', res_persistence)}")
    print(f"  {stat('prior-W baseline', res_baseline)}")

    # Tier-2 anomaly contingency: framework flag × REFM wrong (≥2σ in log10).
    # Use daily-aggregated residuals; per-day "framework flag" = ANY hour
    # in that day had (max_Z ≥ Z_THRESH AND |ε_evolved| ≥ EPS_THRESH).
    if res_refm:
        sigma_refm = max(statistics.stdev(res_refm), 1e-15)
    else:
        sigma_refm = 1.0

    # Build per-day framework flag from preds.jsonl + trajectory.jsonl.
    print(f"\nindexing trajectory for daily-flag computation…")
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

    # Per-voxel residual std for e_flux_gt_2mev to z-score εs
    by_v = defaultdict(list)
    for r in preds:
        if r["obs"] != "e_flux_gt_2mev":
            continue
        by_v[r["v"]].append(log10(r["p"]) - log10(r["o"]))
    voxel_std_e = {v: max(statistics.stdev(vs), 1e-15) for v, vs in by_v.items() if len(vs) > 1}

    day_flag = defaultdict(bool)
    for r in preds:
        if r["obs"] != "e_flux_gt_2mev":
            continue
        v, o = r["v"], r["obs"]
        std = voxel_std_e.get(v)
        if not std:
            continue
        eps = (log10(r["p"]) - log10(r["o"])) / std
        t = parse_iso(r["t"])
        day = datetime(t.year, t.month, t.day, tzinfo=timezone.utc)
        mz = max_z_at(v, o, t)
        if mz is None:
            continue
        if mz >= Z_THRESH and abs(eps) >= EPS_THRESH:
            day_flag[day] = True

    ff_rw, ff_ro, fq_rw, fq_ro = 0, 0, 0, 0
    for d in common:
        obs_d = daily_obs[d]
        refm_fc = refm_by_day[d]["fc_d1"]
        if refm_fc <= 0:
            continue
        eps_refm = (log10(refm_fc) - log10(obs_d)) / sigma_refm
        refm_wrong = abs(eps_refm) >= EPS_THRESH
        flagged = day_flag.get(d, False)
        if flagged and refm_wrong:    ff_rw += 1
        elif flagged and not refm_wrong: ff_ro += 1
        elif not flagged and refm_wrong: fq_rw += 1
        else: fq_ro += 1

    total = ff_rw + ff_ro + fq_rw + fq_ro
    precision = ff_rw / (ff_rw + ff_ro) if (ff_rw + ff_ro) else None
    recall = ff_rw / (ff_rw + fq_rw) if (ff_rw + fq_rw) else None
    base_rate = (ff_rw + fq_rw) / total if total else None

    print(f"\n2×2 contingency (daily; flag = any-hour-in-day framework flag, "
          f"REFM wrong = |ε_refm| ≥ {EPS_THRESH}σ):")
    print(f"                  REFM wrong    REFM ok")
    print(f"  framework flag  {ff_rw:>10}  {ff_ro:>10}")
    print(f"  framework quiet {fq_rw:>10}  {fq_ro:>10}")
    if precision is not None: print(f"  Precision: {100*precision:.1f}%")
    if recall is not None: print(f"  Recall:    {100*recall:.1f}%")
    if base_rate is not None: print(f"  Base rate: {100*base_rate:.1f}%")

    # Markdown report
    lines = [
        "# Tier-2 external comparator — REFM operational baseline",
        "",
        "Generated by `analyze_refm.py`. Compares the framework's `e_flux_gt_2mev` "
        "prediction against SWPC's **Relativistic Electron Forecast Model (REFM)**, "
        "an operational Day-1 forecaster based on ACE solar-wind speed that publishes "
        "its own performance statistics at "
        "<https://services.swpc.noaa.gov/text/relativistic-electron-fluence-statistics.txt>.",
        "",
        "## REFM published skill (from SWPC stats file)",
        "",
        "Prediction Efficiency (PE) is the variance-explained skill score; "
        "a perfect forecast has PE=1, climatology PE=0.",
        "",
        "| Lead time | PE (all-time) | PE (last 30 d) | SS vs persistence | SS vs recurrence |",
        "|---|---|---|---|---|",
    ]
    for lead in sorted(refm_pe):
        s = refm_pe[lead]
        lines.append(f"| +{lead} day | {s['PE_all']:+.2f} | {s['PE_30d']:+.2f} | "
                     f"{s['SS_pers_all']:+.2f} | {s['SS_recur_all']:+.2f} |")

    lines += [
        "",
        "## Daily-fluence prediction skill on the overlap window",
        "",
        f"Overlap = {len(common)} day(s) where both SWPC integral_electrons and "
        f"REFM Day-1 forecast have valid coverage. log10 residual = "
        f"log10(prediction) − log10(observed daily fluence). Lower MAE is better.",
        "",
        "| Predictor | n | log10-MAE | log10-residual variance |",
        "|---|---|---|---|",
    ]
    for name, rs in [("framework (evolved-W)", res_framework),
                     ("REFM Day-1 forecast", res_refm),
                     ("persistence (yesterday)", res_persistence),
                     ("prior-W baseline (W=0)", res_baseline)]:
        if rs:
            mae = sum(abs(x) for x in rs) / len(rs)
            var = statistics.variance(rs) if len(rs) > 1 else 0.0
            lines.append(f"| {name} | {len(rs)} | {mae:.3f} | {var:.3f} |")
        else:
            lines.append(f"| {name} | 0 | — | — |")

    lines += [
        "",
        "## Daily fluence side-by-side (electrons / cm² · d · sr)",
        "",
        "| Date | Observed | Framework | REFM Day-1 | Persistence | Prior-W |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        pers_str = f"{r['persistence']:.2e}" if r['persistence'] else "—"
        lines.append(f"| {r['date']} | {r['obs']:.2e} | {r['framework']:.2e} | "
                     f"{r['refm']:.2e} | {pers_str} | {r['baseline']:.2e} |")

    lines += [
        "",
        "## 2×2 contingency — framework flag vs REFM ≥2σ wrong",
        "",
        f"Per-day flag = any hour in that UTC day had "
        f"(max_Z ≥ {Z_THRESH} AND |ε_evolved| ≥ {EPS_THRESH}σ) on a `e_flux_gt_2mev` "
        "edge. REFM wrong = |log10(REFM Day-1) − log10(observed)| ≥ "
        f"{EPS_THRESH}σ where σ is the empirical REFM log-residual std on the window.",
        "",
        "|  | REFM wrong | REFM ok |",
        "|---|---|---|",
        f"| **framework flag** | {ff_rw} | {ff_ro} |",
        f"| framework quiet | {fq_rw} | {fq_ro} |",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Precision | {('**' + format(100*precision, '.1f') + '%**') if precision is not None else '—'} |",
        f"| Recall | {(format(100*recall, '.1f') + '%') if recall is not None else '—'} |",
        f"| Base rate | {(format(100*base_rate, '.1f') + '%') if base_rate is not None else '—'} |",
        f"| n days | {total} |",
        "",
        "## Caveats",
        "",
        "- **Window: 7 days.** SWPC integral_electrons primary feed serves a "
        "rolling 7-day window. REFM provides ~60 days. The framework-vs-REFM "
        "comparison is over the 7-day overlap only.",
        "- **Daily aggregation.** REFM publishes daily fluence; SWPC publishes 5-min "
        "flux. We aggregate observed flux to daily fluence by mean × 86400. This "
        "treats the diurnal LT variation as integration-internal rather than as "
        "a learning target.",
        "- **REFM input parity.** REFM uses ACE solar-wind speed; the framework "
        "uses DSCOVR plasma + 11 other drivers. The comparator is the operational "
        "forecast a GEO operator currently receives, not a re-derivation under "
        "controlled inputs.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {OUT_MD}")


if __name__ == "__main__":
    main()
