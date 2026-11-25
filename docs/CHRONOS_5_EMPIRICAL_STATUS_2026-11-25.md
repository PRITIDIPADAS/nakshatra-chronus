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

**Status: completed as catalogue/coverage reconnaissance; no population inference or discovery.**

The completed live IRSA TAP workflow queried five predeclared star-forming regions and one high-latitude control. All catalogue and DR1 footprint queries completed below their row caps, with no TAP errors.

| Region | SPLICES catalogue rows | Published YSO labels | ML YSO labels | ML-only labels | DR1 Level-2 footprint rows (all bands) |
|---|---:|---:|---:|---:|---:|
| Taurus–Auriga | 4,176 | 58 | 208 | 179 | 242 |
| Perseus / NGC 1333 | 849 | 130 | 120 | 59 | 241 |
| Orion A | 4,990 | 1,083 | 342 | 254 | 237 |
| Rho Ophiuchi | 2,617 | 167 | 366 | 315 | 297 |
| Lupus III | 4,016 | 52 | 129 | 124 | 235 |
| High-latitude control | 15 | 0 | 0 | 0 | 288 |
| **Total** | **16,663** | **1,490** | **1,165** | **931** | **1,540** |

“Published YSO labels” are rows with \`yso_pub\`; the harmonised \`class_1\` counts were the same in these returned regions. “ML YSO labels” refer to \`stype_ml\` and are not independent confirmations. ML-only counts refer to catalogue rows labelled YSO by \`stype_ml\` but not by the published/harmonised columns. The full row-level snapshots, SQL queries, query hashes and class concordance records are retained in the Actions artifact.

Within the 2,421-row candidate union, all source IDs are unique and the `YSO_PUB` and `CLASS_1` YSO flags have identical membership: 1,256 rows have both published/harmonised labels but no ML YSO label, 931 are ML-only, and 234 have all three labels. This overlap is a property of the returned catalogue fields, not independent confirmation.

The 1,540 Level-2 rows are exposures whose native polygons contain each predeclared region-centre coordinate. They do **not** count every exposure intersecting the full region circles, do not establish source-level visits, and are not necessarily unique across the six region-centre queries. They are footprint-query rows, not extracted source spectra or independent astrophysical samples.

The high-latitude control had 15 catalogue rows, no published/harmonised/ML YSO labels, and 288 centre-coordinate exposure rows. It is not a matched control sample with identical extinction, completeness or observing history.

Primary Actions record: [SPLICES/DR1 reconnaissance run 45624672955](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45624672955).

The results expose catalogue-label disagreement, especially ML-only candidates. That is a useful audit/follow-up list, not evidence those objects are YSOs. A real population-rate analysis still needs a well-defined source-selection function, completeness/contamination estimation, duplicate and overlap handling, epoch/source cross-matching, independent controls, uncertainty propagation and astronomical review.

## 4. Six-region calibrated Jy pilot

**Status: in progress at the time of this report; no complete multi-field summary is claimed here.**

The branch has a six-region D2 DR1 workflow with a high-latitude control. It only counts a field if the exact science-to-spectral-WCS and science-to-absolute-gain provenance links, compatible native audit, supplemental solid-angle map, successful Jy injection/recovery and unique observation/file identity checks all pass. The workflow's setup and field-gate tests completed, but the sequential real-data step had not yet produced a final aggregate report at the time this note was authored. Do not read the running Actions status as a completed multi-field result.

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

1. Complete and audit the six-region D2 pilot report, retaining all failed/ineligible fields rather than excluding them silently.
2. Have an independent astronomer/instrument scientist review the Level-2 variance/solid-angle/ePSF conventions and the pending absolute-gain electron conversion.
3. Appoint an independent custodian outside the analysis team. That custodian must hold the blind key and encrypted real truth data, register the protocol before unblinding, freeze the exact code/data digests and sign the custody record.
4. Run SNR-only, CHRONOS P/D/A, instrument forensics and Sky–Detector Twin on identical held-out real fields with a preregistered operating point. Preserve per-field results, null controls, ablations and uncertainty intervals.
5. Conduct a source-level YSO study with a defined selection function and contamination model, independently reviewed candidate identifications and control-field analysis. Catalogue ML labels alone are not discovery evidence.
6. Only after independent reproduction/review and all empirical gates pass, prepare a scientific release and paper.

No blind benchmark, new YSO discovery, external review or validated scientific release is claimed by this report.
