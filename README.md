# sbir-cislunar

SBIR application scaffold: causal-discovery priors and validation pipelines for
four space-weather regimes — LEO, GEO, cislunar, and Mars surface.

## Layout

```
sbir-cislunar/
├── leo/
│   ├── prior.yaml        # LEO thermosphere density (GRACE-FO derived)
│   └── validate.yaml     # GRACE-FO pipeline endpoints + learning fixes
├── geo/
│   ├── prior.yaml        # GEO energetic particle and field environment
│   └── validate.yaml     # GOES-R SEISS + MAG direct error signals
├── cislunar/
│   ├── prior.yaml        # Cislunar radiation and particle/field environment
│   └── validate.yaml     # CRaTER + THEMIS-ARTEMIS + Chang'E 4 LND endpoints
├── mars/
│   ├── prior.yaml        # Mars surface radiation environment
│   └── validate.yaml     # MSL RAD direct error signal + MAVEN archive
└── README.md
```

## Origin

The schema patterns follow `~/nm-demo/prior.yaml` and `~/nm-demo/validate.yaml`.
The LEO pipeline structure mirrors `~/space-waze/scripts/learn-from-grace-fo.js`
(TU Delft TOLEOS GRACE-FO archive, CC BY 4.0; hourly-averaged density vs hourly
space-weather drivers from MongoDB; η(Z) dissipative learning). GEO, cislunar,
and Mars compose on the LEO precedent and on each other — each one was added
after the previous regime's pattern stabilized.

## Domains

### LEO (space-atlas precedent)

The LEO domain validates the architecture: high-cadence GRACE-FO accelerometer
data (10 s raw, hourly averaged) recovers learnable certainty values that
TLE-derived density could not. All 8 fixes from the TLE pipeline are carried
forward and listed in `leo/validate.yaml` so they don't regress.

Voxelization: latitude × local-solar-time × altitude bins, single altitude
bin (460–510 km) matching GRACE-FO orbit.

Baseline driver certainties (TLE v2 reference):
- Dst: 0.490
- IMF Bz: 0.450
- AE: 0.389
- Solar wind density: 0.196
- Solar wind speed: 0.132

LEO uses an older `sources:` taxonomy (typed measurement / derived_measurement
sources with per-source confidence). GEO, cislunar, and Mars use the newer
epistemic-kind driver-contributor pattern described below.

### GEO

Predicted observables (validated against GOES-R SEISS + MAG):
- `>2 MeV electron flux` — internal/deep-dielectric charging risk
- `>10 MeV proton flux` — SEP-onset SEE risk (log scale)
- `>50 MeV proton flux` — high-energy SEE risk (log scale)
- `1–50 keV electron flux` — surface charging risk
- `local B-field magnitude` — magnetospheric state context

Voxelization: six local-time bins (4 hours each), capturing midnight injection,
dawn-side drift, dayside compression, dusk seed populations, and pre-midnight
growth-phase sectors.

### Cislunar

Predicted observables (validated against CRaTER, THEMIS-ARTEMIS, Chang'E 4 LND):
- `cislunar_dose_rate` — TID at lunar orbit (Artemis crew, CLPS hardware)
- `cislunar_particle_field` — composite IMF + energetic particle environment
  (component observables: IMF Btot/Bz, >1 MeV integral flux, plasma electron
  density at lunar distance)
- `lunar_surface_dose` — surface dose; sparse but high-value Chang'E 4 LND
  cross-validation

Voxelization: three physics-region voxels by magnetospheric shielding regime
(inner_magnetospheric ≤10 RE, magnetotail_transit ~10–60 RE nightside,
outer_lunar_vicinity through L1/L2 ~60 RE). Subdivision criteria are declared
per region and are curiosity-trigger-driven in Phase II.

Phase I posture: **convergence regime, not measurement-gap regime.** CRaTER
(LRO, 2009–present) and THEMIS-ARTEMIS P1/P2 (2011–present) provide ~15–17
years of paired direct measurements with the same L1 drivers used by GEO/LEO.
Genuine remaining gaps (transit-volume dose resolution, high-energy SEP
spectrum, near-side vs far-side surface dose, ion composition) are listed in
`cislunar/prior.yaml`'s `measurement_gaps` block and are the explicit Phase II
CLPS/ESCAPADE engagement targets.

### Mars

Predicted observables (validated against MSL/Curiosity RAD):
- `surface_dose_rate` — TID at the surface (TID budgeting, future crew)
- `integral_charged_particle_flux` (>10 MeV/nuc) — SEE risk, biological dose
  spectrum (log scale)

Voxelization: four seasonal bins by solar longitude (Ls), 90° each. Local-time
variation at Curiosity's location is small compared to seasonal variation;
driver behavior fundamentally differs across Ls bins (atmospheric column
density, dust loading, polar CO2 cycle).

Driver-measurement context: **MAVEN lost contact December 2025** and as of
March 2026 is "likely unrecoverable" per NASA. Phase I uses propagated
heliospheric state from L1 as live driver input, with the 11-year MAVEN
archive (2014–2025) supplying retrospective driver state for storm-replay
validation. **ESCAPADE arrives at Mars September 2027** and becomes the
Phase II live-driver replacement. Verify both items against current NASA
press releases before the file leaves the repo.

## Driver-contributor buckets (GEO, cislunar, Mars)

Drivers are bucketed by **epistemic kind** of the contributing source — not by
sensor or institution. Z_0 is bucket-level and bounded ≤ 0.50 across all
contributors; certainty is earned through validation, never assigned by source
authority.

| Bucket | Z_0 | Role |
|---|---|---|
| operational_model_documentation | 0.40 | Edges from peer-validated operational model docs (AE9/AP9, HESPERIA REleASE, UMASEP, OSPREI, ENLIL) |
| literature | 0.35 | Edges from peer-reviewed heliophysics literature on driver–observable relationships |
| sme_knowledge | 0.50 | Expert priors via documents; populated through Phase I SME engagement (slot at composition time) |
| foundation_model_training | 0.30 | Edges proposed by orchestration LLM lacking direct literature or doc support; held at lowest Z_0 until validation |

SME slots carry candidate contact names in `candidate_contacts` and are
labeled by archetype, not by individual. Candidates currently named per
regime:

- **GEO** — Mark Miesch (NOAA SWPC R2O2R); Tzu-Wei Fang (NOAA SWPC, lunar
  panel chair)
- **Cislunar** — Nathan Schwadron (UNH, CRaTER lead); Vassilis Angelopoulos
  (UCLA, THEMIS-ARTEMIS PI); Rob Lillis (UC Berkeley SSL, ESCAPADE PI,
  established SWWX 2026 contact); Tzu-Wei Fang
- **Mars** — see `mars/prior.yaml`

## Cross-domain coupling

`cross_domain_links` in each `prior.yaml`'s `build:` block:

- `geo/` → `leo/` (shared L1 upstream drivers)
- `cislunar/` → `leo/`, `geo/`, `mars/` (shared L1 drivers; shared SEP source
  mechanism; magnetospheric state for the inner_magnetospheric voxel)
- `mars/` → `leo/`, `geo/` (shared SEP source mechanism; propagated L1 state)

Cross-regime edge transfer (high-certainty GEO edges → cislunar inner
magnetospheric voxel, etc.) is a Phase I success criterion.

## Schema conventions

**Cadences.** All time intervals use ISO 8601 durations (PT60S, PT5M, PT1H,
P1D, etc.). Non-time cadences use reserved string literals: `static`,
`event_driven`, `archive_pull`, `continuous`. Same convention across all
four regimes in both `prior.yaml` and `validate.yaml`.

**Scale convention.** `linear` (default, density-like response) or `log`
(SEP-driven edges spanning >2 orders of magnitude). Declared at the edge
level; observable-level `scale:` is the default for edges that don't
override.

**Endpoint role taxonomy.** Each `validate.yaml` endpoint declares its role:
`direct_error_signal`, `proxy_error_signal`, `input`, `prediction_baseline`,
`state_index`, `archived_input`, `phase_i_partnership_target`,
`phase_ii_forward_marker`.

**Reference integrity.** Every endpoint in `validate.yaml` ties to a
`target_observable` in the matching `prior.yaml`, and driver inputs feed
edges declared in that prior's `driver_contributors`. No external validator
enforces this today. If you edit one file, audit the other. A future
schema-check pass should turn this into a pre-commit hook.

**Versioning + provenance.** Each YAML carries a `version:` and `provenance:`
block at top. Provenance captures who specified the file and what evidence
underwrites it — the same shape as event metadata in the working context
pod, applied to config. This is the audit trail for partner hand-off.

**Mission-status hedges.** Where mission status is uncertain (MAVEN
recoverability, ESCAPADE arrival, IMAP launch confirmation, Lunar Trailblazer
anomaly) the YAML notes `VERIFY ... before sending` rather than presenting a
soft hedge. Confirm against current mission press releases before the file
leaves the repo.

### Learning rate is a property of the edge

The source bucket determines the **prior** — the starting Z for edges
contributed under that epistemic kind. The actual learning rate at any moment
is **η(Z)**, a sigmoid bounded between 0.10 and 0.90, computed
per-cycle from the current certainty and the observed prediction error.

The sensor doesn't have a learning rate. The edge being updated has a
learning rate, and that rate is dynamic. Bucket-level configuration sets the
prior; the global sigmoid bounds the dynamic rate.

That is the architectural commitment, and it's what makes the framework a UQ
system rather than a weighted-average filter. Static per-source rates would
be a Kalman-shaped move and would collapse the per-edge uncertainty
quantification that distinguishes the framework from one-loss ML and from
ensemble-spread approaches.

`leo/validate.yaml` mirrors the shipping `computeLearningRate` loop in
`~/space-waze/lib/dissipative-learning.js` directly and is the source of
truth for the sigmoid bounds. GEO, cislunar, and Mars carry the same
`global_sigmoid_bounds` (eta_floor 0.10, eta_ceiling 0.90) in their
`learning:` blocks.
