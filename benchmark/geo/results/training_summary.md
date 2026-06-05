# GEO benchmark — training summary

Generated 2026-06-05T18:42:08.338453+00:00
Window: 2026-05-29T18:30:00Z → 2026-06-05T18:27:00Z  (7-day SWPC primary feed, GOES-19)
Voxels: 6 LT bins  ·  Observables: 5  ·  Drivers: 12
Edges initialized: 360  ·  Updates applied: 175,450

## Z distribution after one streaming pass

| Statistic | Value |
|---|---|
| Edges Z ≥ 0.85 (curiosity-converged) | 208 / 360 |
| Edges Z < 0.30 (below initial prior) | 41 / 360 |
| Median Z | 1.000 |
| W range (min … max) | -0.438 … +0.829 |

## Per-observable Z (median across voxels × drivers)

| Observable | n edges | median Z |
|---|---|---|
| e_flux_gt_2mev | 72 | 1.000 |
| p_flux_gt_10mev | 72 | 1.000 |
| p_flux_gt_50mev | 72 | 1.000 |
| b_field_magnitude | 72 | 1.000 |
| e_flux_warm_plasma | 72 | 0.440 |

## Next-stage analyses

- **Tier-1 internal comparator:** `python3 analyze_internal.py` →   `results/internal_comparator.md`
- **Tier-2 external comparator (REFM):** `python3 analyze_refm.py` →   `results/tier2_refm_comparison.md`
- **Tier-3 falsifiable architecture test:** `python3 analyze_sign_convergence.py`   → `results/tier3_sign_convergence.md`
- **Lead-time analysis (LEO parity):** `python3 analyze_lead_time.py` →   `results/lead_time_by_severity.md`

## Window-coverage caveat

This summary covers a 7-day SWPC rolling window. The 5/5 observables × 6 voxels × 12 drivers = 360 edges saturate Z=1 for the drivers that have evidence in window (high-cadence DSCOVR / GOES-XRS / Dst); the SEP/CME alert-derived drivers carry decay-tail intensity only because no actively-rising SEP events occurred in the obs window (see `tier3_sign_convergence.md` for the falsifiable test result and scope notes). Multi-month NCEI backfill is the prerequisite for events-in-window evidential convergence of the SEP/CME edges.
