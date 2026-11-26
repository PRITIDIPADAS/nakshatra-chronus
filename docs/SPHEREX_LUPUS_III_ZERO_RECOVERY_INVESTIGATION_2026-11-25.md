# SPHEREx Lupus III zero-recovery anomaly — evidence note

**Status: OPEN — CAUSE NOT DETERMINED**  
**Prepared:** 25 November 2026  
**Scope:** one SPHEREx DR1 D2 Level-2 exposure, one 100-pixel-radius local injection region, 60 synthetic source injections into a real image. This is an exploratory diagnostic, not a discovery or a validated completeness measurement.

## Exact science exposure and integrity checks

| Item | Value |
|---|---|
| Region | Lupus III |
| Observation ID | \`2025W32_1A_0663_1\` |
| Release / detector | SPHEREx DR1 / D2 |
| Observation time | 2025-08-07 06:00:39.781 UTC |
| MJD-OBS | 60894.250460428 |
| Exposure time | 113.5826 s |
| Science MEF | Native 2040 × 2040 Level-2 |
| IMAGE BUNIT | \`MJy / sr\` |
| Pipeline | 7.0.5 |
| Native science SHA-256 | \`272df790de462a6f6cae8cfe6c92fe7a3a34294069234b96532a2fc8e233d570\` |
| Spectral-WCS SHA-256 | \`0eb4e27f351e6161e21372818f9e811480a7ab8bab9295722f180791e151a463\` |
| Absolute-gain SHA-256 | \`d0a4c3352da99326c307e4e0115285faa8cba2769ea6b57cf340d4e6fc271b37\` |
| Solid-angle map SHA-256 | \`231bcdab0aa31d0ee9c9349b10e6c871070bf3ed860b7dc799745c0f9d1c8bc0\` |

The native MEF audit reported \`STRUCTURE_AND_COMPATIBILITY_CHECKS_PASS\`; the calibration compatibility matrix reported \`compatible\`. Required IMAGE, FLAGS, VARIANCE, ZODI and WCS-WAVE structures and the 2040 × 2040 native grid were present. The separate spectral-WCS audit reported CWAVE/CBAND in micrometres with valid fraction 1.0. The detector-matched solid-angle map was full-grid and positive. The exact spectral-WCS and absolute-gain provenance links and archived checksums passed.

The variance plane's finite-positive fraction was **0.9999223856**; **323** samples were non-positive or non-finite. The flags array was aligned and integer-valued (\`int32\`); its documented Level-2 flag dictionary was retained. The injection evaluation excluded the configured flag-bit mask \`167620\`. These structural and provenance checks do not establish that the local noise model, ePSF, or detection response is scientifically adequate.

## Injection protocol and measured result

- Local PSF reference position: \`(x=1019.25, y=1020.75)\`.
- Injection region radius: 100 native pixels.
- PSF/template stamp: 11 × 11 pixels; reported unit sum approximately 1.0.
- Detection threshold: 5σ.
- Matching radius: 2.5 native pixels.
- Baseline source-exclusion radius: 7 pixels; exclusion enabled.
- Background model subtracted: true.
- Position-dependent pixel solid-angle response: enabled in the matched-filter template.
- Random seed: 20261125.
- Injections: 20 at each of 0.5×, 1× and 2× the local nominal 5σ reference.

| Flux bin | Integrated flux | Expected source electrons | Realized source electrons | Recovered |
|---|---:|---:|---:|---:|
| 0.5× local reference | 105.579 µJy | 2,438.79 | 2,464 | **0/20** |
| 1× local reference | 211.158 µJy | 4,905.88 | 4,944 | **0/20** |
| 2× local reference | 422.317 µJy | 9,734.91 | 9,768 | **0/20** |

For each bin, the two-sided Wilson 95% interval for the measured recovery fraction is **0.0%–16.1%**. No median astrometric offset is reported because no injection was recovered. The full exposure had 258 baseline detections. For the 60 injected positions, the nearest baseline-detection distance ranged from **6.37 to 11.32 pixels** (median **7.75 pixels**); none fell within the 2.5-pixel match radius. The post-injection report recorded zero new unmatched peaks inside the evaluated local PSF region.

The added source-Poisson expected/realized electron totals above show that the configured source-Poisson step ran and that non-zero noise realizations were produced. This does **not** independently validate the absolute-gain-to-electron calibration: that derivation remains \`derived_pending_independent_review\`.

## What is established — and what is not

Established for this single exposure:
- Native science/calibration files and byte hashes are retained in the workflow artifact.
- The native MEF structure, wavelength maps, solid-angle map and archive compatibility/provenance checks passed.
- The injection routine ran 60 trials across three declared flux bins, added source-Poisson variance, and recorded zero recovered sources.
- The zero-recovery result is adverse evidence for this local field/position/PSF/mask/threshold combination and is preserved rather than pooled away.

Not established:
- The root cause of the zero recoveries.
- A field-wide completeness curve or universal 5σ operating point.
- Whether a different local background, ePSF model, flag policy, source-confusion treatment or detection implementation would change the result.
- Instrument-calibration approval of the gain-to-electron conversion.
- A CHRONOS advantage over any comparator, a blind-benchmark result, or a population inference.

## Required diagnostic work before interpreting sensitivity

1. Inspect the native science IMAGE, VARIANCE, FLAGS, ZODI and EPSF at the exact 60 injection coordinates and surrounding area. Compare local background, RMS, mask fraction, effective PSF and source crowding with fields that recovered sources.
2. Recompute the local matched-filter response using the original native FITS bytes and verify the injection and detection templates use the same pixel-grid, ePSF convention, solid-angle treatment and subpixel phase.
3. Save the score/SNR at every known injection coordinate, not only the nearest baseline-detection distance. Separate “no peak above threshold” from “peak found but outside match radius.”
4. Repeat with independent seeds and predeclared injection positions, while keeping the field-level result visible. Do not tune the threshold on this field and then reuse the same injections as confirmation.
5. Obtain independent review of the gain-to-electron and source-Poisson variance convention before treating the high-bin injection as a calibrated sensitivity measurement.

The current six-region workflow artifact contains the report JSONs and per-field runner logs, not the native Lupus science MEF bytes. An attempt to retrieve the exact public IRSA MEF in this environment failed at network name resolution; therefore no claim of raw-pixel visual inspection is made here. The exact URI and checksum above allow an independent analyst to retrieve and inspect the original archive file.

## Reproducibility

- Strict six-field workflow: [45639895735](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45639895735).
- Strict aggregate report SHA-256: \`26e237fec2b0e1f5571dd5e527c009a5a2d3de44186c4a240bf63ac4b9bb64e6\`.
- Artifact ID: \`15036382990\`; ZIP SHA-256: \`09978b42c6d626f65fe385d7d004c4a5d120ac7302ae06d8831f231e3dc65a35\`.
- Machine-readable field report: \`fields/Lupus_III/data/real_field_audit_summary.json\`.
- Native audit: \`fields/Lupus_III/data/native_mef_audit.json\`.
- Injection report: \`fields/Lupus_III/data/calibrated_injection/calibrated_jy_injection_recovery.json\`.

**Disposition: retain the Lupus III zero-recovery anomaly as an unresolved negative result. Do not remove the field from the aggregate, call it a calibration success, or generalise it to the whole detector.**


## 26 November 2026 — M101 source-only response follow-up

The completed M101 run [45685593266](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45685593266) (revision `44a96b3ae38e3a93d71687f50cb7accff5dbbeea`) adds a diagnostic of the injected source component, separate from the full native sky. It uses the image difference `post-injection IMAGE − original IMAGE`, the position-dependent Jy matched filter and the original pre-injection VARIANCE map.

The component-only peak-list diagnostic returned 0/20, 8/20 and 20/20 at the three test fluxes. The primary full-scene recovery remains 5/20, 14/20 and 17/20. These different results are **not** a Lupus III diagnosis: the M101 source-only experiment cannot explain the Lupus 0/20 result.

A new six-field source-only aggregate-gated run was still pending at documentation time ([45685593223](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45685593223)); the previous completed six-field artifact predates this diagnostic. No source-only outcome is assigned to Lupus III here.

The root cause remains open. The archive metadata audit and compatible native MEF/calibration structure do not rule out a local ePSF/position-phase mismatch, background residual, flag footprint effects, noise covariance, crowding/blending, source-only/combined-scene peak selection differences, or an implementation/configuration error. These remain hypotheses only. The exact native Lupus image and the original 60 coordinate-level records must be examined together before selecting among them. The absolute-gain/electron convention also remains pending independent instrument review.


## Latest independent six-field rerun — 26 November 2026

The same predeclared Lupus III exposure was included in the strict aggregate workflow [#37 / run 45749547766](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45749547766), artifact 15085687674. The native science file SHA-256 remains `272df790de462a6f6cae8cfe6c92fe7a3a34294069234b96532a2fc8e233d570`; observation ID remains `2025W32_1A_0663_1`. The aggregate report returned 6/6 predeclared fields and 25/25 machine checks per field.

Lupus III again recovered **0/20 at 0.5×, 0/20 at 1× and 0/20 at 2×** its local nominal 5σ reference (105.579, 211.158 and 422.317 µJy). The report digest is `031aacb4dd64345794d246883be141b935689f0de69affaf9965c39b512b60a9`, and its embedded SHA-256 was independently recomputed from the artifact JSON.

This rerun reproduces the same adverse outcome in the same single exposure and local injection region. It does not identify the cause, establish a field-wide completeness limit or validate the gain-to-electron calibration. The absolute-gain conversion remains pending independent instrument review; raw-pixel diagnostic inspection, injection-position score audit and independent-seed tests remain required.
