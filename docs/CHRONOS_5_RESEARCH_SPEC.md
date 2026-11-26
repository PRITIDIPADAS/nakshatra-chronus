# CHRONOS 5.0 research specification

## Category

**Physics**

## One problem worth solving

When SPHEREx appears to observe an infrared source changing, can the measured change be separated into astrophysical evolution, detector behaviour, calibration effects and wavelength-time sampling?

## Research objective

Build a reproducible, instrument-aware investigation framework that compares competing explanations of the same astronomical measurements, identifies when the data cannot distinguish those explanations, tests the leading explanation against counterfactual alternatives, and identifies the next measurement that would best reduce uncertainty.

## Flagship system

**The Counterfactual Sky–Detector Twin** has two coupled states:

- **Sky state:** source position, motion, intrinsic brightness and spectral evolution.
- **Instrument state:** detector coordinates, PSF, wavelength response, background, noise, flags and calibration nuisance parameters.

The forward model should explain the recorded measurement from both states. A real astronomical change and an instrumental effect may coexist.

## Competing explanations

1. Static source.
2. Moving source.
3. Achromatic variable source.
4. Chromatic variable source.
5. Transient source.
6. Instrumental or calibration effect.
7. Mixed astrophysical and instrumental explanation.
8. Unknown or not identifiable with current observations.

The existing P/D/A system and five-hypothesis classifier remain baselines. They are not silently replaced.

## Four website workspaces

1. **Causal Investigation:** synchronized sky and detector coordinates, competing models, identifiability, counterfactuals and residual checks.
2. **Spectral Evolution:** time-wavelength measurements, missing-data-aware reconstruction, calibration groups and feature evolution.
3. **Cosmic Identity Network:** epoch-aware probabilistic source association and alternative counterpart histories.
4. **Experimental Observatory:** detector experiments, four-baseline comparison, blind validation, information-gain planning, population statistics and reproducible evidence.

## Existing capabilities retained

- Main SPHEREx observatory.
- Fair-pair rules.
- P/D/A candidate detection.
- Existing five-hypothesis classifier.
- Candidate dossier and investigation engine.
- Motion mapping, validation, Planet X educational experiment, citizen review and whole-sky tools.
- Existing research add-ons, archive adapters, notebooks, tests and static site.

## Research methods added in the CHRONOS 5 preview

- Measurement-level model competition using supplied uncertainties.
- Sky- and detector-coordinate persistence diagnostics.
- Transient interval search with a search penalty.
- Design-matrix identifiability screen.
- Measurement-level counterfactuals.
- Generic electron-domain detector experiment.
- Sampling-aware local spectral reconstruction.
- Predefined spectral-feature evolution.
- Proper-motion-aware positional association with a no-match result.
- Expected-information-gain ranking of supplied forecasts.
- Completeness-aware population-rate estimate.
- Archive provenance manifest and evidence graph.
- Four-baseline comparison metrics.

## Scientific limits of the current preview

The initial causal engine is a measurement-level model, not a complete pixel-level SPHEREx forward model. Its normalized BIC weights are relative model support, not calibrated posterior probabilities. The identifiability screen is a design-matrix diagnostic, not a full forward-model Jacobian audit. The generic detector simulator is not a calibrated SPHEREx detector model. Proper-motion association does not yet include all parallax, binary-motion and survey-selection terms. The planner relies on supplied forecasts and feasibility information. Synthetic cases test software behaviour, not performance on the real sky.

The website must distinguish the following states:
- **Real:** measurements retrieved from an identified archive product with matching calibration and provenance.
- **Synthetic:** controlled test data with recorded truth.
- **Illustrative:** example values entered to show a workflow.
- **Unverified:** source data, coordinate transforms or calibration compatibility not yet checked.

## Scientific acceptance criteria

A major scientific claim requires:
1. Actual archive files and compatible calibration products.
2. Verified wavelength assignment from the appropriate calibration product.
3. Validated sky-to-detector coordinate transformation.
4. Realistic source noise and variance accounting.
5. Independent field-held-out evaluation.
6. Comparison against SNR-only, existing P/D/A, instrument forensics and the new Twin at matched false-alarm rate or completeness.
7. Field-level uncertainty, residual, flux-bias and astrometric metrics.
8. Identifiability and posterior-predictive checks.
9. Reproducible evidence package.
10. Independent scientific review.

A negative result is acceptable. If the Twin does not outperform the existing baselines, CHRONOS should report that result.

## Positioning

NAKSHATRA CHRONOS is a Physics research project about the interpretation of time-varying infrared observations. Its defensible contribution is the jointly validated SPHEREx-specific workflow connecting sky-coordinate evolution, detector-coordinate behaviour, wavelength-time sampling, calibration uncertainty, counterfactual tests and next-observation selection. Any originality claim must be supported by literature review and measured improvement on held-out real observations.
