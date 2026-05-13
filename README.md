# sbir-cislunar

SBIR application scaffold: causal-discovery priors and validation pipelines for
cislunar and LEO space-weather domains.

## Layout

```
sbir-cislunar/
├── cislunar/
│   ├── prior.yaml        # 8-bucket source taxonomy + causal hypotheses
│   └── validate.yaml     # endpoints, η(Z) learning, validation steps
├── leo/
│   ├── prior.yaml        # LEO thermosphere density (GRACE-FO derived)
│   └── validate.yaml     # GRACE-FO pipeline endpoints + learning fixes
└── README.md
```

## Origin

The schema patterns follow `~/nm-demo/prior.yaml` and `~/nm-demo/validate.yaml`.
The LEO pipeline structure mirrors `~/space-waze/scripts/learn-from-grace-fo.js`
(TU Delft TOLEOS GRACE-FO archive, CC BY 4.0; hourly-averaged density vs hourly
space-weather drivers from MongoDB; η(Z) dissipative learning).

## Source buckets (cislunar)

Each bucket sets a starting certainty Z and a learning-rate class η. The
intent is that operational data anchors the model, research data calibrates
it, and lower-Z buckets (third-party models, SME priors) are learned against
ground truth.

| Bucket | Z_start | η class | Role |
|---|---|---|---|
| operational_instruments | 0.80 | low | Real-time wired feeds (SWPC, GOES, SDO, ACE, DSCOVR) |
| research_historical | 0.65 | low-medium | Van Allen Probes, MMS, ARTEMIS, Arase — calibration only |
| planned_instruments | 0.30 | medium | GDC, IMAP, Lunar Trailblazer, Artemis support — schema-ready |
| commercial_partnerships | 0.45 | medium | Spire, HawkEye 360, Planet, GeoOptics, Muon Space, BlackSky |
| third_party_research | 0.30 | high | CCMC, NAIRAS, IRENE/AE9-AP9, university feeds |
| mission_telemetry | 0.50 | medium | CLPS (IM-1/2/3), Artemis, commercial lunar relay |
| sme_knowledge | 0.35 | high | WAM-IPE prior; expert document → LLM-extracted hypotheses |
| restricted | n/a | n/a | ITAR / classified / proprietary — schema-shaped, content-blank |

SME engagement slots are labeled by archetype, with candidate individuals
named in slot notes only:

- mission_telemetry → CLPS provider SME (candidate: Don Kuettel, Intuitive Machines)
- sme_knowledge → WAM-IPE / commercial spacecraft forecasting SME (candidate: Tzu-Wei Fang)

## LEO (space-atlas)

The LEO domain validates the architecture: high-cadence GRACE-FO accelerometer
data (10 s raw, hourly averaged) recovers learnable certainty values that
TLE-derived density could not. All 8 fixes from the TLE pipeline are carried
forward and listed in `leo/validate.yaml` so they don't regress.

Baseline driver certainties (TLE v2 reference):
- Dst: 0.490
- IMF Bz: 0.450
- AE: 0.389
- Solar wind density: 0.196
- Solar wind speed: 0.132

## Cross-domain coupling

`cislunar/prior.yaml` links to `leo/prior.yaml` because LEO density informs
transit-phase priors for cislunar missions. The shared coupling edge is
`geomagnetic_storm → thermosphere_density_at_leo`.

## Schema conventions

**Cadences.** All time intervals use ISO 8601 durations (PT60S, PT5M, PT1H,
P1D, etc.). Non-time cadences use reserved string literals: `static`,
`event_driven`, `archive_pull`, `continuous`. The same convention applies in
both `prior.yaml` and `validate.yaml` across both domains.

**Reference integrity.** Every endpoint in `validate.yaml` carries `source:`
and `bucket:` fields that must resolve to entries in the matching
`prior.yaml`:

- `endpoint.source` → `prior.sources.<bucket>.providers[].id`
- `endpoint.bucket` → top-level key under `prior.sources`

No external validator enforces this today. If you edit one file, audit the
other. A future schema-check pass should turn this into a pre-commit hook.

**Versioning + provenance.** Each YAML carries a `version:` and
`provenance:` block at top. Provenance captures who specified the file and
what evidence underwrites it — the same shape as event metadata in the
working context pod, applied to config. This is the audit trail for partner
hand-off.

**Mission-status hedges.** Where mission status is uncertain (Lunar
Trailblazer mission anomaly, IMAP launch date confirmation) the YAML notes
`VERIFY ... before sending` rather than presenting a soft hedge. Confirm
against current mission press releases before the file leaves the repo.

**eta_max ceilings.** `cislunar/validate.yaml` carries directional per-bucket
eta_max values flagged `RECONCILE` — they MUST be matched against the
shipping `computeLearningRate` behavior in
`~/space-waze/lib/dissipative-learning.js` and the published GRACE-FO /
quantum benchmark runs before external distribution. `leo/validate.yaml` is
the source of truth (it mirrors the shipping loop).

**SME slot phrasing.** Slots are labeled by archetype, not by individual,
with candidate individuals named only in `notes`. The working pod still
has the Kuettel ↔ panelist-quote attribution at Z=0.60 (hypothesis only) —
do not present it as confirmed in any artifact named at him.
