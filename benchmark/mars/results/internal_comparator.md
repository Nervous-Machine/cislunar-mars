# Tier-1 internal comparator — prior-W vs evolved-W (prequential)

Generated 2026-06-05T19:08:25.875915+00:00
Window: 2024-11-04T06:33:46Z → 2025-11-04T00:30:55Z
Records: 30,067 · Voxels: 4 · Drivers: 6

**What this measures.** A single streaming pass over the obs records;
at each step we compute two predictions BEFORE applying the learning
update: `p_prior` (uses W=0 for all edges — the prior-only baseline)
and `p_evolved` (uses the substrate's current W state). ε is
(prediction − observation) / per-voxel residual std. Statistics are
computed across the prequential trajectory; lower |ε| under evolved-W
is the substrate beating its own prior on held-out residual.

Why this is tier-1: the LEO benchmark uses additive-residual
composition on MSIS as its prediction baseline. The Mars regime has
no time-aligned operational MSIS-equivalent (see README §
External-comparator gap), so the substrate's prior-W prediction is
the only honest self-comparator we can produce today.

## Per-voxel ε statistics

| Voxel | n | mean(\|ε_prior\|) | mean(\|ε_evolved\|) | residual reduction |
|---|---|---|---|---|
| ls_0_90 | 12,019 | 0.7270 | 0.6822 | +6.16% |
| ls_90_180 | 12,035 | 0.7202 | 0.8897 | -23.54% |
| **overall** | **24,054** | **0.7236** | **0.7860** | **-8.63%** |

Median variant (robust to Forbush-event outliers):

| Voxel | n | median(\|ε_prior\|) | median(\|ε_evolved\|) | residual reduction |
|---|---|---|---|---|
| ls_0_90 | 12,019 | 0.5636 | 0.5317 | +5.65% |
| ls_90_180 | 12,035 | 0.5678 | 0.5558 | +2.12% |
| **overall** | **24,054** | **0.5663** | **0.5427** | **+4.17%** |

## Anomaly-flag precision (self-referenced contingency)

Flag definition: (max_Z ≥ 0.85) AND (|ε_evolved| ≥ 2σ). "Anomaly" =
|ε_prior| ≥ 2σ — i.e., a record where the prior-only baseline would
have substantial residual error. The contingency table answers:
*when the substrate flags a record, is the prior actually wrong?*

|  | prior anom (|ε_prior|≥2σ) | prior OK |
|---|---|---|
| **substrate flag** | 618 | 159 |
| substrate quiet | 306 | 22,971 |

| Metric | Value |
|---|---|
| Precision | 79.54% |
| Recall | 66.88% |
| Base rate | 3.84% |
| Lift over base rate | 20.71× |

Interpretation: when the substrate flags a record as anomalous (high
Z + large evolved-W residual), the prior-only baseline is also
substantially wrong this fraction of the time. Lift is the precision
divided by the base rate of records where the prior is wrong; >1× means
the substrate's flags are non-random.
