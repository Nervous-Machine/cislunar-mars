# Cislunar benchmark — training summary

Generated 2026-06-05T19:52:53.594324+00:00
Window: 2024-05-01T00:00:00Z → 2024-05-31T23:00:00Z
Observables: ['imf_btot_at_lunar_distance', 'imf_bz_at_lunar_distance'] (THB+THC FGM hourly mean, nT)
Voxels: 3 physics regions · Drivers: 12 · Edges: 72
Updates applied: 20,232

## Falsifiable architecture predictions

Expected sign + magnitude under known cislunar physics:
  - **imf_bz_l1 → imf_bz_at_lunar_distance**: positive, converging toward
    +1 (direct L1→lunar propagation; Bz_GSE preserved to leading order).
  - **imf_bt_l1 → imf_btot_at_lunar_distance**: positive (same reasoning).
  - **sw_dynamic_pressure → imf_btot**: positive when Moon outside
    magnetopause (compression of nearby IMF), null inside magnetopause.
    The voxel-dependent sign IS the architecture test, mirroring Mars's
    voxel-dependent sep_proton W.
  - **sep_proton → imf_btot**: near-null (SEP events arrive with their own
    IMF disturbance, but the SEP intensity is not the field-magnitude driver).
  - **null drivers** (flare_xclass, geomag_storm, kp_index when its rolling
    feed misses the window): stay near W = 0 at low Z.

| Driver | n edges | median Z | median W | W sign pattern |
|---|---|---|---|---|
| imf_bz_l1 | 6 | 0.535 | +0.0578 | ··−+++ |
| imf_bt_l1 | 6 | 0.920 | +0.0001 | ··−++· |
| sw_speed | 6 | 1.000 | +0.0048 | ··+·++ |
| sw_density | 6 | 0.800 | -0.0019 | ··+·−− |
| sw_dynamic_pressure | 6 | 0.565 | +0.0000 | ··+−+− |
| sep_proton | 6 | 1.000 | +0.0001 | ··−·++ |
| kp_index | 6 | 0.300 | +0.0000 | ······ |
| dst_index | 6 | 1.000 | +0.0005 | ··+·+− |
| f107 | 6 | 0.300 | +0.0000 | ··+−−+ |
| ap | 6 | 0.505 | +0.0000 | ··+·+· |
| flare_xclass | 6 | 0.300 | +0.0000 | ······ |
| geomag_storm | 6 | 0.300 | +0.0000 | ······ |

## Per-edge state

| Driver | Voxel | Observable | Z | W | n updates |
|---|---|---|---|---|---|
| ap | inner_magnetospheric | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| ap | inner_magnetospheric | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| ap | magnetotail_transit | imf_btot_at_lunar_distance | 0.490 | +0.2408 | 85 |
| ap | magnetotail_transit | imf_bz_at_lunar_distance | 0.520 | -0.0035 | 85 |
| ap | outer_lunar_vicinity | imf_btot_at_lunar_distance | 1.000 | +0.0985 | 923 |
| ap | outer_lunar_vicinity | imf_bz_at_lunar_distance | 1.000 | -0.0040 | 923 |
| dst_index | inner_magnetospheric | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| dst_index | inner_magnetospheric | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| dst_index | magnetotail_transit | imf_btot_at_lunar_distance | 1.000 | +0.0445 | 154 |
| dst_index | magnetotail_transit | imf_bz_at_lunar_distance | 1.000 | +0.0010 | 154 |
| dst_index | outer_lunar_vicinity | imf_btot_at_lunar_distance | 1.000 | +0.1632 | 1012 |
| dst_index | outer_lunar_vicinity | imf_bz_at_lunar_distance | 1.000 | -0.0114 | 1012 |
| f107 | inner_magnetospheric | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| f107 | inner_magnetospheric | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| f107 | magnetotail_transit | imf_btot_at_lunar_distance | 0.000 | +0.2835 | 133 |
| f107 | magnetotail_transit | imf_bz_at_lunar_distance | 0.000 | -0.1622 | 133 |
| f107 | outer_lunar_vicinity | imf_btot_at_lunar_distance | 1.000 | -0.1297 | 1211 |
| f107 | outer_lunar_vicinity | imf_bz_at_lunar_distance | 1.000 | +0.0456 | 1211 |
| flare_xclass | inner_magnetospheric | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| flare_xclass | inner_magnetospheric | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| flare_xclass | magnetotail_transit | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| flare_xclass | magnetotail_transit | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| flare_xclass | outer_lunar_vicinity | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| flare_xclass | outer_lunar_vicinity | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| geomag_storm | inner_magnetospheric | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| geomag_storm | inner_magnetospheric | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| geomag_storm | magnetotail_transit | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| geomag_storm | magnetotail_transit | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| geomag_storm | outer_lunar_vicinity | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| geomag_storm | outer_lunar_vicinity | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| imf_bt_l1 | inner_magnetospheric | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| imf_bt_l1 | inner_magnetospheric | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| imf_bt_l1 | magnetotail_transit | imf_btot_at_lunar_distance | 0.840 | -0.0796 | 104 |
| imf_bt_l1 | magnetotail_transit | imf_bz_at_lunar_distance | 1.000 | +0.0190 | 104 |
| imf_bt_l1 | outer_lunar_vicinity | imf_btot_at_lunar_distance | 1.000 | +0.5475 | 1034 |
| imf_bt_l1 | outer_lunar_vicinity | imf_bz_at_lunar_distance | 1.000 | +0.0001 | 1034 |
| imf_bz_l1 | inner_magnetospheric | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| imf_bz_l1 | inner_magnetospheric | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| imf_bz_l1 | magnetotail_transit | imf_btot_at_lunar_distance | 0.440 | -0.3502 | 154 |
| imf_bz_l1 | magnetotail_transit | imf_bz_at_lunar_distance | 0.630 | +0.3941 | 154 |
| imf_bz_l1 | outer_lunar_vicinity | imf_btot_at_lunar_distance | 0.840 | +0.1156 | 1062 |
| imf_bz_l1 | outer_lunar_vicinity | imf_bz_at_lunar_distance | 1.000 | +0.5994 | 1062 |
| kp_index | inner_magnetospheric | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| kp_index | inner_magnetospheric | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| kp_index | magnetotail_transit | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| kp_index | magnetotail_transit | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| kp_index | outer_lunar_vicinity | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| kp_index | outer_lunar_vicinity | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| sep_proton | inner_magnetospheric | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| sep_proton | inner_magnetospheric | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| sep_proton | magnetotail_transit | imf_btot_at_lunar_distance | 1.000 | -0.0054 | 93 |
| sep_proton | magnetotail_transit | imf_bz_at_lunar_distance | 1.000 | +0.0002 | 93 |
| sep_proton | outer_lunar_vicinity | imf_btot_at_lunar_distance | 1.000 | +0.0702 | 527 |
| sep_proton | outer_lunar_vicinity | imf_bz_at_lunar_distance | 1.000 | +0.0394 | 527 |
| sw_density | inner_magnetospheric | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| sw_density | inner_magnetospheric | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| sw_density | magnetotail_transit | imf_btot_at_lunar_distance | 0.990 | +0.0506 | 127 |
| sw_density | magnetotail_transit | imf_bz_at_lunar_distance | 1.000 | -0.0038 | 127 |
| sw_density | outer_lunar_vicinity | imf_btot_at_lunar_distance | 0.610 | -0.0546 | 1077 |
| sw_density | outer_lunar_vicinity | imf_bz_at_lunar_distance | 1.000 | -0.0091 | 1077 |
| sw_dynamic_pressure | inner_magnetospheric | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| sw_dynamic_pressure | inner_magnetospheric | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| sw_dynamic_pressure | magnetotail_transit | imf_btot_at_lunar_distance | 0.450 | +0.4122 | 152 |
| sw_dynamic_pressure | magnetotail_transit | imf_bz_at_lunar_distance | 0.680 | -0.2947 | 152 |
| sw_dynamic_pressure | outer_lunar_vicinity | imf_btot_at_lunar_distance | 0.800 | +0.0549 | 1056 |
| sw_dynamic_pressure | outer_lunar_vicinity | imf_bz_at_lunar_distance | 1.000 | -0.2632 | 1056 |
| sw_speed | inner_magnetospheric | imf_btot_at_lunar_distance | 0.300 | +0.0000 | 0 |
| sw_speed | inner_magnetospheric | imf_bz_at_lunar_distance | 0.300 | +0.0000 | 0 |
| sw_speed | magnetotail_transit | imf_btot_at_lunar_distance | 1.000 | +0.0096 | 136 |
| sw_speed | magnetotail_transit | imf_bz_at_lunar_distance | 1.000 | -0.0029 | 136 |
| sw_speed | outer_lunar_vicinity | imf_btot_at_lunar_distance | 1.000 | +0.0308 | 1076 |
| sw_speed | outer_lunar_vicinity | imf_bz_at_lunar_distance | 1.000 | +0.0764 | 1076 |
