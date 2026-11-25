# CHRONOS 5 source-selection function specification

**Status:** implemented and tested with synthetic fixtures; not yet calibrated on a real, blinded, multi-field SPHEREx source sample.

## Role in the science gate

The selection function estimates the probability that a source is recovered by a frozen source-detection/photometry pipeline conditional on predeclared observable covariates. It is not a substitute for source-level flux extraction, source classification, temporal cadence, false-positive modelling or event-detection completeness.

The fixed joint-bin dimensions are:

- injected source flux (Jy),
- wavelength (µm),
- crowding index,
- background RMS,
- usable epoch count,
- detector zone.

The model refuses to predict outside measured joint-bin support. It does not smooth or extrapolate into an empty bin or substitute another detector zone.

## Trial evidence contract

Each injection trial is tied to one explicitly attested real field and one fixed processing run. All trials in the selection function must share the same:

- source-detection method identifier;
- processing configuration SHA-256;
- injection protocol SHA-256;
- calibration-manifest SHA-256;
- preregistration SHA-256;
- recovery-rule SHA-256;
- photometry quality-policy SHA-256.

The recovery rule is versioned as \`chronos-production-peak-match-fit-quality/1.0\`. A boolean \`recovered\` field is not trusted by itself. The implementation recomputes it from recorded diagnostics:

1. the selected candidate is a local maximum under the production rule;
2. the production primary selection rule passes;
3. the injected source has a one-to-one assigned selected peak;
4. peak SNR meets the frozen threshold;
5. measured injected-to-peak separation is within the frozen match radius;
6. the actual integer flags pass the named SPHEREx mask;
7. measured \`fit_ql\` meets the frozen limit;
8. the background fraction meets the frozen limit.

For a recovered injection, the input also records the selected peak ID and injected/peak coordinates. The measured separation must agree with the coordinate difference. A production peak cannot be assigned to two injections within the same detector output image.

The code validates the internal consistency of these trial records and their digests. It does **not** retrieve the external detector-output or injection-truth bytes and independently re-run the peak finder. The field operator/custodian must retain those bytes and the full detection logs. Hashes alone prove byte identity only when the referenced bytes are available for checking.

## Field-level uncertainty and support

Injections are nested within observed fields. Counting many injections in one field as many independent fields would produce overconfident support. The implementation therefore:

- groups fields by the explicit \`independence_group_id\`;
- requires the minimum number of distinct independently attested groups globally and within each supported joint cell;
- computes a Jeffreys beta posterior within each group from that group's recovered/missed trials;
- draws from each group's beta posterior, resamples independent groups with replacement, and reports a field-cluster bootstrap distribution of the group-averaged detection probability;
- records the field IDs, independence-group IDs, per-group injection counts, random seed and draw count;
- rejects reused production peak IDs within a common detector-output image.

This is a field-cluster bootstrap of per-group Jeffreys beta posteriors. It is **not** a full hierarchical Bayesian model and does not model shared calibration covariance, common systematics or unobserved fields. The interval is conditional on the specified field groups and fixed bin edges.

The per-field \`n_injected\` and \`n_recovered\` summary in the population coverage input must exactly equal the counts recomputed from those same selection-trial records. A separate, more favourable completeness summary cannot pass the coverage gate.

## Source-level quality alignment

Real source photometry imported from IRSA is accepted only under an explicitly frozen quality policy. The policy binds a named bitmask, maximum \`fit_ql\` and maximum \`abs(flux_bkg) / max(abs(flux), flux_err)\`. Real selection trials must carry the same quality-policy digest. A source row cannot silently use a less restrictive quality rule than the injection/recovery experiment.

The imported time series must separately pass native-product, observation identity, WCS, CWAVE/CBAND, calibration and epoch checks. Selection trials cannot repair missing or invalid source epochs.

## API and revalidation

- \`POST /api/v5/population/assess-coverage\` computes coverage and the multidimensional selection function.
- \`POST /api/v5/population/yso/rate\` recomputes the coverage audit, checks the preregistration digest against the one frozen into the selection trials, then runs the currently available exploratory field-level event-rate model.
- \`estimate_event_rate\` recomputes the selection function from the exact trials and compares the trial digest, fixed-bin digest and frozen-provenance record with the submitted coverage audit.

## What a pass would and would not mean

A supported selection function means only that the predeclared covariate cell has sufficient recorded injection evidence under this model. It does not prove that the injection distribution represents the target population, that the underlying detection output is correct, or that selection is independent of the science outcome.

The current rate estimator still uses field-level aggregate event-detection completeness with scaled null-control counts. It does not use source-level inverse-probability weights as an event likelihood, because the repository's current field inputs do not provide event-to-source identity and source-specific event records. The API therefore remains exploratory and must not be presented as a selection-corrected YSO population estimate or discovery.

## External evidence required before Session 19 can pass

- Real source-level SPHEREx exposure measurements with usable repeated epochs.
- Independent YSO classifications and an explicit contamination/sample definition.
- A frozen injection protocol representative of the target source population over the full multidimensional covariate domain.
- Retained detector outputs, injected-truth positions/fluxes, production peak lists and exact selection logs for every trial.
- At least the predeclared number of independent real fields per claimed supported cell.
- A real preregistration receipt and a custodian-controlled held-out sample.
- Null/negative controls, field-level sensitivity checks and independent astronomical review.

Until then, do not report a YSO population result.
