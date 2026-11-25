"""Build the science/calibration candidate matrix from real, file-backed evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from research_discovery.spherex.calibration_compatibility import compatibility_decision


def build_matrix(payload):
    science_exposures = payload.get("science_exposures", [])
    calibrations = payload.get("calibration_candidates", [])
    rows = []
    for exposure in science_exposures:
        science_metadata = dict(exposure.get("metadata") or {})
        science_metadata["native_uri"] = exposure.get("uri")
        science_metadata["sha256"] = exposure.get("sha256")
        for candidate in calibrations:
            if str(candidate.get("product_type", "")) != "spectral_wcs":
                continue
            calibration_metadata = dict(candidate.get("metadata") or {})
            calibration_metadata["native_uri"] = candidate.get("uri")
            calibration_metadata["sha256"] = candidate.get("sha256")
            decision = compatibility_decision(science_metadata, calibration_metadata)
            rows.append({
                "science_id": exposure.get("id"),
                "science_uri": exposure.get("uri"),
                "science_sha256": exposure.get("sha256"),
                "calibration_id": candidate.get("id"),
                "calibration_uri": candidate.get("uri"),
                "calibration_sha256": candidate.get("sha256"),
                "solid_angle_uri": decision.get("solid_angle_uri"),
                "decision": decision["status"],
                "compatibility_group": decision["compatibility_group"],
                "checks": decision["checks"],
                "audit": decision.get("audit"),
            })
    return {
        "schema_version": "1.1",
        "pair_count": len(rows),
        "compatible_pairs": [row for row in rows if row["decision"] == "compatible"],
        "failed_matches": [row for row in rows if row["decision"] == "rejected"],
        "unresolved_pairs": [row for row in rows if row["decision"] == "review_required"],
        "matrix": rows,
        "warning": "No pair is inferred from filename similarity. An exact native-MEF audit and all three manifest products are required.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, default=Path("calibration_compatibility_matrix.json"))
    args = parser.parse_args()
    result = build_matrix(json.loads(args.input.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"pairs={result['pair_count']} compatible={len(result['compatible_pairs'])} "
          f"rejected={len(result['failed_matches'])} unresolved={len(result['unresolved_pairs'])}")


if __name__ == "__main__":
    main()
