# GEO benchmark — Nervous Machine on GOES-19 + REFM comparator

The GEO-regime sibling of the LEO Zenodo benchmark at
[`../`](../). Validates the substrate against the operational SWPC REFM
forecast model for >2 MeV electron fluence, plus an internal prior-W
comparator and a falsifiable architecture-test pass.

Self-contained: framework math mirrored in
[`nm_primitives.py`](nm_primitives.py); regime-portability claim is
that no MCP-server changes were required to go from LEO drag to
GEO trapped-particle / magnetic environment.

## Headline results

From a single-pass prequential (predict-then-update) run over a 7-day
SWPC rolling window (5 observables × 6 LT voxels × 12 drivers = 360
edges, 17,809 obs records, 175,450 edge updates):

- **Tier-1 internal comparator: anomaly-flag precision 45.2%, lift 6.99×**
  over the prior-W baseline (analogous to LEO's 7.90× over MSIS).
  Residual variance reduced 82.9% on B-field, 34.8% on warm-plasma —
  see [`results/internal_comparator.md`](results/internal_comparator.md).
- **Tier-2 external comparator (REFM):** framework log-MAE 0.041 vs REFM
  Day-1 log-MAE 0.169 on the 7-day overlap (4× lower). REFM publishes
  PE=0.15 all-time / 0.42 last-30-d as its own skill — see
  [`results/tier2_refm_comparison.md`](results/tier2_refm_comparison.md).
- **Tier-3 falsifiable architecture test:** `dst → b_field_magnitude`
  edges converge with the correct sign in 4/6 voxels (67%, vs 50% chance);
  null-expected edges hold |W| ≤ 0.10 in 59% of cases. **SEP/CME edges
  show zero in-window event coverage** (0/1966 records ≥10 pfu) — the
  test honestly reports decay-tail-only data, not architecture failure.
  See [`results/tier3_sign_convergence.md`](results/tier3_sign_convergence.md).
- **Lead-time analysis:** 10/11 SWPC alert events in the obs window were
  flagged at SEVERE-tier (≥5σ) before alert onset, median lead +103.8h.
  See [`results/lead_time_by_severity.md`](results/lead_time_by_severity.md).

## What's here

| File | Role |
|---|---|
| `nm_primitives.py` | Framework math (ε, η, ΔW, Z evolution), byte-identical to the LEO benchmark's copy. Standalone. |
| `fetch_goes.py` | Pull 7-day rolling SWPC JSON for GOES + DSCOVR + indices, plus REFM tabular text |
| `extract_obs_jsonl.py` | Time-align drivers, voxelize by LT, parse SWPC alerts → SEP/CME drivers, emit per-(t, voxel, observable) JSONL |
| `learn_geo.py` | Streaming single-pass training; per-observable composition (log-space multiplicative for fluxes, additive-residual for B-field); writes `results/preds.jsonl` + `results/trajectory.jsonl` |
| `analyze_internal.py` | Tier-1 comparator: evolved-W vs prior-W, 2×2 contingency + per-observable variance reduction |
| `analyze_refm.py` | Tier-2 comparator: framework e_flux_gt_2mev vs SWPC REFM Day-1 forecast, daily-fluence aggregation |
| `analyze_sign_convergence.py` | Tier-3 falsifiable architecture test: published a-priori signs vs converged W |
| `analyze_lead_time.py` | Per-event lead time by severity tier (LEO parity) |
| `../sep_alerts.py` | Shared SWPC alerts parser (also used by Mars) |
| `results/` | Committed small artifacts: training summary, final edge state, comparator tables |

## Method, briefly

- **Observables** (5 of 5 in `geo/prior.yaml`): `e_flux_gt_2mev` (>=2 MeV
  electrons), `p_flux_gt_10mev`, `p_flux_gt_50mev` (SEP-relevant protons),
  `b_field_magnitude` (GEO magnetic field total), `e_flux_warm_plasma`
  (79 keV — proxy for the 1-50 keV MPS-LO band declared in prior.yaml;
  L1b MPS-LO is the eventual swap-in once a NetCDF ingest layer is added).
- **Drivers** (12 of 12): DSCOVR plasma (sw_speed, sw_density), DSCOVR
  mag (imf_bz, imf_bt), GOES-EXIS (xrs_long, mgii_index), planetary
  indices (kp_index, dst), and four event-derived drivers from SWPC
  alerts.json — `sep_proton`, `relativistic_electron`, `flare_xclass`,
  `geomag_storm` — each in [0, 1] with exponential decay from onset
  (see `../sep_alerts.py` for the Space Weather Message Code mapping).
- **Voxelization:** 6 local-time bins (lt_0_4 … lt_20_24). GOES-19 at
  ~75.2°W sweeps all 6 voxels every 24 h.
- **Composition modes per observable.** Flux observables use log-space
  multiplicative coupling — `log10(p) = log10(bl) + (Σ d·W)·σ_log`,
  clamped to ±3 OOM — because flux residuals span many decades during
  storms and naive linear coupling saturates W at ±1 with many active
  drivers. B-field uses additive-residual — `p = bl + (Σ d·W)·σ_linear`
  — because GEO B varies only ~±30 nT around ~100 nT and a multiplicative
  form would saturate similarly. See `PREDICTION_FORM` in `learn_geo.py`.
- **ε convention:** dimensionless per-voxel-observable z-scored
  residual. For multiplicative (flux): ε = (log10 p − log10 o) / σ_log;
  for additive (B-field): ε = (p − o) / σ_linear. Framework's
  magnitude-tolerance constants (`W_STEP`, `Z_BIAS_TOL`, `Z_STD_TOL`)
  are rescaled in `learn_geo.py` to match the z-score ε scale, same
  rescale as the LEO benchmark.
- **Evaluation:** single online prequential pass (predict-then-update).
  Each prediction uses edge state *before* the observation; the edge
  then updates.

## Three-tier metric contract

The LEO benchmark has one tier-2 metric available — MSIS exists as
THE operational standard for thermospheric density. The GEO regime
has REFM for >2 MeV electrons but no equivalent for protons / B /
hot plasma. The benchmark therefore reports three metric tiers:

| Tier | What | Where |
|---|---|---|
| 1 | Internal: evolved-W vs prior-W (W=0) baseline. Strict subset comparator — any precision lift is from learned coupling. Always producible. | [`results/internal_comparator.md`](results/internal_comparator.md) |
| 2 | External: SWPC REFM Day-1 forecast for `e_flux_gt_2mev`. Operational baseline with published PE. Wirable for 1/5 observables. | [`results/tier2_refm_comparison.md`](results/tier2_refm_comparison.md) |
| 3 | Falsifiable architecture: per-edge sign match against a-priori expected signs from operational forecasting literature. | [`results/tier3_sign_convergence.md`](results/tier3_sign_convergence.md) |

External comparators surveyed but not wired in this commit:

- **AE9/AP9 (IRENE)** — provides climatological percentile baselines
  for trapped-electron/proton flux at GEO; would give a tier-2
  comparator for the other electron / proton observables. Requires
  either pyirene (no pip release at time of writing) or spacepy +
  IRBEM (heavy C dependency tree). Out of scope for this commit; the
  REFM tier-2 + tier-1 internal + tier-3 architecture test is the
  working publishable contract.
- **CCMC iSWA / SWMF runs** — case-study models for specific events;
  not a continuous operational baseline.

## Data

Large intermediate files (~50 MB obs JSONL + ~17 MB trajectory) are
**not** committed; they regenerate from public archives. Committed:
`results/edges_state.json` (~40 KB), `results/training_summary.md`,
`results/internal_comparator.md`, `results/tier2_refm_comparison.md`,
`results/tier3_sign_convergence.md`, `results/lead_time_by_severity.md`.

All endpoints used by `fetch_goes.py` are public — no auth, no rate
limits encountered at hourly cadence:

1. **SWPC primary GOES feeds** — 7-day rolling JSON
2. **SWPC products** (DSCOVR, Kp, Dst, alerts) — rolling-window JSON
3. **SWPC text REFM** — `relativistic-electron-fluence-tabular.txt` (60 days),
   `relativistic-electron-fluence-statistics.txt` (published PE skill scores)

## Reproduce

```bash
pip install requests certifi
python3 fetch_goes.py                       # ~10 s
python3 extract_obs_jsonl.py                # ~2 s
python3 learn_geo.py                        # ~30 s
python3 analyze_internal.py                 # ~5 s   tier-1
python3 analyze_refm.py                     # ~5 s   tier-2
python3 analyze_sign_convergence.py         # ~1 s   tier-3
python3 analyze_lead_time.py                # ~10 s  LEO parity
```

Approximate total compute on a 2024 Apple-silicon laptop: ~1 minute.

## Window-coverage and scope

The 7-day SWPC rolling window is the *current* publishable window. It
contains 45 deduped SWPC operational alerts (11 onset within the obs
period), enough for lead-time statistics, but **no actively-rising
SEP events** — proton flux stays at quiet background (0/1966 records
≥10 pfu). SEP/CME alert-derived drivers therefore carry decay-tail
intensity only; their architecture-test sign convergence requires
events-in-window evidence.

Multi-month NCEI backfill from the GOES-R AWS S3 NetCDF archive
(`s3://noaa-goes16/SEIS-L1b-MPSL/…`, ditto SGPS/MAG) is the obvious
next step for parity with LEO's 7.5-year storm catalog (21 storms
≤−100 nT). NCEI's `goes-r-series-l2-operational-space-weather-products/`
tree was created but is empty as of 2026-06; the L1b S3 path is
working but requires a netCDF4 + xarray ingest layer that is out of
scope for this commit.

## What this means for operators

The natural readers for this section are GEO satellite operations teams
(Intelsat, SES, Inmarsat, Iridium, USSF GEO assets), NOAA SWPC operational
forecasters, and spacecraft anomaly-response analysts.

**What you get that you don't have today.** Operational REFM is a single
Day-1 forecast number with no calibrated uncertainty and no LT structure.
This substrate produces (a) a calibrated per-edge certainty `Z` per
LT-voxel per observable, (b) a signed coupling `W` per driver that's
voxel-aware (pre-midnight growth-phase risk is structurally different
from afternoon-side and the substrate represents this directly), and
(c) a 4× lower log-MAE than REFM Day-1 on the overlap window with the
same input data REFM uses. The substrate's anomaly flag fires when
both `Z ≥ 0.85` AND `|ε| ≥ 2σ` — the `Z` gate is the part that's
missing from current operational tooling.

**Concrete operational uses.**

- **Deep-dielectric-charging precursor flagging** with per-LT-voxel
  resolution — currently 67% sign-correct on `dst → b_field_magnitude`
  causal edges (vs. 50% random); the unconverged voxels are exactly
  where the operator wants more measurement (§"Skeleton boundary"
  in `results/tier3_sign_convergence.md`).
- **Charging-anomaly EVA-analog timing.** Delay non-critical thruster
  firings during high-`Z` charging windows; the substrate gives an
  hours-to-days lead time with calibrated confidence rather than a
  daily binary forecast.
- **Pre-midnight growth-phase substorm awareness.** The substrate's
  per-LT-voxel state surfaces the LT-structured risk that operational
  forecasts average over. This matters for sensitive-mode scheduling
  on payloads near substorm onset sectors.
- **Lead-time results from the current window:** 10/11 SWPC operational
  alerts in the obs window flagged at SEVERE-tier ahead of alert onset,
  median +103.8h. See [`results/lead_time_by_severity.md`](results/lead_time_by_severity.md).

**Inner/outer architecture context.** This benchmark is the *outer*
(environmental) learning loop. The same primitive math is intended to
deploy on the spacecraft flight computer as an *inner* (mechanical)
learning loop — battery degradation under thermal/charge cycling,
attitude-controller bias under storm-driven torques, etc. — using the
outer loop's converged per-edge `(W, Z)` as the inner loop's prior.
Together the two loops bound the operator's worst-case unknown unknowns
from above (environment surprise) and below (vehicle surprise); either
alone is insufficient for assured autonomy. A first-stage operator
pilot is outer-loop-only; the inner-loop deployment is a follow-on
deliverable.

**What an operator pilot looks like.** 3-6 month shadow run: operator
continues to act on REFM and existing tooling; substrate publishes
per-edge state + flags to a shared dashboard; at end of pilot, we
compute lead-time-vs-current-tooling histograms and per-anomaly trace
reports (which driver was attributable, in which LT voxel, at what
`Z`). The substrate runs against the operator's archive data — no
spacecraft modification required for the outer-loop pilot. Contact:
heidi@everychart.io.

## Provenance

Framework primitives in `nm_primitives.py` are byte-identical to the LEO
benchmark's copy. The regime-specific code is fetch + extract glue, the
SWPC alerts parser (`../sep_alerts.py`), and the four tier analyzers.
The architecture portability claim — same primitives, different regime —
is what this directory is here to test, and the head-of-table edge
counts (208/360 converged, 0% W-saturation) confirm it transfers cleanly.

The framework math here mirrors the implementation in
`~/NM-learning-loop/mcp_validation.py` (the operational MCP server). If
the two disagree, the MCP server is authoritative.
