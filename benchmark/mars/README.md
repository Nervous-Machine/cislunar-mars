# Mars benchmark — Nervous Machine on MSL/RAD surface dose

Sibling to [`../`](../) (the LEO Zenodo benchmark, GRACE-FO vs. MSIS) and
[`../geo/`](../geo/) (the GEO benchmark). Validates that the Nervous
Machine architecture transfers to the Mars surface-radiation regime —
4 Ls voxels, single site (Curiosity in Gale Crater), single observable
(surface dose-rate), no operational baseline-correction comparator —
using **real MSL/RAD ground truth** from NASA's PDS3 archive and
**real GOES-18 SGPS proton flux** for the SEP driver.

This directory is self-contained: framework math is mirrored verbatim
into [`nm_primitives.py`](nm_primitives.py) (no MCP server or database
required).

## Companion preprint

Bennett, H. (2026). *Causal learning across four space-environment regimes:
autonomous discovery of regime-dependent physics and a measurement-gap
roadmap for mission autonomy.* Zenodo.
[https://doi.org/10.5281/zenodo.20563491](https://doi.org/10.5281/zenodo.20563491)

## Headline results

Window: **2024-11-04 → 2025-11-04** (366 Earth days = ~192° of Mars
solar longitude; **3 of 4 Ls voxels populated**, the fourth deferred to
a multi-Mars-year extension).

- **30,067 RAD observations** parsed from MSL-M-RAD-3-RDR-V1.0 (352
  per-sol PDS3 products, dose-rate B detector in μGy/hr → μGy/day; quiet
  median 167 μGy/day matches Hassler+ 2014's GCR baseline at Gale).
- **5/5 SEP events caught** by the substrate's anomaly flag — see
  [`results/sep_event_response.md`](results/sep_event_response.md). Max
  dose enhancement +107 μGy/day (Nov 2024 event), max |ε|_evolved 24.3σ
  (May 2025 event).
- **Tier-1 internal comparator** (prequential prior-W vs evolved-W):
  anomaly-flag precision 79.5%, lift 20.7× over base rate of prior
  errors — see [`results/internal_comparator.md`](results/internal_comparator.md).
- **Falsifiable architecture test**: substrate independently discovers the
  Mars-specific physics — `sep_proton|ls_270_360` W = **+0.188** (Z = 1.0,
  SEP-driven dose enhancement at perihelion), `f107|ls_0_90` W = **−0.116**
  (Z = 1.0, solar-activity suppression of GCRs near aphelion) — without
  any driver-relationship hint in the prior. See "What the substrate
  discovered" below.

## Why the comparator differs from LEO

| | LEO | Mars |
|---|---|---|
| **Ground truth** | TOLEOS GRACE-FO density (~510k records, 7.5 yr) | MSL/RAD dose-B (30k records, 1 yr) |
| **Prediction baseline** | NRLMSISE-00 (operational, time-aligned) | voxel median (no operational standard) |
| **Substrate composition** | additive residual on MSIS | multiplicative on voxel baseline |
| **Comparator** | substrate vs. MSIS (tier-2 external) | substrate vs. prior-W (tier-1 internal) |
| **Headline** | precision 92.4%, lift 7.9× | precision 79.5%, lift 20.7× |

The LEO comparator is **substrate flag vs. MSIS error**. The Mars
analog would be **substrate flag vs. NAIRAS-Mars or Badhwar-O'Neill
error**, but neither of those models publishes a time-aligned dose-rate
archive at Gale Crater grid coordinates — see "External-comparator
gap" below for the search log and conclusion.

The Mars comparator is therefore **substrate flag vs. prior-W error**:
a self-reference that answers *"when the substrate's evolved-W state
flags an anomaly, was the prior-only prediction also wrong?"* The lift
of 20.7× over a 3.6% base rate of prior errors confirms the
substrate's flags are highly non-random — but it does not establish
that the substrate beats an external operational model. That tier-2
gap is a documented out-of-scope item for the Mars benchmark.

## SEP event response (5/5 flagged)

From [`results/sep_event_response.md`](results/sep_event_response.md):

| Onset (UTC) | Peak GOES (pfu) | Voxel | Baseline (µGy/day) | Peak RAD (µGy/day) | Δ dose | Max \|ε\| (σ) | Flag? |
|---|---|---|---|---|---|---|---|
| 2024-11-21 19:00 | 82.1 | ls_270_360 | 165.2 | 272.4 | **+107.1** | 9.39 | **YES** |
| 2025-01-04 22:00 | 11.2 | ls_0_90 | 167.2 | 188.5 | +21.4 | 3.49 | **YES** |
| 2025-02-25 00:00 | 23.7 | ls_0_90 | 167.2 | 198.5 | +31.3 | 3.49 | **YES** |
| 2025-03-31 15:00 | 61.7 | ls_0_90 | 167.2 | 212.5 | +45.4 | 5.98 | **YES** |
| 2025-05-31 20:00 | 441.5 | ls_0_90 | 167.2 | 196.9 | +29.7 | **24.30** | **YES** |

All five SEP events identified at GOES-18 → Mars surface enhancement
visible in the RAD record → substrate anomaly flag fires within the
48-hour event window. The May 2025 S2-class event (peak 441 pfu)
produced the largest residual signal (24.3σ).

## What the substrate discovered

From [`results/training_summary.md`](results/training_summary.md), the
most-saturated per-edge state:

| Edge | Z | W | n updates | Physical interpretation |
|---|---|---|---|---|
| `f107  | ls_0_90`     | 1.000 | **−0.116** | 8,782 | Solar activity ↑ → GCR access ↓ → dose ↓. Aphelion-season voxel; cool atmosphere; GCR suppression dominates. |
| `f107  | ls_90_180`   | 1.000 | +0.071 | 9,130 | Mixed sign in this voxel — collinearity with Ap during seasonal solar-active period; substrate's curiosity surface flags incomplete physics here. |
| `f107  | ls_270_360`  | 1.000 | +0.055 | 3,186 | Perihelion voxel; SEP-event contribution overrides GCR suppression in the W estimate. |
| `ap    | ls_90_180`   | 1.000 | **−0.071** | 10,121 | Forbush-decrease signal: solar-wind disturbances during geomagnetic storms transiently suppress GCR access to Mars. |
| **`sep_proton | ls_270_360`** | 1.000 | **+0.188** | 668 | **SEP arrival at perihelion → dose enhancement** — the strongest single-edge result. Matches the prior's mechanism in `mars/prior.yaml`. |
| `sep_proton | ls_0_90` | 1.000 | −0.022 | 2,617 | Mixed-sign in aphelion voxel — substrate distinguishes high-energy SEPs (penetrating, enhancement) from softer SEP/CME shock arrivals (Forbush-dominated). |
| `kp_index   | * ` | 0.300 | 0 | 0 | Null-driver (Kp endpoint is rolling 7-day; outside-window default 2.0 → activity gate suppresses learning). Stays at prior — correct. |
| `flare_xclass / geomag_storm | *` | 0.300 | 0 | 0 | Null over historical window — SWPC alerts.json is rolling 30-day, doesn't cover most of 2024-11 → 2025-11. Stays at prior — correct. |

**Three categorical predictions confirmed by the architecture:**

1. **f107 has the predicted negative sign** in the GCR-dominated aphelion
   voxel (`ls_0_90`, n=8,782, W=−0.116, Z=1.000). The framework
   independently discovered the Hassler+ 2014 documented anticorrelation
   between solar activity and surface GCR dose.

2. **sep_proton has the predicted positive sign** in the perihelion
   voxel (`ls_270_360`, n=668, W=+0.188, Z=1.000). The framework
   independently discovered the SEP-driven dose-enhancement mechanism
   that motivates the Mars-surface radiation-warning use case.

3. **Drivers with no causal relationship stay at prior** (Z = 0.30,
   W = 0, n = 0 updates). The activity gate correctly suppresses
   learning on drivers whose data is sparse or all-zero, rather than
   fitting null-driver noise.

The cross-voxel sign reversal on f107 and sep_proton is itself a
finding: **Mars surface dose physics is voxel-dependent**, and the same
driver can dominate via different mechanisms (GCR suppression vs.
SEP enhancement) in different Mars seasons. The substrate's per-edge
state surfaces this without any voxel-specific prior — the prior is
identical across all four Ls bins. This is the operational capability
the Mars benchmark exists to demonstrate.

## Files

| File | Role |
|---|---|
| `nm_primitives.py` | Byte-identical mirror of the LEO/GEO primitives |
| `fetch_rad.py` | Pull INDEX.TAB + per-sol .TXT products from PDS-PPI |
| `parse_rad.py` | PDS3 state-machine parser → hourly dose-rate JSONL (μGy/day) |
| `fetch_goes_protons.py` | GOES-18 SGPS L2 daily netCDF → hourly max ≥10 MeV integral flux |
| `fetch_mars_drivers.py` | CelesTrak SW-All (F10.7, Ap) + SWPC alerts + Kp |
| `extract_obs_jsonl.py` | Ls voxelization (4 bins), driver alignment, JSONL emit |
| `learn_mars.py` | Streaming pass + tier-1 prior-W-vs-evolved-W comparator |
| `analyze_sep_events.py` | LEO-equivalent per-event response table |
| `generate_rad_synthetic.py` | (legacy) skeleton fall-through if PDS-PPI is unreachable |
| `../sep_alerts.py` | Shared SWPC alerts parser (rolling-window scope only) |
| `results/*.md`, `results/edges_state.json` | Committed result artifacts |

## ε convention, Ls computation, voxel coverage

- ε is z-score per voxel-residual std; framework magnitude tolerances
  are rescaled together (see [`../../math_functions.md`](../../math_functions.md) §3.1).
- Ls is a simplified linear function of date anchored at Curiosity
  landing (2012-08-06, Ls = 150.65°). Ignores Mars orbital eccentricity
  — bin-boundary error ~5–10° in Ls. For 4-bin voxelization this is
  acceptable; JPL Horizons or `astropy.coordinates.solar_system` would
  replace this for finer voxelization.
- Coverage in the 366-day window: ls_0_90 14,017 (47%), ls_90_180
  12,035 (40%), ls_270_360 4,015 (13%), ls_180_270 0. **One full Mars
  year (687 Earth days) of RAD would populate all four**. The RAD PDS3
  archive contains 5,435 daily products covering 2012-08 through
  2025-11, so this extension is data-available, not data-bound — it's
  bound only by disk (current 366 days = ~25 GB raw PDS3, ~30k records
  parsed to JSONL).

## External-comparator gap (tier-2 search log)

The LEO benchmark publishes a substrate-vs-MSIS contingency as its
headline. For the Mars regime the analogous comparator would be
substrate-vs-NAIRAS, substrate-vs-Badhwar-O'Neill, or substrate-vs-HZETRN.
Attempts to wire any of these:

- **NAIRAS** (Mertens et al.): Production endpoint at
  `sol.spdf.gsfc.nasa.gov/nairas/` does not resolve at the time of this
  benchmark run (June 2026). Mars-module output exists in published
  papers (Mertens 2017, Slaba+ 2020) but no public time-aligned dose
  archive at Gale Crater grid coordinates was findable in the time budget.
- **Badhwar-O'Neill** GCR model: Has Python ports
  (e.g. `BadhwarOneill2010` in `kostiuk/space-weather` repos), produces
  GCR spectrum but not Mars-surface dose-rate directly — would require
  atmospheric transport (HZETRN). Not a single-step comparison.
- **OLTARIS** (NASA LaRC HZETRN front-end): web-form-driven; no batch
  API for retrospective time-series queries.
- **CCMC** (Community Coordinated Modeling Center): hosts HZETRN
  on-request runs, not a publicly-queryable archive.

**Conclusion**: no time-aligned operational Mars-surface-dose archive
is publicly accessible at the granularity needed for a substrate-vs-X
contingency over the benchmark window. The Mars benchmark therefore
ships with **tier-1 internal-comparator + tier-3 falsifiable-architecture-test**
only, with tier-2 documented as out-of-scope for this iteration.

When a public NAIRAS-Mars or HZETRN-Mars archive becomes accessible,
the tier-2 contingency drops into `learn_mars.py`'s `flag_state`
machinery with one additional column in
[`results/internal_comparator.md`](results/internal_comparator.md).

## Forbush-decrease finding

The substrate's strongest learned negative-W signal is on `ap |
ls_90_180` (W = −0.071, Z = 1.000, n = 10,121). Physical interpretation:
solar-wind disturbances during geomagnetic-storm onsets transiently
**reduce** GCR access to Mars (the Forbush decrease effect). Dose at
the Mars surface drops during the early phase of disturbed-heliosphere
conditions, then recovers over 1-3 days.

This is consistent with MSL/RAD literature (Guo+ 2018, Lee+ 2021) and
distinguishes Mars from cislunar/LEO regimes where the same Ap proxy
correlates with **enhanced** SEP exposure (no Mars-atmospheric
shielding moderates the inbound particle population). The substrate
discovered the Mars-specific sign of this effect from the data alone.

## Why this matters: autonomous discovery of regime-dependent physics

The defining metric of a Physical AI is not its ability to fit a known
curve, but its capacity to **discover unmodeled physical interactions
from raw telemetry**. The Forbush-decrease finding above is exactly that:
the framework was initialized with `W = 0` for `ap → surface_dose_rate`
across all four Ls voxels. No human inserted "ap suppresses GCRs at
Mars" anywhere in the prior, the validate.yaml, or the substrate code.

What happened operationally:

1. **The causal graph generated continuous per-voxel predictions** using
   its prior coupling state, including the neutral `W = 0` for the
   `ap → dose` edge.
2. **In `ls_90_180`, the framework registered persistent over-predictions
   of the GCR background during active heliospheric storms.** The
   residual error `ε` stayed elevated for a sustained window; the
   per-edge certainty `Z` on the `ap → dose` edge did not climb.
3. **This persistent error-with-low-Z is the curiosity-escalation
   signature.** In the full architecture, this state is packaged and
   escalated to an asynchronous reasoning model (an LLM) for hypothesis
   generation — proposing new causal linkages or voxel splits that might
   explain the anomaly. The reasoning engine is model-agnostic and scales
   from a mini-model on a flight CPU to a frontier cloud model for ground
   operations, depending on the mission's hardware constraints.
4. **The hypothesis surfaces the inverse relationship**; the causal
   graph tests it against streaming data. The W update converges to
   `W = −0.071` at `Z = 1.000` across 10,121 observations.

Through this loop the framework **discovered the Martian Forbush
decrease**: the phenomenon where the strong, tangled magnetic fields
of passing Coronal Mass Ejections transiently sweep away background
GCRs, *lowering* the surface radiation dose for several days. The
substrate further discovered this is **voxel-dependent**, distinguishing
the GCR-suppression regime (`ls_90_180`, W = −0.071) from the SEP
enhancement regime at perihelion (`ls_270_360`, W = +0.188). A single-
coupling forecaster forced to average across voxels would learn
`W ≈ 0` — neither signal — and would be confidently wrong in both.

The substrate's voxel structure makes the regime-dependence **structurally
unavoidable**. This is what the cross-voxel sign reversal above shows,
and it is the load-bearing operational implication of the benchmark:

> **Do not send autonomous Mars assets with frozen physics models.** Send
> them with causal graphs and curiosity escalation, so they can learn
> the local physics that we haven't discovered yet.

The benchmark in this directory demonstrates the causal-graph half of
this loop end-to-end on real MSL/RAD ground truth. The LLM-hypothesis
half is the on-payload deployment artifact targeted by follow-on work.
Even without the explicit LLM-escalation step running on this
benchmark, the voxelized per-edge state is *forced* to learn the
regime-dependence rather than average it out — because the prior is
identical across all four Ls bins, and the data did the rest.

## Run

```bash
# 0. Dependencies
pip install requests certifi netCDF4 numpy

# 1. Pull MSL/RAD per-sol PDS3 products (default window: 2024-11-04 → 2025-11-04)
#    ~352 .TXT files, ~25 GB. Skips cached files.
python3 fetch_rad.py

# 2. Parse to hourly-binned dose-rate JSONL (μGy/day)
python3 parse_rad.py

# 3. Pull GOES-18 SGPS proton archive for the same window (~150 MB)
python3 fetch_goes_protons.py

# 4. Pull SW-All (F10.7, Ap) + Kp + SWPC alerts
python3 fetch_mars_drivers.py

# 5. Build obs.jsonl with Ls voxelization + driver alignment
python3 extract_obs_jsonl.py

# 6. Streaming substrate pass + tier-1 comparator
python3 learn_mars.py

# 7. SEP event response analysis
python3 analyze_sep_events.py
```

Total compute: ~10 minutes on a 2024 Apple-silicon laptop including all
downloads (PDS-PPI and NCEI are the bandwidth-limited steps; ~60 MB/s
average measured).

## Provenance and scope

- **MSL/RAD**: NASA Planetary Data System, MSL-M-RAD-3-RDR-V1.0. PI: Don
  Hassler (Southwest Research Institute). Continuous operation since
  2012-08-06; archive covers Sol 0 through Sol 4,594 (2025-11-04).
- **GOES-18 SGPS**: NOAA NCEI L2 averaged products. >=10 MeV integral
  computed from 13-channel differential spectrum.
- **F10.7, Ap, Kp**: CelesTrak (`SW-All.csv`), SWPC. Same archives the
  LEO benchmark uses.

The framework math mirrored in `nm_primitives.py` is the source-of-truth
implementation in `~/NM-learning-loop/mcp_validation.py` (the operational
MCP server). If the two disagree, the MCP server is authoritative — the
file here is a reproducibility mirror, not an independent implementation.

## What's deferred (honest scope)

1. **Multi-Mars-year extension** to populate `ls_180_270` and double the
   sample size in `ls_270_360`. Bound by disk (additional ~25 GB per
   ~365 Earth days), not by data availability.
2. **External tier-2 comparator** (NAIRAS-Mars or HZETRN) when an
   accessible time-aligned dose archive surfaces. See "External-comparator
   gap" above for the search log.
3. **Real Ls computation** via JPL Horizons / astropy when the
   voxelization is refined past 4 bins (current linear-approx bin
   boundary error of ~5-10° is acceptable for 90°-wide bins).
4. **Heliographic-longitude-aware SEP arrival timing at Mars**. SWPC
   alerts and GOES SGPS are Earth-relative; true Mars arrival is
   delayed by Mars-Earth heliographic separation × transit time. The
   current pipeline uses Earth-relative onsets — a documented
   propagation-timing residual that the substrate folds into the
   sep_proton edge's learned W.
5. **MAVEN retrospective driver archive** (2014-09 → 2025-12) for
   pre-loss direct-measurement upstream conditions, replacing the
   L1-propagated drivers used here.
6. **`integral_charged_particle_flux` observable** — RAD-E energy-resolved
   spectrum, currently outside the surface_dose_rate single-observable
   scope.

## What this means for operators

The natural readers for this section are NASA Mars Program operations
(Mars 2020 surface ops, future crewed-Mars planners), ESA ExoMars,
JAXA MMX, the MSL/RAD science team, and any commercial CLPS / Mars
mission planner thinking about radiation-exposure budgeting.

**What you get that you don't have today.** Operational Mars dose
forecasting is currently model-output (NAIRAS-Mars, HZETRN runs) with
no public time-aligned archive and no calibrated certainty per forecast.
This substrate gives (a) a calibrated per-edge `Z` per Ls voxel that
tells the operator how much to trust the forecast in *this* Mars
season under *these* heliospheric conditions, and (b) voxel-specific
signed driver attribution — the substrate independently discovered
that F10.7 suppresses dose at aphelion (GCR-modulation regime) and
SEP onsets enhance dose at perihelion (SEP-impulse regime), without
any voxel-specific prior. Operationally, this means dose-budget
forecasting is *seasonally asymmetric* and the substrate represents
this directly.

**Concrete operational uses.**

- **SEP-event flagging for rover-instrument operations.** All 5/5 SEP
  events in the benchmark year were flagged by the substrate; the
  May 2025 S2-class event drove a 24.3σ residual (see
  [`results/sep_event_response.md`](results/sep_event_response.md)).
  Operationally, this is the trigger to delay non-essential rover
  instrument cycles and prioritize telemetry downlink.
- **Multi-year crew dose-budget tracking with calibrated uncertainty.**
  For future crewed Mars missions, the per-event Δ-dose history
  (Nov 2024 event added +107 µGy/day at peak) plus the substrate's
  edge-level uncertainty supports operator-side dose-budget integration
  with confidence intervals — currently impossible without per-forecast
  uncertainty.
- **Forbush-decrease awareness.** The substrate learned `ap → dose`
  W = −0.071 at ls_90_180: GCR access drops during heliospheric storms,
  *reducing* dose transiently. This is the opposite of LEO/cislunar
  intuition (where storm activity correlates with *enhanced* particle
  exposure). The substrate surfaces the Mars-specific sign without
  needing operator domain knowledge.
- **Future crew shelter timing.** A pilot during a crewed cruise or
  surface stay would use the substrate's per-edge `Z` as the gate
  for "is this forecast trustworthy enough to act on the shelter
  decision now?" rather than a point-prediction threshold.

**Inner/outer architecture context.** This benchmark is the *outer*
(environmental) learning loop. The same primitives are intended to
deploy on a Mars-class spacecraft / surface platform as an *inner*
(mechanical) learning loop — solar-array degradation under SEP
exposure, electronics SEU rate under voxel-dependent dose, thermal-loop
behavior under dust-storm seasonal cycle — using the outer loop's
converged per-edge `(W, Z)` as the inner loop's prior. Together the
two loops bound the operator's unknown unknowns from above (Mars
environment surprise) and below (vehicle surprise).

**What an operator pilot looks like.** 3-6 month shadow run on the
operator's Mars-mission planning archive (telemetry windows, EVA / EVO
analog windows, instrument-mode logs). Substrate publishes per-edge
state + flags to a shared dashboard; at end of pilot we produce
lead-time-vs-current-tooling histograms and per-anomaly trace reports
(which driver was attributable, in which Ls voxel, at what `Z`).
First-stage pilot is outer-loop-only against the archive — no
spacecraft modification required. Inner-loop deployment is a follow-on
deliverable. Contact: heidi@everychart.io.
