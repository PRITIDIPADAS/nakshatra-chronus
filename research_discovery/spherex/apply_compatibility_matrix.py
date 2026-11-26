"""Apply only audit-revalidated, unambiguous calibration groups to an archive manifest."""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from research_discovery.spherex.archive_manifest import build_manifest, validate_manifest
from research_discovery.spherex.calibration_compatibility import compatibility_decision


def apply_matrix(manifest, matrix):
    manifest_report = validate_manifest(manifest, verify_local=True, base_dir=Path.cwd())
    if not manifest_report["valid"]:
        raise ValueError(f"Input archive manifest is invalid: {manifest_report['issues'][:5]}")
    products = [dict(product) for product in manifest.get("products", [])]
    by_uri = {product.get("native_uri"): product for product in products}
    if len(by_uri) != len(products):
        raise ValueError("Input manifest contains duplicate native URIs; refusing compatibility assignment")

    applied = []
    unresolved = []
    usage = defaultdict(set)
    compatible_rows = matrix.get("compatible_pairs", [])
    for row in compatible_rows:
        science_uri = row.get("science_uri")
        calibration_uri = row.get("calibration_uri")
        area_uri = row.get("solid_angle_uri")
        if not all((science_uri, calibration_uri, area_uri)):
            unresolved.append({"science_uri": science_uri, "reason": "missing science, spectral-WCS or solid-angle URI"})
            continue
        if any(uri not in by_uri for uri in (science_uri, calibration_uri, area_uri)):
            unresolved.append({"science_uri": science_uri, "reason": "one or more product URIs are absent from the merged archive manifest"})
            continue

        science_product = by_uri[science_uri]
        calibration_product = by_uri[calibration_uri]
        area_product = by_uri[area_uri]
        expected_hashes = (
            (science_product, row.get("science_sha256"), "science"),
            (calibration_product, row.get("calibration_sha256"), "spectral_wcs"),
            (area_product, row.get("solid_angle_sha256"), "solid_angle"),
        )
        hash_mismatch = False
        for product, expected, label in expected_hashes:
            actual = product.get("sha256")
            if not expected or not actual or str(expected).lower() != str(actual).lower():
                unresolved.append({"science_uri": science_uri, "reason": f"{label} archive manifest SHA-256 does not match compatibility matrix"})
                hash_mismatch = True
        if hash_mismatch:
            continue

        science_metadata = row.get("science_metadata")
        calibration_metadata = row.get("calibration_metadata")
        if not isinstance(science_metadata, dict) or not isinstance(calibration_metadata, dict):
            unresolved.append({"science_uri": science_uri, "reason": "matrix omitted the metadata needed to re-run compatibility audit"})
            continue
        if science_metadata.get("native_uri") != science_uri or science_metadata.get("sha256") != science_product.get("sha256"):
            unresolved.append({"science_uri": science_uri, "reason": "science metadata identity does not match manifest"})
            continue
        if calibration_metadata.get("native_uri") != calibration_uri or calibration_metadata.get("sha256") != calibration_product.get("sha256"):
            unresolved.append({"science_uri": science_uri, "reason": "spectral-WCS metadata identity does not match manifest"})
            continue
        if calibration_metadata.get("solid_angle_map_uri") != area_uri or calibration_metadata.get("solid_angle_map_sha256") != area_product.get("sha256"):
            unresolved.append({"science_uri": science_uri, "reason": "solid-angle metadata identity does not match manifest"})
            continue

        decision = compatibility_decision(science_metadata, calibration_metadata)
        if decision["status"] != "compatible":
            unresolved.append({"science_uri": science_uri, "reason": "compatibility decision failed when revalidated",
                               "decision": decision})
            continue
        group = decision.get("compatibility_group")
        if not group or (row.get("compatibility_group") and row["compatibility_group"] != group):
            unresolved.append({"science_uri": science_uri, "reason": "compatibility group does not match revalidated decision"})
            continue

        for product in (science_product, calibration_product, area_product):
            product["compatibility_status"] = "compatible"
            product["compatibility_group"] = group
            note = "Pair revalidated from checksum-linked native-MEF audit."
            product["notes"] = (str(product.get("notes") or "") + " | " + note).strip(" |")
        usage[calibration_uri].add(group)
        usage[area_uri].add(group)
        applied.append({"science_uri": science_uri, "calibration_uri": calibration_uri,
                        "solid_angle_uri": area_uri, "compatibility_group": group,
                        "audit_sha256": decision["audit"].get("audit_sha256")})

    for uri, groups in usage.items():
        if len(groups) > 1:
            unresolved.append({"calibration_uri": uri, "reason": "calibration product maps to multiple compatibility groups"})
            by_uri[uri]["compatibility_status"] = "review_required"
            by_uri[uri]["compatibility_group"] = None

    updated = build_manifest(
        archive="NASA/IPAC IRSA SPHEREx merged product inventory",
        query={
            "source_manifest_sha256": manifest.get("manifest_sha256"),
            "compatibility_matrix_sha256": hashlib.sha256(
                json.dumps(matrix, sort_keys=True, separators=(",", ":"), default=str).encode()
            ).hexdigest(),
        },
        products=products,
        processing_config={
            "operation": "re-validate and apply compatibility matrix",
            "compatible_pair_count": len(applied),
            "unresolved_pair_count": len(unresolved),
        },
    )
    return updated, {"applied_pairs": applied, "unresolved": unresolved}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--out", type=Path, default=Path("data/spherex_compatible_manifest.json"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))
    updated, report = apply_matrix(manifest, matrix)
    validation = validate_manifest(updated)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(updated, indent=2, default=str), encoding="utf-8")
    (args.out.parent / (args.out.stem + ".pairing.json")).write_text(json.dumps(report, indent=2))
    print(json.dumps({"manifest_valid": validation["valid"], "paired": len(report["applied_pairs"]),
                      "unresolved": len(report["unresolved"])}, indent=2))
    if not validation["valid"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
