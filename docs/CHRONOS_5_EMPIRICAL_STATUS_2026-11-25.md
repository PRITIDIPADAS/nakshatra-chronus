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
