# Lead time before storm peak, by flag severity tier

Top 21 geomagnetic storms (Dst ≤ −100 nT) in the 2018-05–2025-12 record.
Lead = hours between first flag at that severity and peak Dst, 240h (10-day) lookback. ε is the framework's prediction
residual in per-voxel sigma units.

Reproduce: `python3 analyze_lead_time.py` (set LOOKBACK to 240h).

## Per-storm lead time (hours before peak)

| Peak date | Dst | MILD ≥2σ | MOD ≥3σ | SEV ≥5σ | CRIT ≥10σ |
|---|---|---|---|---|---|
| 2024-05-11 | -406 | +236h | +223h | +74h | +5h |
| 2024-10-11 | -333 | +240h | +240h | +238h | +14h |
| 2025-11-12 | -217 | +227h | +146h | +4h | +3h |
| 2025-01-01 | -212 | +240h | +237h | +2h | — |
| 2024-08-12 | -188 | +240h | +240h | +230h | — |
| 2024-10-08 | -148 | +240h | +240h | +172h | — |
| 2025-04-16 | -138 | +201h | +174h | — | — |
| 2024-03-24 | -128 | +228h | +177h | +4h | +3h |
| 2024-09-12 | -121 | +240h | +239h | +239h | — |
| 2024-09-17 | -121 | +240h | +240h | +224h | — |
| 2025-06-01 | -119 | +184h | +69h | +69h | — |
| 2024-04-19 | -117 | +239h | +139h | — | — |
| 2025-11-06 | -116 | +239h | +180h | — | — |
| 2024-03-03 | -112 | +237h | +146h | — | — |
| 2025-06-02 | -109 | +208h | +93h | +93h | — |
| 2025-06-03 | -108 | +226h | +111h | +111h | — |
| 2024-06-28 | -107 | +240h | +240h | — | — |
| 2025-09-30 | -106 | +231h | +187h | +39h | — |
| 2024-11-09 | -101 | +240h | +240h | — | — |
| 2025-06-13 | -101 | +225h | +222h | — | — |
| 2024-08-04 | -100 | +240h | +240h | +137h | +137h |

## Summary by tier

| Tier | n storms flagged pre-peak | Min | Median | Mean | Max |
|---|---|---|---|---|---|
| MILD (≥2σ) | 21/21 | +184h | +239h | +231h | +240h |
| MODERATE (≥3σ) | 21/21 | +69h | +222h | +192h | +240h |
| SEVERE (≥5σ) | 14/21 | +2h | +111h | +117h | +239h |
| CRITICAL (≥10σ) | 5/21 | +3h | +5h | +32h | +137h |
