# SPHEREx six-region calibrated-Jy exploratory pilot — 25 November 2026

**Scientific status:** completed exploratory six-field evaluation after post-hoc strict revalidation. This is a detector-calibrated injection/recovery study, not the CHRONOS four-method blind benchmark and not a population result.

## Reproducibility record

- Real-data workflow: [GitHub Actions run 45624461435](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45624461435).
- Workflow revision: \`df1952857cae4ea4c501d12\`.
- Workflow conclusion: \`success\`; six predeclared regions completed sequentially.
- Raw report artifact: ID \`15029628060\`, name \`spherex-multifield-jy-pilot\`, size 138,494 bytes.
- GitHub artifact SHA-256: \`250f3bfdbd3fe81b1d87aa00cd54389377f7c147639c408604cde672d2c31cfb\`.
- Strict post-hoc revalidation report SHA-256: \`a94c010a3d4cfd6d678d93fe32e598218a77d53f13acf61c57d010059ebae299\`.
- Strict validator: \`research_discovery/spherex/run_multifield_jy_pilot.py\`, blob SHA \`f346d00c7ce2b500a406e68c6ea2a20093dac3a9\`.
- Companion current-branch test run [45634302992](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45634302992) passed **297 tests with 2 warnings**, including both JavaScript syntax checks. The real M101 audit also passed in that run.

The raw six-field workflow completed before the stricter validator revision was added. Its six archived field summaries were therefore independently re-evaluated after the fact using the stricter current field checks. That revalidation is preserved separately; it must not be described as a fresh full-field workflow execution on the later commit.

## Strict revalidation result

All six raw field summaries passed all 20 per-field eligibility checks and the additional integrity checks. The report confirms:

- Six completed fields, zero incomplete fields.
- Six distinct science observation IDs and six distinct native science-file SHA-256 values.
- Each field is DR1, detector D2, native Level-2, in \`MJy / sr\`.
- Each native MEF audit reports compatible structure/calibration.
- Each Spectral-WCS and absolute-gain file has the exact science-plane \`spherex.provenance_input\` relation.
- The live provenance relation contains the expected plane IDs and native URIs; the gain archive MD5 and local SHA-256 checks pass.
- The same D2 absolute-gain map has 4,161,600 pixels; 175 invalid/non-positive pixels remain masked, not filled. The per-pixel conversion-map valid fraction is 0.9999579489 (99.9958%).
- Each field has three flux bins with 20 injections per bin. Expected source electrons, realized electrons and added IMAGE-domain source-Poisson variance are recorded and positive in all bins.
- The electron conversion remains \`derived_pending_independent_review\`. The status is explicitly pending, and the reports do not claim human calibration sign-off.

The absolute-gain product is used to derive electrons per Level-2 IMAGE unit; the already calibrated Level-2 science image is not gain-corrected a second time. The detector solid-angle map is used as a supplemental detector-matched product and is not claimed to be a direct pipeline-provenance child.

## Per-field results

Each flux triplet is field-specific: low, nominal local 5-sigma reference, and high (approximately 0.5×, 1× and 2× that field's local reference). Each bin contains 20 simulated source injections.

| Region | Science observation ID | Local 5σ reference | Low / nominal / high injected flux (µJy) | Recovered at low / nominal / high |
|---|---|---:|---:|---:|
| Taurus / Auriga | \`2025W35_1A_0331_1\` | 178.374 | 89.187 / 178.374 / 356.747 | 3/20 / 3/20 / 8/20 |
| Perseus / NGC 1333 | \`2025W34_1B_0227_1\` | 161.588 | 80.794 / 161.588 / 323.176 | 3/20 / 5/20 / 12/20 |
| Orion A | \`2025W37_1A_0365_1\` | 159.317 | 79.658 / 159.317 / 318.633 | 3/20 / 5/20 / 11/20 |
| Rho Ophiuchi | \`2025W31_2A_0170_1\` | 204.960 | 102.480 / 204.960 / 409.921 | 2/20 / 4/20 / 9/20 |
| Lupus III | \`2025W32_1A_0663_1\` | 211.158 | 105.579 / 211.158 / 422.317 | **0/20 / 0/20 / 0/20** |
| High-latitude control | \`2025W20_1C_0491_1\` | 114.063 | 57.032 / 114.063 / 228.126 | 6/20 / 13/20 / 17/20 |

The per-bin Wilson 95% intervals, expected-electron totals, realized-electron totals, variance increments, observation/file hashes and complete field checks are in the machine-readable strict revalidation JSON linked with this report.

**Lupus III is an important anomaly.** No injected source was recovered in any of its three bins, including the bin at twice the local nominal 5-sigma reference. The provenance and data-integrity checks pass, but this outcome is not evidence of good sensitivity. It requires targeted investigation of that field's background, mask, PSF/matched-filter response and local detection behavior before interpreting the multi-field completeness pattern. It is retained in the aggregate and is not silently excluded.

## Interpretation and limits

This is a small exploratory matched-filter injection/recovery study: one D2 exposure in each of six predeclared regions, a local PSF region per field and 60 injected source instances per field. Source locations, injection levels and random seed were available to the evaluator. It is **not blind**, not a comparison of SNR-only versus CHRONOS P/D/A versus instrument forensics versus Sky–Detector Twin, not a survey-wide completeness curve, and not evidence of a CHRONOS performance advantage.

The field-specific 5-sigma references differ; the flux bins must not be pooled as though they shared one universal sensitivity threshold. The Lupus III zero-recovery result also rules out summarizing this pilot with a single flattering average.

Still outstanding: independent instrument/calibration review of the gain-to-electron conversion; a custodian-controlled four-method blind benchmark on genuine held-out SPHEREx fields; a selection-function- and contamination-aware YSO population analysis; independent astronomical reproduction/review; and a validated scientific release. None of those gates is passed by this pilot.
