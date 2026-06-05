# Tier-1 internal comparator — prior-W vs evolved-W (prequential)

Generated 2026-06-05T19:52:53.594762+00:00
Window: 2024-05-01T00:00:00Z → 2024-05-31T23:00:00Z
Records: 2,976 · Voxels: 3 · Observables: 2 · Drivers: 12

**What this measures.** Single streaming pass; at each record we
compute two predictions before applying the learning update:
`p_prior` (uses W=0 everywhere → prediction is the per-voxel-observable
median) and `p_evolved` (uses the substrate's current W state with
additive residual composition). ε = (prediction − observation) / std.
Statistics are computed across the prequential trajectory.

Why this is tier-1: the cislunar regime has no operational SWPC-equivalent
for IMF at lunar distance (REFM exists for ≥2 MeV electrons at GEO;
MSIS exists for LEO density; no public-archive operational baseline
exists for Bz at lunar distance). Tier-2 is the substrate-vs-naive-L1
comparator in `analyze_l1_propagation.py`; tier-3 is the falsifiable
architecture test in `analyze_sign_convergence.py`.

## Per-voxel × observable ε statistics

| Voxel | Observable | n | mean(\|ε_prior\|) | mean(\|ε_evolved\|) | residual reduction |
|---|---|---|---|---|---|
| inner_magnetospheric | imf_btot_at_lunar_distance | 0 | — | — | (empty in window) |
| inner_magnetospheric | imf_bz_at_lunar_distance | 0 | — | — | (empty in window) |
| magnetotail_transit | imf_btot_at_lunar_distance | 202 | 0.8212 | 0.6991 | +14.87% |
| magnetotail_transit | imf_bz_at_lunar_distance | 202 | 0.7186 | 0.6532 | +9.10% |
| outer_lunar_vicinity | imf_btot_at_lunar_distance | 988 | 0.5521 | 1.1275 | -104.21% |
| outer_lunar_vicinity | imf_bz_at_lunar_distance | 989 | 0.6365 | 1.1460 | -80.05% |
| **overall** |  | **2,381** | **0.6241** | **1.0586** | **-69.62%** |

Median variant (robust to event-driven outliers):

| Voxel | Observable | n | median(\|ε_prior\|) | median(\|ε_evolved\|) | residual reduction |
|---|---|---|---|---|---|
| magnetotail_transit | imf_btot_at_lunar_distance | 202 | 0.6893 | 0.5490 | +20.36% |
| magnetotail_transit | imf_bz_at_lunar_distance | 202 | 0.5432 | 0.4825 | +11.18% |
| outer_lunar_vicinity | imf_btot_at_lunar_distance | 988 | 0.3373 | 0.1753 | +48.02% |
| outer_lunar_vicinity | imf_bz_at_lunar_distance | 989 | 0.4321 | 0.1953 | +54.81% |
| **overall** |  | **2,381** | **0.4119** | **0.2169** | **+47.35%** |

## Anomaly-flag precision (self-referenced contingency)

Flag: (max_Z ≥ 0.85) AND (|ε_evolved| ≥ 2σ). "Anomaly" = |ε_prior| ≥ 2σ.
Answers: *when the substrate flags an IMF record, was the prior-only baseline*
*also substantially wrong?*

|  | prior anom (|ε_prior|≥2σ) | prior OK |
|---|---|---|
| **substrate flag** | 63 | 63 |
| substrate quiet | 44 | 2,211 |

| Metric | Value |
|---|---|
| Precision | 50.00% |
| Recall | 58.88% |
| Base rate | 4.49% |
| Lift over base rate | 11.13× |

Interpretation: precision is *the fraction of substrate flags that*
*correspond to a real prior-baseline anomaly*; lift > 1× means the
substrate's anomaly flags are non-random under self-reference.
