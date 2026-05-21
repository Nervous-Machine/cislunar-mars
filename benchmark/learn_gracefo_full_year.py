"""
Full-year curiosity-loop run on GRACE-FO using the patched framework's
in-memory fast path. Reads validation thresholds from
~/sbir-cislunar/leo/validate.yaml and emits threshold-aware verdicts
(CONFIRMED / PARTIAL / REJECTED / INSUFFICIENT_DATA).

Workflow:
  1. Load 89k obs from the existing per-obs JSONL.
  2. Reset test DB, seed originals (physics prior) + 3 hypothesis drivers.
  3. Pre-fetch all edges into an in-memory cache.
  4. Stream all obs through apply_learning_feedback_in_memory (no DB I/O
     during the loop). Track feature ranges and event counts for thresholds.
  5. Bulk-write final edge state.
  6. Apply validate.yaml verdict thresholds; report stratified outcomes.

Writes only to space-waze-test.
"""

import asyncio
import json
import math
import re
import sys
import yaml
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path.home() / "context-os"))
sys.path.insert(0, str(Path.home() / "space-waze" / "scripts"))

from validation_mcp_server_enhanced import ValidationMCPServerEnhanced  # noqa: E402
from learn_gracefo import (  # noqa: E402
    DRIVERS as ORIGINAL_DRIVERS,
    PRIOR_STARTING_Z,
    AE_LAT_PREFIXES,
    normalize as normalize_original,
    initial_weight,
)
from learn_gracefo_curiosity_loop import (  # noqa: E402
    HYPOTHESIS_DRIVERS,
    voxel_passes_filter,
    compute_bz_south_integrated,
    compute_ae_above_threshold,
    compute_season_sh_factor,
)

OBS_LOG = Path.home() / "space-waze" / "results" / "learn-gracefo-obs-multiyear.jsonl"
MSIS_LOG = Path.home() / "space-waze" / "results" / "msis-preds-multiyear.jsonl"  # NRLMSISE-00 preds w/ real F10.7/Ap
SW_CSV = Path("/tmp/sw-all.csv")  # CelesTrak archive for F10.7/Ap by date

# Regime-aware prior: instead of one edge per (driver, voxel), split into
# (driver, regime, voxel). The regime gate ensures only the in-regime edge
# updates per obs, so each regime's W converges to its own stable value.
# This is the curiosity-loop response to the static-W oscillation observed
# in single-W runs across the solar cycle.
SOLAR_REGIMES = ["low_flux", "mid_flux", "high_flux"]
SOLAR_REGIME_THRESHOLDS = {"low_flux": (0, 100), "mid_flux": (100, 150), "high_flux": (150, 9999)}

# SME-informed W priors per (base_driver, solar_regime). Coupling magnitudes
# from thermospheric physics: low_flux has cooler medium so per-driver effect
# is muted; high_flux has hot expanded thermosphere amplifying same driver.
REGIME_W_PRIOR = {
    "imf_bz":             {"low_flux": 0.25, "mid_flux": 0.45, "high_flux": 0.70},
    "dst":                {"low_flux": 0.25, "mid_flux": 0.45, "high_flux": 0.60},
    "ae_index":           {"low_flux": 0.35, "mid_flux": 0.55, "high_flux": 0.80},
    "solar_wind_speed":   {"low_flux": 0.15, "mid_flux": 0.25, "high_flux": 0.35},
    "solar_wind_density": {"low_flux": 0.15, "mid_flux": 0.25, "high_flux": 0.35},
}
VALIDATE_YAML = Path.home() / "sbir-cislunar" / "leo" / "validate.yaml"
OUT_PATH = Path.home() / "space-waze" / "results" / "learn-gracefo-full-year.json"
PRED_LOG_OUT = Path.home() / "space-waze" / "results" / "learn-gracefo-full-year-preds.jsonl"
TRAIN_PRED_LOG = Path.home() / "space-waze" / "results" / "learn-gracefo-train-preds.jsonl"
TEST_PRED_LOG = Path.home() / "space-waze" / "results" / "learn-gracefo-test-preds.jsonl"
TRAJECTORY_LOG = Path.home() / "space-waze" / "results" / "learn-gracefo-trajectory.jsonl"
TRAJECTORY_SAMPLE_EVERY = 50    # snapshot all edge states every N obs (~2h)
                                # for fine-grained anomaly-detection analysis

# Held-out split: train on first TRAIN_FRAC of obs (chronological),
# freeze weights, predict the remainder. If 0 or 1, no split — continuous
# streaming learning over the whole window. Use 1.0 for the anomaly-detection
# experiment (Z must keep evolving to flag events in real time).
TRAIN_FRAC = 1.0

# Single-pass streaming training: the framework operates as designed —
# one online pass through the train obs in chronological order, Z+W co-evolve
# naturally. Multi-pass was a now-removed artifact from chasing OLS-equivalence.
N_EPOCHS = 1

# Calibration-layer constants (ported from quantum_demo.py patterns).
# Time-aware rolling baseline replaces the JSONL's static-quiet-median field,
# which contains future-info leakage (it was computed from the whole year).
BASELINE_WINDOW = 100                # rolling quiet-time obs per voxel
BASELINE_MIN_HISTORY = 10            # need this many quiet-time obs before
                                     # using rolling baseline; else fall back
RESIDUAL_STD_RELATIVE_FLOOR = 0.05   # std floor as fraction of |baseline|
USE_TIME_AWARE_BASELINE = True       # toggle to compare against static

# Baseline source. When "msis", the framework's baseline is NRLMSISE-00's
# prediction per obs — and W_i become per-voxel CORRECTION coefficients
# (W → 0 when MSIS is right; W ≠ 0 where MSIS has systematic bias).
# This is the "framework as calibration layer on top of operational SOTA"
# positioning that earns operational value MSIS cannot provide alone.
BASELINE_SOURCE = "msis"             # "rolling_quiet" or "msis"

# Prediction composition:
#   "multiplicative" → pred = baseline · (1 + Σ d·W)   (LEO standalone mode)
#   "additive_residual" → pred = baseline + (Σ d·W) · std_residual  (MSIS+NM mode)
# Multiplicative over MSIS double-counts storm response. Additive residual
# learning lets W learn what MSIS misses, NOT amplify what MSIS already does.
PREDICTION_FORM = "additive_residual" if BASELINE_SOURCE == "msis" else "multiplicative"

# Per-edge attribution rule (the wedge: per-driver attribution vs joint fit):
#   "activity_weighted" → ΔWᵢ ∝ |dᵢWᵢ|/Σ|dⱼWⱼ| · ε_joint   (composite-fit, biased by current magnitude)
#   "ols_gradient"      → ΔWᵢ ∝ dᵢ · ε_joint               (per-driver OLS gradient — correct attribution)
# OLS gradient converges to true partial-regression coefficients and gives
# per-driver Z that tracks |β̂ᵢ|/σ_β̂ᵢ. Activity-weighted produces joint-fit-stable
# W's that diverge from OLS β̂ when drivers are correlated.
ATTRIBUTION_RULE = "ols_gradient"
ACTIVITY_THRESH = 0.10    # |dᵢ| < this → skip both W and Z updates for that edge
                          # (prevents edges from accumulating confidence when driver inactive)

# ε formulation. quantum_demo uses raw z-score: ε = (pred - obs) / std_pred.
# Switching from relative-residual to z-score requires rescaling the framework's
# bias/consistency thresholds and W_STEP because the typical |ε| magnitude is
# ~1 (sigma units) instead of ~0.1 (relative units).
EPS_FORM = "z_score"                 # "z_score" or "relative_residual"
W_STEP_ZSCORE = 0.02                 # 5x smaller; ε is ~5x larger
Z_BIAS_TOL_ZSCORE = 0.30             # |mean(ε)| < 0.3σ to consider calibrated
Z_STD_TOL_ZSCORE = 1.00              # std(ε) ≤ 1σ to consider consistent
TEST_DB = "space-waze-test"
PROD_DB = "space-waze"
HOUR_S = 3600

# ISO 8601 duration parser (subset we need: P<n>D, P<n>Y, P<n>M).
ISO_DUR_RE = re.compile(r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?$")


def parse_iso_duration_days(s):
    m = ISO_DUR_RE.match(s)
    if not m:
        raise ValueError(f"unsupported ISO duration: {s}")
    y, mo, d = (int(x) if x else 0 for x in m.groups())
    return y * 365 + mo * 30 + d


def load_validate_yaml():
    with open(VALIDATE_YAML) as f:
        return yaml.safe_load(f)


def load_f107_archive():
    """Returns dict: date_str ('YYYY-MM-DD') → F10.7_OBS from CelesTrak archive."""
    import csv
    f107 = {}
    with open(SW_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                f107[row["DATE"]] = float(row["F10.7_OBS"])
            except (KeyError, ValueError):
                continue
    return f107


def solar_regime(f107_val):
    """Map F10.7 value to solar-phase regime tag (low_flux / mid_flux / high_flux)."""
    if f107_val is None:
        return None
    for regime, (lo, hi) in SOLAR_REGIME_THRESHOLDS.items():
        if lo <= f107_val < hi:
            return regime
    return "high_flux"  # F10.7 ≥ 9999 just in case


def evaluate_verdict(driver, edge_stats, run_stats, thresholds):
    """
    Apply validate.yaml thresholds to a hypothesis edge.
    Returns (verdict, reasons).

    verdict ∈ {CONFIRMED, PARTIAL, REJECTED, INSUFFICIENT_DATA}.
    """
    defaults = thresholds.get("default", {})
    per_driver = thresholds.get("per_driver", {}).get(driver, {})

    def th(key, default=None):
        return per_driver.get(key, defaults.get(key, default))

    min_obs = th("min_observations", 0)
    min_days = parse_iso_duration_days(th("min_timespan", "P0D"))
    min_range_frac = th("min_feature_range_frac", 0.0)
    min_storms = th("min_storms", 0)
    min_above_thresh = th("min_above_threshold_events", 0)

    reasons = []
    insufficient = False

    if edge_stats["n_obs"] < min_obs:
        reasons.append(f"n_obs={edge_stats['n_obs']} < {min_obs}")
        insufficient = True
    if edge_stats["timespan_days"] < min_days:
        reasons.append(f"timespan={edge_stats['timespan_days']:.0f}d < {min_days}d")
        insufficient = True
    feature_range_frac = edge_stats["feature_range"] / 2.0  # theoretical range is [-1,+1] = 2
    if feature_range_frac < min_range_frac:
        reasons.append(f"feature_range={feature_range_frac:.2f} < {min_range_frac:.2f}")
        insufficient = True
    if min_storms and run_stats["n_storms"] < min_storms:
        reasons.append(f"storms={run_stats['n_storms']} < {min_storms}")
        insufficient = True
    if min_above_thresh and run_stats["n_above_ae_threshold"] < min_above_thresh:
        reasons.append(f"AE≥300nT events={run_stats['n_above_ae_threshold']} < {min_above_thresh}")
        insufficient = True

    if insufficient:
        return "INSUFFICIENT_DATA", reasons

    avg_z = edge_stats["avg_z"]
    if avg_z >= 0.70:
        return "CONFIRMED", [f"avg Z={avg_z:.3f} ≥ 0.70"]
    if avg_z >= 0.45:
        return "PARTIAL", [f"avg Z={avg_z:.3f} in [0.45, 0.70)"]
    if avg_z <= 0.15:
        return "REJECTED", [f"avg Z={avg_z:.3f} ≤ 0.15"]
    return "INCONCLUSIVE", [f"avg Z={avg_z:.3f} in (0.15, 0.45)"]


async def main():
    server = ValidationMCPServerEnhanced()
    server.db_manager.db_name = TEST_DB
    test_db = server.db_manager.mongo_client[TEST_DB]

    # Rescale framework thresholds for the chosen ε form. Framework defaults
    # are tuned for relative-residual ε (|ε| ~ 0.1); z-score ε (|ε| ~ 1σ)
    # needs proportionally looser tolerances and a smaller W step.
    if EPS_FORM == "z_score":
        server.W_STEP = W_STEP_ZSCORE
        server.Z_BIAS_TOL = Z_BIAS_TOL_ZSCORE
        server.Z_STD_TOL = Z_STD_TOL_ZSCORE
        print(f"  ε form: z_score (W_STEP={server.W_STEP}, "
              f"Z_BIAS_TOL={server.Z_BIAS_TOL}, Z_STD_TOL={server.Z_STD_TOL})")
    else:
        print(f"  ε form: relative_residual (framework defaults)")

    # =====================================================================
    # Load obs + weather
    # =====================================================================
    print("\n" + "=" * 76)
    print("FULL-YEAR CURIOSITY LOOP — fast path, threshold-aware verdicts")
    print("=" * 76)

    thresholds = load_validate_yaml().get("verdict_thresholds", {})
    print(f"  Loaded verdict_thresholds from {VALIDATE_YAML.name}")

    print(f"\nLoading observations from {OBS_LOG.name}...")
    obs = []
    with open(OBS_LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                obs.append(json.loads(line))
    print(f"  {len(obs)} hourly observations")

    voxels = sorted({o["v"] for o in obs})
    t_start = datetime.fromisoformat(obs[0]["t"].replace("Z", "+00:00"))
    t_end = datetime.fromisoformat(obs[-1]["t"].replace("Z", "+00:00"))
    timespan_days = (t_end - t_start).total_seconds() / 86400
    print(f"  Time span: {t_start.date()} → {t_end.date()} ({timespan_days:.0f} days)")
    print(f"  Voxels: {len(voxels)}")

    # Load MSIS predictions keyed by (t, v) when used as baseline source.
    msis_pred = {}
    if BASELINE_SOURCE == "msis":
        print(f"\nLoading MSIS baseline predictions from {MSIS_LOG.name}...")
        with open(MSIS_LOG) as fmsis:
            for line in fmsis:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                msis_pred[(r["t"], r["v"])] = r["p"]
        print(f"  {len(msis_pred)} MSIS predictions indexed")

    # F10.7 daily values for solar-regime gating
    f107_archive = load_f107_archive()
    print(f"\nLoaded {len(f107_archive)} days of F10.7 (solar-regime gating)")
    print(f"  Regimes: {SOLAR_REGIMES}  thresholds: {SOLAR_REGIME_THRESHOLDS}")

    print("\nLoading weather_hourly from prod...")
    prod_db = server.db_manager.mongo_client[PROD_DB]
    weather = {}
    for w in prod_db["weather_hourly"].find({}, {"_id": 0}):
        hk = int(w["timestamp"].replace(tzinfo=timezone.utc).timestamp() // HOUR_S)
        weather[hk] = w
    print(f"  {len(weather)} hour keys indexed")

    # =====================================================================
    # Reset DB; build in-memory edge cache (NOT inserted yet)
    # =====================================================================
    print("\nResetting test DB and building in-memory edge cache...")
    test_db["causal_edges"].drop()

    edges_mem = {}  # key (source_id, target_id) → state dict

    def make_key(src, tgt):
        return (src, tgt)

    for voxel in voxels:
        for driver in ORIGINAL_DRIVERS:
            if driver == "ae_index" and not any(p in voxel for p in AE_LAT_PREFIXES):
                continue
            # Regime-split: each original driver becomes 3 regime-specific edges.
            # SME-informed W prior per regime — magnitude reflects expected
            # coupling strength at that solar phase. Initial Z=0.30 for all
            # (let the data confirm the prior).
            base_W = initial_weight(driver, voxel)
            for regime in SOLAR_REGIMES:
                # Multiply the per-voxel base initial_weight by the regime
                # coupling magnitude so polar/equatorial structure carries over.
                regime_scale = REGIME_W_PRIOR[driver][regime] / max(0.01, abs(base_W) if base_W != 0 else 0.5)
                regime_W = base_W * regime_scale if base_W != 0 else REGIME_W_PRIOR[driver][regime]
                # Clamp to [-1, 1]
                regime_W = max(-1.0, min(1.0, regime_W))
                regime_driver = f"{driver}_{regime}"
                edges_mem[make_key(regime_driver, voxel)] = {
                    "source_id": regime_driver,
                    "target_id": voxel,
                    "weight": regime_W,
                    "certainty": 0.30,  # low-confidence regime-specific hypothesis
                    "validation_history": [],
                    "created_by": "physics_prior_regime_split",
                    "base_driver": driver,
                    "regime": regime,
                }
    for hname, spec in HYPOTHESIS_DRIVERS.items():
        for voxel in voxels:
            if not voxel_passes_filter(voxel, spec["voxel_filter"]):
                continue
            edges_mem[make_key(hname, voxel)] = {
                "source_id": hname,
                "target_id": voxel,
                "weight": spec["starting_w"],
                "certainty": spec["starting_z"],
                "validation_history": [],
                "created_by": "llm_hypothesis",
            }
    n_orig = sum(1 for e in edges_mem.values() if e["created_by"] == "physics_prior")
    n_hyp = sum(1 for e in edges_mem.values() if e["created_by"] == "llm_hypothesis")
    print(f"  In-memory edges: {n_orig} physics_prior + {n_hyp} llm_hypothesis")

    # =====================================================================
    # Pre-pass: feature range tracking + run stats
    # =====================================================================
    feature_range = defaultdict(lambda: {"min": float("inf"), "max": float("-inf")})
    n_storms = 0
    n_above_ae_thresh = 0
    storm_hours_seen = set()
    ae_thresh_hours_seen = set()

    # =====================================================================
    # Baseline init. Two modes:
    #   "rolling_quiet": causal rolling quiet-time obs per voxel (LEO standalone)
    #   "msis":          NRLMSISE-00 prediction per obs, with std from rolling
    #                    (obs - MSIS) residuals — the calibration-layer mode
    # =====================================================================
    voxel_quiet_history = defaultdict(lambda: deque(maxlen=BASELINE_WINDOW))
    voxel_msis_residual_history = defaultdict(lambda: deque(maxlen=BASELINE_WINDOW))
    if BASELINE_SOURCE == "msis":
        print(f"\nCalibration: MSIS-as-baseline. Framework learns per-voxel CORRECTIONS.")
        print(f"  Wᵢ → 0 where MSIS is calibrated; Wᵢ ≠ 0 surfaces MSIS biases per voxel.")
        print(f"  std from rolling {BASELINE_WINDOW}-obs window of (obs - MSIS) residuals.")
    elif USE_TIME_AWARE_BASELINE:
        print(f"\nCalibration: time-aware baseline (rolling window={BASELINE_WINDOW}, "
              f"min_history={BASELINE_MIN_HISTORY}, std_floor={RESIDUAL_STD_RELATIVE_FLOOR})")
    else:
        print(f"\nCalibration: static baseline from JSONL (NOTE: contains future-info leakage)")

    def causal_baseline(voxel, static_fallback, msis_baseline=None):
        """
        Return (baseline, std). Mode-dependent:
          BASELINE_SOURCE='msis': baseline=msis_baseline, std from (obs-MSIS) residuals
          else: baseline=rolling quiet-time median, std from those obs
        Both fall back to a relative-floor std until enough history accumulates.
        """
        if BASELINE_SOURCE == "msis":
            if msis_baseline is None or msis_baseline <= 0:
                return static_fallback, abs(static_fallback) * RESIDUAL_STD_RELATIVE_FLOOR
            hist = voxel_msis_residual_history[voxel]
            if len(hist) < BASELINE_MIN_HISTORY:
                return msis_baseline, abs(msis_baseline) * RESIDUAL_STD_RELATIVE_FLOOR
            mean_r = sum(hist) / len(hist)
            var = sum((r - mean_r) ** 2 for r in hist) / len(hist)
            std = max(var ** 0.5, abs(msis_baseline) * RESIDUAL_STD_RELATIVE_FLOOR)
            return msis_baseline, std

        if not USE_TIME_AWARE_BASELINE:
            return static_fallback, abs(static_fallback) * RESIDUAL_STD_RELATIVE_FLOOR
        hist = voxel_quiet_history[voxel]
        if len(hist) < BASELINE_MIN_HISTORY:
            return static_fallback, abs(static_fallback) * RESIDUAL_STD_RELATIVE_FLOOR
        s = sorted(hist)
        median = s[len(s) // 2]
        mean_d = sum(hist) / len(hist)
        var = sum((d - mean_d) ** 2 for d in hist) / len(hist)
        std = max(var ** 0.5, abs(median) * RESIDUAL_STD_RELATIVE_FLOOR)
        return median, std

    def is_quiet(weather):
        dst = weather.get("dst") or 0
        bz = weather.get("imf_bz") or 0
        return dst > -30 and bz > -5

    # =====================================================================
    # Main loop — pure in-memory, no DB I/O
    # Prediction logging: (t, voxel, baseline, obs, pred, dst, bz, n_drivers)
    # per obs, written as JSONL for downstream benchmark-gracefo-obs.js.
    #
    # Train/test split: first TRAIN_FRAC of chronologically-sorted obs are
    # used to update weights AND log predictions to TRAIN_PRED_LOG. After
    # the boundary, weights are frozen — predictions still logged to
    # TEST_PRED_LOG. Final converged weights are also dumped to PRED_LOG_OUT
    # for backward compatibility (effectively = train log + test log).
    # =====================================================================
    train_cutoff_idx = int(len(obs) * TRAIN_FRAC)
    if 0 < TRAIN_FRAC < 1:
        cutoff_t = datetime.fromisoformat(obs[train_cutoff_idx]["t"].replace("Z", "+00:00"))
        print(f"\nHeld-out split: train first {train_cutoff_idx} obs "
              f"({TRAIN_FRAC:.0%}), freeze weights, test on remainder.")
        print(f"  Cutoff timestamp: {cutoff_t.date()}")
    else:
        print(f"\nNo train/test split (TRAIN_FRAC={TRAIN_FRAC}); all obs train+log.")

    print(f"Streaming {len(obs)} obs through in-memory fast path "
          f"({N_EPOCHS} training epochs + 1 test pass)...")
    # Regime-split drivers: each original becomes {drv}_low_flux, {drv}_mid_flux, {drv}_high_flux
    regime_split_drivers = [f"{drv}_{r}" for drv in ORIGINAL_DRIVERS for r in SOLAR_REGIMES]
    all_drivers = regime_split_drivers + list(HYPOTHESIS_DRIVERS)
    print(f"  Active driver count: {len(all_drivers)}  "
          f"({len(regime_split_drivers)} regime-split + {len(HYPOTHESIS_DRIVERS)} hypothesis)")
    t0 = datetime.utcnow()
    processed = 0
    n_calls = 0
    pred_log = open(PRED_LOG_OUT, "w")
    train_log = open(TRAIN_PRED_LOG, "w")
    test_log = open(TEST_PRED_LOG, "w")
    traj_log = open(TRAJECTORY_LOG, "w")
    snapshots_written = 0

    # Snapshot initial Z values per (driver, voxel) so we can reset between epochs
    # while keeping W. This lets W keep converging across epochs without the
    # Z-η feedback locking it in early.
    initial_z = {key: state["certainty"] for key, state in edges_mem.items()}

    # Build the iteration plan: N_EPOCHS passes over train_obs, then one final
    # pass that runs test_obs only. Non-final training epochs reset Z+history.
    # Predictions are only logged during the FINAL training epoch and the test pass.
    iteration_plan = []
    for epoch in range(N_EPOCHS):
        is_final_train_epoch = (epoch == N_EPOCHS - 1)
        iteration_plan.append({
            "label": f"train_epoch_{epoch+1}/{N_EPOCHS}",
            "obs_range": (0, train_cutoff_idx),
            "is_train": True,
            "log_predictions": is_final_train_epoch,
            "reset_z_before": (epoch > 0),
        })
    if 0 < TRAIN_FRAC < 1 and train_cutoff_idx < len(obs):
        iteration_plan.append({
            "label": "test_pass",
            "obs_range": (train_cutoff_idx, len(obs)),
            "is_train": False,
            "log_predictions": True,
            "reset_z_before": False,
        })

    for plan in iteration_plan:
        if plan["reset_z_before"]:
            for key, state in edges_mem.items():
                state["certainty"] = initial_z[key]
                state["validation_history"] = []
            voxel_quiet_history.clear()
            voxel_msis_residual_history.clear()
        epoch_start = datetime.utcnow()
        epoch_calls_start = n_calls
        start_idx, end_idx = plan["obs_range"]

        for obs_idx in range(start_idx, end_idx):
            o = obs[obs_idx]
            is_train = plan["is_train"]
            log_this = plan["log_predictions"]
            t = datetime.fromisoformat(o["t"].replace("Z", "+00:00"))
            hk = int(t.timestamp() // HOUR_S)
            w = weather.get(hk) or weather.get(hk - 1) or weather.get(hk + 1)
            if not w:
                continue
            voxel = o["v"]
            obs_density = o["o"]
            static_baseline = o["b"]
            msis_p = msis_pred.get((o["t"], voxel)) if BASELINE_SOURCE == "msis" else None
            baseline, baseline_std = causal_baseline(voxel, static_baseline, msis_p)

            # Run-level event tracking (per unique hour, not per obs)
            if hk not in storm_hours_seen:
                if (w.get("dst") or 0) <= -50:
                    n_storms += 1
                    storm_hours_seen.add(hk)
            if hk not in ae_thresh_hours_seen:
                if (w.get("ae_index") or 0) >= 300:
                    n_above_ae_thresh += 1
                    ae_thresh_hours_seen.add(hk)

            # Determine current solar regime from F10.7 for this obs's date
            date_str = t.strftime("%Y-%m-%d")
            f107_today = f107_archive.get(date_str)
            current_regime = solar_regime(f107_today)  # None if no F10.7 available

            # Compute base driver values once, then expand to regime-split drivers.
            base_d = {}
            for drv in ORIGINAL_DRIVERS:
                base_d[drv] = normalize_original(drv, w.get(drv))

            d_vals = {}
            # Regime-split drivers: only active in their matching regime, else 0
            for drv in ORIGINAL_DRIVERS:
                for regime in SOLAR_REGIMES:
                    rkey = f"{drv}_{regime}"
                    d_vals[rkey] = base_d[drv] if regime == current_regime else 0.0
            # Hypothesis drivers (unchanged, not regime-split for this experiment)
            d_vals["bz_south_integrated"] = compute_bz_south_integrated(hk, weather)
            d_vals["ae_above_threshold"] = compute_ae_above_threshold(w)
            d_vals["season_sh_factor"] = compute_season_sh_factor(t)

            for drv, v in d_vals.items():
                fr = feature_range[drv]
                if v < fr["min"]:
                    fr["min"] = v
                if v > fr["max"]:
                    fr["max"] = v

            # Applicable drivers for this voxel
            applicable = []
            for drv in all_drivers:
                # ae_index regime-split: check the BASE driver name for high-lat filter
                if drv.startswith("ae_index_") and not any(p in voxel for p in AE_LAT_PREFIXES):
                    continue
                if drv in HYPOTHESIS_DRIVERS:
                    vf = HYPOTHESIS_DRIVERS[drv]["voxel_filter"]
                    if not voxel_passes_filter(voxel, vf):
                        continue
                applicable.append(drv)

            # Activity gate applied at PREDICTION time, symmetric with the W/Z
            # update gate. A driver that's dormant (|d| < ACTIVITY_THRESH) does
            # NOT contribute to the prediction — otherwise small d × inflated
            # rolling std × accumulated W produces unwarranted corrections
            # during quiet periods (root cause of the +99% multi-year training bias).
            contributions = []
            for drv in applicable:
                key = make_key(drv, voxel)
                if key not in edges_mem:
                    continue
                d_val = d_vals[drv]
                if abs(d_val) < ACTIVITY_THRESH:
                    continue
                wt = edges_mem[key]["weight"]
                contributions.append((drv, d_val, wt, d_val * wt))

            if not contributions:
                continue

            if PREDICTION_FORM == "additive_residual":
                correction = sum(c[3] for c in contributions) * baseline_std
                pred = max(baseline * 0.01, baseline + correction)
            else:
                pred = max(baseline * 0.01, baseline * (1.0 + sum(c[3] for c in contributions)))
            if EPS_FORM == "z_score":
                eps_joint = (pred - obs_density) / baseline_std
            else:
                eps_joint = (pred - obs_density) / obs_density

            if log_this:
                record = json.dumps({
                    "t": o["t"],
                    "v": voxel,
                    "b": baseline,
                    "o": obs_density,
                    "p": pred,
                    "dst": w.get("dst"),
                    "bz": w.get("imf_bz"),
                    "n_drivers": len(contributions),
                    "phase": "train" if is_train else "test",
                }) + "\n"
                pred_log.write(record)
                (train_log if is_train else test_log).write(record)

            # Only update weights during train phase.
            if is_train:
                if ATTRIBUTION_RULE == "ols_gradient":
                    for drv, d_val, wt, contrib in contributions:
                        if abs(d_val) < ACTIVITY_THRESH:
                            continue
                        eps_for_edge = d_val * eps_joint
                        key = make_key(drv, voxel)
                        updated = server.apply_learning_feedback_in_memory(edges_mem[key], eps_for_edge)
                        edges_mem[key]["weight"] = updated["weight"]
                        edges_mem[key]["certainty"] = updated["certainty"]
                        edges_mem[key]["validation_history"] = updated["validation_history"]
                        n_calls += 1
                else:
                    total_act = sum(abs(c[3]) for c in contributions)
                    n_act = len(contributions)
                    for drv, d_val, wt, contrib in contributions:
                        share = (abs(contrib) / total_act) if total_act > 1e-9 else (1.0 / n_act)
                        eps_for_edge = eps_joint * share
                        key = make_key(drv, voxel)
                        updated = server.apply_learning_feedback_in_memory(edges_mem[key], eps_for_edge)
                        edges_mem[key]["weight"] = updated["weight"]
                        edges_mem[key]["certainty"] = updated["certainty"]
                        edges_mem[key]["validation_history"] = updated["validation_history"]
                        n_calls += 1

            if BASELINE_SOURCE == "msis" and msis_p is not None and msis_p > 0:
                voxel_msis_residual_history[voxel].append(obs_density - msis_p)
            elif USE_TIME_AWARE_BASELINE and is_quiet(w):
                voxel_quiet_history[voxel].append(obs_density)

            processed += 1

            # Trajectory snapshot: dump per-edge Z and W every N obs so we can
            # visualize regime-tracking dynamics over the 7.5-year window.
            if processed % TRAJECTORY_SAMPLE_EVERY == 0:
                for ekey, state in edges_mem.items():
                    traj_log.write(json.dumps({
                        "t": o["t"],
                        "src": state["source_id"],
                        "tgt": state["target_id"],
                        "W": round(state["weight"], 5),
                        "Z": round(state["certainty"], 4),
                        "phase": "train" if is_train else "test",
                    }) + "\n")
                snapshots_written += 1

        epoch_elapsed = (datetime.utcnow() - epoch_start).total_seconds()
        epoch_calls = n_calls - epoch_calls_start
        print(f"  [{plan['label']}]  {end_idx - start_idx} obs, {epoch_calls} updates, "
              f"{epoch_elapsed:.1f}s  ({epoch_calls/max(epoch_elapsed,1e-3):.0f} updates/s)")

    pred_log.close()
    train_log.close()
    test_log.close()
    traj_log.close()
    print(f"  Trajectory log: {TRAJECTORY_LOG} ({snapshots_written} snapshots × {len(edges_mem)} edges)")
    elapsed = (datetime.utcnow() - t0).total_seconds()
    print(f"\n  Done. {processed} obs, {n_calls} updates, {elapsed:.0f}s total "
          f"({n_calls/max(elapsed,1e-3):.0f} updates/s)")
    print(f"  Prediction logs: combined={PRED_LOG_OUT.name}")
    print(f"                   train={TRAIN_PRED_LOG.name}")
    print(f"                   test ={TEST_PRED_LOG.name}")

    # =====================================================================
    # Bulk-write final state to DB
    # =====================================================================
    print("\nBulk-writing final edge state...")
    # Truncate validation_history to last 100 entries per edge to keep doc sizes reasonable.
    docs = []
    for state in edges_mem.values():
        d = dict(state)
        if len(d["validation_history"]) > 100:
            d["validation_history"] = d["validation_history"][-100:]
        d["created_at"] = datetime.utcnow()
        d["causal_vectors"] = {"strength": d["weight"], "confidence": d["certainty"],
                               "context": 0.5, "stability": 0.5}
        docs.append(d)
    test_db["causal_edges"].insert_many(docs)
    print(f"  Wrote {len(docs)} edges")

    # =====================================================================
    # Threshold-aware verdicts
    # =====================================================================
    print("\n" + "=" * 76)
    print("VERDICTS — threshold-aware (per validate.yaml)")
    print("=" * 76)
    run_stats = {"n_storms": n_storms, "n_above_ae_threshold": n_above_ae_thresh}
    print(f"  Run stats: n_storms (Dst ≤ -50) = {n_storms},  "
          f"AE ≥ 300nT events = {n_above_ae_thresh}")

    # Group hypothesis edges by driver, compute per-driver stats
    by_driver = defaultdict(list)
    for state in edges_mem.values():
        by_driver[state["source_id"]].append(state)

    print(f"\n  {'driver':<24} {'origin':<16} {'edges':>5} {'avg_W':>9} {'avg_Z':>9} {'feat_rng':>9}  verdict")
    print("  " + "-" * 86)
    full_results = []
    for drv in sorted(by_driver):
        es = by_driver[drv]
        origin = es[0].get("created_by", "?")
        avg_w = sum(e["weight"] for e in es) / len(es)
        avg_z = sum(e["certainty"] for e in es) / len(es)
        fr = feature_range[drv]
        feat_rng = fr["max"] - fr["min"] if fr["max"] > fr["min"] else 0.0

        # Per-edge n_obs and timespan
        n_obs_avg = sum(len(e.get("validation_history", [])) for e in es) / len(es)
        n_obs_int = int(n_obs_avg)
        edge_stats = {
            "n_obs": n_obs_int,
            "timespan_days": timespan_days,
            "feature_range": feat_rng,
            "avg_z": avg_z,
        }
        if origin == "llm_hypothesis":
            verdict, reasons = evaluate_verdict(drv, edge_stats, run_stats, thresholds)
        else:
            verdict = "—"
            reasons = []

        print(f"  {drv:<24} {origin:<16} {len(es):>5} {avg_w:>+9.4f} {avg_z:>9.4f} {feat_rng:>9.3f}  {verdict}")
        if reasons:
            for r in reasons:
                print(f"      ↳ {r}")

        full_results.append({
            "driver": drv,
            "origin": origin,
            "edges": len(es),
            "avg_w": avg_w,
            "avg_z": avg_z,
            "feature_range": feat_rng,
            "n_obs_avg": n_obs_avg,
            "verdict": verdict,
            "reasons": reasons,
        })

    # Curiosity surface
    curious = server._find_curious_edges(n_obs_min=100)
    print(f"\n  Curiosity surface (post-run, n_obs_min=100):")
    print(f"    residual={len(curious['residual'])}  stuck={len(curious['stuck'])}  "
          f"collapsed={len(curious['collapsed'])}")

    OUT_PATH.write_text(json.dumps({
        "meta": {
            "n_obs_processed": processed,
            "n_edge_updates": n_calls,
            "elapsed_seconds": elapsed,
            "timespan_days": timespan_days,
            "n_storms": n_storms,
            "n_above_ae_threshold": n_above_ae_thresh,
        },
        "verdicts": full_results,
        "curiosity_surface": {
            ch: curious[ch] for ch in ("residual", "stuck", "collapsed")
        },
    }, indent=2, default=str))
    print(f"\n  Saved {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
