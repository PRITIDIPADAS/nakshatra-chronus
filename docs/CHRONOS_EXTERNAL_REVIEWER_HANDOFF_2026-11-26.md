# CHRONOS external scientific-review handoff — 26 November 2026

**Status: review requested; scientific acceptance not yet granted.**

This handoff is the single entry point for independent calibration review, independent astronomical reproduction, and blind-benchmark custody. The repository maintainer and code authors cannot satisfy these gates by self-review, CI, hashes, or generated reports. Reviewers may reject the methods or report irreproducible results.

The public request and current status are tracked in [GitHub issue #4](https://github.com/PRITIDIPADAS/nakshatra-chronus/issues/4).

## 1. Current verified software / empirical boundary

- Latest full CI and M101 real-field audit before the current repair series: [run 45752875263](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45752875263), commit `2ed5869ed18d8bdd16637047c9cf62e8e18a941f`; both test and M101 audit jobs passed.
- The M101 audit is one real native D2 exposure with exact archive provenance and a 60-injection engineering pilot. It records `independent_human_reviewed=false`; it is not instrument sign-off or blind field validation.
- The first four-epoch Orion A source-photometry attempt retrieved four native DR1 D2 products and each native structure/calibration compatibility report passed, but the parent workflow reported zero extracted epochs. This was caused by a child audit exit-code condition: the child correctly recorded `calibrated_jy_injection_evaluation=skipped_by_request` because the source-series fit uses delivered Level-2 VARIANCE and must not depend on the still-unreviewed gain-to-electron conversion, yet the child exited non-zero when injection was skipped. Exit handling was corrected and regression-tested. The corrected rerun is tracked by [workflow 45756397305](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45756397305). Do not count the earlier run as a time series.
- The source-linked event-yield endpoint corrects source catalogue inclusion with fixed-bin inverse-probability weights, and its bootstrap includes zero-event eligible sources. It requires event-classifier evidence URI/hash fields, but it does not retrieve those bytes or rerun the classifier: `status='accepted'` is caller-supplied. It also does not correct event-detection efficiency, source-level contamination, or cross-field covariance. It is not a YSO population result.
- The blind four-method benchmark has not been run by an independent custodian. No external preregistration receipt or independent astronomical reproduction is on record.

## 2. Independent SPHEREx calibration reviewer

**Reviewer expertise sought:** SPHEREx/instrument calibration, infrared detector physics, Level-2 uncertainty propagation, ePSF photometry, or equivalent mission-instrument experience. The reviewer must not be an author, parameter tuner, or developer of the CHRONOS calibration implementation.

Read:
- [Gain-to-electron calibration review packet](SPHEREX_GAIN_TO_ELECTRON_CALIBRATION_REVIEW_PACKET_2026-11-25.md)
- [SPHEREx native product/time-series import guide](SPHEREX_SOURCE_TIMESERIES_IMPORT_2026-11-26.md)
- [Native audit and calibration compatibility implementation](../research_discovery/spherex/native_mef_audit.py)
- [Review record verifier](../research_discovery/spherex/independent_calibration_review.py)

The reviewer must independently check, using original archive bytes and authoritative product definitions:

1. Absolute-gain BUNIT ordering and the meaning of the gain array.
2. Exposure-time normalization for each Level-2 exposure and its exact provenance link.
3. Whether delivered Level-2 VARIANCE already contains the relevant photon, background, and electronic noise terms; whether the artificial-source Poisson increment is correct and applied exactly once.
4. The distinction between Jy-to-MJy/sr surface-brightness conversion through the pixel solid-angle map and gain-to-electron conversion.
5. Invalid gain pixels, detector flags, native WCS, CWAVE/CBAND, ePSF support, PSF interpolation, and photometry uncertainty assumptions.
6. Applicability of a calibration product across each science plane; a shared detector, filename date, or array shape alone is not sufficient.
7. A reproducible comparison of expected electrons and added variance from the original M101 bytes, then at least one additional independent science observation.

The reviewer must supply a signed report and a reproduction artifact. The report must list each check as `accepted`, `rejected`, or `not_assessed`, explain its evidence, record conflicts, and state one disposition: `accepted`, `accepted_with_conditions`, or `not_accepted`.

**Existing status remains `derived_pending_independent_review`.** Do not set it to `verified` until a real independent report has been received, the reviewer identity and independence have been confirmed outside this repository, the public key has been pinned out-of-band, and the exact signed input hashes and reproduction outputs have been verified.

## 3. Independent astronomical reproduction

**Reviewer expertise sought:** an astronomer with relevant SPHEREx/infrared time-domain, stellar-population, source-photometry, or astronomical survey experience who did not author or tune the claim being reproduced.

Use the [independent reproduction protocol](CHRONOS_5_INDEPENDENT_REPRODUCTION_PROTOCOL.md). The reviewer should:
- independently retrieve/verify the original native archive products;
- reconstruct at least a predeclared subset of source photometry, source identity, observation/MJD/LVF, wavelength, uncertainty, quality and calibration decisions;
- reproduce source-series and spectral-feature measurements from the original products, not only from supplied derived tables;
- recompute the claimed source-selection cells from injection truth, detector output, complete peak lists, and production recovery criteria;
- review YSO classes and contamination references independently;
- reproduce any candidate-event or population analysis only if event-to-source measurement lineage and the frozen event definition are supplied;
- rerun a blind benchmark only if they are not the custodian or model author and the holdout has been independently frozen;
- publish all differences, negative results, exclusions, tolerances, environment, commands and artifact hashes.

The reviewer may validate only a narrow subset. Their report must not be represented as endorsing claims beyond what they actually reproduced.

## 4. Independent blind-benchmark custodian

**Custodian expertise sought:** independent research data management, reproducible astronomy, or experimental benchmarking. The custodian must not be a model developer, report author, threshold tuner, or member of the analysis team.

Use [the prospective SPHEREx blind protocol](CHRONOS_PROSPECTIVE_PREREGISTRATION_AND_BLIND_SP_HEREX.md) and [the custodian CLI](../backend/chronos_benchmark/custodian_cli.py).

Required order:
1. Register the complete new protocol externally with an immutable timestamp **before** the custodian creates/exposes the new holdout package and before the analysis team sees any holdout field, truth, control label, or injection seed.
2. The independent custodian selects real fields and independent sky groups, seals truth/controls/injection seeds, and transfers only opaque field/exposure tokens and the public/run manifests.
3. Freeze the exact source commit, environment lock, calibration manifest, all four method thresholds, score semantics, operating point, match radii, negative controls, ablations, primary endpoint and multiplicity procedure.
4. The custodian verifies and signs the registration receipt, dataset digest and frozen configuration with an independently managed Ed25519 key. Pin the public-key fingerprint out-of-band.
5. Run SNR-only, CHRONOS P/D/A, instrument forensics, and Sky–Detector Twin on identical images, exposures, WCS, masks and thresholds.
6. Only the custodian unblinds, after verifying the complete detection run and frozen config. Preserve all failed runs and control-field outcomes.
7. The predeclared superiority gate requires a positive family-wise-adjusted paired independent-field lower confidence bound against every comparator and false-candidate/non-inferiority criteria. A failure is a valid result.

The current preregistration document is explicitly a **draft**. It is not an externally registered receipt and does not retroactively preregister prior experiments.

## 5. Signed calibration review record: how to use it

The module `research_discovery.spherex.independent_calibration_review` provides:
- `validate_review_payload`: validates the review identity/conflict declaration, all required scientific checks, disposition and exact input digests;
- `sign_review_payload`: creates a detached Ed25519 signature using the external reviewer’s private key;
- `verify_review_record`: validates the signature against an out-of-band pinned public-key fingerprint and checks the exact commit, all required digests, signed report bytes and reproduction artifact bytes.

The reviewer must retain their private key outside the repository and send only the signed record, public key, report, reproduction artifact, and reviewer identity details through an agreed channel. The repository maintainer must confirm identity/affiliation/independence separately, then pin the public-key fingerprint out-of-band. Never accept a public key and fingerprint supplied only inside the same untrusted review bundle.

Required `input_digests` keys are:
- `science_sha256`
- `absolute_gain_sha256`
- `spectral_wcs_sha256`
- `solid_angle_sha256`
- `native_audit_sha256`
- `review_packet_sha256`
- `input_manifest_sha256`
- `signed_report_sha256`
- `reproduction_artifact_sha256`

Verification returning `valid=true` establishes that a pinned key signed a review bound to the supplied commit and bytes. It does **not** establish scientific correctness or independently prove the reviewer’s credentials; those remain human external checks.

## 6. Release-blocking gates

| Gate | Current status | Minimum evidence to close |
|---|---|---|
| Instrument gain/noise calibration review | Open | Independent signed review + reproduced variance/electron calculation from original bytes |
| Native source-level multi-epoch series | Open pending corrected rerun | At least four independently identified native observations, successful native audits, actual fits, passband overlap, and an assembled source-series manifest |
| Session 18 blind four-method result | Open | Externally preregistered holdout, independent custodian, all four same-input methods, sealed unblinding, controls and paired field-level statistics |
| Session 19 YSO population science | Open | Independent YSO classification, real source series, representative selection and event-detection injections, source-level contamination, null controls, external preregistration, source-linked event likelihood, independent review |
| Independent astronomical reproduction | Open | Signed independent report tied to exact commit and data hashes |
| Browser/accessibility/researcher usability | Open | Independent browser e2e, keyboard/accessibility and researcher usability assessment |
| Validated scientific release | Closed | All relevant empirical gates closed and claims limited to what reviewers reproduced |

No single review, green workflow, or checksum closes every gate. Keep the scientific release closed until the specific release requirements are met.
