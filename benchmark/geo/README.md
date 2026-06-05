# GEO regime — skeleton benchmark

Sibling to [`../`](../) (the published LEO Zenodo benchmark). This directory
proves the LEO architecture transfers to the GEO regime with no MCP-server
changes, on real data from public SWPC JSON endpoints.

**Status:** skeleton (plumbing-proof). 1-day rolling SWPC window, 4 of 5
target observables wired, SEP/CME/flare event drivers parsed from
`alerts.json`, no operational comparator baseline yet. See "Deferred" below.

## What it shows

A streaming single-pass run over 24 h of GOES-19 SEISS + GOES-MAG +
GOES-EXIS observations (~2,300 records), with drivers aligned from DSCOVR,
GOES-XRS, GOES-EUVS (MgII), Kp, Dst, and four event-driven drivers parsed
from `alerts.json` (`sep_proton`, `relativistic_electron`, `flare_xclass`,
`geomag_storm`), produces:

- 288 edges across 6 LT voxels × 4 observables × 12 drivers
- 24,000+ edge updates via the same `apply_learning_feedback_in_memory`
  primitive used in the LEO benchmark
- 117/288 edges converge to Z ≥ 0.85 in one pass; median Z = 0.55
- Z evolution at the expected rates; W exercises the full \[−1, +1\]
  range; activity gating fires on inactive drivers
- B-field magnitude edges use additive-residual composition
  (`p = baseline + (Σ d·W)·σ`) — multiplicative coupling had saturated
  6/6 voxels at W=±1 because B at GEO varies only ~±30 nT around ~100 nT
  while sum-of-W can exceed ±1 with 8+ active drivers; per-observable
  composition mode in `learn_geo.py` solves this without changing fluxes
- All six LT voxels see observations (no geometric coverage gap)

See `results/training_summary.md` and `results/edges_state.json`.

The framework's `nm_primitives.py` is byte-identical to the LEO benchmark's
copy — the only regime-specific code is fetch + extract glue and a shared
SWPC alerts parser at [`../sep_alerts.py`](../sep_alerts.py).

## Files

| File | Role |
|---|---|
| `nm_primitives.py` | Identical copy of the LEO benchmark's primitives |
| `fetch_goes.py` | Pull 1-day rolling SWPC JSON for GOES + DSCOVR + indices |
| `extract_obs_jsonl.py` | Time-align drivers, voxelize by LT, parse SWPC alerts → SEP/flare drivers, emit per-(t, voxel, observable) JSONL |
| `learn_geo.py` | Streaming single-pass training using the shared primitives; per-observable composition mode (additive for B-field, multiplicative for fluxes) |
| `../sep_alerts.py` | Shared SWPC alerts parser (also used by Mars). Maps Space Weather Message Codes to graded event-driver intensity with exponential decay |
| `results/` | Committed small artifacts: training summary, final edge state |

## ε convention

Same as LEO: z-score residual `ε = (p − o) / σ_v`. The framework's
magnitude-tolerance constants (`W_STEP`, `Z_BIAS_TOL`, `Z_STD_TOL`) are
rescaled together for this ε scale — see
[`../../math_functions.md`](../../math_functions.md) §3.1 for the
provenance of that rescale and its planned API cleanup.

## Run

```bash
pip install requests certifi
python3 fetch_goes.py        # ~10 s
python3 extract_obs_jsonl.py # ~2 s
python3 learn_geo.py         # ~5 s
```

All endpoints used by `fetch_goes.py` are public — no auth, no rate limits
encountered at hourly cadence.

## Deferred for full benchmark

1. **AE9/AP9 baseline.** For ≥ 2 MeV electrons and ≥ 10 MeV protons, AE9/AP9
   provides climatological percentile baselines (IRENE distribution). The
   framework's `additive_residual` composition mode is designed to ride on
   top of a comparator. Without it, current predictions use a median-based
   placeholder; precision-vs-baseline metrics aren't meaningful yet.
2. **NCEI multi-year backfill.** SWPC primary endpoints serve a rolling
   1-day window. NOAA NCEI's `goes-space-environment-monitor/access/full/`
   archive holds historical GOES-R data on the same field schema — drop-in
   replacement for `fetch_goes.py` URLs.
3. **`e_flux_hot_plasma` (1–50 keV).** The primary SWPC
   `differential-electrons-1-day.json` feed starts at 79 keV — outside the
   MPS-LO band the validate.yaml targets. A direct MPS-LO endpoint or
   secondary feed is required to wire this observable.
4. **GOES-EXIS solar inputs as first-class drivers.** XRS-B and EUVS MgII are
   currently aligned and consumed in the driver vector; the prior.yaml
   needs explicit `solar_xray_flux` and `solar_euv_index` edges (with
   `operational_model_documentation` Z₀ = 0.40) so the framework knows
   they're declared causal contributors, not opportunistic features.
5. **~~`alerts.json` parsing.~~** Done. SWPC alerts are parsed via
   [`../sep_alerts.py`](../sep_alerts.py) into four graded event drivers
   (`sep_proton`, `relativistic_electron`, `flare_xclass`, `geomag_storm`)
   each in [0, 1] with exponential decay from onset. Wired into the
   driver vector. In the current 1-day SWPC window the parsed events
   all occurred 3+ days before the GOES obs window opens, so the
   convergence ride-along here is more about plumbing than evidence —
   the multi-year NCEI backfill (#2 above) is what makes these edges
   evidentially load-bearing.
6. **MCP integration.** Current `learn_geo.py` is hand-written glue; the
   refactor target is `nm benchmark geo`, where the MCP server composes the
   pipeline from `geo/prior.yaml` + `geo/validate.yaml`. The file boundaries
   here (fetch → extract → learn) map cleanly to MCP tool calls.

## Why it took ~half a day

The hardest part was zero hours of it — the LEO benchmark's `nm_primitives.py`
moved over unchanged. The work was all regime-specific glue:
endpoint inventory (`fetch_goes.py`), schema parsing per observable
(`extract_obs_jsonl.py`), LT voxelization, and driver normalization scales.
Architecturally, that's exactly what the four-regime claim predicted.
