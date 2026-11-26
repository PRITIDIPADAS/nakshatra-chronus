# Independent astronomical reproduction verifier and release-readiness gate

This software accompanies the independent reproduction protocol and external reviewer handoff.

## Signed independent reproduction record

The module research_discovery.spherex.independent_reproduction verifies a detached Ed25519 record containing:
- reviewer ID, role, affiliation, declared independence and conflicts;
- the exact repository commit and hashes for the input manifest, native source data, source time series, calibration audit, selection trials, analysis output, environment lock, signed report and reproduction artifact;
- the specific scientific claims reviewed and required check results for that scope;
- the signed conclusion and any unresolved conditions.

The reviewer public-key fingerprint and identity must be confirmed out of band. The private key stays with the external reviewer. The verifier opens the signed report and reproduction artifact and checks their exact bytes. It cannot prove reviewer identity, expertise, independence or scientific correctness by itself.

Use verify_reproduction_record only after receiving the signed record, public key, original signed report and reproduction artifact from the reviewer through an agreed channel. Never accept a public key and its pin only from the same untrusted bundle.

## Scope-specific acceptance

The review can cover source time series, instrument calibration, source selection, candidate-event yield, blind benchmark or population inference. Unconditional acceptance requires every check needed by the declared scope to be accepted. Missing checks cannot be hidden as out-of-scope.

## Scientific release readiness

The evaluate_scientific_release_readiness function reports a machine-readable checklist covering:
- independent calibration sign-off and astronomical reproduction;
- independent blind custodian and completed four-baseline benchmark;
- verified multi-epoch source series and real multi-field source-selection support;
- event-detection efficiency measured on real source time series;
- source-level contamination controls and independent source classifications;
- an external preregistration receipt created before data access.

The function only reports readiness. It does not publish a release, create a tag, change a scientific status, or authorize a claim. A true readiness flag means only “evidence gates passed, pending human release authorization.”

No independent astronomer report, reviewer key pin, custodian signature, independent source classifications or external preregistration receipt has been supplied. The verifier's unit tests use synthetic keys and fixtures only. They are not scientific evidence and do not close Session 20.


## Population release gate: signed field evidence is re-verified

The readiness evaluator does not accept `independent_field_count >= 5` or a caller-provided `supported=true` flag by itself. Both the source-selection and event-detection-efficiency evidence must carry the full per-field Ed25519 custodian envelopes. The readiness check re-verifies each signature against the deployment's out-of-band pinned custodian key and identity/independence settings, then recomputes the pairwise-disjoint spherical-footprint audit. Missing signatures, altered envelopes, a missing trust anchor, or overlapping signed fields keep the corresponding gate closed.

The source-linked event-yield report carries the signed field-independence audit through its embedded selection-function record so downstream readiness can re-verify it. This signature check still does not independently establish the custodian's institutional authority or the truth of the signed field manifest; those require outside confirmation and original-byte verification.
