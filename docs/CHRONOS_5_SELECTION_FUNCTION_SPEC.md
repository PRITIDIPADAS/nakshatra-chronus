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

## Source-linked event-yield path

The separate `POST /api/v5/population/yso/source-linked-event-yield` endpoint rejects aggregate-only event counts. Every event must carry its source ID, field ID, accepted status under the frozen event rule, preregistration digest, event-definition digest, event interval and exact measurement IDs. The coverage audit supplies the source's native measurement-to-observation/MJD lineage; event rows are refused unless they map to at least two distinct valid epochs inside the source's measured interval. **The event decision is not recomputed by this endpoint:** `status='accepted'` is supplied by the caller, and the endpoint validates the declared evidence URI/hash but does not retrieve those bytes or execute the classifier. Its output records `event_acceptance_recomputed=false`; independent event-classifier reproduction remains a release prerequisite.

For each accepted source event, the endpoint applies the Horvitz–Thompson weight (1/p_i) from the supported multidimensional source-selection cell. It keeps multiple events from one source in one source-level Poisson bootstrap cluster and resamples the complete eligible source set for each field, including zero-event sources, rather than conditioning uncertainty on positive-event sources alone. Null-control counts remain separate and are scaled only by the declared area-time ratio.

This is an additional source-selection correction, not a full YSO population likelihood. It does **not** correct event-detection efficiency, model the source-level composition of contaminants, or account for cross-field covariance. It reports a source-selection-weighted candidate-event yield and explicitly labels it as **not a population result**. A separate, event-level injection/recovery model and independently reviewed contamination model are still needed before Session 19 can pass.

## What a pass would and would not mean

A supported selection function means only that the predeclared covariate cell has sufficient recorded injection evidence under this model. It does not prove that the injection distribution represents the target population, that the underlying detection output is correct, or that selection is independent of the science outcome.

The legacy `/api/v5/population/yso/rate` endpoint still uses aggregate field-level event counts and must not be presented as source-selection corrected. The new `/api/v5/population/yso/source-linked-event-yield` endpoint requires exact source-to-measurement lineage and applies source inverse-probability weights, but does not yet correct event-detection efficiency or the source-level composition of contaminants. Both paths remain exploratory and neither is a validated YSO population estimate or discovery.

## External evidence required before Session 19 can pass

- Real source-level SPHEREx exposure measurements with usable repeated epochs.
- Independent YSO classifications and an explicit contamination/sample definition.
- A frozen injection protocol representative of the target source population over the full multidimensional covariate domain.
- Retained detector outputs, injected-truth positions/fluxes, production peak lists and exact selection logs for every trial.
- At least the predeclared number of independent real fields per claimed supported cell.
- A real preregistration receipt and a custodian-controlled held-out sample.
- Null/negative controls, field-level sensitivity checks and independent astronomical review.

Until then, do not report a YSO population result.


## Externally pinned field-independence attestation — 26 November 2026

The selection fit no longer treats the `independent_field` boolean or a caller-supplied group ID as evidence. Every real field contributing to a selection calibration must carry an Ed25519 attestation from the external field custodian. The deployment must provision all four trust anchors out of band:

- `CHRONOS_FIELD_INDEPENDENCE_ATTESTATION_KEY_ID`
- `CHRONOS_FIELD_INDEPENDENCE_ATTESTATION_PUBLIC_KEY_B64`
- `CHRONOS_FIELD_INDEPENDENCE_CUSTODIAN_ID`
- `CHRONOS_FIELD_INDEPENDENCE_CUSTODIAN_OUT_OF_BAND_INDEPENDENCE_VERIFIED=true`

The signed payload binds the exact field ID, real dataset class, DR1/QR3 release, independence-group ID, science-manifest SHA-256, preregistration SHA-256, custodian identity/role, explicit custodian-independence assertion, attestation time, and a conservative spherical footprint cap (centre and enclosing radius) with its SHA-256. The verifier checks the signed payload against the field record and preregistered trial metadata, checks that the signed custodian ID matches the independently pinned ID, and requires independent groups to have distinct, pairwise non-overlapping signed footprint caps. A field without a valid signature, missing deployment trust anchors, a repeated group/footprint, mismatched preregistration or overlapping cap prevents the selection fit from being supported.

The public key and custodian identity/independence must be confirmed outside the repository before these variables are provisioned. The verifier checks that a pinned key signed the claimed statement; it does not prove a person's real-world identity or impartiality by itself. It also does not inspect original archive bytes or prove that a custodian's footprint declaration is correct. The exact science-manifest bytes must still be downloaded and checked against the signed digest. Unit tests use deterministic test-only keys and fictional fields; those signatures are not scientific evidence and must never be configured in a deployment. See [the signed field-independence attestation contract](CHRONOS_FIELD_INDEPENDENCE_ATTESTATION.md).
