# CHRONOS signed independent-field attestation contract

**Status:** verifier and synthetic tests implemented. No external field custodian key or signed real-field attestations have been supplied in the current run. The real-data source-selection gate therefore remains **blocked** until these are provisioned and independently confirmed.

## Purpose

The multidimensional injection/recovery model estimates uncertainty by resampling independent sky-field groups, not individual injections. Earlier code accepted operator-supplied `independent_field=true` and `independence_group_id` values. Those fields are not sufficient evidence of spatial independence.

The selection fit now calls `chronos_population.independence.audit_independent_field_records`. Every real field must have a detached Ed25519 custodian signature. The verified payload binds:
- field ID, real-data class and DR1/QR3 release;
- independence-group ID;
- a circular sky-footprint cap (centre RA/Dec and maximum enclosing radius);
- SHA-256 of the canonical footprint and exact science-manifest digest;
- preregistration digest;
- custodian ID, role, explicit independence assertion, and timezone-aware attestation timestamp.

All signed field caps are checked pairwise for non-overlap. Multiple product records can belong to one independence group only when their signed group and footprint agree. Each selection injection trial must reference a field that passed verification, and its release, independence group and preregistration digest must match the signed field payload.

This is a conservative spatial-independence screen, not a full model of all possible statistical correlations between sky regions. It does not replace a custodian's judgment about duplicated exposures, repeated observations, shared survey systematics or a valid independent-sky-group design.

## Deployment trust anchors

Provision the following variables in the trusted deployment environment (never in a request body or a public data manifest):

| Variable | Required meaning |
|---|---|
| `CHRONOS_FIELD_INDEPENDENCE_ATTESTATION_KEY_ID` | Key identifier pinned by the deployment owner |
| `CHRONOS_FIELD_INDEPENDENCE_ATTESTATION_PUBLIC_KEY_B64` | Base64 encoding of the custodian's raw 32-byte Ed25519 public key |
| `CHRONOS_FIELD_INDEPENDENCE_CUSTODIAN_ID` | Custodian identity independently confirmed by the deployment owner |
| `CHRONOS_FIELD_INDEPENDENCE_CUSTODIAN_OUT_OF_BAND_INDEPENDENCE_VERIFIED` | Must be literal `true` only after an out-of-band check confirms the custodian is independent of the analysis team |

If any trust anchor is missing, the field verification fails closed. The deployment owner must confirm the custodian identity and independence outside the repository; a signed string alone is not that confirmation.

## Signed envelope

The field record includes `field_independence_attestation` with schema `chronos-field-independence-attestation/1.0`, algorithm `Ed25519`, the pinned `key_id`, canonical JSON `payload`, and base64 detached signature. The signer uses the canonical UTF-8 JSON representation with sorted keys, compact separators and NaN disallowed.

A payload must contain exactly:
- `schema`, `field_id`, `dataset_class`, `release`, `independence_group_id`;
- `footprint`, `footprint_sha256`, `science_manifest_sha256`, `preregistration_sha256`;
- `custodian_id`, `custodian_role`, `custodian_independent_of_analysis_team`, `attested_utc`.

The custodian role must be `independent_custodian`; the signed independence assertion must be true; the signed ID must match the independently pinned custodian ID. Attestations for source-selection calibration must carry the same preregistration SHA-256 as all corresponding injection trials.

## Operational boundary

- A test-generated key exists only in synthetic unit tests. It must never be used for real data.
- A valid signature proves that the pinned key signed the declared field record; it does not independently authenticate a person's real-world identity, expertise or impartiality. Those are verified out-of-band before the key is pinned.
- A valid field-independence attestation does not certify calibration correctness, injection representativeness, recovery-log authenticity, or a YSO classification.
- This gate is separate from the blind benchmark's custodian attestation, sealed truth-store custody and unblinding record. It cannot substitute for them.
- A passing selection-function fit remains a conditional fixed-bin detection-probability model. It is not by itself a population result or discovery.

## Implementation

- `backend/chronos_population/independence.py`: canonical payload, footprint validation, Ed25519 verification, pinned identity/independence checks, pairwise spatial-cap separation.
- `backend/chronos_population/selection.py`: verifies all real-field attestations before counting field groups or accepting injection trials.
- `tests/test_multidimensional_selection.py`: synthetic signatures, missing trust anchors, tampered group IDs, overlapping footprints and out-of-band custodian checks.
