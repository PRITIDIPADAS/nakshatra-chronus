# Observation-planner feasibility attestation

**Purpose:** prevent a caller-supplied \`status: verified\` label from being treated as authenticated external visibility, archive availability or observing-window evidence.

## Trust model

The planner ranks scientific information gain from supplied model forecasts. It does not query an observatory, archive or telescope scheduler itself.

A candidate may be ranked without feasibility evidence, but it is labelled \`forecast_ranked_feasibility_unverified\` / \`science_ranked_but_feasibility_unverified\` and is not returned as a feasible recommendation.

A candidate is promoted to \`verified\` feasibility only when all of the following are true:

1. The record contains a detached Ed25519 signature over the complete feasibility record, using canonical UTF-8 JSON (sorted keys, compact separators, no NaN/Infinity). The \`attestation\` member itself is excluded from the signed payload.
2. The signature's \`key_id\` matches the deployment's pinned key ID.
3. The signature verifies under the Ed25519 public key configured outside the repository.
4. Required signed fields are complete: HTTPS \`source_uri\`, timezone-aware \`checked_utc\`, boolean \`feasible\`, valid start/end UTC window, calculator identifier, query ID, non-empty exact query parameters and a 64-hex SHA-256 digest of the underlying evidence.
5. The candidate's requested time lies within the signed external window.

The service does not accept a public key supplied inside the request as a trust anchor. The request cannot choose its own trusted signing identity.

## Deployment configuration

Provision these environment variables through the deployment secret/configuration system (never commit a private key):

- \`CHRONOS_FEASIBILITY_ATTESTATION_KEY_ID\`: the out-of-band pinned key identifier.
- \`CHRONOS_FEASIBILITY_ATTESTATION_PUBLIC_KEY_B64\`: base64-encoded 32-byte raw Ed25519 public key.

The private signing key belongs to the independent visibility/availability service or authority and must remain outside CHRONOS. Do not place the private key in this repository, request payloads, CI artifacts or analysis-runner environment.

When either deployment variable is absent, every caller-supplied \`status: verified\` record remains unverified. That is intentional fail-closed behaviour, not a planner outage.

## Signed record shape

A service signs every field except the detached \`attestation\` member:

\`\`\`json
{
  "status": "verified",
  "feasible": true,
  "source_uri": "https://visibility.example/query/123",
  "checked_utc": "2026-11-25T12:00:00Z",
  "window_start_utc": "2026-11-25T13:00:00Z",
  "window_end_utc": "2026-11-25T15:00:00Z",
  "calculator": "visibility-calculator/version",
  "query_id": "Q-123",
  "query_parameters": {
    "target": "approved-target-id",
    "instrument": "approved-instrument",
    "configuration": "approved-configuration"
  },
  "evidence_sha256": "64-character-sha256-of-the-retrieved-evidence",
  "attestation": {
    "algorithm": "Ed25519",
    "key_id": "deployment-pinned-key-id",
    "signature_b64": "base64-ed25519-signature-over-canonical-fields-above"
  }
}
\`\`\`

The digest is an integrity reference, not a substitute for signature verification. A signed digest binds the external evidence identifier/content hash to the source URI, query, feasible state, time window and checked time.

## Status semantics and limitations

- \`available\`, \`unknown\`, unsigned \`verified\`, bad-signature \`verified\`, unknown-key \`verified\`, and a well-formed record with no deployment trust key remain unverified.
- A cryptographically valid signature proves that the configured signing key signed the stated record. It does not prove the signing service's scientific competence, live sensor calibration, target identity or correctness of its underlying astronomy. Those remain governance and operational responsibilities of the external authority.
- Key rotation must be an explicit deployment operation. Do not accept arbitrary request-supplied keys or silently fall back to a public key included in a record.
- The legacy \`/api/addons/observations/plan\` route and the main \`/api/v5/observations/plan\` route use the same fail-closed verifier. The structured \`/api/v5/observations/plan-candidate\` route also requires the same attestation before returning a feasible recommendation.

## Tests

Automated tests cover:
- a caller-supplied \`verified\` record without a detached signature;
- a valid Ed25519 signature from a generated test key pinned through the same environment-variable interface;
- a record modified after signing;
- an \`available\`-only response that cannot be promoted.

These tests establish the software contract. A production key, external signer, real service query and live end-to-end signature exchange must be configured and independently operated before any real observation is labelled feasible.
