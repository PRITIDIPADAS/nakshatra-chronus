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

The current M101 run on the latest branch revision is the authoritative rerun.
Do not substitute the previous failed injection report or infer recovery
completeness from the successful calibration audit.

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
| Calibrated real-data injection/recovery | **Pilot rerun in progress; no result claim yet** |
| Multi-field calibration-compatible evaluation | Not satisfied |
| Four-baseline blind benchmark on actual held-out SPHEREx fields | Not satisfied |
| Population-level YSO discovery | Not satisfied |
| Independent astronomical reproduction / review | Not satisfied |
| Validated scientific release | Not satisfied |

A software or workflow success must never automatically overwrite these
scientific statuses. Only a new, checksummed, reviewable empirical report can
change a corresponding gate.
