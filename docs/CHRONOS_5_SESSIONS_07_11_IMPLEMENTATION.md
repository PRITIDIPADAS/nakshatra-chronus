# CHRONOS 5.0 Sessions 07–11 implementation notes

**Scope:** four-baseline evaluation, field-level blind validation, a controlled pixel forward model, Jacobian identifiability and falsification.

**Status:** software implementation on the chronos-5-causal-sky-twin branch. This document does not claim that Sessions 07–11 have passed their empirical acceptance gates. The benchmark still needs the same calibrated real exposures, independently prepared truth, and genuinely held-out sky fields for all four methods.

## Implementation status

| Session | Implemented in this branch | Not established yet |
|---|---|---|
| 07 | Common-input benchmark package, SHA-256 checks, four detector records, threshold curves, matched operating points, field-bootstrap intervals, match provenance, unmatched detections and missed truth IDs | No complete four-method result on the same real held-out SPHEREx fields |
| 08 | Whole-field split, optional shared split-group IDs, opaque field tokens, authenticated encrypted truth store, frozen configuration, unblinding checks and negative-control labels | An independent custodian must hold the key; real fields, controls and injection truth still need to be prepared |
| 09 | Generic pixel-level spectral exposure model with separately returned components, explicit units, supplied PSF/response, background, dark current, read noise, masks, fixed detector term, nuisance parameters and provenance | Not a calibrated SPHEREx detector model; no real exposure is reconstructed by default |
| 10 | Finite-difference Jacobian helper, whitened local sensitivity matrix, singular values, rank, condition number, near-collinearity, nuisance degeneracies and candidate extra-measurement tests | The result is only as good as the chosen forward model, derivatives and validated covariance |
| 11 | Grouped residuals, conditional parametric-bootstrap diagnostics, family-wise transient-window scan, predeclared sky/detector/mixed measurement interventions and fail-closed verdict | Not a full posterior predictive sampler; current counterfactual interventions operate on measurements, not raw FITS pixels |

The existing CHRONOS P/D/A implementation, measurement-level hypothesis engine and original detector simulator remain available. No existing pipeline is silently replaced.

---

## Session 07 — Common-input four-baseline comparison

### Baselines

1. **SNR-only:** positive matched-filter peaks in the existing field pipeline DEEPS map.
2. **CHRONOS P/D/A:** candidates returned by the existing P/D/A pipeline.
3. **Instrument forensics:** the same P/D/A candidate list after the existing transparent forensic diagnostics. Forensics is a triage/veto layer, not an independent source finder.
4. **Sky–Detector Twin:** detections exported by the causal analysis for the identical field and exposure set.

The adapter is in **backend/chronos_benchmark/adapters.py**. Use **field_mask_sha256(state)** and **reference_wcs_sha256(state["ref"])** to construct the verified common-input signature. Call **pipeline.run(...)** once per field, then pass that one state to **build_benchmark_field_record(...)**. This returns the complete field row, including truth, split, matching radius and all four methods. Supply Twin detections from the causal analysis of that same field. The adapter returns the input signature with each method record. It preserves each detection's score semantics and evidence provenance.

Example Python integration:

~~~python
from chronos_benchmark.adapters import (
    build_benchmark_field_record, field_mask_sha256, reference_wcs_sha256,
)
from chronos_benchmark.runner import truth_catalogue_digest

truth_catalogue = [
    {"truth_id": "inj-0001", "x": 501.2, "y": 722.6, "flux_bin": "faint"},
]
signature = {
    "field_id": "field-001",
    "dataset_class": "real",
    "exposure_ids": ["archive-product-id-a", "archive-product-id-b"],
    "mask_sha256": field_mask_sha256(field_state),
    "truth_catalogue_sha256": truth_catalogue_digest(truth_catalogue),
    "coordinate_frame": "sky",
    "coordinate_unit": "pixel",
    "pixel_wcs_sha256": "<SHA256 of the registered field WCS header>",
    "pipeline_input_sha256": "<SHA256 of the immutable prepared field inputs>",
}
thresholds = {
    "snr_only": [12, 10, 8, 6, 5],
    "chronos_pda": [12, 10, 8, 6, 5],
    "instrument_forensics": [12, 10, 8, 6, 5],
    "sky_detector_twin": [12, 10, 8, 6, 5],
}
field_record = build_benchmark_field_record(
    field_state,
    signature,
    truth_catalogue,
    split="development",
    independence_group_id="field-001",
    match_radius=2.0,
    sky_detector_twin_detections=twin_detections,
    score_thresholds=thresholds,
)
~~~

The example IDs, match radius, and thresholds are placeholders, not real archive identifiers or recommended scientific values. Replace them only with the real field manifest and thresholds frozen for the experiment. Append each returned field_record to the package's fields list and use the same root score_thresholds for every field.

### Package format

Save all fields together in one JSON package. The complete example schema is shown below. For clarity, repeated method signatures are abbreviated in the example; in the actual file each method must carry the complete, identical field signature.

~~~json
{
  "schema": "chronos-four-baseline-package/1.0",
  "benchmark_id": "real-heldout-run-001",
  "score_thresholds": {
    "snr_only": [12, 10, 8, 6, 5],
    "chronos_pda": [12, 10, 8, 6, 5],
    "instrument_forensics": [12, 10, 8, 6, 5],
    "sky_detector_twin": [12, 10, 8, 6, 5]
  },
  "matched_target": {
    "false_candidates_per_field": 0.5,
    "completeness": 0.8
  },
  "fields": [
    {
      "split": "blind_test",
      "match_radius": 2.0,
      "field_area_deg2": 0.01,
      "input_signature": {
        "field_id": "opaque-field-token",
        "dataset_class": "real",
        "exposure_ids": ["opaque-exposure-a", "opaque-exposure-b"],
        "mask_sha256": "<64 lowercase hex characters>",
        "truth_catalogue_sha256": "<digest from truth_catalogue_digest>",
        "coordinate_frame": "sky",
        "coordinate_unit": "pixel",
        "pixel_wcs_sha256": "<SHA256 of the registered field WCS header>",
        "pipeline_input_sha256": "<64 lowercase hex characters>"
      },
      "truth_catalogue": [
        {"truth_id": "opaque-truth-001", "x": 501.2, "y": 722.6}
      ],
      "methods": {
        "snr_only": {
          "input_signature": {"field_id": "same complete signature as the field"},
          "detections": [
            {
              "detection_id": "snr-001",
              "x": 501.4,
              "y": 722.5,
              "score": 7.2,
              "provenance": {"map": "DEEPS", "score_definition": "matched-filter S/N"}
            }
          ]
        },
        "chronos_pda": {"input_signature": {"field_id": "same complete signature"}, "detections": []},
        "instrument_forensics": {"input_signature": {"field_id": "same complete signature"}, "detections": []},
        "sky_detector_twin": {"input_signature": {"field_id": "same complete signature"}, "detections": []}
      }
    }
  ]
}
~~~

Required signature fields are field ID, dataset class, exact exposure ID list, mask checksum, truth catalogue checksum, coordinate frame and coordinate unit. Sky positions expressed in pixels also require the WCS checksum. Include immutable pipeline-input and calibration-manifest checksums whenever available. The complete signature is compared for every method, so additional provenance keys are also enforced. Truth coordinates and IDs are hashed in deterministic canonical order.

The truth catalogue includes a unique truth ID and finite x/y coordinates in the declared frame. A detection includes a unique detection ID, finite x/y and score, and non-empty provenance. Detection lists may be empty. Empty fields may have an empty truth catalogue.

The four outputs and truth catalogue are in the registered field WCS pixel frame produced by the single pipeline.run state, not the native detector grid. Use coordinate_frame="sky", coordinate_unit="pixel" and the SHA-256 returned by adapters.reference_wcs_sha256(state["ref"]). The adapter verifies the actual exposure IDs, combines each exposure's bad-pixel, out-of-footprint and invalid-image masks, computes adapters.field_mask_sha256(state), and rejects a signature whose exposure, mask or WCS checksum does not match the prepared field. The matching radius is mandatory per field and expressed in the declared coordinate unit. Matching is one-to-one: one truth source cannot explain two detections. Every threshold row retains matched detections, unmatched detections, missed truth IDs, precision, completeness, Wilson intervals and astrometric residuals. It also reports pooled metrics by control_type and by each named injection_stratum dimension, so empty-field false candidates and detector/shuffled-time control behaviour are not hidden in the science-field average. Threshold curves and operating-point summaries are returned per method. Whole-field bootstrap intervals are calculated independently at each supplied threshold.

The matched target can request false candidates per field, completeness, or both. Each method is assigned the nearest observed threshold for each target. The report records the actual value and distance from target; it does not interpolate detections or imply exact equality. Use a dense, preregistered threshold grid if the operating point is important.

Run the report:

~~~bash
python scripts/chronos_benchmark.py compare \
  --package benchmark/heldout_package.json \
  --output benchmark/reports/heldout_report.json \
  --draws 5000 \
  --seed 20261125
~~~

The endpoint **POST /api/v5/benchmark/compare-package** accepts the same package. The older **POST /api/v5/benchmark/baselines** endpoint remains for compatibility, but it does not enforce the richer common-input signature. Use compare-package for the acceptance gate.

The report sets scientific-claim eligibility to true only when every included field is declared real and every field is marked blind_test or held_out. This is an eligibility check, not proof of scientific validity. It does not declare a winner.

---

## Session 08 — Blind field split, sealed truth and unblinding

### Field selection and controls

Prepare one independent row per field. Do not split exposures, pixels or candidates from the same field across development and test. If several rows are related observation periods from the same sky region, assign them the same split_group_id; they will stay in one split and are represented by the same opaque independence_group_token. The benchmark's field bootstrap resamples that group as a single independent unit. Field-level results also carry the control type and injection strata so the report can isolate empty-field, shuffled-time and detector-pattern false alarms. Otherwise the field ID is the default split group.

Each field row contains:

- field_id
- split_group_id where related periods must stay together (private custodian field; converted to an opaque shared token in the public run manifest)
- control_type: science, empty_field, negative_control, shuffled_time_control or detector_pattern_control
- optional injection_stratum, such as flux, background, crowding, detector zone and wavelength bin
- input_signature
- truth_catalogue
- optional non-public data_locator_token, matching the custodian's external locator table

The control label, injection strata and source properties remain in the encrypted truth store. The public analysis manifest uses opaque field, exposure and independent-group tokens. After unblinding, the report restores control_type and injection_stratum and emits per-threshold summaries for each control and injection stratum. Empty fields should have an empty truth catalogue. Shuffled-time and detector-pattern control data must be created from real inputs according to a recorded, predeclared recipe. Do not label a random synthetic noise image as a real negative control.

### Create the sealed package

Install dependencies, then let an independent custodian run:

~~~bash
python scripts/chronos_benchmark.py seal \
  --fields benchmark/custodian/field_truth_records.json \
  --output-dir benchmark/blind_public \
  --key-file ../chronos-secrets/chronos-blind-fernet.key \
  --test-fraction 0.3 \
  --seed 17
~~~

The key path must be outside this repository. The command refuses a key path inside the repository. Keep the key with the independent custodian, not the person tuning the model. Share only public_manifest.json and run_manifest.json with the analysis runner. Keep truth_store.enc with the custodian until unblinding. The encrypted store is authenticated ciphertext, but the key must never be committed or placed in the analysis environment.

The public manifest includes a checksum of the encrypted truth store and a key fingerprint. The run manifest has opaque tokens, split roles and checksums but not the original field IDs or truth positions. The encrypted store contains the private split manifest, original field identities, truth labels and truth catalogue.

### Freeze the exact run configuration

Create a JSON configuration containing all four method threshold arrays, the matched operating-point target, matching radii keyed by opaque field token, source and calibration choices, noise assumptions, model version, seeds, control recipes and exclusions. The three benchmark policy fields are mandatory: score_thresholds, matched_target and matching_radii_by_field. Do not tune on held-out fields. Freeze it against the exact public manifests and source commit:

~~~bash
python scripts/chronos_benchmark.py freeze \
  --public-manifest benchmark/blind_public/public_manifest.json \
  --run-manifest benchmark/blind_public/run_manifest.json \
  --configuration benchmark/config/frozen_config.json \
  --commit <FULL_GIT_COMMIT_SHA> \
  --output benchmark/blind_public/frozen_configuration.json
~~~

The returned configuration checksum is the run seal. The detector-run JSON must carry the same configuration object, its checksum, dataset digest, source commit, full public run manifest, exact method threshold lists, matched targets, matching_radii_by_field and the four method records for every held-out token. Unblinding recomputes the public-manifest digest and verifies that the separately reported thresholds, matched target and radii equal the frozen configuration. It must contain each held-out token once and no development tokens. Every method must carry the exact public signature used by that field.

### Unblind only after sealing

The custodian runs this command after the analysis outputs and configuration are frozen:

~~~bash
python scripts/chronos_benchmark.py unblind \
  --public-manifest benchmark/blind_public/public_manifest.json \
  --run-manifest benchmark/blind_public/run_manifest.json \
  --truth-store benchmark/blind_public/truth_store.enc \
  --key-file ../chronos-secrets/chronos-blind-fernet.key \
  --frozen-configuration benchmark/blind_public/frozen_configuration.json \
  --detection-run benchmark/results/frozen_detection_run.json \
  --output benchmark/reports/blind_unblinded_report.json \
  --draws 5000 \
  --seed 20261125
~~~

Unblinding rejects a changed ciphertext, invalid freeze seal, changed dataset digest, mismatched commit, changed configuration, changed method signatures, missing held-out tokens or duplicate tokens. Only after these checks does it decrypt the truth and evaluate held-out fields.

The software can enforce cryptographic integrity and field grouping. It cannot establish independence if the custodian and developer collude, if the developer has already seen the truth, or if the custodian's source field mapping is wrong. Real blindness requires a genuinely independent custodian.

---

## Session 09 — Pixel-level Sky–Detector forward model

Endpoint: **POST /api/v5/causal/forward-exposure**.

Python entry point: **chronos_causal.pixel_forward.simulate_spectral_exposure**.

One call models a small synthetic exposure. It needs a 2-D image shape, MJD, exposure time, strictly increasing wavelengths, channel bandwidths, wavelength-response cube, source list and PSF kernel. A source specifies pixel position, reference epoch, motion in pixels per day and spectral rates in electrons per second per micrometre before wavelength response.

The result returns inspectable maps for source electrons by wavelength, total source electrons, background, dark current, fixed detector contribution, expected total, Poisson realization, read-noise realization, measured electrons, variance, missing-pixel mask, effective wavelength and unexplained residual. It also returns PSF, wavelength response, flat field, noise maps, nuisance settings and parameter provenance.

All transformations state their units. Source motion is evaluated at the exposure MJD. The PSF kernel is normalized and shifted at sub-pixel positions with no wraparound. Source, background and dark-current photon counts enter the Poisson draw; the fixed detector term is added deterministically and does not receive photon shot noise; read noise is drawn separately as Gaussian noise. The reported variance includes photon-generated counts and read-noise variance, not the deterministic fixed term. Flag bits and an explicit missing-pixel mask are excluded from measurements. Input arrays are not mutated.

Parameter provenance supports measured, calibrated, assumed, illustrative and placeholder. A measured parameter requires a source URI; a calibrated parameter requires a calibration ID. If any component remains assumed or placeholder, calibration_ready is false. This is a hard warning, not a cosmetic label.

The current implementation deliberately does not reproduce SPHEREx readout electronics, spatially varying ePSFs, saturation, nonlinear calibration, full pixel covariance or mission-specific crosstalk. It is a generic controlled model. It must not be described as calibrated SPHEREx physics.

---

## Session 10 — Joint inference and identifiability

Python entry points:

- **finite_difference_jacobian(model, parameters)** estimates a deterministic local Jacobian.
- **audit_forward_model_identifiability(jacobian, parameter_names, ...)** evaluates the resulting local sensitivity matrix.
- Endpoint: **POST /api/v5/causal/identifiability/jacobian**.

The audit can whiten the Jacobian using a positive variance vector or positive-definite full covariance matrix. It reports rank, singular values, a normalized-column condition number, zero-sensitivity parameters, near-collinear parameter pairs, sky/instrument/nuisance conflicts, local standard errors when full rank, and null-space directions when rank deficient.

Statuses are:

- **identifiable:** no rank deficiency or configured conditioning warning in the local model.
- **weakly_identifiable:** the local system is full rank but poorly conditioned.
- **degenerate:** full rank with near-collinear sensitivities or severe conditioning.
- **not_identifiable:** rank deficient; one or more parameter combinations cannot be independently constrained.

A rank-deficient model does not receive deceptively precise local parameter errors: those values are returned as unavailable. Extra-measurement proposals can provide a candidate Jacobian row and uncertainty. The report indicates whether the proposal improves rank or conditioning; it does not claim the proposed observation is feasible or guaranteed to break a global degeneracy.

The flux model-comparison likelihood also accepts a full covariance matrix. Its diagonal must agree with the supplied sigma values, and the matrix must be symmetric positive definite. Sky and detector coordinate fits remain independent per axis in this version. The covariance must be physically justified. covariance_verified is an explicit operator assertion, not an automatic validation. The audit is local and cannot prove global identifiability. Keep BIC differences and normalized BIC weights labelled as relative model comparisons, never calibrated posterior probabilities.

---

## Session 11 — Falsification and predictive checks

Endpoint: **POST /api/v5/causal/falsify**. The request may include **candidate_family**, a complete list of candidate ID, observations and optional flux covariance records for all candidates considered in the field-wide transient search.

Python entry point: **chronos_causal.falsification.run_falsification_suite**.

The suite fits the existing static, moving, achromatic, chromatic, transient, instrumental and mixed measurement-level explanations. It then:

1. reports residual summaries grouped by epoch, wavelength, detector and observed-brightness bin;
2. runs seeded parametric-bootstrap checks under the stated noise model;
3. evaluates the maximum transient-window statistic after scanning the complete set of allowed contiguous intervals;
4. replays declared sky-only, detector-only and mixed measurement interventions;
5. retains each intervention, parameter set, result and relative model score.

The single-candidate transient bootstrap repeats the full interval scan under each simulated null realization. It corrects for the set of contiguous intervals scanned for that candidate, conditional on the supplied null prediction and Gaussian uncertainties. A second maximum-statistic bootstrap accepts the complete searched candidate family and corrects across every supplied candidate as well as its interval scan. A transient-leading interpretation is forced to unknown unless that complete family includes the current candidate and the family-wise false-alarm probability passes the declared alpha. The correction cannot account for candidates omitted from the family, upstream image-detection thresholds, field selection or other post-hoc search decisions. It is not a substitute for a frozen real-field negative-control experiment.

The current predictive bootstrap is conditional on supplied point predictions. It does not draw model parameters from a posterior and therefore is not a full Bayesian posterior-predictive check. It can use the same supplied full flux covariance as the model comparison; its diagonal must match sigma squared. The report also returns observation-level residual records and conditional pointwise predictive intervals for plotting by epoch, wavelength, detector and brightness bin. Uncertainty rows must explicitly carry uncertainty_status equal to validated or calibrated before the suite can return a provisional survival verdict. Otherwise it returns unknown, even if residual plots look reassuring.

Counterfactual challenges are measurement-level transformations. They do not edit or regenerate original FITS pixels. Hashing the canonical intervention plan and supplying challenge_plan_sha256 verifies plan-content integrity only. It does not prove that the plan was registered before inspecting the data. This version has no independently timestamped or signed preregistration record, so the report explicitly marks predeclaration_verified=false. A genuine preregistration needs a separate custodian or trusted timestamp/signature before the held-out data are opened. Original observation rows are copied, not mutated.

A candidate returns unknown when the model is not decisively supported, uncertainties are not validated, predictive checks fail, or a transient-leading model lacks a passing candidate-family correction. A passing result is provisional and conditional on the model and noise assumptions. Preserve contradictory checks and failed interventions in the evidence package.

---

## Acceptance checklist before scientific claims

- [ ] At least two independent real fields exist for any field-bootstrap interval; several heterogeneous blind fields are preferable.
- [ ] All four methods share the exact field, exposure list, mask checksum, truth checksum, coordinate frame and matching radius.
- [ ] Every real measurement has verified release, product and calibration provenance.
- [ ] Sky-pixel matching uses the same validated WCS solution for truth and detections.
- [ ] Thresholds, matching radii, model version, seeds and exclusions were frozen before unblinding.
- [ ] Blind truth was held by an independent custodian until the run was sealed.
- [ ] Empty-field, negative, shuffled-time and detector-pattern controls were evaluated.
- [ ] Metrics are reported by field and relevant flux/background/crowding/detector/wavelength strata.
- [ ] The same held-out fields produce all four baseline curves.
- [ ] Jacobian and nuisance-parameter identifiability are assessed on the calibrated forward model.
- [ ] Residual and predictive checks survive the predeclared tests.
- [ ] Results include false alarms, missed truth, unmatched detections and uncertainty intervals.
- [ ] A negative result is retained. No method is declared superior solely because synthetic tests pass.

**Current scientific status:** software interfaces and synthetic regression tests are being added. No new result from real held-out SPHEREx fields is claimed by this implementation.
