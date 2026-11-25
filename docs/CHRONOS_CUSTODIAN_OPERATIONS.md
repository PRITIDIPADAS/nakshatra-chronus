# CHRONOS independent custodian operations

This runbook is for a real, separate human custodian. The custodian must not be the model developer, threshold tuner, or primary report author. Do not run these commands as a substitute for an independent person or claim independence merely because two accounts or two key files exist.

## Required order

1. Submit the complete protocol to an independent registration service. Save the registration receipt, record URL/ID, and exact UTC time. The receipt must precede blind dataset creation and holdout inspection.
2. The custodian creates the Fernet truth-encryption key and a separate Ed25519 signing key outside the repository, on a controlled machine.
3. The custodian prepares the opaque whole-field split and keeps the encrypted truth store and Fernet key private. The analyst receives only the public manifest and opaque run manifest.
4. The analyst freezes the exact code commit, environment, thresholds, priors, matching radii, exclusions and metric definitions before executing on blind fields.
5. Before releasing the frozen public run bundle to the analyst, the custodian signs an attestation binding the external receipt and exact dataset/configuration digests. The Ed25519 private key and Fernet key remain with the custodian.
6. The analyst runs all four methods using the frozen commit/configuration and returns the complete detection package. No truth catalogue, injection key, control labels, original field names or holdout metadata is included.
7. The custodian verifies the detection package and performs unblinding on the custodian-controlled machine. The decrypt-and-score command refuses to open truth without a valid signature and a public-key fingerprint pinned out-of-band.

Use Python with the repository backend on the module path:

\`\`\`bash
export PYTHONPATH=backend
\`\`\`

On Windows PowerShell:

\`\`\`powershell
$env:PYTHONPATH = "backend"
\`\`\`

## Custodian key setup

Run these commands on the custodian's controlled machine. Use paths outside the repository. Store the private keys in offline or access-controlled storage.

\`\`\`bash
python -m chronos_benchmark.custodian_cli generate-key \
  --key-file /custodian-private/chronos-truth.fernet

python -m chronos_benchmark.custodian_cli generate-signing-key \
  --private-key-file /custodian-private/chronos-custodian-ed25519.pem \
  --public-key-file /custodian-transfer/chronos-custodian-ed25519.pub.pem
\`\`\`

Share the public signing key and its SHA-256 fingerprint with the analysis team through a separately authenticated channel. The team must pin that fingerprint independently. Never transfer or commit either private key.

## Prepare the sealed field set

The custodian's private input JSON contains actual independent field records, real field science inputs, calibration manifests, truth catalogues, injection metadata, split-group IDs, control labels, and exact matching radii. Each field must use dataset_class \`real\` only when the raw archive inputs and their provenance have actually been verified. Synthetic fixtures cannot be used to make a real-data eligibility claim.

\`\`\`bash
python -m chronos_benchmark.custodian_cli prepare \
  --fields /custodian-private/field_truth_and_inputs.json \
  --key-file /custodian-private/chronos-truth.fernet \
  --output-dir /custodian-private/chronos-blind-2026-001 \
  --test-fraction 0.30 \
  --seed 20261125
\`\`\`

Keep \`encrypted_truth_store.bin\`, \`custodian_summary.json\`, and the Fernet key with the custodian. Transfer only \`public_manifest.json\` and \`run_manifest.json\` to the analysis team. The opaque run manifest contains enough information to run the declared methods but no truth or original field identities.

## Freeze the configuration before the blind run

The configuration must include the full per-method score threshold lists, the matched false-candidate/completeness target, exact matching radii for every opaque field token, and the externally registered protocol digest. Include the paired superiority endpoint's predeclared false-candidate non-inferiority margin and multiplicity method.

Example configuration shape (replace every example value with the registered, scientifically justified value):

\`\`\`json
{
  "preregistration_sha256": "<64 hex characters from the immutable protocol deposit>",
  "score_thresholds": {
    "snr_only": [12, 10, 8, 6, 5],
    "chronos_pda": [12, 10, 8, 6, 5],
    "instrument_forensics": [12, 10, 8, 6, 5],
    "sky_detector_twin": [12, 10, 8, 6, 5]
  },
  "matched_target": {
    "false_candidates_per_field": 0.2
  },
  "matching_radii_by_field": {
    "<opaque-field-token-1>": 2.0
  },
  "false_candidate_noninferiority_margin": 0.05,
  "multiple_comparison_correction": "bonferroni_95_familywise"
}
\`\`\`

The matching-radii object must contain every opaque field token, with the exact radius in the frozen coordinate unit. These threshold numbers are illustrative placeholders and must not be copied as supposedly calibrated thresholds.

Compute the public dataset digest from the public manifest and opaque run manifest:

\`\`\`bash
python - <<'PY'
import json
from chronos_benchmark.runner import sha256_json

with open("/custodian-transfer/public_manifest.json", encoding="utf-8") as f:
    public = json.load(f)
with open("/custodian-transfer/run_manifest.json", encoding="utf-8") as f:
    run = json.load(f)
print(sha256_json({"public_manifest": public, "run_manifest": run}))
PY
\`\`\`

The analyst or custodian freezes the exact commit and config before running any blind detection:

\`\`\`bash
python -m chronos_benchmark.custodian_cli freeze \
  --configuration /analysis-transfer/frozen_config.json \
  --source-commit <full-40-or-64-character-commit-sha> \
  --dataset-digest <64-character-dataset-sha256> \
  --output /analysis-transfer/frozen_configuration.json
\`\`\`

Both parties should independently check the commit SHA and frozen configuration SHA before the run.

## Sign the preregistration and blind dataset attestation

The custodian signs the external receipt hash, registration record, holdout-access statement, public/run manifest hashes, encrypted truth hash, frozen config hash, and source commit. The explicit confirmation flags are assertions made by the human custodian; they are not independently inferred by software.

\`\`\`bash
python -m chronos_benchmark.custodian_cli attest \
  --custodian-id "<independent custodian identity>" \
  --registration-url "https://<registration-service>/<record>" \
  --registration-id "<immutable record ID>" \
  --registered-utc "<receipt timestamp with timezone>" \
  --registration-receipt /custodian-private/registration-receipt.pdf \
  --public-manifest /custodian-private/chronos-blind-2026-001/public_manifest.json \
  --run-manifest /custodian-private/chronos-blind-2026-001/run_manifest.json \
  --encrypted-store /custodian-private/chronos-blind-2026-001/encrypted_truth_store.bin \
  --frozen-configuration /analysis-transfer/frozen_configuration.json \
  --private-signing-key /custodian-private/chronos-custodian-ed25519.pem \
  --output /custodian-transfer/custodian_attestation.json \
  --confirm-no-prior-holdout-access \
  --confirm-independent-custodian \
  --confirm-registration-receipt-checked
\`\`\`

Transfer the detached attestation JSON and public signing key to the analysis team. The team must verify the signature using the public key and fingerprint received independently. The attestation code verifies that the signed statement binds the registered timestamp and receipt hash to the data/configuration hashes; it does not itself contact the registration service or cryptographically certify the service's timestamp.

## Blind analysis handoff

The analysis team runs exactly the frozen source commit and environment. It must process every opaque holdout token exactly once, execute SNR-only, CHRONOS P/D/A, the forensic veto and Sky–Detector Twin against the same pixels, masks, exposures, WCS and score thresholds, and preserve a complete machine-readable detection run. The detection run must include the public fields, dataset digest, frozen configuration SHA, source commit, configuration object, thresholds, matched target, matching radii and all four methods' outputs for every token.

Do not include truth catalogues, original field IDs, injection seeds, control labels, decrypted stores or the custodian's key in the detection run.

## Custodian-only unblind and score

The custodian receives the complete detection run and verifies it is from the frozen code/configuration. Only then does the custodian run:

\`\`\`bash
python -m chronos_benchmark.custodian_cli unblind \
  --key-file /custodian-private/chronos-truth.fernet \
  --public-manifest /custodian-private/chronos-blind-2026-001/public_manifest.json \
  --encrypted-store /custodian-private/chronos-blind-2026-001/encrypted_truth_store.bin \
  --frozen-configuration /analysis-transfer/frozen_configuration.json \
  --detection-run /analysis-transfer/detection_run.json \
  --output /custodian-private/chronos-blind-2026-001/unblinded_report.json \
  --custodian-attestation /custodian-transfer/custodian_attestation.json \
  --custodian-public-key /custodian-transfer/chronos-custodian-ed25519.pub.pem \
  --expected-custodian-key-sha256 <out-of-band-pinned-64-hex-fingerprint> \
  --bootstrap-draws 10000 \
  --seed 20261125
\`\`\`

The truth is not decrypted when the attestation is missing, invalid, or signed by an unpinned key. Preserve the access logs, detection run, public manifest, encrypted-store hash, frozen config, signed attestation, output report, and custodian signature/audit trail.

## What counts as success

A benchmark report can be reproducible yet fail the scientific eligibility gates. The Sky–Detector Twin superiority gate requires all of the following: only real held-out fields, an independently verified registration-first custodian attestation, frozen source/configuration, complete holdout processing, paired field-group bootstrap with the declared family-wise correction, positive lower confidence bound versus every comparator, and false-candidate non-inferiority. A failed gate is a valid empirical outcome. Do not tune on the holdout and reuse it as confirmation.
