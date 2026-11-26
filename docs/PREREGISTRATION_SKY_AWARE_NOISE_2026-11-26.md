# Preregistration: the sky-aware noise rule on held-out fields

Written and committed on 26 November 2026, before any of the fields below was downloaded. The commit that adds this file is the record of what was predicted.

## Why

On the six pilot fields, Lupus III recovered 0 of 60 planted sources. The diagnostic in `data/injection_diagnostics.json` traced this to structured nebular sky: in the injection region the pixel scatter was 5.5 times the pipeline noise. A sky-aware variant (32-pixel mesh background, variance scaled by the empirical scatter, sources planted at the 5σ limit this honest noise implies) was built on those same six fields. Because it was built on them, those fields cannot test it.

## Held-out fields

Chamaeleon I (167.0, −77.3), Serpens Main (277.45, +1.25), Corona Australis (285.4, −36.95), NGC 2264 (100.24, +9.9), IC 348 (56.13, +32.16), and a southern high-latitude control (30.0, −60.0). One native DR1 D2 exposure each, chosen by the same code path as the pilot (`run_multifield_jy_pilot.py --field-set holdout`). No setting of the variant changes.

## Predictions

* **P1.** Across the fields that complete, primary recovery at 2 × 5σ falls as the region noise excess rises: Spearman ρ < 0.
* **P2.** In every completed field, the sky-aware variant at 2 × its honest limit finds at least as many of 20 sources as the primary rule at 2 × its limit, minus 2 (allowing for counting noise).
* **P3.** In every completed field with noise excess ≥ 2, the variant at 2 × its honest limit finds strictly more than the primary rule at 2 × its limit.
* **P4.** The variant's sensitivity ratio (honest 5σ over pipeline 5σ) rises with the noise excess: Spearman ρ > 0.8.

## Decision rule

If P2 holds in every completed field and P3 holds in every field it applies to, the sky-aware rule becomes the reported rule for fields with noise excess ≥ 2, and the primary rule stays reported beside it. If either fails, the variant stays secondary and the failure is reported here. Fields that fail to download are reported as incomplete and do not count either way. P1 and P4 are reported whatever they show.
