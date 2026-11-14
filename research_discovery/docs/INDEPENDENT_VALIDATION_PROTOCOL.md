# SPHEREx real-sky validation protocol

## Research question

How reliably can the CHRONOS candidate pipeline distinguish genuine point-source motion or flux change from SPHEREx detector/system artifacts in actual DR1/QR3 Level-2 spectral-image observations?

## Claims under test

1. Flux/centroid measurements remain stable under realistic flags and variance weighting.
2. Artifact triage reduces candidate false alarms without rejecting a disproportionate fraction of injected sources.
3. A detector-template overlap signal provides incremental predictive value beyond simple SNR, local background and flag counts.
4. Performance transfers to unseen sky fields and separate observation periods.

These claims are hypotheses. They must not be presented as results until the frozen test is run.

## Data selection and leakage control

- Query `spherex_dr1` and `spherex_qr3` via IRSA SIA2. Keep `spherex_dr1_deep` and `spherex_qr3_deep` as a separately reported stratum.
- Use the individual MEFs for motion/time analysis; do not treat All-Sky Cube pixels as individual exposures.
- Group by sky region and observation ID before splitting. All exposures and cutouts from a field belong to one split.
- Split into development/calibration fields and blind held-out fields before threshold tuning. If the number of fields permits, use at least three independent held-out sky regions, ideally spanning different zodiacal backgrounds and crowding.
- Download the matching DR1/QR3 ePSF and detector template products from the documented calibration directories. Preserve checksums, product versions, processing dates and source URLs.
- Exclude calibration-incompatible exposures rather than mixing them silently.

## Injection controls

Use measured ePSFs extracted from the relevant detector zones. Use at least five logarithmically spaced source-flux bins spanning below and above the expected detection threshold. Randomize locations with a fixed published seed and avoid image borders, flagged pixels, existing source cores and previously injected sources. Include a blind subset whose injected coordinates and fluxes are concealed from the pipeline analyst until the run is frozen.

The injection distribution must reflect the science question. For moving-object tests, inject linked appearances across actual exposure epochs with positions following predeclared motion distributions. For artifact tests, construct controls using genuine detector-fixed or atmospheric patterns and independently reviewed artifact labels. A single-frame point-source injection alone does not validate moving-object identification.

## Baselines and ablations

Compare at least:

- baseline forced photometry with the official ePSF;
- the same pipeline with selected template/flag diagnostics disabled;
- the proposed template-aware triage;
- an intentionally simple SNR-only baseline.

Keep all other thresholds, field lists and measurement choices identical. Record changes in recovery and false-positive rate. Avoid a complex classifier if a simpler physically motivated test performs equally well.

## Metrics

- Detection completeness by flux, background, detector, wavelength channel and field.
- False alarms per 2040×2040 detector frame and per square degree where mapping is available.
- Centroid residuals in pixels and arcseconds; report robust median and 95th percentile.
- Flux bias `(measured - injected)/injected`, scatter and uncertainty coverage.
- Precision/recall only where the truth set is independently labelled.
- Wilson confidence intervals for binomial completeness/precision; field-level bootstrap for transfer uncertainty.
- Calibration curves for any reported probabilities. A raw score is not a probability.

## Stop/go rules

Preregister numeric criteria before the blind evaluation. Suggested minimum evidence: no material degradation in recovery at the faint end, lower false-alarm burden than the SNR-only baseline, unbiased astrometry within the instrument's measured calibration floor, and no catastrophic failure in a held-out background/detector stratum. The team must set actual tolerances from instrument requirements and its science use case, not copy arbitrary values from this template.

## Required archive

Save input FITS checksums, SIA query URLs, calibration URLs/checksums, code commit hash, locked configuration, seeds, injection catalog (with truth labels restricted until unblinding), run logs, per-field metrics, failure cases and the final unblinding record. A JSON summary without the raw provenance is not enough for independent reproduction.
