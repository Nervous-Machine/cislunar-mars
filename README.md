# sbir-cislunar

Source-listing configs for four space-weather regimes — LEO, GEO, cislunar,
and Mars surface. Each regime has a `prior.yaml` (sources for prior
provisioning) and a `validate.yaml` (endpoints for validation / error
signals). An agent (Claude or other) reads these YAMLs and calls MCP-server
tools (in `~/NM-learning-loop/`) to compose the prior, build the validation
pipeline, build the learning function, and package for deployment. The
framework math lives in the MCP-server code; these files are just inert
inputs to it.

## Layout

```
sbir-cislunar/
├── leo/
│   ├── prior.yaml          # LEO thermosphere density (GRACE-FO derived)
│   └── validate.yaml       # GRACE-FO + weather endpoints
├── geo/
│   ├── prior.yaml          # GEO energetic particle and field environment
│   └── validate.yaml       # GOES-R SEISS + MAG endpoints
├── cislunar/
│   ├── prior.yaml          # Cislunar radiation and particle/field environment
│   └── validate.yaml       # CRaTER + THEMIS-ARTEMIS + Chang'E 4 LND endpoints
├── mars/
│   ├── prior.yaml          # Mars surface radiation environment
│   └── validate.yaml       # MSL RAD endpoints + MAVEN archive
├── benchmark/              # Reproducible LEO demonstration (GRACE-FO vs MSIS)
└── README.md
```

## What each file is for

**`prior.yaml`** — sources for prior provisioning. External data, model
documentation, and expert priors that Claude can draw on to inform a regime's
prior when its own training-data inference isn't enough. Includes regions /
voxelization, the predicted observables the prior is built for, driver
contributors (bucketed by epistemic kind), state indices, and notes about
measurement gaps.

**`validate.yaml`** — endpoints for validation and error signals (mostly
sensors). Where to fetch the data, at what cadence, in what format, and what
role each endpoint plays.

Neither file describes the learning math, the validation pipeline, what
counts as convergence, or any framework-internal tuning. Those live in the
MCP-server code and are accessed only through MCP tool calls. If something
in a YAML implies the framework's internal behavior, it's drift.

## Benchmark

[`benchmark/`](benchmark/) is the reproducible LEO-regime demonstration cited
by the SBIR: the substrate vs. NRLMSISE-00 on 7.5 years of GRACE-FO ground
truth. It is self-contained (framework math mirrored in `nm_primitives.py`,
no MCP server required) and regenerates its headline results — anomaly-flag
precision 92.36% / 7.90× lift, and storm lead-time-by-severity — from public
archives. Large intermediate data is not committed; small result tables are.
See [`benchmark/README.md`](benchmark/README.md).

## Domains

### LEO (space-atlas precedent)

Validates the architecture: high-cadence GRACE-FO accelerometer data (10 s
raw, hourly averaged) recovers learnable certainty values that TLE-derived
density could not.

Voxelization: latitude × local-solar-time × altitude bins, single altitude
bin (460–510 km) matching GRACE-FO orbit.

Baseline driver certainties (TLE v2 reference):
- Dst: 0.490
- IMF Bz: 0.450
- AE: 0.389
- Solar wind density: 0.196
- Solar wind speed: 0.132

LEO uses an older `sources:` taxonomy (typed `measurement` / `derived_measurement`
sources). GEO, cislunar, and Mars use the newer epistemic-kind
driver-contributor pattern.

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
`cislunar/prior.yaml`'s `measurement_gaps` block.

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
archive (2014–2025) for retrospective driver state. **ESCAPADE arrives at
Mars September 2027** and becomes the Phase II live-driver replacement.

## Driver-contributor buckets (GEO, cislunar, Mars)

Drivers are bucketed by **epistemic kind** of the contributing source — not
by sensor or institution. Z_0 is bucket-level and bounded ≤ 0.50; certainty
is earned through validation, never assigned by source authority.

| Bucket | Z_0 | Role |
|---|---|---|
| operational_model_documentation | 0.40 | Edges from peer-validated operational model docs (AE9/AP9, HESPERIA REleASE, UMASEP, OSPREI, ENLIL) |
| literature | 0.35 | Edges from peer-reviewed heliophysics literature |
| sme_knowledge | 0.50 | Expert priors via documents; populated through Phase I SME engagement |
| foundation_model_training | 0.30 | Edges proposed by orchestration LLM lacking direct literature or doc support; held at lowest Z_0 until validation |

## Schema conventions

**Cadences.** ISO 8601 durations (PT60S, PT5M, PT1H, P1D, etc.). Non-time
cadences use reserved literals: `static`, `event_driven`, `archive_pull`,
`continuous`.

**Scale.** `linear` (default) or `log` (SEP-driven edges spanning >2 orders
of magnitude). Declared at the edge level; observable-level `scale:` is the
default for edges that don't override.

**Endpoint roles** (in `validate.yaml`): `direct_error_signal`,
`proxy_error_signal`, `input`, `prediction_baseline`, `state_index`,
`archived_input`, `phase_i_partnership_target`, `phase_ii_forward_marker`.

**Versioning + provenance.** Each YAML carries a `version:` and `provenance:`
block at top. Provenance captures who specified the file and what evidence
underwrites it — the audit trail for partner hand-off.


