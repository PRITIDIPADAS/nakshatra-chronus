# CHRONOS 5.0: 20-session implementation and research workflow

**Project category:** Physics  
**Flagship problem:** When SPHEREx appears to observe an infrared source changing, can the measured change be separated into astrophysical evolution, detector behaviour, calibration effects and wavelength-time sampling?

**Flagship system:** The Counterfactual Sky–Detector Twin.

This workflow turns the roadmap into twenty bounded ChatGPT development sessions. Each session should end with committed code or a concrete research artifact, tests, a short decision log, and an explicit list of unresolved assumptions. Do not ask a session to rebuild the whole project. Preserve the existing observatory and its P/D/A pipeline.

## Rules for every session

1. Work only in PRITIDIPADAS/nakshatra-chronus, on the active CHRONOS 5 feature branch until integration review.
2. Inspect current files before editing. Do not assume the previous session completed its work.
3. Preserve existing interfaces unless a migration is necessary and documented.
4. Put scientific calculations in the Python backend. The website calls the API and renders returned measurements; it must not maintain a second implementation of scientific methods.
5. Keep original archive inputs immutable. Every derived product records its inputs, code version, configuration and random seed.
6. Label every dataset as real, synthetic, illustrative or unverified. Never mix the labels.
7. Use unknown or not identifiable when evidence is insufficient. Never turn a relative model score into a calibrated probability.
8. No performance target may be invented. Measure the current baseline first, freeze the protocol, then evaluate the new method.
9. A test passing proves software behaviour, not that the astronomy is scientifically correct.
10. Do not claim novelty for Bayesian inference, image differencing, detector modelling, cross-matching, spectral reconstruction or information gain individually. Evaluate the validated SPHEREx-specific combination.

---

## Session 01 — Freeze the research question and scientific scope

**Goal:** Make the whole project answer one Physics question.

**Work**
- Audit the existing observatory, P/D/A pipeline, five-hypothesis engine, investigation engine, add-ons, research-discovery tools, static site and tests.
- Create a capability ledger: implemented, partly implemented, documented only, empirically verified, blocked.
- Define static source, moving source, achromatic variability, chromatic variability, transient, instrumental, mixed and unknown.
- Write measurement units, calibration assumptions, supported data products and scientific limits.
- Reconcile inconsistent release descriptions, laboratory counts, API paths and documentation claims.
- Record simulated classification accuracy and real QR3 injection recovery as separate quantities.

**Deliverables**
- docs/CHRONOS_5_RESEARCH_SPEC.md
- docs/CHRONOS_5_CAPABILITY_LEDGER.md
- A single authoritative project description in the README.

**Acceptance gate:** A new developer can identify the central question, current baseline, unknowns and next required measurement without relying on chat history.

**Session prompt**
> Audit the entire NAKSHATRA CHRONOS repository for the Physics problem of separating astronomical variability from detector and sampling effects. Preserve all existing working systems. Produce the research specification, capability ledger, model definitions, data requirements, limits and measurable acceptance criteria. Distinguish code that exists from results actually measured on real archive data. Do not add unrelated features.

## Session 02 — Establish the real-data archive manifest

**Goal:** Make every real-data experiment start from traceable source files.

**Work**
- Identify the exact SPHEREx release and product families used by each experiment.
- Preserve archive identifiers, product type, detector, observation time, processing version and native file URI.
- Hash each downloaded file and calibration product.
- Record source query, retrieval time, software version and processing configuration.
- Keep each exposure and matching calibration product in a named compatibility group.
- Make failed and incomplete downloads visible.

**Deliverables:** Versioned archive manifest schema, reproducible retrieval script, manifest validator, and a real-data manifest for a documented test field when actual files are available.

**Acceptance gate:** Another person can retrieve the same files and verify hashes and identifiers.

**Session prompt**
> Implement the archive manifest and retrieval workflow for exact SPHEREx products used by CHRONOS. Inspect the existing research_discovery scripts before changing them. Do not fabricate archive IDs, hashes or calibration matches. The manifest must retain original file identity, release, detector, observation time, product type, URI, byte count and SHA-256. Add tests for duplicate products, malformed hashes, missing fields and changed files.

## Session 03 — Native-MEF inspection and data-quality audit

**Goal:** Verify that the software reads actual multi-extension FITS products correctly.

**Work**
- Retrieve actual Level-2 MEFs and their associated calibration files.
- Inspect named HDUs, headers, shapes, units and WCS metadata.
- Confirm IMAGE, FLAGS, VARIANCE, ZODI, PSF and other required products.
- Check that image and variance arrays align and invalid values are masked.
- Inspect file history and instrument metadata.
- Preserve a machine-readable audit report and concise human-readable summary.

**Deliverables:** Native-MEF audit command, FITS structure tests using small fixtures, and real-file audit reports with original checksums.

**Acceptance gate:** At least one actual exposure is inspected and its structure independently checked. A synthetic FITS fixture is not a substitute.

**Session prompt**
> Execute the existing native-MEF inspection path on actual supplied SPHEREx archive files. Verify HDU names, units, array dimensions, headers, flags, variance, background, PSF and coordinate metadata. Add fail-closed checks for incompatible files. Save the audit report and preserve untouched source files. If a necessary file is unavailable, report the exact blocker instead of describing the workflow as completed.

## Session 04 — Calibration compatibility and science wavelength assignment

**Goal:** Prevent mismatched calibration products from entering the science pipeline.

**Work**
- Validate release, detector, pipeline version, processing date and coordinate frame.
- Confirm the correct CWAVE/CBAND calibration product for each spectral image.
- Reject display-grade wavelength information as a substitute for science wavelength assignment.
- Document flag meanings from actual product headers.
- Verify required pixel-area or solid-angle maps.
- Create a compatibility decision record for every exposure/calibration pair.

**Deliverables:** Calibration compatibility auditor, CWAVE/CBAND sampling tests, calibration compatibility matrix and failed-match report.

**Acceptance gate:** Every science measurement has an explicit and verified wavelength source and calibration group, or is rejected.

**Session prompt**
> Audit the SPHEREx calibration adapters. Confirm exact release, pipeline, detector, date and coordinate-frame compatibility for every exposure/calibration pair. Use CWAVE and CBAND for science wavelength assignment. Add tests for detector mismatch, release mismatch, wrong pixel grid, missing calibration, invalid wavelength and bandwidth values. Do not silently substitute WCS-WAVE or interpolate invalid calibration pixels.

## Session 05 — Sky-to-detector coordinate transformation

**Goal:** Make sky persistence and detector persistence measurable in the same investigation.

**Work**
- Trace existing WCS and alternate WCS A handling.
- Verify the relationship between cutout coordinates and native detector coordinates.
- Validate cutout origins, detector IDs, orientation and pixel transformations.
- Compare transformed coordinates with actual detector landmarks or known sources.
- Propagate positional uncertainty through the coordinate transform.
- Record residuals and unverified coordinate conventions.

**Deliverables:** A single tested coordinate-transform module, transformation residual report, and tests for cutout offsets, rotation, axes and detector mismatch.

**Acceptance gate:** Sky and detector coordinates are linked by a validated transform for the selected real observations.

**Session prompt**
> Inspect all existing sky, detector and WCS A transformations. Build one documented conversion path from registered sky coordinates to native detector coordinates and back. Preserve cutout origins and detector identity. Test rotations, offsets, edge pixels and incompatible frames. Use actual detector landmarks where available and report residuals. Do not claim detector persistence evidence until this transform is validated.

## Session 06 — Realistic source injection and photon-noise accounting

**Goal:** Correct the injection-to-reality gap without inventing detector constants.

**Work**
- Trace the exposure's calibrated image units and variance.
- Obtain the exposure-specific conversion from image units to expected electrons from verified instrument calibration.
- Inject the PSF-shaped source signal in correct detector and image units.
- Draw source Poisson noise in electron space.
- Transform the realization back into image units.
- Add the corresponding source shot-noise variance to the existing variance map.
- Preserve pixel phase, source position, detector zone, flags and source-exclusion region.
- Keep the deterministic path clearly labelled when gain conversion is unavailable.

**Deliverables:** Updated real-image injection implementation; tests for seeded reproducibility and variance update; per-field report with noise mode recorded.

**Acceptance gate:** A photon-noise injection is called physically modelled only when its exposure-specific conversion is supplied and documented.

**Session prompt**
> Audit both backend/inject.py and research_discovery/validation/injection_recovery.py. Implement source photon noise only through a verified exposure-specific electron conversion. Draw Poisson counts, convert back to image units and add the matching variance contribution. Retain a clearly marked deterministic option when the conversion is unavailable. Add tests for seeded reproducibility, variance increments, units, PSF normalization, bad-pixel handling and edge placement. Never invent a gain or exposure calibration.

## Session 07 — Four-baseline benchmark

**Goal:** Establish whether the Causal Sky Twin adds value beyond simpler systems.

**Required baselines**
1. SNR-only detection.
2. Existing CHRONOS P/D/A detection.
3. Existing instrument-forensics diagnostics.
4. The new Sky–Detector Twin.

**Work**
- Run all methods on the same fields, masks, truth catalogue and exposure set.
- Preserve scores and per-candidate detection provenance.
- Compare recovery at matched false candidates per field or matched completeness.
- Include unmatched detections and non-detections.
- Report exact thresholds and matching radius.
- Do not compare methods using different fields or truth sets.

**Deliverables:** Baseline comparison command, matched-comparison metrics and threshold curves, reproducible baseline report.

**Acceptance gate:** The benchmark compares all four baselines on the same input without silently changing the field or truth set.

**Session prompt**
> Build the four-baseline comparison for SNR-only, CHRONOS P/D/A, existing instrument forensics and the Sky–Detector Twin. Reuse current matching and validation utilities. Require common fields, masks, truth positions, matching radii and detection records. Report completeness, false candidates per field, precision, astrometric residuals and threshold curves. Add matched false-alarm and matched-completeness comparisons. Do not claim one method is better until the same real held-out fields have been processed.

## Session 08 — Blind benchmark protocol and field split

**Goal:** Prevent information leakage and threshold tuning on test fields.

**Work**
- Select independent sky fields with differing backgrounds, crowding and detector coverage.
- Split by entire field and, where needed, observation period.
- Freeze thresholds and configuration before unblinding.
- Keep injection locations, fluxes and truth labels hidden from the analysis runner.
- Include empty fields, negative controls, shuffled-time controls and detector-pattern controls.
- Record random seeds, holdout policy and truth-file access.

**Deliverables:** Preregistered benchmark protocol, blind truth store and unblinding script, field-level split manifest.

**Acceptance gate:** Test-field identities and injection truth are not available to the developer tuning the model.

**Session prompt**
> Turn the independent validation protocol into an executable blind real-field experiment. Define field-level splits, negative controls, injection strata and a frozen unblinding process. Keep truth positions and source properties hidden until the pipeline configuration is sealed. Add field-level uncertainty estimates. Do not random-split pixels or candidates from the same field across train and test.

## Session 09 — Pixel-level Sky–Detector forward model

**Goal:** Explain the measured exposure from a sky state and an instrument state.

**Model components:** Astronomical source position, motion, intrinsic brightness and spectrum; exposure time and wavelength response; PSF/ePSF and pixel integration; background and source shot noise; detector response, flags and missing pixels; calibration nuisance parameters; unexplained residual.

**Work**
- Start with a small, well-characterized exposure.
- Keep each input component separately inspectable.
- Preserve units through every transformation.
- Support mixed astrophysical and instrumental contributions.
- Keep raw inputs immutable.
- Record placeholders rather than presenting them as measured instrument parameters.

**Deliverables:** Forward-model module and synthetic tests, measurement decomposition report, documented instrument-parameter schema.

**Acceptance gate:** A controlled experiment can be reconstructed from supplied parameters without presenting generic settings as SPHEREx calibration.

**Session prompt**
> Build the pixel-level Counterfactual Sky–Detector Twin on top of the real calibration foundation. Implement the source image, PSF, wavelength response, background, source and detector noise, masks, calibration nuisance parameters and residual terms as separately inspectable components. Begin with a small number of well-characterized real exposures. Preserve all raw files. Do not claim generic simulator settings are calibrated SPHEREx detector physics.

## Session 10 — Joint inference and identifiability

**Goal:** Determine which parameters the available observations can actually constrain.

**Work**
- Define the joint sky/instrument parameter vector.
- Implement a likelihood using validated variance and covariance assumptions.
- Calculate the forward-model Jacobian or equivalent local sensitivity matrix.
- Detect rank deficiency, near-collinearity and parameter degeneracy.
- Propagate measurement uncertainty.
- Include an explicit no-decision state.
- Identify measurements that would break current degeneracy.

**Deliverables:** Identifiability auditor, joint model specification and inference interface, tests for identifiable, weakly identifiable, degenerate and not-identifiable cases.

**Acceptance gate:** The system distinguishes weak evidence from an intrinsically unidentifiable experimental design.

**Session prompt**
> Upgrade the initial design-matrix screen into an identifiability auditor for the calibrated forward model. Examine the Jacobian, singular values, parameter correlations and nuisance-parameter degeneracies. Classify each case as identifiable, weakly identifiable, degenerate or not identifiable with current observations. Explain which additional measurement would help. Keep relative BIC scores distinct from calibrated posterior probabilities.

## Session 11 — Falsification and posterior-predictive checks

**Goal:** Test the proposed explanation rather than merely rank it.

**Work**
- Compare static, moving, achromatic, chromatic, transient, instrumental and mixed models.
- Generate posterior-predictive or parametric-bootstrap measurements using validated noise assumptions.
- Plot residuals by time, wavelength, detector and source brightness.
- Run predeclared sky-only, detector-only and mixed interventions.
- Include search penalties for scanned transient windows and post-hoc selection.
- Keep contradictory and failed tests in the evidence record.

**Deliverables:** Model-comparison report, residual and predictive-check panel, counterfactual replay with immutable original measurements.

**Acceptance gate:** The leading model survives predeclared negative controls and predictive checks. Otherwise report unknown or model inadequacy.

**Session prompt**
> Integrate the competing physical models, predictive checks and counterfactual experiments into one investigation. Test sky-only, detector-only and mixed explanations against the same data. Account for searched event intervals and post-hoc selection. Show residuals by epoch, wavelength and detector. Preserve failed challenges and return unknown when no explanation survives. Do not call a model score a posterior probability unless calibration has been demonstrated.

## Session 12 — Spectrotemporal reconstruction and covariance

**Goal:** Reconstruct spectral history without hiding missing data or shared calibration errors.

**Work**
- Use source-specific calibrated F(lambda,t) observations.
- Retain observation timestamps and native sampling grid.
- Preserve missing channels and invalid pixels.
- Model shared calibration-group errors and covariance between observations.
- Separate overall brightness changes from wavelength-dependent changes.
- Display measured, inferred and unsupported regions differently.

**Deliverables:** Spectrotemporal reconstruction module, covariance model and validation tests, interactive wavelength-time view with clickable measurement provenance.

**Acceptance gate:** Every reconstructed value can be traced to input observations and uncertainty assumptions. No extrapolation is presented as measurement.

**Session prompt**
> Extend the source-specific spectral bridge into a calibrated F(lambda,t) reconstruction. Preserve native wavelength samples, observation times, missing channels, calibration groups and shared systematic errors. Implement and validate covariance propagation. Separate achromatic and chromatic changes. Make the heatmap, selected light curve, epoch spectrum and uncertainty view traceable to the original rows.

## Session 13 — Spectral feature evolution and resolution

**Goal:** Measure predeclared spectral features without overclaiming molecular identification.

**Work**
- Measure feature depth, equivalent width and continuum uncertainty.
- Include instrumental line-spread function or documented spectral resolution.
- Flag unresolved blends and overlapping continua.
- Track features across epochs and calibration groups.
- Compare to laboratory reference spectra only when units and resolution are compatible.
- Keep candidate interpretations separate from confirmed species identification.

**Deliverables:** Feature-evolution module, resolution and blending diagnostics, feature-specific report and uncertainty plots.

**Acceptance gate:** Every reported feature includes continuum choice, resolution, measurement uncertainty and blending limitations.

**Session prompt**
> Extend the existing equivalent-width measurement into a resolution-aware feature-evolution analysis. Compare continuum models, model the applicable line-spread function, flag blended bands and propagate uncertainty. Track only predeclared feature intervals across suitable epochs. Do not identify H2O, CO2, CO, CH3OH or OCN-minus from wavelength resemblance alone. Require supporting spectral evidence and independent review before a molecular claim.

## Session 14 — Probabilistic source identity network

**Goal:** Replace nearest-position matches with epoch-aware association evidence.

**Work**
- Propagate coordinates using proper motion and parallax where supported.
- Include position and motion uncertainties.
- Account for local source density and chance coincidence.
- Record survey epoch, angular resolution and wavelength compatibility.
- Keep multiple counterparts and no-counterpart probability visible.
- Do not force a single identity when evidence is ambiguous.

**Deliverables:** Astrometric propagation utilities, probabilistic counterpart association, source-observation graph and ambiguity view.

**Acceptance gate:** Output reports assumptions, uncertainty and competing matches; nearest neighbour is never labelled confirmed identity.

**Session prompt**
> Extend CHRONOS source association using epoch-propagated astrometry, proper motion, parallax when available, positional uncertainty, local density and chance-coincidence probability. Integrate only archives with a clear data-access and epoch policy. Present alternative counterparts and a no-match option. Keep positional association separate from physical identity.

## Session 15 — Candidate-specific next-best-observation planner

**Goal:** Recommend the observation that best distinguishes remaining physical explanations.

**Work**
- Generate forecasts from current competing models.
- Calculate expected information gain with uncertainty.
- Include wavelength availability and detector/array alternatives.
- Use actual visibility or archive-availability constraints from a verified external calculator.
- Explain why the recommendation separates hypotheses.
- Compare rankings under reasonable prior assumptions.

**Deliverables:** Candidate-specific forecast API, information-gain ranking and sensitivity analysis, feasibility source and timestamp record.

**Acceptance gate:** Planner recommends a measurement with a traceable physical forecast and explicit feasibility source. It does not claim to schedule or command a telescope.

**Session prompt**
> Connect the existing expected-information-gain planner to the candidate's fitted physical models. Generate predictions for later epochs, other wavelengths and independent partner-array measurements. Include uncertainty and real availability/visibility constraints. Explain which ambiguity each observation resolves. Show how the ranking changes under alternative priors. Do not invent observing windows or telescope control.

## Session 16 — Evidence graph and reproducible investigation package

**Goal:** Make every scientific statement traceable to original observations.

**Work**
- Link source files, calibration products, measurements, model versions, configurations and tests.
- Include evidence for and against each explanation.
- Preserve failed tests, residuals and unknown decisions.
- Hash the export package and verify it after download.
- Record code commit and software environment.
- Provide a reproduction command and machine-readable report.

**Deliverables:** Claim-to-measurement graph, reproducible investigation package, verification command and documentation.

**Acceptance gate:** A second user can reproduce the same analysis from original inputs and recorded configuration. A hash is described as integrity checking, not proof of authorship or scientific truth.

**Session prompt**
> Extend the evidence passport into a claim-to-measurement provenance graph. Link archive files, calibration versions, source measurements, uncertainties, models, counterfactuals, failed tests and conclusion status. Include code commit and environment. Export a package another researcher can reproduce. Add tamper detection and explicit limitations. Do not present SHA-256 as proof of identity or scientific validity.

## Session 17 — Four-workspace website and scientific visualisation

**Goal:** Make the full research method understandable and usable without adding unrelated laboratories.

**Four workspaces**
1. Causal investigation.
2. Spectral evolution.
3. Cosmic identity network.
4. Experimental observatory.

**Visuals to complete**
- Linked sky-coordinate and detector-coordinate trajectory braid.
- Observation timeline with exposure selection.
- Measurement decomposition: source, detector, background and residual.
- Competing explanation chamber with data and model predictions.
- Time-wavelength heatmap with gaps visibly missing.
- Identity network with uncertainty-labelled edges.
- Information-gain landscape.
- Evidence lineage graph.

**Controls**
- Candidate search and filters.
- Compare two investigations.
- Save a candidate shortlist.
- Share candidate selection in the URL.
- Export CSV, JSON and figures.
- Download evidence packages.
- Tooltips, scientific units, keyboard access and responsive layouts.
- Persistent real/synthetic/unverified labels.

**Deliverables:** Four linked workspaces inside the existing site, shared interaction and visual components, API-only science rendering.

**Acceptance gate:** All interactive results are returned by the Python API, and every view exposes its data class and limitations.

**Session prompt**
> Finish the CHRONOS website around the four workspaces: Causal Investigation, Spectral Evolution, Cosmic Identity Network and Experimental Observatory. Preserve the classic observatory. Build the linked sky/detector trajectory, exposure timeline, measurement decomposition, hypothesis chamber, spectral-time surface, identity network, information-gain landscape and evidence graph. Add candidate search, filters, comparison, URL state, exports, tooltips and keyboard access. The frontend must render Python API outputs rather than reimplement scientific methods. Every page must distinguish real data, synthetic data and unverified inputs.

## Session 18 — Execute the blind real-data evaluation

**Goal:** Measure whether the new method improves the baseline.

**Work**
- Run frozen protocol on actual calibration-compatible real fields.
- Unblind only after analysis configuration is sealed.
- Compare all four baselines at matched false-alarm rate or completeness.
- Report completeness versus flux, false candidates per field, flux bias, astrometric residual, uncertainty coverage, calibration, OOD behaviour and field transfer.
- Report field-level variation and uncertainty.
- Run ablations to establish which additions contribute.
- Preserve null or negative results.

**Deliverables:** Reproducible real-data benchmark, per-field metrics and confidence intervals, ablation report and unblinding record.

**Acceptance gate:** The new model demonstrates measurable value on unseen real fields, or the project reports that it did not outperform simpler methods.

**Session prompt**
> Execute the preregistered blind benchmark on actual held-out SPHEREx fields. Do not change thresholds after unblinding. Compare SNR-only, P/D/A, existing forensics and the Sky–Detector Twin under matched false-alarm rate or completeness. Report all predefined metrics, field-level uncertainty, ablations, failures and data provenance. Do not omit negative results or describe a synthetic run as a real benchmark.

## Session 19 — One population-level Physics investigation

**Goal:** Use the validated method for one carefully selected scientific question.

**Candidate science case**
- Suitable young stellar objects, only if real observations contain enough independent epochs, usable wavelength coverage and signal-to-noise.
- Possible question: do infrared brightness changes coincide with measured evolution in predeclared ice-feature intervals?

**Work**
- Inspect archive coverage before selecting the sample.
- Define inclusion and exclusion rules.
- Estimate completeness and null rates.
- Freeze the question and analysis plan before examining outcomes.
- Correct for the survey selection function.
- Report sensitivity to calibration, source identity and feature-definition assumptions.

**Deliverables:** Preregistered population protocol, selection-corrected sample and result, scientific interpretation with alternatives and limitations.

**Acceptance gate:** Report a result only if data support the sample and selection model. Otherwise document why the study is not yet feasible.

**Session prompt**
> Evaluate one population-level Physics question using the validated CHRONOS pipeline. First inspect actual archive coverage, cadence, wavelength sampling and signal-to-noise. Choose a sample only if the data support it. Define selection, exclusions, completeness, null controls and analysis before measuring the outcome. Do not start several unrelated population studies. A null or infeasible result is acceptable.

## Session 20 — Independent reproduction, paper and release

**Goal:** Turn the work into a reviewable research contribution.

**Work**
- Prepare a technical paper with method, data, calibration, validation and limits.
- Include four-baseline results and ablations.
- Publish benchmark protocol and reproducibility package where data licences permit.
- Prepare a 90-second demonstration with one real candidate, if one passes the evidence gates.
- Show original observation, sky and detector coordinates, competing models, falsification, next measurement and evidence package.
- Obtain independent review from an astronomy researcher before making discovery or instrument-performance claims.
- Tag a release only when software tests and empirical acceptance gates are complete.

**Deliverables:** Technical paper draft, public reproducibility package, final website and demonstration, versioned release and changelog.

**Acceptance gate:** Another researcher can inspect data, calibration, code, thresholds, measurements and failed tests and reproduce the stated result.

**Session prompt**
> Prepare the CHRONOS 5.0 research release. Write the technical paper from measured results, not planned features. Include data provenance, calibration checks, model assumptions, four-baseline comparisons, blind-field validation, ablations, limitations and null results. Prepare the 90-second demonstration around one real candidate only if it passes validation gates. Package the inputs and configuration for independent reproduction. Do not claim a discovery or novelty beyond the evidence.

---

## Cross-session integration checkpoints

| Checkpoint | Must be true before proceeding |
|---|---|
| After 01 | One Physics question and one source of truth for project status |
| After 04 | Compatible real data and calibrated wavelength assignment |
| After 06 | Injection noise assumptions are explicit and physically parameterized |
| After 08 | Held-out fields and truth records are frozen |
| After 11 | Inference, identifiability and falsification operate on the same measurement model |
| After 13 | Spectral features retain resolution, continuum and uncertainty limits |
| After 16 | A candidate can be reproduced from its evidence package |
| After 18 | Real-data performance is measured against all four baselines |
| After 20 | An independent researcher can reproduce the stated result |

## Sessions 07–11 implementation status

The implementation-to-evidence mapping, code entry points, test boundaries and outstanding scientific acceptance gates are tracked in [the Sessions 07–11 implementation status note](CHRONOS_5_SESSIONS_07_11_IMPLEMENTATION_STATUS_2026-11-25.md). Treat the note as a status snapshot, not as a substitute for the per-session acceptance criteria below.

## What must not be rushed

The user interface can be built while the scientific backend is being validated, but an attractive visual cannot substitute for calibration or empirical evidence. The highest-risk work is exact archive/calibration compatibility, source-noise conversion, detector-coordinate transform and blind real-field benchmark. If these are not complete, the website should say so plainly.

## Judge-facing demonstration

The demonstration should follow one candidate from raw observation to a cautious conclusion:

1. Open an actual SPHEREx observation and show its release, detector, timestamp, wavelength and calibration provenance.
2. Show why the apparent change is scientifically ambiguous.
3. Link the sky-coordinate and detector-coordinate tracks.
4. Compare static, moving, variable, transient, instrumental and mixed explanations.
5. Open the identifiability result and show what the current data cannot separate.
6. Run one predeclared counterfactual and inspect the residuals.
7. Show the next measurement with the highest expected information gain.
8. Export the evidence graph and reproduce the same result.

**Core statement:** CHRONOS does not just ask whether the sky changed. It tests whether the sky is the only explanation that survives.


## Evidence refresh — 25 November 2026

The current repair-branch validation is recorded in [CHRONOS 5 empirical status](CHRONOS_5_EMPIRICAL_STATUS_2026-11-25.md). Latest evidence: workflow #888 passed 314 tests with 7 warnings, both JavaScript syntax checks and the M101 archive/native-audit/artifact-upload job; workflow #17 completed the six-field exploratory D2 calibrated-Jy pilot (6/6 fields, 20/20 checks per field); workflow #36 completed the six-region SPLICES/DR1/QR3 reconnaissance and candidate inventory. The corresponding reports are [M101](SPHEREX_M101_DR1_D2_REAL_DATA_PILOT_2026-11-25.md), [six-field Jy pilot](SPHEREX_MULTIFIELD_JY_REVALIDATION_2026-11-25.md) and [SPLICES/DR1 reconnaissance](SPHEREX_SPLICES_DR1_RECON_2026-11-25.md).

These runs do not satisfy independent gain-calibration review, the custodian-controlled blind four-method benchmark, source-level SPHEREx exposure/epoch association, a selection-function- and contamination-aware YSO population result, independent astronomical reproduction or scientific release. Source-to-exposure linkage remains unavailable in all six regions; the All-Sky Cube inventory query reached its 1,000-row cap. Do not convert these limitations into zero measurements or passed gates.


## Evidence refresh — 25 November 2026 (run #38)

The current successful SPLICES/DR1/QR3 workflow is [#38](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648715196). Its checksummed artifact contains 2,421 candidate-source summaries, 924,443 geometric SIAv2 candidate–product polygon pairs, 6,214 Level-2 spectral-image metadata rows and 32 distinct All-Sky Cube metadata tiles across the six searched field cones. The local source matcher is spherical point-in-polygon over SIAv2 s_region metadata; these matches do not establish extracted flux, spectrum quality, validated epochs or cadence. The cube metadata are complete for the six selected cones only, not for the all-sky universe; no native cube data were downloaded.

The latest combined test/M101 workflow [#896](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648715416) passed 316 tests with 12 warnings, both JavaScript syntax checks and the M101 retrieval/native-audit/artifact-upload job. The test-only workflow [#897](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648724365) passed 316 tests with 7 warnings and both JavaScript syntax checks. Independent gain-calibration review, blind four-method benchmark, selection-aware YSO population analysis, independent astronomical reproduction and validated release remain open.
