# CHRONOS 5.0 — Sessions 07–11 implementation and evidence status

**Review date:** 25 November 2026  
**Branch:** `chronos-5-causal-sky-twin`  
**Scope:** software implementation, reproducibility contracts and the boundary between software tests and scientific acceptance.

This note separates three things that must not be conflated: implemented software, successful synthetic/contract tests, and empirical scientific acceptance. A green test suite does not establish real-data superiority or a discovery.

## Session 07 — Four-baseline comparison

**Implemented**
- `backend/chronos_benchmark/adapters.py` builds SNR-only, CHRONOS P/D/A, instrument-forensics and supplied Sky–Detector Twin detection records from one prepared pipeline state.
- The adapter verifies exposure IDs, mask checksum and registered WCS checksum. The four method records carry the same field input signature.
- `backend/chronos_benchmark/runner.py` enforces a common truth catalogue and input signature, evaluates threshold curves, reports completeness and false candidates, and emits astrometric/flux summaries when their inputs are available.
- Field-group bootstrap intervals and paired Twin-versus-comparator intervals are implemented. Matched operating points use the supplied threshold grid and do not interpolate detections.

**Boundary**
- The adapter accepts Sky–Detector Twin detections from the caller; it does not independently prove that a production Twin detector ran on every field.
- A populated evaluator package is not a real benchmark. The actual four methods still need to be executed on the same independent, real, held-out fields with a predeclared threshold grid and complete provenance.

## Session 08 — Sealed blind benchmark

**Implemented**
- `backend/chronos_benchmark/blind.py` creates field-level blind splits, opaque field/exposure tokens, encrypted truth storage, and a frozen configuration/dataset digest.
- The truth-free handoff validates that every held-out token appears exactly once and that each method uses the same frozen field signature, masks, WCS and thresholds.
- `backend/chronos_benchmark/custodian_attestation.py` verifies a detached custodian signature against a separately pinned public-key digest. Unblinding is blocked when independent custody is absent or invalid.

**Boundary**
- Test fixtures prove rejection of altered manifests, configuration drift and missing attestations. They are not an independent custodian, real preregistration, or a completed blind SPHEREx experiment.
- The real held-out truth must remain sealed until an external custodian has frozen the protocol, run the detection handoff and signed the unblinding receipt.

## Session 09 — Spectral pixel forward model

**Implemented**
- `backend/chronos_causal/pixel_forward.py` accepts explicit wavelength grids/bandwidths, spatial response, pixel-sampled ePSF, source spectra and positions/motions, flat field, background, dark current, read noise, fixed detector terms, flags and missing-pixel masks.
- The model keeps source, background, dark, detector-fixed, Poisson, read-noise, variance and residual maps separate. It labels the output as a synthetic controlled experiment and tracks every parameter as measured, calibrated, assumed, illustrative or placeholder.
- Source motion is now integrated across the finite exposure with configurable uniform midpoint quadrature (1–101 substeps). The default of one substep preserves instantaneous-position behavior for compatibility.
- The HTTP `/api/v5/causal/forward-exposure` route exposes the motion integration control.

**Boundary**
- This is not a SPHEREx raw-readout simulator. It does not yet model a complete calibrated detector response including nonlinear readout, saturation, correlated noise, spatially varying PSFs or a verified time-dependent throughput. The supplied PSF is spatially constant and subpixel shifted with bilinear weights.
- The M101 Jy injection pilot is a separate archive-data evaluation; it does not turn generic simulator defaults into measured SPHEREx coefficients.

## Session 10 — Identifiability and inference

**Implemented**
- `backend/chronos_causal/identifiability.py` includes finite-difference Jacobians, covariance whitening, SVD rank/condition analysis, near-collinearity and sky/instrument nuisance-pair diagnostics, null-space directions and proposed additional-measurement comparisons.
- Full measurement covariance must now be finite, symmetric and positive definite before Cholesky whitening. Diagonal variance vectors must be finite and positive.
- `backend/chronos_causal/inference.py` compares measurement-level static, variable, moving, transient, instrumental and mixed explanations with explicit abstention conditions.

**Boundary**
- Identifiability is local to the supplied forward model and covariance. It does not prove global identifiability or calibration validity.
- BIC differences are relative model-selection scores, **not posterior probabilities**. The ordinary measurement-level BIC report must not be described as Bayesian posterior evidence.

## Session 11 — Falsification and predictive checks

**Implemented**
- `backend/chronos_causal/falsification.py` combines grouped residual checks, conditional parametric-bootstrap challenges, model competition and predeclared sky/detector/mixed counterfactuals.
- Transient scans correct across searched time intervals. Candidate-family maximum-statistic tests require an explicit completeness declaration before returning a candidate-selection-adjusted result.
- Missing uncertainty validation, incomplete candidate families and failed predictive checks produce unknown/blocked outcomes rather than an automatic astrophysical verdict.

**Boundary**
- The parametric bootstrap is conditional on the supplied null predictions, uncertainty model and declared candidate family. It is **not** a full Bayesian posterior-predictive analysis of the joint sky, detector and calibration model.
- Counterfactuals alter measurement-level rows; they do not by themselves rerender archive-native pixels or establish causal truth.
- A failed/contradictory challenge must remain visible in the final evidence package.

## Current implementation tests and real-data evidence

The latest fully completed CI + archive-audit run verified before the strict six-field final-exit hardening is workflow [45638162464](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45638162464). Its test job passed **304 tests with 12 warnings**; both JavaScript syntax checks passed. The companion PR run [45638182131](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45638182131) passed **304 tests with 2 warnings**. The push workflow also completed the live M101 DR1 D2 retrieval, the fail-closed archive-evidence validator and artifact upload successfully.

The M101 artifact from that run records:
- One SPHEREx DR1 D2 Level-2 science MEF, 2040 × 2040 pixels, 113.5826 s, observation ID `2025W19_2B_0346_1`, exposure time 2025-05-10, FITS pipeline version `7.0.5`.
- Fourteen archive `spherex.provenance_input` rows for the science plane. Spectral-WCS and absolute-gain products have exact direct input links; the solid-angle map is explicitly recorded as a same-release/same-detector supplemental area map, not falsely labelled a direct input.
- Native science, spectral-WCS, absolute-gain and solid-angle products have retained byte counts and SHA-256 hashes. Compatibility checks report `compatible`; 175 invalid absolute-gain pixels remain masked and are not interpolated.
- A one-exposure local Jy injection pilot with 20 injections at each of 0.5×, 1× and 2× the local 5σ reference recovered 5/20, 14/20 and 17/20, respectively. The absolute-gain-derived electron conversion and source-Poisson variance are enabled for this exploratory pilot, but the conversion record remains `derived_pending_independent_review`.

The fresh CI artifact is run 45638162464, artifact 15033532053 (`spherex-m101-dr1-d2-audit`), 91,213,913 bytes. Its uploaded ZIP SHA-256 is `bfc7f21895f8192abc7ed70b1e95ea0af7ea8e331b7b67f06987db34fc0218be`. I downloaded and inspected that exact ZIP: it contains the 64,800,000-byte native science MEF, 33,312,960-byte spectral-WCS file, 16,652,160-byte absolute-gain matrix, 16,652,160-byte solid-angle map, native MEF audit, source-Poisson Jy report and archive manifest. The artifact retains the same file SHA-256 values recorded in the report. The run's explicit validator output confirms the calibration/provenance and 3×20 injection checks; the electron conversion remains pending human review.

The source-Poisson pilot is not blind: injection positions and seed are visible to the run, the evaluation is local to one exposure, and it is not the Session 07 four-method comparison. The detailed report and artifact hashes are in [the M101 real-data pilot note](SPHEREX_M101_DR1_D2_REAL_DATA_PILOT_2026-11-25.md).

## Six-region calibrated-Jy result — evidence-qualified status

Workflow [#17 / run 45637115746](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45637115746) completed all six predeclared D2 fields. The machine report confirms six unique observations, six unique native science hashes and 20/20 successful eligibility checks in each field (120/120 checks). Artifact 15034299164 has ZIP SHA-256 `96ff0c2025d098ebb3d63d64bd1361aabdeb2c4830920227a53ce53364c01afb`; the embedded report digest is `cfd0ce32a6ce5f8206a64ebb6927cc186784259af2914b846bd633d5a74e626e`. Full recovery data and limits are in [the six-region report](SPHEREX_MULTIFIELD_JY_REVALIDATION_2026-11-25.md).

This completes the exploratory six-field injection/recovery workflow only. Gain-to-electron conversion still requires independent instrument/calibration review, and the Session 07/08 four-baseline blind benchmark remains unsatisfied. Lupus III is retained as a critical adverse result: 0/20 recoveries at each of 105.579, 211.158 and 422.317 µJy, including twice its local nominal 5σ reference. Investigate local background, masks, ePSF/matched-filter response and detection behaviour before drawing a sensitivity conclusion.

## Current repair-branch CI — 25 November 2026

Workflow [#888 / run 45641583358](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45641583358) passed **314 tests with 7 warnings**, including both JavaScript syntax checks. Its M101 real-field job also completed archive retrieval, native compatibility audit, machine-readable evidence validation and artifact upload. This validates code and evidence handling, not human calibration review or blind scientific acceptance.

## Acceptance gates that remain open

| Gate | Status |
|---|---|
| Session 07 software adapters/evaluator and common-input tests | Implemented; synthetic/contract tests only |
| Session 08 sealed handoff and cryptographic custodian checks | Implemented; no independent real-field custodian run |
| Session 09 explicit spectral pixel forward simulation | Implemented as a controlled synthetic model; not a validated SPHEREx raw-readout model |
| Session 10 local Jacobian/SVD identifiability and covariance checks | Implemented; depends on supplied model and covariance |
| Session 11 falsification, interval correction and complete-family gate | Implemented; conditional checks, not full joint Bayesian PPC |
| Calibration review for M101 gain-to-electron conversion | Pending independent human review |
| Multi-field calibration-compatible injection evaluation | Completed exploratory run #17; 6/6 fields passed all 20 runner checks; gain conversion review pending |
| Four-baseline blind benchmark on actual held-out SPHEREx fields | Not satisfied |
| Population-level YSO discovery | Not satisfied |
| Independent astronomical reproduction/review | Not satisfied |
| Validated scientific release | Not satisfied |

A workflow validator can prove that the expected artifacts exist and that their hashes match; it cannot sign off on an instrument calibration, substitute for independent custody, or change any open scientific acceptance gate.
