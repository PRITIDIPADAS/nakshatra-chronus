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
| Multi-field calibration-compatible evaluation | **Completed exploratory six-region evaluation; 6/6 field summaries pass post-hoc strict revalidation; gain conversion pending independent review** |
| Four-baseline blind benchmark on actual held-out SPHEREx fields | Not satisfied |
| Population-level YSO discovery | Not satisfied |
| Independent astronomical reproduction / review | Not satisfied |
| Validated scientific release | Not satisfied |

A software or workflow success must never automatically overwrite these
scientific statuses. Only a new, checksummed, reviewable empirical report can
change a corresponding gate.


Detailed single-exposure evidence, exact product hashes and injection/recovery intervals: [M101 DR1 D2 pilot report](SPHEREX_M101_DR1_D2_REAL_DATA_PILOT_2026-11-25.md).

## Live SPLICES / DR1 catalogue reconnaissance

**Status: COMPLETED AS A DESCRIPTIVE RECONNAISSANCE; NOT A POPULATION RESULT.** Workflow [45619403576](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45619403576) completed the predeclared catalogue and footprint queries for Taurus/Auriga, Perseus/NGC 1333, Orion A, Rho Ophiuchi, Lupus III and a high-latitude control. It returned 16,663 catalogue rows and a 2,421-row candidate union across regional queries. The three YSO-related fields were retained separately: 1,490 rows with non-null `YSO_PUB`, 1,490 `CLASS_1` YSO-labelled rows, and 1,165 `STYPE_ML` YSO-labelled rows. All regions were below query caps and all query errors were empty. The detailed report, exact region-level counts, report SHA-256 and artifact SHA-256 are in [the reconnaissance report](SPHEREX_SPLICES_DR1_RECON_2026-11-25.md).

The 1,540 Level-2 footprint rows summed across regions are not deduplicated unique exposures. SPLICES is a target compilation, the ML class is not independent confirmation, the regional counts are not an unbiased YSO census, and no population rate or discovery is claimed.

## Gain-derived source Poisson implementation and multi-field workflow

A detector-pixel electron conversion is now derived as exposure time divided by the exact provenance-linked absolute-gain matrix. The conversion validator checks the native calibration SHA-256, archive MD5 result, detector and unit identity, live `spherex.provenance_input` relation, both plane IDs, exact native URIs, and query digest. A provenance-derived record remains `derived_pending_independent_review`; source Poisson modelling is enabled only by an explicit exploratory opt-in. The absolute-gain matrix validates the existing Level-2 calibration and supplies the electron conversion; it is not applied again to Level-2 science pixels. Invalid gain pixels remain masked.

The six-region D2 DR1 workflow completed on run [45624461435](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45624461435). Its raw report artifact (15029628060; SHA-256 `250f3bfdbd3fe81b1d87aa00cd54389377f7c147639c408604cde672d2c31cfb`) contains six distinct native science observations and six distinct science-file hashes. The six archived field summaries were then revalidated against the stricter current field-gate implementation: all six pass all 20 field checks plus the additional identity/Poisson-integrity checks. The post-hoc strict report SHA-256 is `a94c010a3d4cfd6d678d93fe32e598218a77d53f13acf61c57d010059ebae299`; see [the full six-region report](SPHEREX_MULTIFIELD_JY_REVALIDATION_2026-11-25.md). This supports a completed **exploratory** multi-field result, not a blind benchmark or performance-acceptance claim. Lupus III recovered 0/20 in all three flux bins and is a field-level anomaly requiring investigation. All six gain-derived conversion records remain `derived_pending_independent_review`.


## Updated M101 source-Poisson evidence — 25 November 2026

The earlier deterministic injection table is retained as a historical baseline. A later real-data run enabled source Poisson noise using a per-pixel conversion derived from the exact provenance-linked absolute-gain matrix. [Workflow run 45622359188](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45622359188) completed successfully on `1065d862877ef3fbea250d74f7a6f03f3c11eab8`; the companion test run [45622372718](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45622372718) passed 269 tests with 12 warnings. Artifact 15026536639 has SHA-256 `89e47150827c093dadd1fe8b8bcbb1273be15548b9a7f87c1eb1b8483eafce99`.

The source-Poisson pilot recovered 5/20, 14/20 and 17/20 sources at 54.198, 108.396 and 216.792 microJy respectively. The exact calibration relation, archive MD5, local gain-file hash and 175 masked gain pixels are preserved in the machine report. The electron conversion is deliberately tagged `derived_pending_independent_review`; software verification is not human calibration sign-off. See [the updated M101 evidence report](SPHEREX_M101_DR1_D2_REAL_DATA_PILOT_2026-11-25.md) for file hashes and Wilson intervals.

## SPLICES / DR1 regional reconnaissance

The live catalogue/footprint query is complete for five predeclared star-forming regions and one high-latitude control. Run [45619403576](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45619403576) returned 16,663 catalogue rows and 2,421 regional candidate-union rows below query caps. Literature-reference, harmonised-class and ML labels remain separate. This is a target-catalogue reconnaissance only; it does not satisfy the YSO population-discovery gate. Details and report/artifact checksums are in [the SPLICES/DR1 report](SPHEREX_SPLICES_DR1_RECON_2026-11-25.md).


## Latest fail-closed M101 workflow verification — 25 November 2026

The latest completed M101 workflow with the strict evidence validator is [run 45638162464](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45638162464). The full test job passed **304 tests with 12 warnings**; the companion pull-request test run [45638182131](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45638182131) passed **304 tests with 2 warnings**. Both JavaScript syntax checks passed in both runs.

The push run completed the M101 DR1 D2 retrieval, native compatibility audit, machine-readable archive validator and artifact upload. Artifact 15033532053 contains 91,213,913 bytes and has ZIP SHA-256 `bfc7f21895f8192abc7ed70b1e95ea0af7ea8e331b7b67f06987db34fc0218be`. Its validator output confirms the native science hash/byte count, three detector-matched calibration files, archive MD5 checks, native MEF compatibility and three 20-injection Jy bins. The source-Poisson conversion still explicitly records pending independent human review; CI does not change that status.

## Six-region calibrated-Jy evidence — 25 November 2026

The six-region pilot is completed as an exploratory evaluation. The post-hoc strict revalidation confirms six completed fields, zero incomplete fields, distinct science observation IDs and distinct native science hashes. Each field passed the native compatibility audit, exact WCS/gain provenance, archive MD5, invalid gain masking, source-Poisson and per-bin variance checks. The gain-derived electron conversion remains pending independent instrument/calibration review.

The recovered fractions differ substantially by field. In particular, Lupus III had 0/20 recoveries in each of its three bins (105.579, 211.158 and 422.317 µJy), including the bin at twice its local nominal 5-sigma reference. This must remain visible and investigated; it is not averaged away. Full field-level values, Wilson intervals, hashes and strict checks are in [the six-region report](SPHEREX_MULTIFIELD_JY_REVALIDATION_2026-11-25.md).

The pilot remains non-blind and single-exposure-per-region. It is not a four-method comparison, all-sky completeness curve, YSO population result or validated scientific release.
