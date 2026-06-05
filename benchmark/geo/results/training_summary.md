# GEO skeleton — training summary

Generated 2026-06-05T18:12:16.424472+00:00
Window: 2026-05-22T01:05:00Z → 2026-05-23T01:03:00Z  (skeleton, 1-day SWPC primary feed)
Voxels: 6 LT bins  ·  Observables: 4  ·  Drivers: 12
Edges initialized: 288  ·  Updates applied: 24,275

## Z distribution after one streaming pass

| Statistic | Value |
|---|---|
| Edges Z ≥ 0.85 (curiosity-converged) | 117 / 288 |
| Edges Z < 0.30 (below initial prior) | 20 / 288 |
| Median Z | 0.550 |
| W range (min … max) | -0.785 … +1.000 |

## Per-observable Z (median across voxels × drivers)

| Observable | n edges | median Z |
|---|---|---|
| e_flux_gt_2mev | 72 | 0.350 |
| p_flux_gt_10mev | 72 | 0.370 |
| p_flux_gt_50mev | 72 | 0.350 |
| b_field_magnitude | 72 | 0.995 |

## What this validates

- The framework primitives in `nm_primitives.py` accept GEO observations and produce non-trivial W and Z updates with no code changes — the LEO architecture transfers as designed.
- All 6 LT voxels see observations within the 24h window (no coverage gaps).
- Driver alignment from SWPC JSON works end-to-end: DSCOVR plasma/mag, GOES-XRS, GOES-EUVS (Mg II), Kp, and Dst all align by nearest-time lookup.

## Skeleton boundary (deferred)

- **Baseline = median.** Production needs AE9/AP9 climatology (additive-residual   composition) and/or rolling quiet-time baseline gated by Dst > −30.
- **Window = 1 day.** Production needs NCEI multi-year backfill for storm coverage;   Z convergence requires many more observations per edge.
- **`e_flux_hot_plasma` missing.** Primary SWPC differential-electrons feed starts   at 79 keV; the 1–50 keV MPS-LO observable needs a different endpoint.
- **Anomaly-flag analysis (precision/recall vs a comparator) requires a baseline.**   Wire AE9/AP9 next.
