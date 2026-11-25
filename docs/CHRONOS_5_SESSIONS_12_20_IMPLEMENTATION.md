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

## Remaining empirical work

No compatible real SPHEREx sample was downloaded or reprocessed as part of this software change. No blind held-out real-field evaluation, YSO population inference, independent review or paper submission has been performed here. The website may be used with real data only when the wavelength/calibration provenance gates pass; synthetic tests validate software behaviour, not astronomy performance.
