# Anomaly-detection result — framework flag vs. MSIS error

Generated from a single-pass prequential (predict-then-update) run over the
full GRACE-FO record, 2018-05 to 2025-12. Flag = (max_Z ≥ 0.85) AND
(|ε_framework| ≥ 2.0σ). "MSIS wrong" = |ε_MSIS| ≥ 2.0σ,
where ε_X = (pred_X − obs) / per-voxel residual std.

Reproduce: `python3 analyze_flag_vs_msis.py`

## 2×2 contingency (n = 511,794 observations)

|  | MSIS wrong | MSIS OK |
|---|---|---|
| **framework flag** | 26,652 | 2,206 |
| framework quiet | 33,202 | 449,734 |

## Operational metrics

| Metric | Value |
|---|---|
| Precision | **92.36%** |
| Recall | 44.53% |
| Base rate (P(MSIS wrong)) | 11.69% |
| Lift over base rate | **7.90×** |

Interpretation: when the framework flags an observation, MSIS is genuinely
wrong 92.4% of the time — 7.9× more often than the background
rate of MSIS errors.
