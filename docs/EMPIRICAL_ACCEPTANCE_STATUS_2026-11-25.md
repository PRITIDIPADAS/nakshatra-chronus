# CHRONOS 5 empirical acceptance status — 2026-11-25

This record distinguishes a verified real-data calibration audit from the larger
scientific acceptance gates. It must not be read as an announcement that all
empirical gates passed.

## Verified real-data calibration pilot

**Field / exposure:** M101, SPHEREx DR1, detector D2, observation
\`2025W19_2B_0346_1\`, 2025-05-10, 113.5826 s.

**Science MEF:** pipeline 7.0.5, processing batch \`2026-198\`, native
2040 × 2040 IMAGE plane, BUNIT \`MJy/sr\`.

**Native science URI:**
\`https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W19_2B/l2b-v27-2026-198/2/level2_2025W19_2B_0346_1D2_spx_l2b-v27-2026-198.fits\`

**Science SHA-256:**
\`fba39ecd1930274aea655a744287908d6d677daeec59c8efe1ebbcffb844be90\`

**Verified calibration lineage:**
- The spectral-WCS calibration file is linked to this exact science plane by
  IRSA's \`spherex.provenance_input\` foreign-key relation. Its \`CWAVE\` and
  \`CBAND\` arrays are native 2040 × 2040 maps, in micrometres, with all pixels
  valid for this audit.
- The absolute-gain matrix is also linked to the exact science plane through
  the same provenance chain. Its archive checksum and local SHA-256 were
  verified. 175 of 4,161,600 samples are non-positive/non-finite and are
  explicitly masked; no interpolation or filling is applied.
- The detector solid-angle map is a separately queried DR1/D2 calibration
  product from the same calibration batch. It passed its detector, native-grid,
  units and file-integrity checks. It is **not** represented as a direct
  \`provenance_input\` child of the science plane.
- Native FITS structure, IMAGE/VARIANCE/FLAGS/ZODI alignment, alternate WCS A,
  detector identity, release and the file-backed compatibility checks passed.

**Verified workflow:** GitHub Actions run
[45612193703](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45612193703)
completed successfully on commit \`808973de5f4bcafeff55170d959da24b46a62f10\`.
Its file-backed result reported
\`STRUCTURE_AND_COMPATIBILITY_CHECKS_PASS\` and compatibility \`compatible\`.

This is a one-exposure calibration compatibility result. It is not a multi-field
performance estimate, a four-baseline benchmark, or evidence of a new YSO
discovery.

## Injection/recovery status

A Jy-domain single-exposure matched-filter injection workflow is implemented.
It uses the measured Level-2 VARIANCE, detector-aligned solid-angle map and a
position-specific ePSF. Flux is reported in integrated Jy, with the
position-dependent pixel-area conversion used in the matched filter.

An earlier run found a valid local ePSF footprint but failed PSF physicality
validation because the rendered stamp contained a tiny negative interpolation
lobe. The current code keeps the raw ePSF stamp and applies one explicit
physicality check: both the negative peak fraction and integrated negative
flux fraction must be below 0.1%; otherwise the PSF is rejected. The corrected
unit-sum stamp receives its own SHA-256 and diagnostic record. No science image,
variance or calibration pixels are modified or interpolated by this PSF-only
correction.

**Completed calibrated real-data evaluation:** GitHub Actions run
[45614873760](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45614873760)
completed successfully on commit `dfe3bc322902758a9d317efddb718112a03e2a04`.
The report recorded:
- Local reference 5σ sensitivity: **0.000108396 Jy (108.396 μJy)**.
- Injected integrated flux levels: **54.198, 108.396, and 216.792 μJy**.
- Recoveries: **5/20 (25%)**, **13/20 (65%)**, and **19/20 (95%)**.
- Corresponding two-sided 95% Wilson intervals: **11.2–46.9%**, **43.3–81.9%**, and **76.4–99.1%**.
- Median astrometric offset: **0.791 native pixels**; 95th-percentile offset was **0.791–1.057 pixels** across the three levels.
- 246 baseline detections were present in the full exposure; zero new unmatched peaks were reported within the evaluated local PSF region.

The position-dependent ePSF was extracted at (x=1019.25, y=1020.75). One negative
interpolation sample was clipped under the predeclared two-part limit: its
negative-to-positive peak fraction was 0.0001716 and its integrated negative
flux fraction was 0.00008576, both below 0.001. The corrected stamp was
renormalized to unit sum and separately SHA-256 hashed.

**Interpretation:** this is evidence that the pipeline can run a calibrated
single-exposure Jy injection/recovery experiment on a real SPHEREx DR1 exposure.
The 20 injections per flux level are a small local pilot, not a complete
completeness curve or an all-sky estimate. The measured 65% recovery at the
nominal local 5σ estimate also shows that the current threshold/sensitivity
mapping is not yet validated as a 50%/completeness operating point.

Limitations of this pilot:
- One M101 D2 exposure only; no multi-field or time-domain generalisation.
- Synthetic signal is injected into measured real image data; this is not a
  blind trial.
- Source Poisson variance is not added because the independently signed
  electron-conversion evidence needed for that calculation is not yet part of
  this evaluation.
- This matched-filter experiment is not the four-method CHRONOS comparison and
  is not a substitute for the separately implemented SNR-only baseline.

## Independent blind benchmark

**Status: NOT SATISFIED.**

The repository now requires an independent custodian's detached Ed25519
attestation, an out-of-band pinned public-key fingerprint, hashes binding the
external preregistration receipt to the exact holdout dataset and frozen
configuration, and verification before any held-out truth is decrypted.

No genuine independent custodian, externally timestamped preregistration
receipt, pinned independent public key, sealed real-SPHEREx held-out field
catalogue, or completed four-method detection run is recorded here. The
benchmark evaluator measures supplied method outputs; it does not itself run
all four detection methods. A benchmark must use identical real exposures,
masks, coordinates and frozen processing choices for all methods.

## Population-level YSO discovery

**Status: NOT SATISFIED.**

The coverage and population endpoints fail closed unless there are multiple
independent real fields, independently classified YSO sources, source-level
epoch and wavelength coverage, null controls, and measured injection/recovery
completeness. A coverage pass is only permission to proceed with a frozen
study; it is not a physical discovery.

No validated multi-field YSO sample, population denominator, selection
function, contamination audit, or completed preregistered population estimate
is recorded in this run. M101's calibration pass is not a YSO population result.

## Independent astronomical reproduction / researcher review

**Status: NOT SATISFIED.**

No independent astronomy researcher has reproduced the result from the
original archive inputs or signed a review of the methods and claims. A local
test suite, GitHub Actions success, checksum, or software-generated attestation
cannot substitute for an external researcher.

## Validated scientific release

**Status: NOT SATISFIED.**

Do not describe the branch as a validated scientific release or claim all
empirical acceptance gates have passed. The remaining gates are independent:
multi-field calibrated evaluation, actual held-out blind benchmark with
independent custody, YSO population analysis under a preregistered selection
protocol, and external astronomical reproduction/review.

## Machine-readable status

| Gate | Current status |
|---|---|
| M101 D2 DR1 calibration compatibility | **Passed for one exposure** |
| Calibrated real-data injection/recovery | **Completed one-exposure Jy pilot with gain-derived source Poisson; conversion pending independent review** |
| Multi-field calibration-compatible evaluation | **Completed exploratory run #17; 6/6 fields passed all 20 runner checks; gain conversion pending independent review** |
| Four-baseline blind benchmark on actual held-out SPHEREx fields | Not satisfied |
| Population-level YSO discovery | Not satisfied |
| Independent astronomical reproduction / review | Not satisfied |
| Validated scientific release | Not satisfied |

A software or workflow success must never automatically overwrite these
scientific statuses. Only a new, checksummed, reviewable empirical report can
change a corresponding gate.


Detailed single-exposure evidence, exact product hashes and injection/recovery intervals: [M101 DR1 D2 pilot report](SPHEREX_M101_DR1_D2_REAL_DATA_PILOT_2026-11-25.md).

## Live SPLICES / DR1 catalogue reconnaissance

**Status: completed descriptive reconnaissance with geometric archive-footprint linkage; not a population result.** The latest successful workflow is [run #38](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648715196). It returned 16,663 regional catalogue rows, 2,421 candidate-union rows, 1,540 Level-2 region-centre rows and 6,214 DR1/QR3 SIAv2 Level-2 image products. Local spherical matching against SIAv2 s_region polygons yielded 924,443 geometric candidate–product footprint pairs, with at least one match for all 2,421 candidates in the five star-forming regions. All four SIAv2 collections completed below their caps; no candidate coordinates or returned product polygons were invalid. The All-Sky Cube metadata inventory returned 32 records for the six searched field cones, not the whole sky. Exact hashes and field-level results are in [the run-#38 report](SPHEREX_SPLICES_DR1_RECON_2026-11-25.md).

These are metadata footprint associations, not extracted source flux, usable time cadence, validated light curves or physical class confirmation. The 931 ML-only rows remain follow-up candidates, not newly confirmed YSOs. This does not satisfy the YSO population-discovery gate.

## Gain-derived source Poisson implementation and multi-field workflow

A detector-pixel electron conversion is derived as exposure time divided by the exact provenance-linked absolute-gain matrix. Validation records the calibration SHA-256, archive MD5, detector/unit identity, live `spherex.provenance_input` relation, plane IDs, native URIs and query digest. The Level-2 science image is not gain-corrected a second time. Invalid gain pixels stay masked. The conversion status is `derived_pending_independent_review`; source-Poisson modelling is enabled only with an explicit exploratory opt-in.

The newest six-field run is [#17 / 45637115746](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45637115746). All six predeclared fields completed and passed all 20 runner checks per field; the machine report and all field-level recovery intervals are in [the six-region evidence report](SPHEREX_MULTIFIELD_JY_REVALIDATION_2026-11-25.md). The report retains the Lupus III zero-recovery result. This is exploratory evidence only; the gain-conversion reviewer has not signed off.

## Updated M101 source-Poisson evidence — 25 November 2026

The earlier deterministic injection table is retained as a historical baseline. A later real-data run enabled source Poisson noise using a per-pixel conversion derived from the exact provenance-linked absolute-gain matrix. [Workflow run 45622359188](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45622359188) completed successfully on `1065d862877ef3fbea250d74f7a6f03f3c11eab8`; the companion test run [45622372718](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45622372718) passed 269 tests with 12 warnings. Artifact 15026536639 has SHA-256 `89e47150827c093dadd1fe8b8bcbb1273be15548b9a7f87c1eb1b8483eafce99`.

The source-Poisson pilot recovered 5/20, 14/20 and 17/20 sources at 54.198, 108.396 and 216.792 microJy respectively. The exact calibration relation, archive MD5, local gain-file hash and 175 masked gain pixels are preserved in the machine report. The electron conversion is deliberately tagged `derived_pending_independent_review`; software verification is not human calibration sign-off. See [the updated M101 evidence report](SPHEREX_M101_DR1_D2_REAL_DATA_PILOT_2026-11-25.md) for file hashes and Wilson intervals.

## SPLICES / DR1 regional reconnaissance

Workflow [#38 / run 45648715196](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648715196) completed five star-forming regions plus a high-latitude control. It returned 16,663 catalogue rows, 2,421 candidate rows, 1,540 region-centre Level-2 rows and 6,214 DR1/QR3 SIAv2 Level-2 image products. The SIAv2 polygon matcher returned 924,443 geometric source–product pairs and at least one footprint association for every candidate source in the star-forming regions. The All-Sky Cube metadata search returned 32 distinct tile metadata records across the six predeclared field cones; it is not a full-sky inventory. No source flux was extracted, and metadata time spans are not validated epochs or cadence. See the [run-#38 report](SPHEREX_SPLICES_DR1_RECON_2026-11-25.md).

## Latest fail-closed M101 workflow verification — 25 November 2026

The latest completed combined test/M101 workflow on the final merged feature branch is [#904 / run 45651695959](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45651695959), commit `be3821df40a45f3cd1372658e13bd95d0fd409ac`. It passed **316 tests with 2 warnings**; both JavaScript syntax checks passed. The M101 real-field job completed archive retrieval, native compatibility validation, machine-readable evidence validation and artifact upload. Artifact `15041211977` is `91,213,917` bytes with ZIP SHA-256 `828ce12e05b2ce325e15e7ecd9c1843c55cc5b4c9254f5a508402462d6695cf3`.

The run-#904 native-MEF audit JSON has SHA-256 `e56c5601077e47c317aa01023b0866e608b7e0425e1dc4f801b48eb7ef417bf6` and reports `STRUCTURE_AND_COMPATIBILITY_CHECKS_PASS`, calibration compatibility `compatible`. The field summary JSON has SHA-256 `2cac9b465641ef4bc95ce422b767ffbafb670c50f028d6e78317f2d2d75d1c7e`; the source-Poisson injection JSON has SHA-256 `93611054c67dd33d4b40934b3da44b18830eb54401bcd09e1b608c3b7b9cba5a`. The M101 recovery values remain 5/20, 14/20 and 17/20 at 54.198, 108.396 and 216.792 µJy.

The absolute-gain product SHA-256 remains `d0a4c3352da99326c307e4e0115285faa8cba2769ea6b57cf340d4e6fc271b37`; 175 invalid/non-positive pixels remain masked. The source-Poisson/electron conversion record explicitly remains `derived_pending_independent_review`, with `independent_human_reviewed=false`. Automated provenance and compatibility checks are not independent instrument-calibration sign-off.

The parallel test-only workflow [#905 / run 45651701705](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45651701705) also passed **316 tests with 7 warnings**, with both JavaScript syntax checks passing.
## Six-region calibrated-Jy evidence — 25 November 2026

The latest six-field pilot is [workflow #17 / run 45637115746](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45637115746), revision `b286210ea64af43c282e44dfa6939757dd2642c8`. All six predeclared regions completed; each passed all 20 machine eligibility checks. Artifact 15034299164 has ZIP SHA-256 `96ff0c2025d098ebb3d63d64bd1361aabdeb2c4830920227a53ce53364c01afb`; its embedded summary digest is `cfd0ce32a6ce5f8206a64ebb6927cc186784259af2914b846bd633d5a74e626e`. The full field-level observations, native science hashes, recovery values and Wilson intervals are in [the six-region report](SPHEREX_MULTIFIELD_JY_REVALIDATION_2026-11-25.md).

The pilot remains exploratory and non-blind, one D2 exposure per region. Lupus III produced 0/20 recoveries at all three flux levels, including 2× its local nominal 5-sigma reference; the adverse outcome remains in the aggregate. Gain-derived electron conversions remain pending independent calibration review. This is not a four-baseline comparison, YSO population result, survey-wide completeness estimate or validated scientific release.
