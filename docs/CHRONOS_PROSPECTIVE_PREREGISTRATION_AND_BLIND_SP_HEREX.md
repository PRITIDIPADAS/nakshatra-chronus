# CHRONOS prospective preregistration and SPHEREx blind evaluation protocol

**Protocol status: DRAFT — NOT EXTERNALLY REGISTERED — NOT PROOF OF HISTORICAL PREREGISTRATION**

This file is a prospective protocol template. It does not establish that an earlier analysis was preregistered. CHRONOS work and software inspection have already occurred. This document can support a new, untouched holdout evaluation only after it is externally timestamped and signed before the independent custodian releases or exposes any holdout field, truth catalogue, injection key, labels or hidden metadata.

## 1. Scientific question and scope

**Question:** Can an instrument-aware Sky–Detector Twin separate astrophysical source evidence from detector, wavelength-sampling, calibration and background effects more reliably than the three specified comparator methods on independent SPHEREx fields?

The target claim is source-detection performance on the defined SPHEREx Level-2 data products. It is not a claim that the method discovers new YSOs, proves astrophysical transients, or improves all SPHEREx analyses.

## 2. Data release and product policy

Use only the current uniformly processed **DR1 and QR3** releases for this protocol. Record the exact release per field; do not mix QR2 with DR1/QR3. DR1/QR3 Level-2 spectral-image MEFs are the science images. Record native archive identifiers, URI, detector, observing time, pipeline version, processing date, byte count and SHA-256 for every science and calibration file.

For each Level-2 science MEF retain, at minimum:
- IMAGE and its BUNIT (MJy/sr);
- VARIANCE in the corresponding squared unit;
- FLAGS and the exact accepted/rejected bit mask;
- ZODI, with the policy for including it in the sky model;
- EPSF and the exact ePSF calibration file/version;
- WCS-WAVE metadata and the matching native spectral-WCS product containing CWAVE and CBAND;
- the science image WCS, detector, observation time and full-frame/cutout origin.

Record and checksum the detector-specific calibration candidates relevant to the chosen product level: spectral WCS, ePSF, solid-angle pixel map, dark-current map, absolute-gain matrix, nonlinearity parameters, read-noise parameters, electronic gain factors, nonfunctional-pixel map and applicable crosstalk products. Compatibility is not inferred from a similar filename. Require detector, release, product-version/processing-date metadata, science pipeline metadata, coordinate frame, native-file hashes and a file-backed MEF/calibration audit. The archive manifest must preserve rejected and unresolved candidate pairs too.

**Level-2 policy:** IMAGE is already in calibrated surface-brightness units and the delivered VARIANCE already represents the Level-2 uncertainty product. Do not apply the absolute gain, dark current, read noise or nonlinearity corrections a second time to a Level-2 image. Those terms belong in a separate upstream L0/L1 detector model only when the corresponding raw/count-domain inputs and exact engineering calibration products are available. For the Level-2 forward model, use the delivered image, variance, flags, zodiacal-background information, spectral WCS, ePSF and pixel solid angle in their documented roles.

## 3. Four frozen methods

The methods must receive the same immutable field, exposure set, registered WCS, valid-pixel mask, coordinate units, truth definition and matching radius:

1. **SNR-only:** existing matched-filter/DEEPS detection output.
2. **CHRONOS P/D/A:** the frozen existing candidate pipeline.
3. **Instrument forensics:** forensic triage/veto of the same P/D/A candidate set. It is not an independent source finder.
4. **Sky–Detector Twin:** the frozen instrument-aware model, with its own output threshold fixed on development fields.

Record source commit, package/environment lock, model parameters, calibration manifest digest, image-preparation digest, score semantics, candidate de-duplication policy and all thresholds. No method may tune on blind-test truth.

## 4. Field independence and split

The independent custodian selects fields and groups correlated pointings/epochs from the same sky region into one split group. No sky region, target, repeated visit, or overlapping detector footprint may cross the development/holdout boundary. The custodian creates opaque field and exposure tokens for the analysis team. All truth catalogues, injection seeds, control labels and original field identifiers remain sealed.

The holdout must include science fields and predeclared controls: empty fields, negative controls, shuffled-time controls and detector-pattern controls. Injections must span predeclared flux, background, crowding, detector-zone, wavelength and completeness strata. The custodian retains the truth-generation procedure and verifies its provenance independently.

## 5. Primary endpoint and superiority rule

The primary endpoint is **completeness at a frozen false-candidate-per-field operating point**, calculated per independent field with one-to-one matching and the same truth catalogue for all methods. Secondary endpoints include false candidates per field at matched completeness, astrometric residuals, flux bias/pull coverage, control-field false positives, per-stratum completeness and abstention rate.

For Sky–Detector Twin versus each comparator, calculate paired field/group bootstrap confidence intervals for the difference in primary completeness on the sealed holdout. Resample independent sky groups, not detections or individual epochs. Control family-wise error across the three comparator contrasts using a predeclared multiplicity procedure. The Twin is superior only if the predeclared lower confidence bound for its paired completeness improvement is greater than zero against every comparator, while its false-candidate rate and negative-control false-positive rate satisfy the frozen non-inferiority limits. No threshold or metric may be changed after seeing holdout results.

A failed superiority gate is a valid result. Do not tune the Twin using blind results and then report the same holdout as independent confirmation.

## 6. Bayesian inference and model scores

BIC is a model-selection score. Normalized exp(-Delta-BIC/2) weights are approximate relative support under restrictive assumptions; they are not posterior probabilities that a model is true. The new CHRONOS Bayesian endpoint computes posterior distributions and model probabilities for a narrower, explicit linear-Gaussian model with known positive-definite covariance and proper Gaussian coefficient priors. Its posterior model probabilities are conditional on the specified model set and priors and come from exact Gaussian marginal likelihoods, not from BIC.

The Bayesian posterior-predictive endpoint draws coefficient vectors from the exact conjugate Gaussian posterior and then draws replicated data. This is a genuine posterior-predictive check for that specified linear-Gaussian measurement model. It does not constitute full Bayesian inference over the entire sky/detector/astrometry/calibration model. A whole-pipeline Bayesian claim additionally requires explicit priors and posterior sampling for calibration parameters, spatially varying ePSFs, detector effects, source selection, coordinate models and relevant covariance structures.

## 7. Transient claims

Transient intervals are searched over multiple possible start/end times. Candidate and interval selection must be included in the false-alarm calculation. The candidate-family set must be complete for the declared search domain, and its completeness must be attested by the independent custodian from the original detection/search logs. A caller's boolean declaration alone is not independent verification.

A transient claim is eligible only when:
- the independently timestamped protocol predates holdout inspection;
- calibration and uncertainty products pass the frozen validation;
- the candidate and full searched candidate family are preserved;
- the family-wise false-alarm analysis covers the complete search family;
- the same result passes the predeclared negative and detector-pattern controls;
- the independent custodian releases the truth only after the frozen run and hash verification.

This protocol does not retroactively remove boundaries from earlier exploratory transient claims.

## 8. External preregistration and custody requirements

Before holdout data are opened, deposit the complete protocol, code commit, environment lock, field-selection rule, calibration policy, method versions, thresholds, priors, metrics, statistical tests, exclusion rules and analysis scripts in an independent immutable registration/timestamping service. Preserve the returned registration identifier, UTC timestamp, immutable version/digest, author identity and public or embargoed audit trail. Obtain a separate signed statement from the custodian confirming that the holdout files and truth were not inspected by the analysis team before that time.

The custodian must:
- generate and encrypt the truth store outside the analysis environment;
- keep the decryption key in a separate controlled account/device;
- publish only the public manifest, encrypted-store SHA-256 and opaque tokens;
- verify the frozen commit/configuration and dataset digest before executing or permitting unblinding;
- retain access logs and sign the unblinding record;
- not be the model developer, parameter tuner or report author.

A Git commit timestamp, repository SHA, encryption key fingerprint or self-authored declaration is not independent proof of preregistration or independent custody. CHRONOS cannot act as its own independent custodian.

## 9. Release criteria and reporting

Publish the complete public input manifest, calibration compatibility matrix, calibration audit reports, frozen configuration, source commit, environment lock, holdout access record, unblinding record, all-method metrics, field-level paired comparisons, control results, exclusions and failures. Keep restricted data and truth encrypted under archive terms.

The final report must clearly separate synthetic verification, development-field performance and sealed real-field performance. A real-world performance advantage is established only by the predeclared holdout superiority rule above. No real blind result is claimed by this protocol file.
