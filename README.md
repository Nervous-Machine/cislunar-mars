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

SME engagement slots are present and named where individuals have been
identified:

- mission_telemetry → Don Kuettel (Astrobotic)
- sme_knowledge → Tzu-Wei Fang (WAM-IPE, commercial spacecraft forecasting)

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
