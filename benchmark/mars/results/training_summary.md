# Mars skeleton — training summary

Generated 2026-06-05T18:10:49.379203+00:00
Window: 2025-05-22T00:00:00Z → 2026-05-22T00:00:00Z (1 Earth year)
Observable: surface_dose_rate (**SYNTHETIC PLACEHOLDER** — see README)
Voxels: 4 Ls bins · Drivers: 6 · Edges: 24
Updates applied: 27,671

## Falsifiable test outcome

Synthetic ground truth was generated with F10.7-anticorrelated baseline + SEP
spikes. F10.7 has a real causal relationship with the synthetic observable;
Ap and Kp do not. We expect F10.7 edges to converge with negative W and
Ap/Kp edges to stay near prior.

| Driver | n edges | median Z | median W | W sign pattern |
|---|---|---|---|---|
| f107 | 4 | 0.455 | -0.047 | ·+−− |
| ap | 4 | 0.940 | -0.030 | ·−·− |
| kp_index | 4 | 0.780 | -0.052 | ·−+− |
| sep_proton | 4 | 0.320 | +0.000 | ··+· |
| flare_xclass | 4 | 0.300 | +0.000 | ··+· |
| geomag_storm | 4 | 0.320 | -0.004 | ···· |

## Per-edge state

| Driver | Voxel | Z | W | n updates |
|---|---|---|---|---|
| ap | ls_0_90 | 0.880 | -0.0013 | 511 |
| ap | ls_180_270 | 1.000 | +0.0396 | 4098 |
| ap | ls_270_360 | 0.300 | -0.0612 | 6 |
| ap | ls_90_180 | 1.000 | -0.0595 | 4122 |
| f107 | ls_0_90 | 0.510 | -0.0102 | 511 |
| f107 | ls_180_270 | 1.000 | -0.0844 | 4122 |
| f107 | ls_270_360 | 0.300 | -0.2145 | 6 |
| f107 | ls_90_180 | 0.400 | +0.0770 | 4122 |
| flare_xclass | ls_0_90 | 0.300 | +0.0000 | 0 |
| flare_xclass | ls_180_270 | 1.000 | +0.1676 | 94 |
| flare_xclass | ls_270_360 | 0.300 | +0.0000 | 0 |
| flare_xclass | ls_90_180 | 0.300 | +0.0000 | 0 |
| geomag_storm | ls_0_90 | 0.300 | +0.0000 | 0 |
| geomag_storm | ls_180_270 | 1.000 | -0.0216 | 621 |
| geomag_storm | ls_270_360 | 0.340 | -0.0076 | 6 |
| geomag_storm | ls_90_180 | 0.300 | +0.0000 | 0 |
| kp_index | ls_0_90 | 0.630 | -0.0025 | 511 |
| kp_index | ls_180_270 | 1.000 | +0.1892 | 4122 |
| kp_index | ls_270_360 | 0.300 | -0.1018 | 6 |
| kp_index | ls_90_180 | 0.930 | -0.1926 | 4122 |
| sep_proton | ls_0_90 | 0.300 | +0.0000 | 0 |
| sep_proton | ls_180_270 | 1.000 | +0.5548 | 685 |
| sep_proton | ls_270_360 | 0.340 | -0.0123 | 6 |
| sep_proton | ls_90_180 | 0.300 | +0.0000 | 0 |
