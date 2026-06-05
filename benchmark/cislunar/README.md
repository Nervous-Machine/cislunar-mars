# Cislunar benchmark — Nervous Machine on ARTEMIS + CRaTER

The cislunar-regime sibling of the LEO Zenodo benchmark at
[`../`](../), and the fourth and final regime in the
LEO / GEO / Mars / Cislunar portability claim (see also
[`../geo/`](../geo/), [`../mars/`](../mars/)). Validates that the
Nervous Machine architecture transfers to the cislunar fields-and-
particles regime — 3 physics-region voxels by magnetospheric shielding
state, 2 observables (IMF magnitude + Bz at lunar distance), no
operational SWPC-equivalent comparator — using **real ARTEMIS L2 FGM
ground truth** from both probes (THB = P1, THC = P2) across the
May 2024 G5 superstorm window.

A supplementary CRaTER 2009-2012 dose-rate thread is included to
document the deep-solar-minimum GCR signal and the public-archive
coverage gap.

Self-contained: framework math mirrored verbatim in
[`nm_primitives.py`](nm_primitives.py); regime-portability claim is
that no MCP-server changes were required to go from GEO trapped
particles to cislunar fields-and-plasma.

## Headline results

Window: **2024-05-01 → 2024-05-31** (the May 2024 G5 superstorm month;
contains the strongest sustained SEP event of solar cycle 25 — 102 hours
above the SWPC S1 10-pfu threshold — and the deepest geomagnetic storm
since 2003 — Ap peaking at 271, F10.7 stable at 215-233 sfu).

From a single prequential pass over 2,976 obs records (2 observables ×
3 voxels × 12 drivers = 72 edges, 20,232 edge updates from both ARTEMIS
probes):

- **Tier-1 internal comparator:** anomaly-flag precision **50.0%**,
  **lift 11.13×** over the 4.49% base rate. Median residual reduction
  **+47.4%** overall (+48% on imf_btot, +55% on imf_bz in the populated
  outer_lunar_vicinity voxel). See
  [`results/internal_comparator.md`](results/internal_comparator.md).
- **Tier-2 external comparator (substrate vs naive L1→lunar
  propagation):** substrate **wins in magnetotail_transit** by **+48%
  (imf_btot)** and **+74% (imf_bz)** absolute-residual reduction;
  substrate **loses in outer_lunar_vicinity** where naive ballistic
  propagation is already excellent (its baseline behaviour). The
  voxel-dependent winner is itself the architecture-test signal: the
  substrate adds value precisely in the physics regime where the
  operational baseline is broken. See
  [`results/tier2_l1_propagation.md`](results/tier2_l1_propagation.md).
- **Tier-3 falsifiable architecture test:**
  - **Signed convergence: 2/3 correct (67%)** — the two highest-confidence
    direct-propagation edges (`imf_bz_l1 → imf_bz_at_lunar` W=+0.60 Z=1.0,
    `imf_bt_l1 → imf_btot_at_lunar` W=+0.55 Z=1.0) recovered as expected.
  - **Null-held: 5/6 (83.3%)** — drivers with no expected coupling stayed
    with |W| ≤ 0.10 at the Z ≥ 0.85 threshold.
  - **Voxel-dependent W discovered**: `imf_bt_l1 → imf_btot` collapses
    from **+0.55 in outer_lunar_vicinity** to **−0.08 in magnetotail_transit**
    — the substrate independently discovered that lobe magnetic field
    magnitude is decoupled from upstream L1 IMF, without any voxel-specific
    prior. See
    [`results/tier3_sign_convergence.md`](results/tier3_sign_convergence.md).
- **Supplementary CRaTER thread:** Pearson **r(F10.7, dose-rate) = −0.71**
  over 1,059 daily records (2009-06-26 → 2012-12-31). Strong classical
  GCR-modulation signature; CRaTER D1 median 9.4 µGy/hr at lunar orbit is
  within order-of-magnitude of the Chang'E 4 LND surface value
  (16.3 µGy/hr, Jan 2019, Wimmer-Schweingruber et al.). See
  [`results/crater_supplementary.md`](results/crater_supplementary.md).

## What the substrate discovered

The load-bearing finding is the **voxel-dependent W on `imf_bt_l1 →
imf_btot_at_lunar_distance`**:

| Voxel | Z | W | n updates | Physical interpretation |
|---|---|---|---|---|
| outer_lunar_vicinity | 1.00 | **+0.5475** | 1,034 | Moon in solar wind — IMF magnitude propagates ~directly from L1 → lunar distance with the converted scale ratio. Large positive W is the direct-propagation signature. |
| magnetotail_transit | 0.84 | **−0.0796** | 104 | Moon inside Earth's magnetotail — the locally-observed |B| is the tail-lobe field, set by Earth's magnetospheric current systems and **decoupled from upstream L1**. The substrate correctly drives W toward null. |
| inner_magnetospheric | 0.30 | 0 | 0 | ARTEMIS never enters this voxel at lunar orbit (~56 RE > 10 RE threshold). Stays at prior. |

This is the cislunar analog of Mars's `sep_proton` voxel-dependent W:
the same upstream driver has **different operational meaning in
different physics regions**, and the substrate's per-edge state surfaces
that without any voxel-specific prior. The prior is identical across
all three regions; the voxel-dependent W emerges from the data.

The `imf_bz_l1 → imf_bz_at_lunar_distance` edge shows the same pattern
(W = +0.60 outer / +0.39 magnetotail — direct propagation in the solar
wind, partial decoupling in the tail) but the magnetotail voxel did not
fully converge (Z = 0.63) due to the small sample size (n = 154 updates
on the 13.6% magnetotail-occupancy portion of the window).

## Why the comparator differs from LEO and GEO

|  | LEO | GEO | Cislunar |
|---|---|---|---|
| **Ground truth** | TOLEOS GRACE-FO (510k records) | GOES-19 fluxes + B + warm plasma (7-d rolling) | ARTEMIS THB + THC FGM (3 s, hourly-averaged) |
| **Observables** | 1 (atmospheric density) | 5 (electrons, protons, B, warm plasma) | 2 (\|B\|, Bz at lunar distance) |
| **Composition** | additive on MSIS | log-mult on flux + additive on B | additive on per-voxel median |
| **Tier-2 baseline** | NRLMSISE-00 (operational) | SWPC REFM (operational, electrons only) | naive ballistic L1→lunar IMF propagation |
| **Tier-2 result** | precision 92%, lift 7.9× | log-MAE 4× lower than REFM | substrate wins in magnetotail, loses in solar wind (voxel-dependent — the architecture-test signal) |
| **Tier-3 hit rate** | n/a | 67% signed-correct on `dst → b_field` | 67% signed-correct on direct-propagation edges |

The cislunar tier-2 metric is *unique to this regime*: naive ballistic
propagation of L1 IMF to the lunar Moon is the operational physics
baseline, and the per-voxel decoupling of L1 from local field is the
target the substrate is required to learn. Substrate-wins-in-magnetotail
is the load-bearing finding — that is exactly where naive ballistic
propagation is structurally broken.

## Files

| File | Role |
|---|---|
| `nm_primitives.py` | Byte-identical mirror of LEO/GEO/Mars primitives |
| `fetch_artemis.py` | THB + THC L2 FGM + L1 STATE CDFs from the Berkeley archive |
| `parse_artemis.py` | CDF → hourly JSONL with GSE position + voxel assignment |
| `fetch_drivers.py` | OMNI 1-min L1 + CelesTrak SW-All + SWPC alerts.json + SWPC Kp |
| `fetch_goes_protons.py` | GOES-18 SGPS L2 protons (byte-identical to Mars copy) |
| `fetch_crater.py` | LRO/CRaTER L30 dose-rate from UNH legacy HTML table |
| `extract_obs_jsonl.py` | Voxel-aware driver alignment + JSONL emit |
| `learn_cislunar.py` | Streaming substrate pass + tier-1 prior-W-vs-evolved-W |
| `analyze_l1_propagation.py` | Tier-2: substrate vs naive ballistic L1→lunar |
| `analyze_sign_convergence.py` | Tier-3: falsifiable per-edge sign-convergence test |
| `analyze_crater_supplementary.py` | Supplementary: CRaTER F10.7-vs-dose correlation |
| `../sep_alerts.py` | Shared SWPC alerts parser (also used by GEO and Mars) |
| `results/*.md`, `results/edges_state.json` | Committed result artifacts |

## Method, briefly

- **Observables** (2): `imf_btot_at_lunar_distance` (|B| in nT) and
  `imf_bz_at_lunar_distance` (Bz_GSE in nT), both from THB+THC FGM
  3-second L2 records aggregated to hourly means.
- **Voxelization** (3 physics regions, computed from ARTEMIS state-CDF
  GSE position):
  - `inner_magnetospheric`  — r ≤ 10 RE (always empty for ARTEMIS at lunar orbit)
  - `magnetotail_transit`   — nightside (x_GSE < −10 RE) inside a static
    tail half-width ~25 RE flaring proxy (suppressing the need for
    self-consistent magnetopause computation; the substrate's
    voxel-dependent W absorbs the residual)
  - `outer_lunar_vicinity`  — everything else at r > 10 RE
- **Drivers** (12):
  - L1 IMF + plasma from OMNI HRO 1-min: `imf_bz_l1`, `imf_bt_l1`,
    `sw_speed`, `sw_density`, `sw_dynamic_pressure` (derived), `dst_index`
    (SYM/H, 1-min cadence) — 93.3% coverage in the window.
  - Daily solar / geomag from CelesTrak SW-All: `f107`, `ap` — 100% coverage.
  - SWPC Kp (3-hour): `kp_index` — 7.6-day rolling, partial coverage.
  - GOES SGPS protons (5-min averaged → hourly max): `sep_proton`,
    graded by SWPC S-scale (0.33 / 0.67 / 1.00 at the 10 / 100 / 1000 pfu
    thresholds), with 48-hour exponential decay matching the GEO/Mars
    convention. SEP active on 57.9% of records in this window — the
    storm-rich May 2024 ≥10-MeV proton signal.
  - SWPC alerts.json-derived: `flare_xclass`, `geomag_storm` — rolling
    30-day, so completely disjoint from the 2024-05 obs window. Stay
    null as documented falsifiable null-driver test.
- **Composition mode:** additive residual,
  `p = baseline + (Σ d·W)·σ` on driver-normalized inputs and per-
  voxel-observable σ. Same convention as LEO (additive on MSIS) and
  GEO (additive on B-field). IMF observables vary ~±tens of nT around
  a small mean (~5 nT median |B|, ~0 nT median Bz); a multiplicative
  form would diverge when baseline ≈ 0 for Bz.
- **ε convention:** per-voxel z-scored residual. Framework constants
  rescaled in `learn_cislunar.py` to match the z-score scale (same
  rescale as LEO / GEO / Mars). The single z-scored ε signal is then
  scaled by per-driver `d_norm` to produce the per-edge update.
- **Evaluation:** single prequential pass; each prediction uses edge
  state *before* the observation; the edge then updates. Warm-up: first
  20% of records (state evolves but metrics excluded).

## Three-tier metric contract

| Tier | What | Where |
|---|---|---|
| 1 | Internal: evolved-W vs prior-W (W=0) baseline. Strict-subset comparator — any precision lift is from learned coupling. Always producible. | [`results/internal_comparator.md`](results/internal_comparator.md) |
| 2 | External: substrate vs naive ballistic L1→lunar IMF propagation. Operational physics baseline; uniquely available for the cislunar regime where L1-to-target propagation is non-trivial. | [`results/tier2_l1_propagation.md`](results/tier2_l1_propagation.md) |
| 3 | Falsifiable architecture: per-edge sign match against a-priori expected signs from cislunar operational physics. Includes voxel-dependent expectations as the load-bearing test. | [`results/tier3_sign_convergence.md`](results/tier3_sign_convergence.md) |

External comparators surveyed but **not** wired in this commit:

- **AE9/AP9 (IRENE)** — climatological percentile baselines for trapped-
  electron/proton flux in inner_magnetospheric voxel. Same pip-availability
  constraints documented in the GEO benchmark; AE9/AP9 also requires
  IRBEM bindings (heavy C dependency tree) and would only provide a
  baseline for the empty inner_magnetospheric voxel in this window.
  Out of scope for this commit.
- **NAIRAS-Lunar** — production endpoint at `sol.spdf.gsfc.nasa.gov/nairas/`
  was unreachable at benchmark run time (June 2026; the same gap reported
  by the Mars benchmark). When a public archive surfaces, the tier-2
  contingency drops in with one additional column.

## Data and reproducibility

Large intermediate files are **not** committed:

- `raw/artemis/`        — ARTEMIS L2 FGM + L1 STATE CDFs (~1.9 GB raw for 30 days × 2 probes)
- `raw/omni/`           — OMNI HRO 1-min ASCII (~13 MB / month)
- `raw/goes_protons/`   — GOES-18 SGPS L2 daily netCDF (~600 KB / day)
- `obs.jsonl`           — joined obs records (~1.5 MB)
- `artemis_hourly.jsonl` — intermediate (~480 KB)

Committed: `results/edges_state.json` (~13 KB), the four `results/*.md`
artifacts, and `raw/crater_l30_daily.jsonl` (the small daily CRaTER
table for the supplementary thread).

All endpoints used by the fetch scripts are public; no auth, no rate
limits encountered:

1. **Berkeley THEMIS-ARTEMIS** — `http://themis.ssl.berkeley.edu/data/themis/thb/`
   and `/thc/` — L2 FGM + L1 STATE CDFs, ~22 MB/day for FGM, ~600 KB/day
   for STATE. cdflib parser used (pure-Python, pip-installable).
2. **NASA SPDF OMNI HRO** — `https://spdf.gsfc.nasa.gov/pub/data/omni/high_res_omni/monthly_1min/`
   — 1-minute multi-spacecraft L1-propagated upstream wind, monthly ASCII files.
3. **NOAA NCEI GOES-18 SGPS** — same path as the Mars benchmark uses.
4. **SWPC products** (Kp, alerts) — same rolling-window JSON as GEO / Mars.
5. **CelesTrak SW-All** — `https://celestrak.org/SpaceData/SW-All.csv`.
6. **UNH CRaTER L30** — `https://crater-products.sr.unh.edu/data/inst/dose/table_l30drate.php`
   — single HTML table parsed with a stdlib `html.parser` derivative.

## Reproduce

```bash
pip install requests certifi cdflib netCDF4 numpy

python3 fetch_artemis.py 2024-05-01 2024-05-31  # ~1.9 GB, ~60 s
python3 fetch_drivers.py                          # ~13 MB, ~10 s
python3 fetch_goes_protons.py 2024-05-01 2024-05-31  # ~20 MB, ~25 s
python3 fetch_crater.py                          # ~330 KB, ~5 s
python3 parse_artemis.py                         # ~10 s
python3 extract_obs_jsonl.py                     # ~5 s
python3 learn_cislunar.py                        # ~30 s   tier-1
python3 analyze_l1_propagation.py                # ~3 s    tier-2
python3 analyze_sign_convergence.py              # ~1 s    tier-3
python3 analyze_crater_supplementary.py          # ~1 s    supplementary
```

Approximate total compute on a 2024 Apple-silicon laptop: **~3 minutes**
including downloads.

## Window-coverage and scope

The 2024-05 ARTEMIS window is **storm-rich**: it includes the
historic May 10-11 G5 superstorm (one of the strongest events of the
modern era) and several days of sustained S1+ SEP activity (102 hours
above 10 pfu integral ≥10 MeV proton flux). This is *exactly* the
data window the architecture portability claim should be tested on —
the substrate has to learn from the strongest available driver state
in the window.

Voxel coverage in the window:
- inner_magnetospheric: **0 records** (ARTEMIS at lunar orbit ~56 RE
  never enters this voxel — pure geometry; not a data gap)
- magnetotail_transit: **404 records (13.6%)** — Moon spent ~3-5 days
  in Earth's magnetotail during this month, consistent with lunar-cycle
  geometry
- outer_lunar_vicinity: **2,572 records (86.4%)** — dominant ARTEMIS regime

The May 2024 window scopes to a single lunar cycle. Multi-month / multi-
year backfill is straightforward (ARTEMIS THB+THC FGM has continuous
coverage 2011-2026); the fetcher is parameterized on (start, end). A
multi-year ingest would populate magnetotail_transit at higher sample
counts and expose the substrate to a wider range of driver phases.

## Provenance

Framework primitives in `nm_primitives.py` are byte-identical to the
LEO / GEO / Mars benchmarks' copies (verified `diff` returns 0). The
regime-specific code is fetch + parse glue, the OMNI-1min plain-text
parser, the CDF→hourly aggregation, and the three tier analyzers.

The framework math mirrored here is the source-of-truth implementation
in `~/NM-learning-loop/mcp_validation.py` (the operational MCP server).
If the two disagree, the MCP server is authoritative.

## What's deferred (honest scope)

1. **Multi-month / multi-year ARTEMIS backfill** for higher
   magnetotail_transit sample counts and full coverage of solar-cycle
   phase. Bound by disk (~2 GB per 30 days × 2 probes); data is
   continuously available from 2011 to present.
2. **CRaTER post-2012 ingest.** The UNH endpoint exposes 2009-2012 only.
   Post-2012 CRaTER ingests require direct UNH outreach (Nathan Schwadron)
   or a working PDS-PPI `LROCRA_2*` collection (currently 404). The
   `cislunar/validate.yaml`'s 17-year claim cannot be substantiated
   from public endpoints without that outreach. Documented as a Phase II
   gap, not a benchmark failure.
3. **CRaTER substrate training pass.** The main benchmark trains on
   ARTEMIS IMF observables; the CRaTER supplementary thread is a
   correlation-only analysis (Pearson r=−0.71, F10.7 vs dose-rate). A
   unified multi-window substrate pass spanning 2009-2012 dose-rate AND
   2024-05 IMF is Phase II scope.
4. **AE9/AP9 trapped-radiation tier-2** for the inner_magnetospheric
   voxel — IRBEM dependency tree is heavy; voxel was geometry-empty
   anyway in this 30-day ARTEMIS window.
5. **NAIRAS-Lunar tier-2** when a public archive surfaces. Endpoint
   surveyed (same as Mars benchmark) and unreachable at run time.
6. **Chang'E 4 LND time-aligned data.** Only the published Jan 2019
   summary value is publicly available (16.3 µGy/hr total surface dose);
   no time-aligned archive is accessible at the granularity needed for
   substrate training. Used here as an order-of-magnitude sanity check
   against the CRaTER D1 median (9.4 µGy/hr, Si, no albedo correction).
7. **ESCAPADE near-moon-passage data** during 2026 loiter phase. SIMPLEx
   proprietary period; partnership access via PI engagement is in the
   Phase I Task 3.3 plan, not in this pre-Phase-II benchmark.

## What this means for operators

The natural readers for this section are the Artemis program (NASA HQ,
JSC, MSFC), CLPS lunar-lander providers (Intuitive Machines, Astrobotic,
Firefly, etc.), the ESCAPADE team, and any commercial cislunar-transit
mission operator planning radiation-environment-aware autonomy.

**What you get that you don't have today.** Operational cislunar IMF
forecasting today is naive ballistic propagation: take the L1 DSCOVR
measurement, assume the field convects unchanged to the Moon. This
substrate produces (a) a calibrated per-voxel correction that's regime-
aware (solar wind vs. magnetotail transit), (b) a per-edge `Z` that tells
the operator how much to trust the propagation correction in *this*
voxel, and (c) the structural result that **no single coupling can
represent both regimes** — a single-coupling forecaster (naive ballistic)
is excellent in the solar wind and structurally broken in the magnetotail,
and only a per-voxel learner can represent the regime-dependence. The
substrate discovered magnetotail lobe-field decoupling from L1 *without
any voxel-specific prior* — that result is the load-bearing falsifiable
signature for cislunar-regime portability.

**Concrete operational uses.**

- **Cislunar transit dose forecasting that's voxel-aware.** Matters for
  Artemis crew transit through the magnetotail crossing; matters for
  CLPS surface-mission planning during cislunar approach. Naive
  ballistic dose forecasts overweight L1-driven exposure inside the
  magnetotail where the field is decoupled. The substrate corrects this
  regime-by-regime.
- **Comm-degradation prediction during magnetotail passage.** Lobe
  plasma + lobe field set comm-band absorption differently from
  solar-wind conditions. The substrate's per-voxel state can drive
  on-board comm-mode selection (data rate, frequency band) without
  ground-loop latency.
- **ESCAPADE-class mission planning during loiter.** Near-moon passage
  during the 2026 loiter phase covers cislunar regions the substrate
  has voxel-edge structure for. A live ESCAPADE data feed during loiter
  is the natural Phase II pilot input — substrate priors at delivery
  inform mission-planning loops; loiter telemetry advances the per-edge
  state at higher cadence than the public ARTEMIS-only base supports.
- **Lunar surface dose budget for crewed operations.** The supplementary
  CRaTER 2009-2012 thread already shows F10.7-vs-orbital-dose r=−0.71
  on real lunar-orbit data — the classical GCR-modulation signature.
  For Artemis surface ops, this is the regime baseline against which
  per-event SEP enhancements have to be planned.

**Inner/outer architecture context.** This benchmark is the *outer*
(environmental) learning loop. The same primitives deploy on a
cislunar / lunar-surface platform as an *inner* (mechanical) learning
loop — solar-array degradation under transit dose, comm-band attenuation
under lobe-plasma conditions, thermal-loop behavior under lunar-night
extremes — using the outer loop's converged per-edge `(W, Z)` as the
inner loop's prior. Together the two loops bound the operator's unknown
unknowns from above (cislunar environment surprise, regime-dependent)
and below (vehicle surprise).

**What an operator pilot looks like.** 3-6 month shadow run against
the operator's cislunar / lunar-mission archive (transit telemetry,
comm logs, instrument-mode windows). Substrate publishes per-voxel
state + flags to a shared dashboard; at end of pilot we produce
lead-time-vs-current-tooling histograms, per-anomaly trace reports,
and an inner-loop scaffold proposal specific to the platform class
(crew vehicle, CLPS lander, smallsat). First-stage pilot is outer-loop-
only against the archive — no spacecraft modification required.
Contact: heidi@everychart.io.

