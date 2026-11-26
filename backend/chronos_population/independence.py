"""Pinned-key verification of independent-field custodian attestations."""
from __future__ import annotations
import base64, hashlib, json, math, os
from datetime import datetime
from typing import Any, Mapping, Sequence

FIELD_INDEPENDENCE_SCHEMA = "chronos-field-independence-attestation/1.0"
KEY_ID_ENV = "CHRONOS_FIELD_INDEPENDENCE_ATTESTATION_KEY_ID"
PUBLIC_KEY_ENV = "CHRONOS_FIELD_INDEPENDENCE_ATTESTATION_PUBLIC_KEY_B64"
CUSTODIAN_ID_ENV = "CHRONOS_FIELD_INDEPENDENCE_CUSTODIAN_ID"
CUSTODIAN_INDEPENDENCE_ENV = "CHRONOS_FIELD_INDEPENDENCE_CUSTODIAN_OUT_OF_BAND_INDEPENDENCE_VERIFIED"
_PAYLOAD_KEYS = {
    "schema", "field_id", "dataset_class", "release", "independence_group_id",
    "footprint", "footprint_sha256", "science_manifest_sha256",
    "preregistration_sha256", "custodian_id", "custodian_role",
    "custodian_independent_of_analysis_team", "attested_utc",
}


def canonical_field_independence_payload(payload: Mapping[str, Any]) -> bytes:
    if not isinstance(payload, Mapping):
        raise ValueError("field independence attestation payload must be an object")
    try:
        return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("field independence attestation payload must be strict JSON") from exc


def _sha(value: Any, label: str) -> str:
    value = str(value or "").strip().lower()
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{label} must be a 64-character SHA-256 digest")
    return value


def _footprint(value: Any) -> dict[str, float]:
    keys = {"center_ra_deg", "center_dec_deg", "maximum_radius_deg"}
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError("signed footprint needs centre RA/Dec and maximum enclosing radius")
    try:
        ra, dec, radius = (float(value[k]) for k in (
            "center_ra_deg", "center_dec_deg", "maximum_radius_deg"
        ))
    except (TypeError, ValueError):
        raise ValueError("signed footprint values must be numeric") from None
    if (not all(math.isfinite(v) for v in (ra, dec, radius))
            or not 0 <= ra < 360 or not -90 <= dec <= 90 or not 0 < radius < 90):
        raise ValueError("signed footprint coordinates or enclosing radius are invalid")
    return {"center_ra_deg": ra, "center_dec_deg": dec, "maximum_radius_deg": radius}


def _separation(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    ra1, dec1 = math.radians(a["center_ra_deg"]), math.radians(a["center_dec_deg"])
    ra2, dec2 = math.radians(b["center_ra_deg"]), math.radians(b["center_dec_deg"])
    dot = math.sin(dec1)*math.sin(dec2) + math.cos(dec1)*math.cos(dec2)*math.cos(ra1-ra2)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def verify_field_independence_attestation(field: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(field, Mapping):
        raise ValueError("field record must be an object")
    fid = str(field.get("field_id", "")).strip()
    if not fid:
        raise ValueError("field independence attestation requires field_id")
    if str(field.get("dataset_class", field.get("data_class", ""))).lower() != "real":
        raise ValueError(f"{fid}: field is not labelled real")
    if field.get("independent_field") is not True:
        raise ValueError(f"{fid}: independent_field must be true in addition to custodian attestation")
    key_id, public_b64 = os.environ.get(KEY_ID_ENV, "").strip(), os.environ.get(PUBLIC_KEY_ENV, "").strip()
    expected_custodian_id = os.environ.get(CUSTODIAN_ID_ENV, "").strip()
    custodian_independence_confirmed = os.environ.get(CUSTODIAN_INDEPENDENCE_ENV, "").strip().lower() == "true"
    if not key_id or not public_b64:
        raise ValueError("trusted external field-independence custodian Ed25519 key is not configured")
    if not expected_custodian_id or not custodian_independence_confirmed:
        raise ValueError("custodian identity and independence from the analysis team must be confirmed out-of-band")
    envelope = field.get("field_independence_attestation")
    if not isinstance(envelope, Mapping) or envelope.get("schema") != FIELD_INDEPENDENCE_SCHEMA:
        raise ValueError(f"{fid}: signed field_independence_attestation is required")
    if envelope.get("algorithm") != "Ed25519" or envelope.get("key_id") != key_id:
        raise ValueError(f"{fid}: attestation algorithm or pinned key_id does not match")
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping) or set(payload) != _PAYLOAD_KEYS:
        raise ValueError(f"{fid}: custodian attestation payload has missing or unexpected fields")
    expected = {
        "schema": FIELD_INDEPENDENCE_SCHEMA, "field_id": fid, "dataset_class": "real",
        "release": str(field.get("release", "")).upper(),
        "independence_group_id": str(field.get("independence_group_id", "")).strip(),
        "science_manifest_sha256": str(field.get("science_manifest_sha256", "")).lower(),
        "preregistration_sha256": str(field.get("preregistration_sha256", "")).lower(),
    }
    for name, value in expected.items():
        if not value or payload.get(name) != value:
            raise ValueError(f"{fid}: signed custodian payload does not match field record ({name})")
    if expected["release"] not in {"DR1", "QR3"}:
        raise ValueError(f"{fid}: independent field release must be DR1 or QR3")
    _sha(payload["science_manifest_sha256"], f"{fid}.science_manifest_sha256")
    _sha(payload["preregistration_sha256"], f"{fid}.preregistration_sha256")
    footprint = _footprint(payload["footprint"])
    if field.get("footprint") != payload["footprint"]:
        raise ValueError(f"{fid}: signed footprint does not match field record")
    fp_sha = _sha(payload["footprint_sha256"], f"{fid}.footprint_sha256")
    actual_sha = hashlib.sha256(canonical_field_independence_payload(footprint)).hexdigest()
    if fp_sha != actual_sha or field.get("footprint_sha256") != fp_sha:
        raise ValueError(f"{fid}: signed footprint SHA-256 does not match its geometry")
    if (
        not str(payload.get("custodian_id", "")).strip()
        or payload.get("custodian_role") != "independent_custodian"
        or payload.get("custodian_id") != expected_custodian_id
    ):
        raise ValueError(f"{fid}: signed custodian identity does not match the out-of-band pinned custodian")
    if payload.get("custodian_independent_of_analysis_team") is not True:
        raise ValueError(f"{fid}: custodian did not attest independence from the analysis team")
    try:
        stamp = datetime.fromisoformat(str(payload.get("attested_utc")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{fid}: attested_utc must be timezone-aware ISO-8601") from exc
    if stamp.tzinfo is None:
        raise ValueError(f"{fid}: attested_utc must include a timezone")
    try:
        pub = base64.b64decode(public_b64, validate=True)
        sig = base64.b64decode(str(envelope.get("signature_base64", "")), validate=True)
        if len(pub) != 32 or len(sig) != 64:
            raise ValueError("invalid Ed25519 key or signature length")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(pub).verify(sig, canonical_field_independence_payload(payload))
    except Exception as exc:
        raise ValueError(f"{fid}: custodian field-independence signature is invalid ({type(exc).__name__})") from exc
    return {**dict(payload), "footprint": footprint}


def audit_independent_field_records(field_records: Sequence[Mapping[str, Any]], *,
                                    minimum_independent_fields: int
                                    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if not isinstance(field_records, (list, tuple)) or not field_records:
        raise ValueError("field_records must contain signed real-field records")
    by_id, verified = {}, {}
    for field in field_records:
        if not isinstance(field, Mapping):
            raise ValueError("field_records entries must be objects")
        fid = str(field.get("field_id", "")).strip()
        if not fid or fid in by_id:
            raise ValueError("field_records must have unique non-empty field_id values")
        by_id[fid] = field
        if str(field.get("dataset_class", field.get("data_class", "unverified"))).lower() == "real":
            verified[fid] = verify_field_independence_attestation(field)
    groups: dict[str, dict[str, Any]] = {}
    for fid, payload in verified.items():
        group, fp_sha = str(payload["independence_group_id"]), str(payload["footprint_sha256"])
        current = groups.get(group)
        if current and current["footprint_sha256"] != fp_sha:
            raise ValueError(f"independence group {group} has conflicting signed footprints")
        groups.setdefault(group, {"footprint_sha256": fp_sha, "footprint": payload["footprint"], "custodians": set()})
        groups[group]["custodians"].add(str(payload["custodian_id"]))
    group_ids = sorted(groups)
    if len(group_ids) < int(minimum_independent_fields):
        raise ValueError(
            f"selection calibration requires at least {minimum_independent_fields} signed, independently attested real-field groups; found {len(group_ids)}"
        )
    for i, left_id in enumerate(group_ids):
        for right_id in group_ids[i+1:]:
            left, right = groups[left_id], groups[right_id]
            if left["footprint_sha256"] == right["footprint_sha256"]:
                raise ValueError("distinct independence groups reuse the same signed field footprint")
            sep = _separation(left["footprint"], right["footprint"])
            radius_sum = left["footprint"]["maximum_radius_deg"] + right["footprint"]["maximum_radius_deg"]
            if sep <= radius_sum + 1e-9:
                raise ValueError(f"independent field footprints overlap or cannot be proven disjoint ({left_id}, {right_id})")
    summary = {
        "status": "verified_signed_independent_fields", "schema": FIELD_INDEPENDENCE_SCHEMA,
        "pinned_key_id": os.environ.get(KEY_ID_ENV, "").strip() or None,
        "custodian_identity_verified_out_of_band": True,
        "custodian_independence_verified_out_of_band": True,
        "verified_real_field_count": len(verified), "independent_group_count": len(group_ids),
        "verified_field_ids": sorted(verified), "independence_group_ids": group_ids,
        "custodian_ids": sorted({v for g in groups.values() for v in g["custodians"]}),
        "spatial_caps_pairwise_disjoint": True,
        "field_attestations": [
            {"field_id": fid, "independence_group_id": p["independence_group_id"],
             "release": p["release"], "science_manifest_sha256": p["science_manifest_sha256"],
             "preregistration_sha256": p["preregistration_sha256"],
             "footprint_sha256": p["footprint_sha256"], "custodian_id": p["custodian_id"],
             "attested_utc": p["attested_utc"]}
            for fid, p in sorted(verified.items())
        ],
    }
    return verified, summary
