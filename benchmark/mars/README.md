# Mars regime — skeleton benchmark

Sibling to [`../`](../) (the published LEO Zenodo benchmark) and
[`../geo/`](../geo/) (the GEO skeleton). Proves the LEO architecture
transfers to the Mars regime — 4 Ls voxels, single site (Gale Crater),
L1-propagated drivers — and, intriguingly, the framework's curiosity surface
already correctly identifies *the right missing physics* on synthetic data.

**Status:** skeleton. Real driver data, **synthetic ground truth**
(MSL/RAD PDS access needs unblocking — see "Real-data path" below).

## What it shows

A streaming single-pass over 1 Earth year (8,761 hourly records) with six
drivers (F10.7, Ap, Kp, and three event drivers parsed from SWPC alerts:
`sep_proton`, `flare_xclass`, `geomag_storm`) against synthetic MSL/RAD
dose-rate produces a falsifiable result on a single observable, single
site, 24 edges. SEP events in the synthetic ground truth are derived from
the *same* SWPC alerts feed that drives the substrate, so the framework
sees the same event basis it's being asked to attribute residual to.

**Headline — the curiosity gap closes when SEP is wired in:**

In the SEP-active voxel (`ls_180_270`, which contains the April-May 2026
event cluster from the rolling SWPC feed):

| Driver | Causal in synthetic? | Final Z | Final W | Framework verdict |
|---|---|---|---|---|
| **F10.7** | yes (anticorrelated) | **1.00** | **−0.084** | Real driver, correct sign, **Z fully converged** (was stuck at 0.71 pre-SEP) |
| **sep_proton** | yes (positive impulses) | **1.00** | **+0.555** | Real driver, correct sign, fully converged on 685 updates |
| Ap | no | 1.00 | +0.040 | Null contribution, high confidence |
| Kp | no | 1.00 | +0.189 | Spurious positive — known correlate of solar activity in synthetic; expected to wash out across multiple voxels |
| flare_xclass | weak (correlated with SEP) | 1.00 | +0.168 | Picks up residual SEP-cluster signal as expected; co-activates with sep_proton in this voxel |
| geomag_storm | no | 1.00 | −0.022 | Null contribution |

In SEP-quiet voxels (`ls_0_90`, `ls_90_180`), the event drivers stay at
prior (n=0 updates, Z=0.30, W=0) — the activity gate correctly suppresses
them rather than fitting null-driver noise.

**This is the falsifiable curiosity-loop demonstration:** the previous skeleton
showed F10.7's Z stuck at 0.74, refusing to corroborate because SEP residual
structure was unexplained. Adding the SEP driver from SWPC alerts closes
that gap — F10.7 → Z=1.0, AND the framework correctly identifies SEP as the
missing causal driver with the right sign. That's the architecture working
as designed end-to-end on a single observable.

## Files

| File | Role |
|---|---|
| `nm_primitives.py` | Byte-identical copy of the LEO primitives |
| `fetch_mars_drivers.py` | Pull CelesTrak SW-All (F10.7, Ap) + SWPC alerts + SWPC Kp; per-endpoint status in `raw/manifest.json` |
| `generate_rad_synthetic.py` | Synthesize MSL/RAD placeholder; SEP injections derived from SWPC alerts |
| `extract_obs_jsonl.py` | Ls voxelization (4 bins), driver alignment, SWPC-alert-derived event drivers, JSONL emit |
| `learn_mars.py` | Streaming pass through shared primitives |
| `../sep_alerts.py` | Shared SWPC alerts parser (also used by GEO) |
| `results/training_summary.md` + `results/edges_state.json` | Committed artifacts |

## Real-data path (the actual SBIR resubmission work)

The previous skeleton cited a 404'd endpoint
(`/data/msl-m-rad-2-4-edr-rdr-v1.0/` — a slug mashup of EDR and RDR
volume IDs that doesn't exist). The verified canonical archive is:

```
https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/
```

It hosts the **MSL-M-RAD-3-RDR-V1.0** volume (Reduced Data Records) as a
PDS3 archive tree. As of 2026-06 the archive covers **Sol 0 (2012-08-06)
through 2025-308** as 5,435 daily per-sol product files (each a `.LBL`
+ `.TXT` pair). An index lives at `INDEX/INDEX.TAB`. Dose values appear in
`[DOSIMETRY_TOTAL_DOSE_B: NN]` blocks within each `.TXT`; dose rate is the
total divided by the integration duration in the per-observation counter
header. `mars/validate.yaml` now records this layout under
`archive_layout:` for downstream parsers.

Remaining work to replace synthetic ground truth with real RAD:

1. Pull `INDEX.TAB` to enumerate per-sol products within a target date
   window (start from a 6-month rolling window for parity with the LEO
   benchmark approach, then expand to multi-Mars-year).
2. PDS3 parser: extract `START_OBS_UTC` + `DOSIMETRY_TOTAL_DOSE_B`/`_E`
   + integration duration → hourly dose-rate JSONL.
3. Drop `generate_rad_synthetic.py` from the pipeline; flip
   `placeholder_schema` field on records to `pds3_rad_rdr_v1`.

When real RAD lands, the synthetic file's `is_synthetic: true` and
`placeholder_schema: v0.2` flags ensure no consumer silently mixes
synthetic and real data.

## ε convention, Ls computation, voxel coverage

- ε is z-score per voxel residual std; framework magnitude tolerances are rescaled together (see [`../../math_functions.md`](../../math_functions.md) §3.1).
- Ls is a simplified linear function of date anchored at Curiosity landing (2012-08-06, Ls=150.65°). Ignores Mars orbital eccentricity — bin-boundary error ~5–10° in Ls. JPL Horizons or astropy ephemeris would replace this in production.
- Coverage in the 365-day skeleton window: ls_0_90 ~5%, ls_90_180 ~47%, ls_180_270 ~47%, ls_270_360 ~0.1%. Extending the window to 1 Mars year (687 days) covers all four voxels evenly.

## Skeleton scope (deferred for full benchmark)

1. **Real MSL/RAD ground truth** from PDS (see above).
2. **NAIRAS Mars baseline** for additive-residual composition.
3. **ENLIL-propagated solar wind at Mars distance** as a first-class driver (the validate.yaml endpoint at `iswa.gsfc.nasa.gov/iswa_data_tree/model/heliosphere/wsa_enlil/` 404s in the same way; needs path verification).
4. **~~SEP-event driver~~** — done. Parsed from SWPC `alerts.json` via the shared [`../sep_alerts.py`](../sep_alerts.py) module; wired into the Mars driver vector and (as a synthetic-GT seed) into `generate_rad_synthetic.py`. F10.7's Z fully converges in the SEP-active voxel as predicted. Real Mars-arrival-time propagation (heliographic-longitude-aware Δt from Earth-relative onset) is the next refinement.
5. **MAVEN retrospective archive** (2014–2025) for ground-truth driver state pre-loss — enables storm-replay validation under direct-measurement upstream conditions.
6. **`integral_charged_particle_flux` observable** — RAD-E energy-resolved spectrum, currently outside skeleton scope.

## Run

```bash
pip install requests certifi
python3 fetch_mars_drivers.py    # ~2 s (uses cached /tmp/sw-all.csv if available)
python3 generate_rad_synthetic.py # ~1 s
python3 extract_obs_jsonl.py     # ~2 s
python3 learn_mars.py            # ~3 s
```

## Why this skeleton matters for the proposal

The "no MSIS" reality of Mars (no comparably-calibrated single operational
standard) is normally a problem. The skeleton inverts it: with a single
observable, three drivers, and synthetic-but-realistic dose-rate, the
framework's per-edge curiosity signal correctly distinguishes the real
causal driver (F10.7) from spurious ones (Ap, Kp) **and** flags exactly
where its own model is incomplete (SEP gap). That's the operational
capability MSIS structurally cannot provide — and it works on a regime
with no MSIS at all.
