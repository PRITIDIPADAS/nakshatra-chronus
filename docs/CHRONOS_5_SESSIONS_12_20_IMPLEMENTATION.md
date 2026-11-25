# CHRONOS 5 Sessions 12–20 implementation

This guide documents the software added for Sessions 12–20. It separates implemented software from empirical results. No real-data benchmark, population discovery, telescope scheduling, independent paper review or scientific release gate is claimed to have passed unless a separate report records that result.

## Session 12 — Spectrotemporal reconstruction and covariance

**Module:** \`backend/chronos_spectrotemporal/reconstruction.py\`

**API:** \`POST /api/v5/spectrotemporal/reconstruct\`

The bridge accepts source-specific samples with explicit source IDs, observation IDs, MJD, native wavelength samples, flux, uncertainty, unit, validity, detector, calibration group and wavelength provenance. Each reconstruction is restricted to a single compatible calibration group. The API accepts a full measurement covariance matrix indexed against the original submitted rows and adds the shared calibration-group systematic as a rank-one covariance term.

The local generalized least-squares reconstruction returns the flux estimate, measurement uncertainty, shared calibration contribution, total uncertainty, neighbor count, effective sample size, original source rows and each contributing linear coefficient. The temporal covariance between reconstructed epochs at each wavelength is retained. An optional full covariance for supported grid cells is available for at most 400 cells.

Every grid position is classified as \`measured\`, \`inferred\` or \`unsupported\`. Unsupported values are serialized as JSON \`null\`; they are not replaced by zero. The native wavelength samples and observation times remain in the output. The API does not extrapolate outside the sampled wavelength/time envelope.

The achromatic/chromatic decomposition is a descriptive ratio analysis over common supported wavelength samples. It is not a physical source model and cannot resolve wavelength/time confounding by itself. A grid cell called measured still contains a local GLS estimate; its exact-grid contributor rows are listed so it is not mistaken for an independently calibrated single input sample.

## Session 13 — Spectral feature evolution and resolution

**Modules:** \`backend/chronos_addons/molecular.py\`, \`backend/chronos_spectrotemporal/feature_evolution.py\`

**API:** \`POST /api/v5/spectrotemporal/feature-evolution\`

Feature intervals and both continuum sidebands are explicitly predeclared. The measurement reports equivalent width, its uncertainty and significance where supported, feature depth, continuum uncertainty, the fitted continuum coefficients and covariance, and the difference between linear and constant continuum models.

Resolution is retained through the line-spread-function or resolving-power diagnostics. The feature is not deconvolved to an invented intrinsic profile. Unresolved features, undersampling and overlapping or nearby supplied blend intervals are flagged. The reported feature track retains calibration groups and epoch provenance; no unrequested inter-group correction is silently applied.

Optional laboratory reference comparisons require an HTTPS source, SHA-256 digest, wavelength units in micrometres, matching observed/laboratory intensity units, valid reference samples, and documented observed and laboratory resolution. A higher-resolution laboratory reference is convolved to the observed Gaussian LSF. Lower-resolution references, incompatible units, absent resolution, insufficient wavelength coverage and unsupported non-Gaussian LSFs are rejected from the comparison. Shape similarity is candidate evidence only. The module never identifies H2O, CO2, CO, CH3OH or OCN-minus from wavelength resemblance alone.

## Session 14 — Probabilistic source identity

**Modules:** \`backend/chronos_identity/associations.py\`, \`backend/chronos_identity/source_graph.py\`

**APIs:** \`POST /api/v5/identity/associate\`, \`POST /api/v5/identity/source-graph\`

The association model propagates catalogue positions to a common epoch and uses the available proper-motion/parallax information and uncertainty. It retains positional uncertainty, local source density, chance-coincidence evidence, survey epoch, angular resolution, wavelength metadata, competing counterparts and no-counterpart probability.

A positional association is not physical identity confirmation. The output remains conditional on supplied priors, source density, astrometric conventions and catalogue completeness. A nearest-neighbour match is never automatically reported as a confirmed identity.

## Session 15 — Candidate-specific next observation

**Module:** \`backend/chronos_addons/planner.py\`

**API:** \`POST /api/v5/observations/plan-candidate\`

Every competing model forecast must retain a \`fit_id\` and the original observation IDs used by the fit. Candidate options can specify later epochs, wavelengths, detectors or arrays. The planner reports expected information gain and sensitivity to supplied alternative priors.

A recommendation is emitted only when the candidate carries a structured externally verified feasibility record. It must include a verified status, feasible boolean, exact HTTPS source URI, timezone-aware check time, calculator, query ID, evidence SHA-256 and query parameters. CHRONOS checks that the record is structurally complete, but does not independently authenticate the external visibility/availability service. If the record is missing or incomplete, the science-only ranking remains visible and no observation is labelled feasible. This API does not schedule or command a telescope.

## Session 16 — Evidence graph and reproducible package

**Modules:** \`backend/chronos_causal/evidence_graph.py\`, \`backend/chronos_causal/provenance.py\`, \`backend/chronos_causal/investigation_package.py\`

**APIs:** \`POST /api/v5/evidence/manifest\`, \`POST /api/v5/evidence/manifest/verify\`, \`POST /api/v5/evidence/graph\`, \`POST /api/v5/evidence/package/export\`

The archive manifest records the query, retrieval timestamp, release, product family, native URI, observation time, detector, file size and SHA-256, calibration/processing versions, software commit and processing choices. Missing provenance fields are returned as completeness issues rather than treated as complete metadata.

The evidence graph links input files and calibration products to source observations, measurement rows, model runs, counterfactuals, failed tests, conclusion status, software environment and code commit. The investigation package records these details and includes member hashes and a ZIP sidecar hash. Original FITS files are referenced through exact source URI and digest where licences/size prevent embedding.

Verify a downloaded package from the repository root:

\`\`\`bash
PYTHONPATH=backend python -m chronos_causal.package_cli verify chronos-investigation-package.zip
\`\`\`

The verification command checks ZIP/member integrity against recorded hashes. SHA-256 is not proof of authorship, source authenticity or scientific truth. The package's reproducibility command must be the exact command used by the analyst. A second researcher still needs access to the original archive products and the recorded environment/calibration files.

## Session 17 — Four linked workspaces

The existing observatory and causal-lab page are preserved. The site groups the research workflow into Causal Investigation, Spectral Evolution, Cosmic Identity Network and Experimental Observatory.

The browser renders values returned by the Python API; it does not reproduce scientific fitting, spectral reconstruction, counterpart association or information-gain calculations in JavaScript. Views include the sky/detector coordinate pairing, observation timeline, measurement decomposition, competing model results, spectral-time heatmap with missing cells, selected-epoch spectrum, selected-wavelength light curve, uncertainty decomposition, counterpart network, next-observation ranking and evidence graph.

Candidate search and filters group loaded observation rows on the server. A locally stored shortlist can be shared through candidate IDs in the URL and compared in pairs. JSON/CSV exports, heatmap figure export and investigation-package export are available. Synthetic, illustrative, unverified and real labels are inherited from the submitted rows; missing labels are unverified. A plotted sky/detector pairing is not a substitute for a validated coordinate transform.

## Session 18 — Blind real-data evaluation

**Module:** \`backend/chronos_benchmark/runner.py\`

The comparison evaluator accepts four supplied detector outputs on identical field inputs and truth catalogues: SNR-only, CHRONOS P/D/A, instrument forensics and Sky–Detector Twin. It reports matched operating points, per-field precision/completeness/false candidates, astrometric residuals, field-level bootstrap intervals, control/injection strata and flux-bias/uncertainty coverage when both truth flux and reported detection uncertainty are supplied.

A generic evaluator call cannot declare itself a blind scientific result by adding an unblinding-looking JSON object. \`scientific_claim_eligible\` can become true only through the custodian-controlled unblinding path after the frozen configuration, public run manifest, dataset digest, encrypted truth-store checksum, key fingerprint, source commit, method signatures and complete held-out token set have been verified. A field-level software test or a synthetic challenge is not a blind real-data benchmark.

### Independent-custodian procedure

The custodian holds the Fernet key and encrypted truth store separately from the analysis runner. The key must never be committed to the repository or shared with the detector team.

Create an owner-only key:

\`\`\`bash
PYTHONPATH=backend python -m chronos_benchmark.custodian_cli generate-key --key-file /secure/offline/chronos-custodian.key
\`\`\`

Prepare a blind split. Transfer only the public run manifest to the analysis team; retain the key and encrypted truth store with the custodian:

\`\`\`bash
PYTHONPATH=backend python -m chronos_benchmark.custodian_cli prepare --fields /secure/input/real-fields.json --key-file /secure/offline/chronos-custodian.key --output-dir /secure/custodian/blind-package
\`\`\`

The preregistered configuration must record the protocol SHA-256, all thresholds and processing choices. Freeze it against the exact commit and dataset digest before running detectors:

\`\`\`bash
PYTHONPATH=backend python -m chronos_benchmark.custodian_cli freeze --configuration preregistered-config.json --source-commit FULL_GIT_COMMIT_SHA --dataset-digest DATASET_SHA256 --output frozen-configuration.json
\`\`\`

Run every method on the exact same exposures, masks, coordinate frame and pipeline configuration. The run record must include all public held-out tokens exactly once, four method outputs, score thresholds, matched operating point, source commit and frozen-configuration digest.

Only after the run record is sealed does the custodian unblind:

\`\`\`bash
PYTHONPATH=backend python -m chronos_benchmark.custodian_cli unblind --key-file /secure/offline/chronos-custodian.key --public-manifest /secure/custodian/blind-package/public_manifest.json --encrypted-store /secure/custodian/blind-package/encrypted_truth_store.bin --frozen-configuration frozen-configuration.json --detection-run detection-run.json --output blind-four-baseline-report.json
\`\`\`

This workflow has software support; it does not imply that any real SPHEREx held-out fields have already been benchmarked. The evaluator scores supplied method outputs and does not itself run the four detection algorithms.

## Session 19 — One population-level physics investigation

**Module:** \`backend/chronos_population/coverage.py\`

**APIs:** \`POST /api/v5/population/assess-coverage\`, \`POST /api/v5/population/yso/rate\`

The current population path is a single predeclared YSO feature-evolution study. The coverage audit checks real-field labels, independent fields, source classification references, null-control IDs, source-specific epochs, native wavelength coverage in the predeclared feature and continuum bands, calibrated wavelength provenance, median SNR and injection-recovery completeness.

The YSO rate endpoint repeats the coverage audit on the same submitted source rows and requires a preregistration SHA-256 before estimating a rate. If the sample does not pass, the endpoint refuses the calculation and returns the coverage audit. A pass only means a study may proceed under a frozen protocol; it is not evidence of a physical population trend. Selection effects, independent field assumptions and null controls still require review.

## Session 20 — Paper and release gate

This implementation supplies methods and infrastructure; it does not supply a scientific result. A technical paper must use measured real-data outcomes and include calibration provenance, all four baseline comparisons, blind field-level uncertainty, ablations, null results, failed tests and limitations. An independent astronomy researcher must review any discovery or instrument-performance claim.

Do not tag a validated CHRONOS 5.0 scientific release until real archive calibration is verified, held-out fields have passed the blind protocol, negative controls and ablations are reported, and another researcher can reproduce the result from original inputs and recorded configuration.

## Empirical status update — 25 November 2026

Current evidence includes the M101 single-exposure D2 DR1 native calibration/injection audit (source-Poisson enabled; gain review pending), the six-field D2 exploratory Jy pilot (6/6 fields and all 20 runner checks per field passed), and six-region SPLICES/DR1/QR3 archive reconnaissance with SIAv2 product-footprint matching. Workflow [#38](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648715196) returned 2,421 candidate-source summaries, 924,443 geometric source–product pairs and 32 All-Sky Cube metadata records for the six searched field cones. The dedicated checksummed reports preserve all field-level counts and limitations.

Repair-branch test/M101 workflow [#896](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648715416) passed 316 tests with 12 warnings, both JavaScript syntax checks and the M101 archive/native-audit/artifact-upload job. Test-only workflow [#897](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648724365) passed 316 tests with 7 warnings and both JavaScript syntax checks. These results are software and archive-evidence validation, not independent calibration review, a blind benchmark, a YSO population discovery, external reproduction or scientific release.

## Archive-coverage update — DR1 + QR3 (25 November 2026)

The reconnaissance queries the four IRSA SIAv2 collections separately: spherex_dr1, spherex_dr1_deep, spherex_qr3 and spherex_qr3_deep. The fixed region-centre Level-2 TAP query remains a separate narrower diagnostic. The former direct SPLICES-to-spherex.artifact TAP join was removed after the archive resolver rejected its table metadata lookup.

Candidate-to-product footprint association is now computed locally from the SIAv2 s_region polygons using the spherical-gnomonic-pip/1.0 method. Run #38 completed below declared caps with 2,421 candidate-source summaries and 924,443 geometric candidate–product pairs across the five star-forming regions. All returned product polygons and candidate coordinates passed validation. This is a coordinate-in-product-footprint match only; it does not imply that source flux was extracted, spectra passed quality cuts, epochs are usable or light curves are validated.

The run-#38 archive report contains 6,214 SIAv2 Level-2 image products: 4,432 DR1 and 1,782 QR3. Metadata time spans are not validated cadence. Product definitions follow the [IRSA SPHEREx Data Access guide](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/) and [Data Releases guide](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-releases/).

## DR1 All-Sky Cube metadata inventory

Workflow #38 queried spherex_dr1_cube separately for each of the six predeclared POS-circle regions. It returned 32 distinct archive product metadata records: 8 Taurus/Auriga, 4 Perseus, 6 Orion A, 4 Rho Ophiuchi, 4 Lupus III and 6 high-latitude control. Each region query completed below its 20,000-row cap. This is a complete metadata result for those six cones, not a complete all-sky inventory. The product has a nominal 102 channels over 0.75–5.0 μm. Native cube data were not downloaded and the records are not temporal exposures.


## Population-gate hardening — 25 November 2026

The Session 19 coverage/rate path has additional fail-closed checks on the current feature branch:

- A YSO candidate must have validated CWAVE/CBAND provenance for each accepted measurement, explicit measurement IDs and flux units, and no duplicate observation/wavelength/calibration-group rows.
- Feature samples and both continuum sidebands must be present in the same repeated epochs. Aggregate feature counts from one epoch and continuum counts from other epochs can no longer satisfy the cadence gate.
- Reusing one source identity across different fields marks those field/source records ineligible; a repeated catalogue source is not counted twice as an independent population member.
- A population rate cannot subtract raw null-control counts from a science-field count without an explicit positive `null_control_to_science_exposure_ratio`. The rate estimator scales the control exposure using a Gamma–Poisson predictive draw and records the ratio and expected control count on the science exposure.
- The rate estimator, when called directly, skips records not labelled real or not explicitly marked as independent, as well as fields without a null-control ID and exposure ratio.

These checks are tested using synthetic fixtures with synthetic archive/provenance URLs and fake hashes. They are software regressions, not real measurements or custodian attestations. The ratio still has to be derived from documented control/science solid-angle and time coverage, and the scalar completeness model still does not replace a multidimensional selection function. The new population-gate CI for current head `63b800601a3a24372bf9426099d094eeba24bda9` was pending at the moment this note was edited.



## Exact candidate-to-archive product manifest — 25 November 2026

The SIAv2 matcher now emits exact source/product pair records as well as compact per-source summaries. `candidate_source_product_matches.csv` is written under each predeclared region and `candidate_source_product_matches_all_regions.csv` is written across the six regions. Each pair records the source ID, publisher dataset ID where available, native access URI, archive `obs_id`, collection/release, spectral band, archive time bounds and matcher version. The full regional SIAv2 manifest retains the `s_region` polygon used for each geometric association.

The population inventory analyzer now uses `archive_product_id` rather than assuming legacy `planeid` for schema 1.1 cross-region source/product overlap. Schema 1.0 continues to use its historical plane-ID interpretation. Missing per-source product manifests now set the region and aggregate product-match result to unavailable rather than zero. Regression tests cover missing manifests and a repeated source/product identity across fields.

The matcher’s `complete_below_declared_caps` status is counted as a completed archive-metadata query by the analyzer, but it is not a claim of temporal completeness or usable cadence. The exact current branch has pending CI; no new pass is claimed here.


## Current-head code verification — 25 November 2026

Branch head `84300c5ed225dc5ba190e8dac8b32650d37eafeb` passed 338 tests (7 warnings) and both JavaScript syntax checks in push workflow [45663142338](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45663142338); the PR companion [45663158946](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45663158946) passed 338 tests with 12 warnings. These tests include coverage/rate API digest binding, repeated same-epoch feature/continuum sampling, calibration group consistency, control area×time scaling, signed pooled excess tests, and the source-identity coordinate ambiguity gate.

The latest code hardens SPLICES/SIAv2 candidate identity: duplicate source IDs with conflicting ICRS coordinates are omitted from source-to-product matching and make the source-coordinate inventory incomplete. This is an archive metadata association only; it does not create source photometry or usable epochs. Current live SIAv2 and exact-roster six-field workflows remain pending at the time of this note.

No Session 19 population estimate is produced. Independent classifications, usable source-level spectral epochs, multidimensional selection/completeness, contamination modeling, external preregistration and independent review are still required.


## Session 15 — pinned observation-feasibility attestation

The legacy and structured observation-planning paths no longer treat a caller-supplied `status: verified` string as authenticated. A detached Ed25519 attestation must verify against an out-of-band deployment-pinned public key. The signed canonical JSON covers the feasibility status, true/false feasible value, source URI, checked time, exact UTC window, calculator, query ID, query parameters and evidence SHA-256. The request cannot supply its own trust anchor.

Deployment trust is configured by `CHRONOS_FEASIBILITY_ATTESTATION_KEY_ID` and `CHRONOS_FEASIBILITY_ATTESTATION_PUBLIC_KEY_B64`. Without those values, the planner remains science-ranked/feasibility-unverified and does not return a feasible recommendation. A verified signature authenticates the record as signed by that key; it does not certify the service’s physical or operational accuracy.

Tests cover unsigned caller claims, a valid pinned test-key signature, and record tampering after signing. The deployment still needs a real external signer, a production public key provisioned out of band, and an end-to-end signed availability query before any observing window is claimed feasible. See [the attestation trust model](OBSERVATION_FEASIBILITY_ATTESTATION.md).



## 26 November 2026 — source-series import and selection-gate hardening

This update adds a concrete import route for the official IRSA SPHEREx Spectrophotometry Tool output and strengthens the Session 19 selection evidence contract.

### Session 12 source-series path

\`research_discovery.spherex.irsa_spectrophotometry\` reads IRSA VOTable/XML or CSV rows and binds them to an explicit sidecar containing source catalogue coordinates/classification references and exact \`(lvf_id, detector, release) → archive_product_id\` mappings. It converts µJy to Jy, preserves uncertainty/MJD/wavelength/bandwidth/quality fields, and applies a predeclared photometry flag, fit-QL and background-fraction policy. Rejected rows remain in the import audit.

\`research_discovery.spherex.source_timeseries\` now supports sub-pixel native-map sampling and an optional celestial-WCS check against the supplied IRSA sky coordinate. The assembler verifies native IMAGE/VARIANCE, CWAVE, CBAND, solid-angle and ePSF file provenance; checks archive observation/product/calibration binding; and uses per-measurement MJD when constructing the series. Hosted-service provenance is distinguished from a version-controlled extractor.

Regression tests cover conversion, product mapping, quality exclusions, coordinate-origin declaration and the native-source-series audit. These use synthetic fixtures. No genuine source photometry export and product roster were supplied in this implementation run; Session 12 is therefore **software path implemented, real source series not yet established**.

### Session 19 selection-function path

The injection model now requires a digest-bound recovery evidence record. Recovery is recomputed from the frozen local-maximum/primary-selection rule, SNR threshold, one-to-one peak assignment, match radius, flag mask, fit-QL and background cuts. A reused selected peak is rejected.

The uncertainty estimate is a field-cluster bootstrap of per-group Jeffreys beta posteriors. Multiple injections within one observing field do not count as independent fields. Field-level injection/recovery totals must match the exact trial rows. The YSO rate route checks that the request preregistration digest is identical to the digest frozen into the selection trials, and event-rate revalidation binds the fixed selection bins, trial digest and frozen provenance.

This is a conditional selection-function model, not a full hierarchical model. The current field-level event-rate estimator still does not consume source-level inverse-probability weights as an event likelihood because its input does not link each event to a source. Do not present it as a fully selection-corrected YSO population rate.

### Session 20

The independent-reproduction protocol now specifies the package, original-data checks, blind benchmark, source-level measurement reproduction, selection curve reproduction, discrepancies and signed report needed for external acceptance. No independent astronomer report was obtained or generated. Session 20 and the scientific release gate remain **NOT SATISFIED**.

See [the source-series import guide](SPHEREX_SOURCE_TIMESERIES_IMPORT_2026-11-26.md), [selection-function specification](CHRONOS_5_SELECTION_FUNCTION_SPEC.md), [independent reproduction protocol](CHRONOS_5_INDEPENDENT_REPRODUCTION_PROTOCOL.md) and [Sessions 12–20 remaining-work status](CHRONOS_5_SESSIONS_12_20_REMAINING_WORK_STATUS_2026-11-26.md).
