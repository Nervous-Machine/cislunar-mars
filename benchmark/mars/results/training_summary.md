# Mars benchmark — training summary

Generated 2026-06-05T18:52:18.583028+00:00
Window: 2025-05-22T14:39:40Z → 2025-11-04T00:30:55Z
Observable: surface_dose_rate (**REAL** (MSL/RAD detector B, μGy/day))
Schema: `pds3_rad_rdr_v1`
Voxels: 4 Ls bins · Drivers: 6 · Edges: 24
Updates applied: 21,860

## Falsifiable architecture test

On real MSL/RAD data we expect:
  - **f107**: NEGATIVE W (solar activity suppresses GCR access to Mars)
  - **sep_proton**: POSITIVE W (SEP events drive dose spikes when active)
  - **ap, kp_index**: near null (Mars has no global B-field deflecting GCRs)
  - **flare_xclass, geomag_storm**: null over historical RAD window — their
    driver values come from SWPC alerts.json (rolling 30-day) and so are
    zero outside that window; this is a documented gap, not a bug.

| Driver | n edges | median Z | median W | W sign pattern |
|---|---|---|---|---|
| f107 | 4 | 0.650 | +0.0003 | +··· |
| ap | 4 | 0.345 | +0.0000 | +−·· |
| kp_index | 4 | 0.300 | +0.0000 | ···· |
| sep_proton | 4 | 0.300 | +0.0000 | +··· |
| flare_xclass | 4 | 0.300 | +0.0000 | ···· |
| geomag_storm | 4 | 0.300 | +0.0000 | ···· |

## Per-edge state

| Driver | Voxel | Z | W | n updates |
|---|---|---|---|---|
| ap | ls_0_90 | 0.390 | +0.0263 | 1719 |
| ap | ls_180_270 | 0.300 | +0.0000 | 0 |
| ap | ls_270_360 | 0.300 | +0.0000 | 0 |
| ap | ls_90_180 | 0.980 | -0.0831 | 10121 |
| f107 | ls_0_90 | 1.000 | +0.0867 | 947 |
| f107 | ls_180_270 | 0.300 | +0.0000 | 0 |
| f107 | ls_270_360 | 0.300 | +0.0000 | 0 |
| f107 | ls_90_180 | 1.000 | +0.0007 | 8320 |
| flare_xclass | ls_0_90 | 0.300 | +0.0000 | 0 |
| flare_xclass | ls_180_270 | 0.300 | +0.0000 | 0 |
| flare_xclass | ls_270_360 | 0.300 | +0.0000 | 0 |
| flare_xclass | ls_90_180 | 0.300 | +0.0000 | 0 |
| geomag_storm | ls_0_90 | 0.300 | +0.0000 | 0 |
| geomag_storm | ls_180_270 | 0.300 | +0.0000 | 0 |
| geomag_storm | ls_270_360 | 0.300 | +0.0000 | 0 |
| geomag_storm | ls_90_180 | 0.300 | +0.0000 | 0 |
| kp_index | ls_0_90 | 0.300 | +0.0000 | 0 |
| kp_index | ls_180_270 | 0.300 | +0.0000 | 0 |
| kp_index | ls_270_360 | 0.300 | +0.0000 | 0 |
| kp_index | ls_90_180 | 0.300 | +0.0000 | 0 |
| sep_proton | ls_0_90 | 1.000 | +0.0404 | 753 |
| sep_proton | ls_180_270 | 0.300 | +0.0000 | 0 |
| sep_proton | ls_270_360 | 0.300 | +0.0000 | 0 |
| sep_proton | ls_90_180 | 0.300 | +0.0000 | 0 |
