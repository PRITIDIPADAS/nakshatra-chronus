# SPHEREx six-region calibrated-Jy exploratory pilot — 25 November 2026

**Scientific status:** completed exploratory six-field evaluation on real SPHEREx DR1 D2 Level-2 exposures. This is not a blind benchmark, not a four-method comparison, and not a population result. The absolute-gain electron conversion remains pending independent instrument/calibration review.

## Reproducibility record

- GitHub Actions: [run 45637115746](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45637115746), workflow run #17.
- Workflow revision: `b286210ea64af43c282e44dfa6939757dd2642c8`.
- Conclusion: success; all six predeclared D2 fields completed sequentially.
- Artifact ID `15034299164`, 138,776 bytes; ZIP SHA-256 `96ff0c2025d098ebb3d63d64bd1361aabdeb2c4830920227a53ce53364c01afb`.
- Machine report `multi_field_jy_pilot_summary.json`, 88,114 bytes; raw SHA-256 `81e8badae3e8ecb4bf0ed02d627e28f7a864fb203aa814bd3d237bc7339131e3`.
- Embedded canonical report SHA-256 `cfd0ce32a6ce5f8206a64ebb6927cc186784259af2914b846bd633d5a74e626e`; independently recomputed and matched.
- Six of six predeclared fields completed, zero incomplete. All six passed all 20 runner eligibility checks (120/120 true); six distinct observation IDs and six distinct science-file SHA-256 values were recorded.

## Calibration and source-Poisson implementation

Each field has direct live-IRSA `spherex.provenance_input` links from its science plane to detector-matched Spectral-WCS and absolute-gain calibration products. The absolute-gain matrix SHA-256 is `d0a4c3352da99326c307e4e0115285faa8cba2769ea6b57cf340d4e6fc271b37`. The pixel conversion uses exposure time divided by the absolute-gain matrix; Poisson draws and their IMAGE-domain variance are applied only to injected sources. The existing Level-2 science pixels are not gain-corrected a second time. The 2040 × 2040 conversion map has valid fraction 0.9999579489; all 175 invalid/non-positive gain pixels remain masked, not interpolated.

**Calibration boundary:** all six conversions are `derived_pending_independent_review`, with independent review pending and `independent_human_reviewed=false`. Software provenance checks are not human instrument-calibration sign-off.

## Per-field injection/recovery

Each exposure has 20 injections at each of three levels, approximately 0.5×, 1× and 2× that field's own local nominal 5σ reference. Fluxes are integrated microJy; intervals are 95% Wilson intervals.

| Region | Observation ID | Science SHA-256 | Local 5σ (µJy) | Injected low / nominal / high (µJy) | Recovered low / nominal / high |
|---|---|---|---:|---:|---|
| Taurus / Auriga | `2025W35_1A_0331_1` | `068e1d328be3c6b5d992bbdcee9e72d8b58e744a3ce64c53524bc99513d6d76f` | 178.374 | 89.187 / 178.374 / 356.747 | 3/20 / 3/20 / 8/20 |
| Perseus / NGC 1333 | `2025W34_1B_0227_1` | `cb8342a9a7d9c3deb967fc5081b621a4e6beef35f884d37f75e363af07a7b638` | 161.588 | 80.794 / 161.588 / 323.176 | 3/20 / 5/20 / 12/20 |
| Orion A | `2025W37_1A_0365_1` | `897087b899986bc94bf57626006f02bf9a01b8e047c2f3a4bd5eb82b3f89c636` | 159.317 | 79.658 / 159.317 / 318.633 | 3/20 / 5/20 / 11/20 |
| Rho Ophiuchi | `2025W31_2A_0170_1` | `9029725265a97d26e1f1e90989a96add168a64542a57560d80c11d8c46309547` | 204.960 | 102.480 / 204.960 / 409.921 | 2/20 / 4/20 / 9/20 |
| Lupus III | `2025W32_1A_0663_1` | `272df790de462a6f6cae8cfe6c92fe7a3a34294069234b96532a2fc8e233d570` | 211.158 | 105.579 / 211.158 / 422.317 | **0/20 / 0/20 / 0/20** |
| High-latitude control | `2025W20_1C_0491_1` | `7aa8b711e109e85220c9a0bd22aaa2b4df956cdecb214f5dffaee2b09874da90` | 114.063 | 57.032 / 114.063 / 228.126 | 6/20 / 13/20 / 17/20 |

| Region | Low-bin completeness (95% Wilson) | Nominal-bin completeness (95% Wilson) | High-bin completeness (95% Wilson) |
|---|---:|---:|---:|
| Taurus / Auriga | 15% (5.2–36.0%) | 15% (5.2–36.0%) | 40% (21.9–61.3%) |
| Perseus / NGC 1333 | 15% (5.2–36.0%) | 25% (11.2–46.9%) | 60% (38.7–78.1%) |
| Orion A | 15% (5.2–36.0%) | 25% (11.2–46.9%) | 55% (34.2–74.2%) |
| Rho Ophiuchi | 10% (2.8–30.1%) | 20% (8.1–41.6%) | 45% (25.8–65.8%) |
| Lupus III | 0% (0–16.1%) | 0% (0–16.1%) | 0% (0–16.1%) |
| High-latitude control | 30% (14.5–51.9%) | 65% (43.3–81.9%) | 85% (64.0–94.8%) |

## Interpretation and limits

Lupus III's 0/20 result in every bin, including twice its local nominal 5σ reference, is a material adverse result. It remains included; it must not be averaged away or selectively removed. Investigate local background, masks, ePSF/matched-filter response and detector behaviour before any sensitivity conclusion.

The flux references differ by field and cannot be pooled into a universal sensitivity curve. Each result is local to one detector region and one exposure. Injection truth and seed were visible; this is not blind. The four CHRONOS methods were not run, so no comparative performance advantage is established.

## Acceptance gates

| Gate | Status |
|---|---|
| Six-field exploratory calibrated-Jy workflow | **Completed; 6/6 fields passed all 20 checks** |
| Independent gain-to-electron calibration review | **Pending** |
| Lupus III anomaly investigation | **Pending** |
| Custodian-controlled four-baseline blind benchmark on held-out SPHEREx fields | **Not satisfied** |
| Selection-function- and contamination-aware YSO population analysis | **Not satisfied** |
| Independent astronomical reproduction / researcher review | **Not satisfied** |
| Validated scientific release | **Not satisfied** |

## 26 November 2026 — current multi-field diagnostic gate status

The original six-field real-data pilot remains the primary recovery reference documented above. The most recently completed pilot artifact [45674421060](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45674421060) contains six completed predeclared D2 fields, 360 primary injection rows and 360 bound local-SNR diagnostic rows. It flags Lupus III as zero recovery at all three flux levels. This artifact was generated before the new source-only component diagnostics and therefore does not satisfy the newer source-only aggregate gate.

The newer source-only pilot [45685593223](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45685593223) had no job result or artifact available at the time of this addendum. The earlier attempt [45685127482](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45685127482) was based on revision `930885e89`, before the latest aggregate-gate enforcement. Neither can be promoted to a verified six-region source-only result unless the complete current report passes the exact six-field, per-injection, science/gain identity, report-hash and aggregate validators.

The source-only diagnostic uses the post-injection-minus-baseline image and original VARIANCE map. It is a secondary experiment and does not replace primary combined-scene recovery. Lupus III remains an unresolved adverse result: 0/20 at 0.5×, 1× and 2× its local reference in the previously completed six-field run. No threshold/match-radius relaxation or field removal is justified by the current evidence.


## Latest strict six-field rerun — workflow #37 (26 November 2026)

The latest six-field real-data execution is [workflow #37 / run 45749547766](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45749547766), on code revision `02c072ec58d5b216b8a6883ed6e2d18915823f90`.

- All six predeclared regions were returned exactly once: six requested, six returned, six completed, zero incomplete.
- The exact field-name/role manifest passed; observation IDs and native science SHA-256 values are unique.
- Each of the six field records passed 25/25 machine eligibility checks (150/150 true).
- Artifact 15085687674 is 219,691 bytes; ZIP SHA-256: `4c34a822761d8ea57b4109ff67f3318d014259874fa835a399c69fb6bf7e4017`.
- Aggregate report SHA-256: `031aacb4dd64345794d246883be141b935689f0de69affaf9965c39b512b60a9`. Recomputed from the downloaded JSON after removing its embedded digest; exact match.

| Region | Observation ID | Local 5σ reference (µJy) | 0.5× / 1× / 2× recoveries |
|---|---|---:|---:|
| Taurus / Auriga | `2025W35_1A_0331_1` | 178.374 | 3/20 / 3/20 / 8/20 |
| Perseus / NGC 1333 | `2025W34_1B_0227_1` | 161.588 | 3/20 / 5/20 / 12/20 |
| Orion A | `2025W37_1A_0365_1` | 159.317 | 3/20 / 5/20 / 11/20 |
| Rho Ophiuchi | `2025W31_2A_0170_1` | 204.960 | 2/20 / 4/20 / 9/20 |
| Lupus III | `2025W32_1A_0663_1` | 211.158 | **0/20 / 0/20 / 0/20** |
| High-latitude comparison | `2025W20_1C_0491_1` | 114.063 | 6/20 / 13/20 / 17/20 |

The low/nominal/high fluxes are field-specific multiples of each local 5σ reference; they are not common absolute flux bins and must not be pooled as if they were.

Every field report continues to mark the gain-derived electron conversion as pending independent review and `independent_human_reviewed=false`. The 25/25 checks validate the automated file/provenance/runner contract, not physical calibration. The workflow remains non-blind, uses one exposure per field, and does not execute the four CHRONOS comparison baselines. Lupus III remains an unresolved 0/20 adverse result and has not been removed or averaged away.
