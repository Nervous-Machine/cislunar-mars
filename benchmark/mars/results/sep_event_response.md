# Mars SEP event response

Generated 2026-06-05T19:08:26.762926+00:00
Window: 2024-11-04T06:33:46Z → 2025-11-04T00:30:55Z
Records: 30,067 · SEP events identified: 5

**Identification rule.** A SEP event is a GOES-18 SGPS >=10 MeV
integral proton flux that crosses 10 pfu and remains above 1 pfu
for at least 2 hours. Event window for response analysis is
[onset, onset + 48h] — matches the substrate's sep_proton
exponential-decay time constant.

**"Substrate flag"** = within the event window, at least one record
with max_Z ≥ 0.85 AND |ε_evolved| ≥ 2σ. "Dose response" = peak
RAD dose-rate in the window minus the in-voxel baseline median,
expressed in μGy/day.

## Per-event response

| Onset (UTC) | Peak GOES (pfu) | Voxel | Baseline (µGy/day) | Peak RAD (µGy/day) | Δ dose | Max \|ε\| (σ) | Flag? |
|---|---|---|---|---|---|---|---|
| 2024-11-21 19:00 | 82.1 | ls_270_360 | 165.2 | 272.4 | +107.1 | 9.39 | **YES** |
| 2025-01-04 22:00 | 11.2 | ls_0_90 | 167.2 | 188.5 | +21.4 | 3.49 | **YES** |
| 2025-02-25 00:00 | 23.7 | ls_0_90 | 167.2 | 198.5 | +31.3 | 3.49 | **YES** |
| 2025-03-31 15:00 | 61.7 | ls_0_90 | 167.2 | 212.5 | +45.4 | 5.98 | **YES** |
| 2025-05-31 20:00 | 441.5 | ls_0_90 | 167.2 | 196.9 | +29.7 | 24.30 | **YES** |

## Summary

- SEP events with substrate anomaly flag fired: **5 / 5**
- SEP events with positive RAD dose enhancement (Δ > +5 µGy/day): **5**
- SEP events with dose suppression (Δ < −5 µGy/day): **0**

**Interpretation.** Whether a SEP event drives a dose enhancement
or suppression at the Mars surface depends on the event's energy
spectrum and Mars atmospheric column at the time. High-energy SEPs
(>~100 MeV) drive surface enhancement; lower-energy events plus
Forbush-decrease GCR suppression can produce a net dose drop.
The substrate learns this voxel-by-voxel — see edge state for
sep_proton|ls_*_* in training_summary.md.
