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

## Result

Run on GitHub Actions on 26 November 2026, run 45835103107, from the commit that adds this file. The two log steps are kept in [data/holdout_run_45835103107.log](../data/holdout_run_45835103107.log); `python scripts/evaluate_holdout.py data/holdout_run_45835103107.log --run 45835103107` scores them and writes [data/holdout_result.json](../data/holdout_result.json).

Five of six fields completed with 25 of 25 field checks. Corona Australis stopped after 10 of 25 checks: its field runner exited before the per-injection report was written, so the strict multi-field gate reports it as incomplete. Under the rule above it does not count either way.

| Field | Noise excess | Primary rule at 2 × its limit | Sky-aware rule at 2 × its limit | Limit ratio |
|---|---|---|---|---|
| High-latitude control (south) | 1.18 | 15 of 20 | 18 of 20 | 1.10 |
| IC 348 | 1.36 | 14 of 20 | 14 of 20 | 1.15 |
| NGC 2264 | 2.30 | 0 of 20 | 3 of 20 | 1.53 |
| Chamaeleon I | 3.32 | 12 of 20 | 17 of 20 | 1.55 |
| Serpens Main | 7.95 | 1 of 20 | 15 of 20 | 5.27 |

* **P1 holds.** Spearman ρ between noise excess and primary recovery is −0.70.
* **P2 holds** in all five fields. The smallest margin is IC 348, where both rules find 14.
* **P3 holds** in the three fields with excess of 2 or more: 3 against 0, 17 against 12, 15 against 1.
* **P4 holds.** Spearman ρ between noise excess and the limit ratio is 1.00.

**Decision.** P2 and P3 hold, so the decision rule fires. From this commit the sky-aware rule is the reported rule for fields whose region noise excess is 2 or more (`reported_rule` in `research_discovery/validation/injection_recovery.py`, written into every real-field audit as `reported_rule` and `region_noise_excess`). The primary rule is still computed and reported beside it in every field.

**What this does and does not show.** Each rule is counted at twice its own stated limit. In a noisy field the sky-aware limit is brighter (5.3 times in Serpens Main), so its planted sources are brighter too. The test shows that the sky-aware limit is an honest one, which the primary limit is not in structured sky. It does not show that the sky-aware rule sees fainter sources. NGC 2264 remains hard for both rules: almost every miss there is a brighter neighbour winning the peak.
