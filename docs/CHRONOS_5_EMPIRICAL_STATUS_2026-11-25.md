# CHRONOS 5 empirical status — 25 November 2026

This note records the real archive work completed on the \`chronos-5-causal-sky-twin\` branch. It deliberately separates file-backed validation and exploratory measurements from discovery, blind-benchmark and release claims.

## 1. Calibration-compatible real-data evaluation

**Status: completed for one SPHEREx DR1 exposure; not a population-level or blind benchmark.**

- Field/product: M101, SPHEREx detector D2, DR1 Level-2.
- Science MEF: native 2040 × 2040 pixels, IMAGE in MJy/sr, exposure time 113.5826 s.
- Science processing version/date: 7.0.5 / 2026-198.
- The exact science plane was resolved through the IRSA TAP \`spherex.artifact\` and \`spherex.plane\` records. Its pipeline lineage was checked through \`spherex.provenance_input\`.
- The separate spectral-WCS calibration product was directly linked to that science plane by the archive foreign-key relationship. Its CWAVE and CBAND maps are native 2040 × 2040 arrays in micrometres.
- The detector solid-angle map is a DR1 D2 2040 × 2040 auxiliary map in arcsec², selected at the same calibration date. It is explicitly recorded as supplemental and **not** asserted to be a direct \`provenance_input\` child.
- The absolute-gain product is a direct provenance-linked D2 input. Its 175 invalid pixels remain masked; they are not interpolated or filled.
- Science and calibration native files were checked against archive checksums and local SHA-256 digests. The file-backed compatibility audit returned \`compatible\` for this single science/calibration set.

The science and spectral-WCS pipeline version/date labels differ. Compatibility was not inferred from matching version strings or dates: the direct archive input relation and exact file-backed audit were used.

## 2. Single-exposure calibrated Jy injection/recovery

**Status: completed as an exploratory M101 D2 pilot.**

The real Level-2 image, delivered variance, flags, position-specific ePSF and pixel solid-angle map were used. The source-Poisson noise term was derived from the provenance-linked absolute-gain product, with invalid gain pixels excluded.

Local nominal 5-sigma sensitivity: **1.0839603767 × 10⁻⁴ Jy**.

| Injected integrated flux | Recovered | Observed recovery fraction | Wilson 95% interval |
|---|---:|---:|---:|
| 0.5 × local 5σ | 5 / 20 | 25% | 11.2–46.9% |
| 1.0 × local 5σ | 14 / 20 | 70% | 48.1–85.5% |
| 2.0 × local 5σ | 17 / 20 | 85% | 64.0–94.8% |

No newly unmatched peaks were reported inside the evaluated local PSF region in these injections. There were 246 baseline detections in the evaluated image.

**Interpretation boundary:** this is one exposure, one detector and one local PSF region. It is conditional on the supplied mask, variance, background and injection setup. It is not an all-sky completeness curve, a transient discovery, a YSO identification or a four-method CHRONOS comparison. The absolute-gain-derived electron conversion is labelled \`derived_pending_independent_review\`; the pilot is exploratory until a human instrument/calibration reviewer signs off that derivation.

Primary Actions record: [M101 real-data audit run 45623016499](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45623016499).

## 3. SPLICES and DR1 population reconnaissance

**Status: completed descriptive six-region reconnaissance with geometric archive-footprint linkage; no YSO population result.** The latest completed live-data workflow is [#38 / run 45648715196](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648715196). It returned 16,663 catalogue rows, 2,421 candidate rows, 1,540 region-centre Level-2 rows and 6,214 DR1/QR3 SIAv2 Level-2 image products. Local spherical matching associated all 2,421 candidate sources in the five star-forming regions with at least one returned product footprint, yielding 924,443 geometric source–product pairs. All four SIAv2 collections completed below caps and all returned product polygons were valid. The 32 All-Sky Cube metadata rows are complete for the six searched region cones, not the whole sky. Exact hashes and per-region counts are in [the current reconnaissance report](SPHEREX_SPLICES_DR1_RECON_2026-11-25.md).

The source matcher uses SIAv2 s_region polygon metadata; it does not use the failed direct SPLICES/spherex.artifact TAP join. These associations establish only coordinate-in-footprint overlap. They do not establish extracted source flux, spectral quality, usable epoch cadence or validated light curves. Catalogue label overlap remains descriptive: 931 ML-only rows are follow-up candidates, not confirmed YSOs. No completeness-, contamination- or selection-corrected population analysis or discovery is claimed.

## 4. Six-region calibrated Jy pilot

**Status: completed exploratory six-field evaluation; independent calibration review pending.** Workflow [#17 / run 45637115746](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45637115746) completed all six predeclared D2 fields. All six fields passed their 20 machine eligibility checks; the report contains six distinct science observation IDs and six distinct native science hashes. The artifact and embedded report digest are recorded in [the six-region pilot report](SPHEREX_MULTIFIELD_JY_REVALIDATION_2026-11-25.md).

Results differ materially by field. Most importantly, Lupus III recovered 0/20 at all three local flux levels, including twice its nominal local 5-sigma reference. All six gain-derived electron-conversion records remain derived_pending_independent_review. The pilot is non-blind, uses one exposure per field and does not compare the four CHRONOS baselines.

## 4a. Current repair-branch CI and M101 evidence — 25 November 2026

The latest combined test/M101 workflow is [#896 / run 45648715416](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648715416), on commit cb66210536713df52e5530a05185d6fe1353c6e3. It passed **316 tests with 12 warnings**; both JavaScript syntax checks passed. Its M101 real-field job completed archive retrieval, native compatibility validation, machine-readable audit and artifact upload. Artifact 15039337449 is 91,213,914 bytes with ZIP SHA-256 e584b2255bc398d7abbee6c0294408c11498d7878cdea50226b37faa5afeaddd. The field-summary SHA-256 is a9162173aac9202da85da4d77d2a7fc536086fd40c360143e0742be1f8f29382; the source-Poisson injection report SHA-256 is 18463d1e709da27fb58f43b136a2e44534281aa51fe0ad6c36aaf59868cbb9eb. M101 recovery remains 5/20, 14/20 and 17/20 at 54.198, 108.396 and 216.792 µJy. The gain-to-electron conversion remains pending independent human review.

The test-only companion [#897 / run 45648724365](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648724365) also passed **316 tests with 7 warnings** and both JavaScript syntax checks.

## 5. Acceptance gates

| Requested empirical gate | Status | Evidence / blocker |
|---|---|---|
| Calibration-compatible real-data evaluation | **Completed for one M101 D2 exposure** | File-backed DR1 MEF, exact WCS/gain provenance, supplemental area map, checksum audit and calibrated Jy injections |
| Blind benchmark on actual held-out SPHEREx fields | **Not satisfied** | No independently controlled custodian, signed attestation, sealed real held-out truth and complete four-method run |
| Four-method comparison on identical blind data | **Not satisfied** | The M101 test uses one matched-filter SNR baseline; detector outputs for all four methods have not been supplied and scored on held-out fields |
| Population-level YSO discovery | **Not satisfied** | SPLICES/DR1 reconnaissance only; no independent candidate confirmation or selection-function-corrected population inference |
| Independent astronomical reproduction / researcher review | **Not satisfied** | No external astronomer has reviewed or reproduced the M101 analysis |
| Validated scientific release | **Not satisfied — keep release gate closed** | Blind benchmark, population inference and independent review/reproduction remain open |

## 6. What must happen next

1. Investigate the Lupus III zero-recovery result and obtain independent instrument/calibration review of the pending gain-to-electron conversion, retaining all six fields.
2. Have an independent astronomer/instrument scientist review the Level-2 variance/solid-angle/ePSF conventions and the pending absolute-gain electron conversion.
3. Appoint an independent custodian outside the analysis team. That custodian must hold the blind key and encrypted real truth data, register the protocol before unblinding, freeze the exact code/data digests and sign the custody record.
4. Run SNR-only, CHRONOS P/D/A, instrument forensics and Sky–Detector Twin on identical held-out real fields with a preregistered operating point. Preserve per-field results, null controls, ablations and uncertainty intervals.
5. Conduct a source-level YSO study with a defined selection function and contamination model, independently reviewed candidate identifications and control-field analysis. Catalogue ML labels alone are not discovery evidence.
6. Only after independent reproduction/review and all empirical gates pass, prepare a scientific release and paper.

No blind benchmark, new YSO discovery, external review or validated scientific release is claimed by this report.


## Latest strict six-region and M101 evidence — 25 November 2026

This section supersedes the older six-field post-hoc-revalidation-only wording above where the same field set is concerned.

The dedicated strict six-region runner completed on [workflow #19 / run 45639895735](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45639895735). It retrieved all six predeclared D2 fields sequentially and the final aggregate validator reported:
- six requested, six returned, six completed and zero incomplete fields;
- exact expected field manifest, roles and field names;
- all per-field eligibility checks true;
- unique native science observation IDs and unique science-file SHA-256 values;
- per-field audit-summary SHA-256 values valid; and
- aggregate JSON SHA-256 recomputed and matched: `26e237fec2b0e1f5571dd5e527c009a5a2d3de44186c4a240bf63ac4b9bb64e6`.

Artifact 15036382990 is 138,771 bytes with ZIP SHA-256 `09978b42c6d626f65fe385d7d004c4a5d120ac7302ae06d8831f231e3dc65a35`. The results are the same field-specific recovery counts documented in [the six-region report](SPHEREX_MULTIFIELD_JY_REVALIDATION_2026-11-25.md), including Lupus III's 0/20 at all three bins. The run completes the **exploratory multi-field injection/recovery** gate, not instrument calibration approval, a blind benchmark or all-sky completeness.

The latest completed combined test/M101 run available for this refresh is [45652295910](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45652295910), commit `f9f315bf35fcb0a46a69cc30b7c4a434ed165e1d`: 316 tests passed with 7 warnings, both JavaScript checks passed, and M101 native retrieval, compatibility/provenance audit, evidence validator and artifact upload passed. Artifact 15041901578 has SHA-256 `7f0451a82e979d1abd3c77e9a433f44fefd3e51a09470fd18a99a8f0e7b20e4f`. The test-only companion [45652301839](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45652301839) passed 316 tests with 12 warnings.

The population software has since been hardened so a source must have feature and both continuum sidebands in the same repeated epochs; duplicate/reused source IDs across fields are rejected; and null counts cannot be used without an explicit science-to-control solid-angle-times-time ratio. Tests for these controls are committed on the current feature branch. The current CI triggered by those changes was still in progress at the time of this status update, so no passing result is claimed for that latest population-gate change until its workflow completes.

The following gates remain open: gain-to-electron calibration review; external preregistration and an independent custodian; blind four-method testing on common real held-out fields; a source-level, selection- and contamination-aware YSO population study; independent astronomical reproduction/review; and a validated scientific release.

## Committed archive manifest snapshot

The repository now includes data/spherex_archive_manifest.M101_DR1_D2.json, a four-product M101 DR1 D2 metadata/checksum snapshot for the native science MEF, CWAVE/CBAND spectral-WCS map, absolute-gain map and supplemental solid-angle map. Each product has a source URI, archive plane identity, byte count and SHA-256; available calibration archive MD5 values are also retained. Only the spectral-WCS and absolute-gain products are asserted as direct spherex.provenance_input links to the science plane. The solid-angle map is explicitly supplemental. The native FITS files remain in the checksummed workflow #904 artifact and are not duplicated in Git.

The manifest preserves the one-exposure claim boundary and the gain conversion state derived_pending_independent_review. It is an archive traceability improvement, not additional empirical validation and not an independent calibration sign-off.

## Latest pooled-rate and API verification — 25 November 2026

On feature-branch head f5fe73471c83d1e9639ebf204abbf139ae01da77, push workflow #967 / 45657439621 passed the complete suite: **334 passed, 7 warnings**; both JavaScript syntax checks and the live M101 retrieve/audit/hash-validation/artifact-upload job passed. The matching PR workflow #968 / 45657453959 also completed successfully.

The population-rate estimator now reuses the frozen completeness threshold from the coverage audit unless an explicit matching threshold is supplied; it revalidates the audit against the exact submitted field records. Science-minus-null-control count draws remain signed while field results are pooled, and the non-negative boundary is applied once to the pooled sum, divided by the combined science-field solid-angle×time exposure. Null-control exposure ratios are checked against both area-time denominators. The generic /api/v5/population/rate route now requires a coverage-audit object rather than allowing an unaudited rate request.

These are software/statistical-contract improvements only. No source-photometry sample, YSO discovery or independent population result is claimed; the population-selection, classification, contamination, cadence and independent preregistration gates remain open.


## Source-to-product association software update — 25 November 2026

The six-region pipeline no longer relies on the rejected direct SPLICES/artifact/plane TAP join. It uses local spherical gnomonic point-in-polygon matching against SIAv2 `s_region` metadata, and now preserves the exact source-to-product pairs in per-region and aggregate CSV manifests. The inventory analyzer consumes the pair manifest and computes cross-region overlap using archive product IDs. Missing pair files are marked unavailable, not zero. This is a provenance/coverage improvement only; it is not source photometry, a verified time series, a new YSO discovery, or a population result.

The latest committed code head when this note was updated is `fc64357658bc042fc27623b743ae7c7e08226116`. The combined tests/M101 and refreshed six-region YSO workflows were pending; no passing status is claimed for that revision.


## Current-head evidence refresh — 25 November 2026

The latest fully completed combined push/M101 workflow is [45663142338](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45663142338), on branch head `84300c5ed225dc5ba190e8dac8b32650d37eafeb`. The test job passed **338 tests with 7 warnings**; both JavaScript syntax checks passed. The real M101 job completed native retrieval, compatibility/provenance audit, strict evidence validation and artifact upload. Artifact 15046223269 is 91,213,911 bytes with SHA-256 `5e7aeeeb79ff4f9b2ae8d97e9b56a0c3e47ee01c234dffd84c97ed29541747b0`. The companion PR run [45663158946](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45663158946) passed **338 tests with 12 warnings**.

The current tests include fail-closed checks for catalogue source IDs with conflicting coordinates and invalid ICRS bounds. The SIAv2 matcher excludes ambiguous source identities rather than arbitrarily using the first TAP row; a coordinate-inventory conflict makes the matching result a lower bound/incomplete.

A fresh SIAv2 source-to-product archive reconnaissance is running at [45663142077](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45663142077). The six-region exact-roster calibrated-Jy rerun is running at [45663010413](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45663010413). Neither run has a completed result/artifact at the time of this update; the previously completed six-field result [45639895735](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45639895735) remains the latest completed multi-field evidence.

The current M101 artifact retains the 2040×2040 native DR1 D2 science MEF, exact spectral-WCS and absolute-gain provenance, supplemental solid-angle map, native audit and 3×20 Jy source-Poisson injection evidence. The gain-to-electron convention remains `derived_pending_independent_review`; automated CI is not calibration sign-off.

Open empirical gates remain: independent instrument calibration review; external preregistration and independent custody; four-method benchmark on common real held-out fields; validated source spectra/epochs and a selection/contamination-aware YSO analysis; independent astronomical reproduction; validated scientific release.


## Superseding 3fdf current-head and SIAv2 integrity evidence — 25 November 2026

The latest full push suite is [45670644445](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45670644445) on `3fdfd81ddd6e5d3dc2a7a58929a58eec2c2a41f3`: **342 passed, 12 warnings**; both JS syntax checks passed. The real M101 retrieve/native audit/strict evidence validator/artifact upload all passed. The matching PR workflow [45670657450](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45670657450) passed **342 tests with 2 warnings**.

The current M101 artifact is 15050046463 (91,220,621 bytes; SHA-256 `032094d4a817960dc1780502166c9f380bb11f02251af1a7dd5acc923a55f6da`). It contains the native MEF, calibration files, evidence reports and local matched-filter SNR diagnostics. The new diagnostics do not modify detection or recovery outcomes.

The updated M101 diagnostic reports 19/20, 20/20 and 20/20 injections with a local matched-filter **maximum sample** at or above 5σ within 2.5 px, while the accepted peak matcher recovered 5/20, 14/20 and 17/20. This maximum sample is not guaranteed to satisfy the production 11 × 11 local-maximum predicate. For unrecovered injections with a selected peak, the nearest selected-peak distances were outside the 2.5 px match radius. This is a detection-stage diagnostic, not a demonstrated root cause; see [the dedicated note](SPHEREX_LOCAL_SNR_PEAK_SELECTION_DIAGNOSTICS_2026-11-25.md).

The fresh SIAv2 source-to-product reconnaissance [45670644451](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45670644451) completed successfully at the same head. Artifact 15049153600 (70,934,662 bytes; SHA-256 `1c517cc377bb0f4ae12191c9daf8cb7221dbf09053285cbc25dc98cfce488f4c`) reports 2,421 candidate sources, 6,214 SIAv2 products, 32 cube metadata rows, and 924,443 source/product pairs. Exact per-region pair manifests, source summary counts, ID-set SHA-256 digests and SIAv2 product metadata agree with zero integrity errors. Pair rows are metadata-only, not extracted flux or epochs.

The strict exact-roster six-field run [45663010413](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45663010413) remains a completed exploratory result. The more recent diagnostic rerun [45670018299](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45670018299), which runs the new per-injection SNR audit on all six fields, was still in progress at the time of this note. Do not describe its per-field diagnostics as complete until its artifact is uploaded and inspected.

Independent gain calibration review, externally preregistered four-method blind evaluation, source-level selection/contamination-aware YSO population study, independent astronomical reproduction and validated release remain open.


## 26 November 2026 — source-only injection diagnostic and archive-manifest revalidation

This addendum records the most recent completed evidence without rewriting earlier run history.

### M101 source-only diagnostic

[Workflow 45685593266](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45685593266) completed on revision `44a96b3ae38e3a93d71687f50cb7accff5dbbeea`; its real M101 D2 audit and artifact upload passed. Artifact 15054464829 (91,222,025 bytes) has ZIP SHA-256 `64895b24b2ed030070b0474b9b000f8afa8d92d43599b90cbd1017ec3ccba46f`.

The source-only diagnostic constructs the injected component as the post-injection image minus the original image, then computes matched-filter response and a separate peak list with the **original pre-injection variance map**. This intentionally isolates the injected component from the native sky/background; it does not represent the actual source-detection environment and is not used for the primary recovery assignment.

| Flux relative to local nominal 5σ | Integrated flux | Primary combined-image recovery | Source-only diagnostic peak-list count | Median source-only local maximum SNR | Median combined-image local maximum SNR |
|---:|---:|---:|---:|---:|---:|
| 0.5× | 54.198 µJy | 5/20 | 0/20 | 2.465 | 5.959 |
| 1× | 108.396 µJy | 14/20 | 8/20 | 4.906 | 8.140 |
| 2× | 216.792 µJy | 17/20 | 20/20 | 9.056 | 11.150 |

The primary recovery values, matching radius and threshold were not changed. The isolated-component peak counts are diagnostic only and must not be substituted into the completeness curve. The comparison helps separate injected-component response from the full-scene detection problem, but it does not establish why a particular injection is missed. In particular, this report does not establish the exact 11 × 11 local-maximum suppression status at every full-scene injected coordinate and does not explain the Lupus III anomaly.

### Six-region archive manifest revalidation

[Workflow 45677731011](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45677731011) completed successfully on the source/product manifest implementation. Artifact 15052808730 (70,934,685 bytes) has ZIP SHA-256 `9fb16d20ff2a621a4882a61275efc3591921f942f3521404bbd9e5fd0a3af08b`. It contains 2,421 candidate source IDs, 924,443 unique source/product pairs and 6,214 regional SIAv2 spectral-image product metadata records. All six per-region integrity reports are available and valid, with no duplicate pairs, pair IDs outside the candidate set, missing product IDs in the regional SIAv2 inventory, count mismatches, per-source product-set SHA-256 mismatches or product metadata inconsistencies. The high-latitude comparison has zero candidate sources and zero pairs; it is not a matched YSO/control population.

**Boundary:** these are geometrical source-coordinate-in-`s_region` metadata associations. The 32 All-Sky Cube rows are metadata only; no native cubes or all source-level Level-2 pixels were downloaded in this reconnaissance. There are no validated source fluxes, independent temporal visits, light curves, or population-level YSO measurements from this run.
