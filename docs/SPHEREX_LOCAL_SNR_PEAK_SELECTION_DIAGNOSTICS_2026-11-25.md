# SPHEREx M101 local-SNR versus peak-selection diagnostic

**Status:** completed diagnostic on one M101 SPHEREx DR1 D2 exposure; interpretation remains limited to this field, local PSF zone, image/mask and detection configuration.  
**Run:** [current-head combined tests/M101 workflow 45670644445](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45670644445)  
**Commit:** \`3fdfd81ddd6e5d3dc2a7a58929a58eec2c2a41f3\`  
**Artifact:** 15050046463, 91,220,621 bytes, ZIP SHA-256 \`032094d4a817960dc1780502166c9f380bb11f02251af1a7dd5acc923a55f6da\`.

## Exposure and method

- Field: M101; SPHEREx DR1 D2; observation \`2025W19_2B_0346_1\`.
- Native science MEF: 2040 × 2040; pipeline 7.0.5; exposure 113.5826 s.
- Science SHA-256: \`fba39ecd1930274aea655a744287908d6d677daeec59c8efe1ebbcffb844be90\`.
- Spectral-WCS SHA-256: \`0eb4e27f351e6161e21372818f9e811480a7ab8bab9295722f180791e151a463\`.
- Absolute-gain SHA-256: \`d0a4c3352da99326c307e4e0115285faa8cba2769ea6b57cf340d4e6fc271b37\`.
- The source-Poisson/electron conversion is still \`derived_pending_independent_review\`.

The injection report records the maximum matched-filter SNR *sample* within circular windows of 2.5 pixels and 5 pixels around each injected coordinate. The baseline and post-injection SNR maps use the same detection-validity mask. These added values **do not change** peak extraction, threshold, recovery assignment or matching.

The detector's peak extractor is separate: \`detect_peaks\` requires a sample above 5σ that also equals the local maximum in an 11 × 11 maximum-filter window (\`min_sep=5\) pixels. A high local SNR sample inside 2.5 pixels is therefore not, by itself, proof that the sample is a selected detector peak. Recovery requires a selected peak to lie within 2.5 pixels and be available for one-to-one assignment.

## Results

| Injected flux | Actual recovery | Local-window samples ≥5σ within 2.5 px | Median local max SNR | Median SNR increase | Missed injections with nearest selected peak |
|---:|---:|---:|---:|---:|---|
| 54.198 µJy | 5/20 (25%) | 19/20 | 5.959 | 0.234 | 15; nearest-peak distance 6.37–16.08 px (median 8.16 px) |
| 108.396 µJy | 14/20 (70%) | 20/20 | 8.140 | 2.642 | 6; nearest-peak distance 7.12–8.55 px (median 7.65 px) |
| 216.792 µJy | 17/20 (85%) | 20/20 | 11.150 | 5.898 | 3; nearest-peak distance 6.60–6.75 px (median 6.64 px) |

All three bins recorded zero newly unmatched peaks within the configured local PSF region. The median maximum SNR within the wider 5-pixel radius was 6.390, 8.415 and 11.150; the corresponding median SNR changes were 0.007, 2.017 and 4.744.

The Wilson 95% intervals for the primary recovery fractions remain:
- 54.198 µJy: 11.2%–46.9%.
- 108.396 µJy: 48.1%–85.5%.
- 216.792 µJy: 64.0%–94.8%.

## Interpretation boundary

This is a **diagnostic discrepancy**, not proof that the detector should have returned more detections or that the threshold should be loosened. It establishes that the largest matched-filter sample in a local window can exceed the nominal threshold even when the production peak-selection and matching pipeline does not assign a detection to that injection. The selected peaks for the missed injections are outside the matching radius.

Possible contributors requiring direct examination include the 11 × 11 local-maximum rule, nearby stronger peaks, PSF/subpixel phase, local background/noise structure, overlap between injection footprints and one-to-one peak assignment. The current report does not save a per-injection flag saying whether the local SNR maximum sample itself satisfied the exact 11 × 11 local-maximum predicate. Nor does it compare alternative minimum-separation or matching rules on independent injections.

Do not change the production detector or matching radius based on this one M101 field. A next diagnostic should save, for each injection, the nearest selected peak's score, coordinates and separation; explicitly test whether the local SNR maximum is itself selected by the production local-maximum predicate; and repeat on predeclared independent fields while preserving the current recovery rule as the primary metric.

This M101 diagnostic does not explain the Lupus III zero-recovery anomaly. The six-field SNR diagnostic rerun is tracked separately and was still in progress when this note was written.

**Scientific gates remain open:** independent gain-to-electron calibration review, externally preregistered blind four-method evaluation, source-level selection/contamination-aware YSO analysis, independent astronomical reproduction and validated scientific release.


## 26 November 2026 — isolated injected-component response

The current completed M101 validation is [workflow 45685593266](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45685593266), revision `44a96b3ae38e3a93d71687f50cb7accff5dbbeea`, artifact 15054464829, ZIP SHA-256 `64895b24b2ed030070b0474b9b000f8afa8d92d43599b90cbd1017ec3ccba46f`.

An additional source-only diagnostic now evaluates the injected component separately: `injected_img - work_image`. It applies the Jy matched filter and the same peak extractor to that difference image while retaining the **original pre-injection VARIANCE map**. This answers a narrower question than primary recovery: whether the injected component alone produces a selected local peak when the native sky/background is removed.

| Injected flux | Primary combined-image recovery | Source-only component peak-list count | Median source-only local maximum SNR |
|---:|---:|---:|---:|
| 54.198 µJy | 5/20 | 0/20 | 2.465 |
| 108.396 µJy | 14/20 | 8/20 | 4.906 |
| 216.792 µJy | 17/20 | 20/20 | 9.056 |

Median combined-image local maximum SNR values are 5.959, 8.140 and 11.150 respectively. These measures differ because they are computed on different images and noise treatments. The primary combined-image recovery and its Wilson intervals remain unchanged. Source-only counts are **not** completeness, false-positive-corrected recovery or evidence of a CHRONOS advantage.

The source-only result shows that the injection implementation can produce increasing isolated-component response on this M101 example. It does not identify the full-scene missed-peak mechanism. The earlier diagnostic question remains open: save per-injection exact full-scene local-maximum predicate outcomes and nearest selected-peak coordinates/scores, then compare on independent predeclared fields without changing the primary detector or matching rule.

The six-field source-only aggregate-gated run [45685593223](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45685593223) was still pending at this documentation refresh. No multi-field source-only conclusion is claimed.
