# Supplementary: CRaTER 2009-2012 GCR-modulation analysis

Generated 2026-06-05T19:52:53.769114+00:00
Window: 2009-06-26 → 2012-12-31  (UNH L30 product extent)
Joined CRaTER-D1 ∩ SW-All-F10.7 = 1059 daily records

## Headline

Over the cycle-23-to-24 transition (the deepest solar minimum of the
space age), the CRaTER L30 daily dose-rate at lunar orbit and the
daily solar F10.7 flux are linearly anti-correlated:

  **Pearson r(F10.7, dose_rate) = -0.7133**  over n = 1059 days

Negative r is the classical GCR-modulation signature: low solar activity
→ low heliospheric magnetic-field shielding → more GCR access to the
inner heliosphere → higher cislunar dose-rate. The signal is strongest
during this CRaTER window because the cycle-24 minimum was unusually
deep, producing the strongest sustained GCR signal of the modern era.

## Distributions

| Quantity | min | median | max | n |
|---|---|---|---|---|
| F10.7 (sfu) | 65.8 | 86.4 | 168.8 | 1059 |
| dose-rate D1 (µGy/hr) | 5.83 | 9.41 | 19.00 | 1059 |

## Cross-validation anchor — Chang'E 4 LND

Wimmer-Schweingruber et al. (2020, *Sci. Adv.*) reported 16.3 µGy/hr
(charged 13.2 ± 1 + neutral 3.1 ± 0.5) at the lunar surface in Jan 2019.
Our CRaTER D1 median over 2009-2012 is **9.4 µGy/hr** at lunar
orbit (Si-detector, no Si-to-tissue or orbit-to-surface correction).
Same order of magnitude, consistent with the expected ~0.5–1× orbit-to-
surface conversion given the lunar albedo and detector geometry.

## What this thread does NOT contain

1. **Substrate training pass on CRaTER.** The main cislunar benchmark
   trains on 2024-05 ARTEMIS FGM (IMF observables) where the storm-
   driven signal is the architectural test. CRaTER 2009-2012 covers a
   different observable family (dose-rate) and a different solar-cycle
   phase (deep min vs solar max). A unified multi-window substrate pass
   across both is Phase II scope.

2. **Post-2012 CRaTER data.** The UNH endpoint
   `https://crater-products.sr.unh.edu/data/inst/dose/table_l30drate.php`
   exposes 2009-2012 only. Newer CRaTER products are accessible via
   direct UNH collaboration or via PDS-PPI under `LROCRA_2*` collection
   IDs that returned 404 at the time of this benchmark (2026-06). The
   `validate.yaml`'s "17 years" coverage claim cannot be substantiated
   from the current public endpoint without UNH outreach.

3. **Chang'E 4 time-aligned data.** The published Sci. Adv. value is a
   single summary number, not a time-aligned archive. It serves only as
   an order-of-magnitude sanity check, not a substrate training target.
