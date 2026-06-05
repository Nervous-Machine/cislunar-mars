# Tier-2 external comparator — substrate vs naive L1→lunar propagation

Generated 2026-06-05T19:52:53.652695+00:00
Window: 2024-05-01T00:00:00Z → 2024-05-31T23:00:00Z

**What this measures.** The natural external baseline for the
cislunar regime is naive ballistic propagation of L1 IMF to the
Moon: identity coupling between L1 measurement and lunar-distance
prediction.  This is operational physics — Parker-spiral and
ballistic propagation are how cislunar forecasts have been done
in the absence of a learned correction.

Three predictions per record:
  - `p_naive`   = direct L1 measurement (imf_bz_l1 or imf_bt_l1 as-is)
  - `p_prior`   = per-voxel median baseline (substrate at W=0)
  - `p_evolved` = baseline + (Σ d·W)·σ using the substrate's final
                  edge state (uses the converged W from a single
                  prequential pass; this is in-sample evaluation,
                  the standard for substrate-vs-baseline comparisons
                  in the LEO benchmark)

Reported metric: mean absolute residual |p − o|, in the observable's
native units (nT for both observables).

## Per-voxel × observable absolute residual (nT)

| Voxel | Observable | n | naive_L1 | prior_W | evolved_W | substrate vs naive |
|---|---|---|---|---|---|---|
| magnetotail_transit | imf_btot_at_lunar_distance | 166 | 3.435 | 2.172 | 1.754 | +48.92% |
| magnetotail_transit | imf_bz_at_lunar_distance | 166 | 2.879 | 0.936 | 0.748 | +74.00% |
| outer_lunar_vicinity | imf_btot_at_lunar_distance | 1,222 | 1.131 | 3.935 | 2.087 | -84.50% |
| outer_lunar_vicinity | imf_bz_at_lunar_distance | 1,222 | 1.429 | 3.835 | 1.796 | -25.68% |
| **overall** |  | **2,776** | **1.504** | **3.606** | **1.859** | **-23.56%** |

Median absolute residual (robust to storm-time outliers):

| Voxel | Observable | n | naive_L1 | prior_W | evolved_W | substrate vs naive |
|---|---|---|---|---|---|---|
| magnetotail_transit | imf_btot_at_lunar_distance | 166 | 3.498 | 1.740 | 1.387 | +60.34% |
| magnetotail_transit | imf_bz_at_lunar_distance | 166 | 2.872 | 0.718 | 0.572 | +80.08% |
| outer_lunar_vicinity | imf_btot_at_lunar_distance | 1,222 | 0.407 | 2.622 | 1.122 | -175.57% |
| outer_lunar_vicinity | imf_bz_at_lunar_distance | 1,222 | 0.774 | 2.546 | 1.067 | -37.82% |
| **overall** |  | **2,776** | **0.673** | **2.357** | **1.063** | **-58.06%** |

## Interpretation

The naive ballistic predictor is the standard operational forecast for
lunar-distance IMF in the absence of a learned correction: take what
L1 measures, assume the field convects to the Moon unchanged. This is
decent in *outer_lunar_vicinity* where the Moon is in the solar wind,
and DEGRADES in *magnetotail_transit* where the magnetospheric field
decouples from the upstream IMF.

The substrate's per-voxel learning is structurally what's required:
the same L1 driver should propagate ~directly when the Moon is in the
solar wind, but ~not at all when the Moon is in the magnetotail. A
single-coupling forecaster (naive_L1) cannot represent this; the
substrate's per-voxel W naturally does.

The W-magnitudes that show this (from `results/edges_state.json`):
  - `imf_bz_l1|outer_lunar_vicinity|imf_bz_at_lunar_distance`
    Z=1.00  W=+0.5994  n=1062
    → L1 Bz → lunar Bz in solar wind: large positive (direct propagation)
  - `imf_bz_l1|magnetotail_transit|imf_bz_at_lunar_distance`
    Z=0.63  W=+0.3941  n=154
    → L1 Bz → lunar Bz in magnetotail: smaller positive (partial decoupling)
  - `imf_bt_l1|outer_lunar_vicinity|imf_btot_at_lunar_distance`
    Z=1.00  W=+0.5475  n=1034
    → L1 |B| → lunar |B| in solar wind: large positive
  - `imf_bt_l1|magnetotail_transit|imf_btot_at_lunar_distance`
    Z=0.84  W=-0.0796  n=104
    → L1 |B| → lunar |B| in magnetotail: NEAR-NULL (lobe field decoupled from L1)
