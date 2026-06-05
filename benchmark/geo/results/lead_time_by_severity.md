# Lead time before event onset, by flag severity tier

All SWPC operational alerts (11) onset within the 7-day GOES-19 obs window, lookback 168h. Each row shows the lead time between the framework's first flag at that tier and the event's alert onset. ε is per-voxel-observable residual-std-normalized.

Flag at tier τ = (max_Z ≥ 0.85) AND (|ε_evolved| ≥ τσ) on at least one observable.

## Per-event lead time (hours before alert onset)

| Category | Onset (UTC) | Alert tier | MILD ≥2σ | MOD ≥3σ | SEV ≥5σ | CRIT ≥10σ |
|---|---|---|---|---|---|---|
| sep_proton | 2026-06-03 01:43 | 1.00 | +98.5h | +94.2h | +77.8h | — |
| geomag_storm | 2026-06-03 14:52 | 1.00 | +111.7h | +107.4h | +91.0h | — |
| sep_proton | 2026-06-02 17:18 | 0.67 | +90.1h | +85.8h | +69.4h | — |
| flare_xclass | 2026-06-03 01:37 | 0.67 | +98.4h | +94.1h | +77.7h | — |
| flare_xclass | 2026-06-03 11:41 | 0.67 | +108.5h | +104.2h | +87.8h | — |
| geomag_storm | 2026-06-05 14:41 | 0.67 | +159.5h | +155.2h | +138.8h | — |
| geomag_storm | 2026-05-29 19:32 | 0.33 | — | — | — | — |
| geomag_storm | 2026-05-30 18:52 | 0.33 | +19.7h | +15.4h | — | — |
| geomag_storm | 2026-06-01 17:54 | 0.33 | +66.7h | +62.4h | +46.0h | — |
| geomag_storm | 2026-06-03 22:38 | 0.33 | +119.5h | +115.2h | +98.7h | — |
| geomag_storm | 2026-06-05 04:35 | 0.33 | +149.4h | +145.1h | +128.7h | — |

## Summary by tier

| Tier | n events flagged pre-onset | Min | Median | Mean | Max |
|---|---|---|---|---|---|
| MILD (≥2.0σ) | 10/11 | +19.7h | +108.5h | +102.2h | +159.5h |
| MODERATE (≥3.0σ) | 10/11 | +15.4h | +104.2h | +97.9h | +155.2h |
| SEVERE (≥5.0σ) | 9/11 | +46.0h | +87.8h | +90.6h | +138.8h |
| CRITICAL (≥10.0σ) | 0/11 | — | — | — | — |

## Window context

- Obs window: 7 days SWPC rolling (2026-05-29 to 2026-06-05)
- Total events within window: 11 (deduped within 6h × category)
- The LEO benchmark publishes this table at 240h lookback over 7+   years of GRACE-FO data (21 major storms). The 7-day GEO window is   proof-of-method; NCEI multi-year backfill is the prerequisite for   parity-scale storm coverage.
- Event onset is `Begin Time` from the alert body if present, else   issue datetime. SWPC alert tiers are 0.33 / 0.67 / 1.00 per   `sep_alerts.py` mapping of Space Weather Message Codes.
