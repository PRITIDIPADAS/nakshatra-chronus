#!/usr/bin/env python3
"""Audit SPLICES candidate-label overlap, IDs, missingness and regional DR1 coverage.

This is a catalogue-integrity and candidate-inventory report. It does not infer
physical YSO classes, a survey selection function, a population rate, or a
source-level SPHEREx exposure history.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "chronos-splices-candidate-inventory/1.0"
DEFAULT_ROOT = Path("data/yso_population_recon")
NUMERIC_FIELDS = (
    "ra", "dec", "w1", "w1err", "w2", "w2err", "w3", "w3err",
    "w4", "w4err", "plx", "e_plx", "gaiadist", "mc_dist", "av",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str,
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"required reconnaissance input is missing: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def nonempty(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def numeric(value: Any) -> float | None:
    if not nonempty(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def label_flags(row: dict) -> dict[str, bool]:
    """Retain the three catalogue labels as separate, non-independent flags."""
    return {
        "published_yso_reference_present": nonempty(row.get("yso_pub")),
        "class_1_contains_yso": "YSO" in str(row.get("class_1") or "").upper(),
        "stype_ml_contains_yso": "YSO" in str(row.get("stype_ml") or "").upper(),
    }


def pattern_key(flags: dict[str, bool]) -> str:
    return (
        f"published={int(flags['published_yso_reference_present'])};"
        f"class_1={int(flags['class_1_contains_yso'])};"
        f"stype_ml={int(flags['stype_ml_contains_yso'])}"
    )


def _check_input_report(report: dict, candidate_rows: list[dict]) -> dict:
    if report.get("schema") != "chronos-spllices-yso-recon/1.0":
        raise ValueError("unsupported SPLICES reconnaissance report schema")
    expected = report.get("report_sha256")
    actual = sha256_json({key: value for key, value in report.items() if key != "report_sha256"})
    if not isinstance(expected, str) or expected.lower() != actual.lower():
        raise ValueError("SPLICES reconnaissance report SHA-256 mismatch")
    declared_count = report.get("candidate_record_count")
    if declared_count is not None and int(declared_count) != len(candidate_rows):
        raise ValueError(
            f"candidate row count mismatch: report={declared_count}, CSV={len(candidate_rows)}"
        )
    if report.get("errors"):
        raise ValueError("SPLICES reconnaissance report contains query errors")
    required_columns = {
        "source_id", "ra", "dec", "recon_region", "region_role",
        "yso_pub", "class_1", "stype_ml", "w1var_class", "w2var_class",
    }
    if candidate_rows:
        missing = required_columns - set(candidate_rows[0])
        if missing:
            raise ValueError("candidate CSV is missing required columns: " + ", ".join(sorted(missing)))
    return {
        "report_sha256_verified": True,
        "candidate_record_count_verified": True,
        "candidate_rows": len(candidate_rows),
        "source_report_sha256": actual,
    }


def _source_id_audit(rows: list[dict]) -> dict:
    by_id: dict[str, list[dict]] = defaultdict(list)
    missing_id_rows = 0
    for row in rows:
        source_id = str(row.get("source_id") or "").strip()
        if not source_id:
            missing_id_rows += 1
            continue
        by_id[source_id].append(row)
    duplicate_groups = []
    for source_id, members in sorted(by_id.items()):
        if len(members) <= 1:
            continue
        regions = sorted({str(row.get("recon_region") or "") for row in members})
        coordinates = sorted({
            (str(row.get("ra") or ""), str(row.get("dec") or ""))
            for row in members
        })
        duplicate_groups.append({
            "source_id": source_id,
            "row_count": len(members),
            "regions": regions,
            "coordinate_pairs": [
                {"ra": ra, "dec": dec} for ra, dec in coordinates
            ],
            "coordinate_consistent_as_exported": len(coordinates) == 1,
        })
    return {
        "candidate_rows": len(rows),
        "rows_with_source_id": len(rows) - missing_id_rows,
        "missing_source_id_rows": missing_id_rows,
        "unique_nonempty_source_ids": len(by_id),
        "duplicate_source_id_groups": len(duplicate_groups),
        "rows_beyond_first_occurrence": sum(
            len(items) - 1 for items in by_id.values() if len(items) > 1
        ),
        "duplicate_groups": duplicate_groups,
        "deduplication_policy": (
            "No positional-only merge is performed. Repeated non-empty source_id "
            "values are reported as groups; all original candidate rows are retained."
        ),
    }


def _label_overlap(rows: list[dict]) -> dict:
    combinations: Counter[str] = Counter()
    marginal = Counter()
    agreement = 0
    for row in rows:
        flags = label_flags(row)
        combinations[pattern_key(flags)] += 1
        for name, value in flags.items():
            marginal[name] += int(value)
        agreement += int(
            flags["published_yso_reference_present"] == flags["class_1_contains_yso"]
        )
    total = len(rows)
    return {
        "candidate_rows": total,
        "marginal_counts": dict(sorted(marginal.items())),
        "three_label_intersection_patterns": [
            {"pattern": key, "rows": count}
            for key, count in sorted(combinations.items(), key=lambda item: (-item[1], item[0]))
        ],
        "published_vs_class_1_membership": {
            "agreement_rows": agreement,
            "disagreement_rows": total - agreement,
            "agreement_fraction": agreement / total if total else None,
            "exact_membership_equivalence_in_candidate_export": bool(total and agreement == total),
        },
        "interpretation_boundary": (
            "These are overlaps among catalogue fields in the query-selected candidate union. "
            "They are not independent validation labels and do not establish physical class truth."
        ),
    }


def _region_summaries(root: Path, report: dict, candidate_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    region_rows = []
    all_exposures = []
    for result in report.get("region_results", []):
        region = result.get("region") or {}
        name = str(region.get("name") or "")
        regional_candidates = [
            row for row in candidate_rows if str(row.get("recon_region") or "") == name
        ]
        flags_counter = Counter()
        for row in regional_candidates:
            flags = label_flags(row)
            flags_counter[pattern_key(flags)] += 1
        exposure_path = root / name / "dr1_level2_exposures.csv"
        exposures = read_csv(exposure_path)
        by_band: dict[str, list[dict]] = defaultdict(list)
        seen_plane_ids: set[str] = set()
        for exposure in exposures:
            band = str(exposure.get("energy_bandpassname") or "UNKNOWN")
            by_band[band].append(exposure)
            plane_id = str(exposure.get("planeid") or "").strip()
            if plane_id:
                seen_plane_ids.add(plane_id)
            all_exposures.append({**exposure, "recon_region": name})
        band_summary = {}
        for band, values in sorted(by_band.items()):
            lower = [numeric(row.get("time_bounds_lower")) for row in values]
            upper = [numeric(row.get("time_bounds_upper")) for row in values]
            lower = [value for value in lower if value is not None]
            upper = [value for value in upper if value is not None]
            band_summary[band] = {
                "rows": len(values),
                "unique_plane_ids": len({
                    str(row.get("planeid") or "").strip()
                    for row in values if nonempty(row.get("planeid"))
                }),
                "unique_native_uris": len({
                    str(row.get("uri") or "").strip()
                    for row in values if nonempty(row.get("uri"))
                }),
                "first_mjd": min(lower) if lower else None,
                "last_mjd": max(upper) if upper else None,
            }
        region_rows.append({
            "region": name,
            "role": region.get("role"),
            "catalogue_rows": (result.get("counts") or {}).get("catalogue_rows_returned"),
            "candidate_rows": len(regional_candidates),
            "candidate_unique_source_ids": len({
                str(row.get("source_id") or "").strip()
                for row in regional_candidates if nonempty(row.get("source_id"))
            }),
            "label_patterns": [
                {"pattern": key, "rows": count}
                for key, count in sorted(flags_counter.items(), key=lambda item: (-item[1], item[0]))
            ],
            "dr1_level2_footprint_rows": len(exposures),
            "dr1_level2_unique_plane_ids": len(seen_plane_ids),
            "dr1_level2_by_band": band_summary,
            "source_level_epoch_coverage": "not measured by this regional footprint query",
        })
    return region_rows, all_exposures


def _field_quality(rows: list[dict]) -> dict:
    availability = {}
    for field in NUMERIC_FIELDS:
        values = [numeric(row.get(field)) for row in rows]
        observed = [value for value in values if value is not None]
        observed_fraction = len(observed) / len(rows) if rows else None
        sorted_values = sorted(observed)
        median = (
            sorted_values[len(sorted_values) // 2]
            if sorted_values and len(sorted_values) % 2
            else (sorted_values[len(sorted_values)//2 - 1] + sorted_values[len(sorted_values)//2]) / 2
            if sorted_values else None
        )
        availability[field] = {
            "numeric_rows": len(observed),
            "missing_or_non_numeric_rows": len(rows) - len(observed),
            "observed_fraction": observed_fraction,
            "median": median,
            "minimum": min(observed) if observed else None,
            "maximum": max(observed) if observed else None,
        }
    variability = {}
    for field in ("w1var_class", "w2var_class"):
        counter = Counter(
            str(row.get(field) or "UNRECORDED").strip() or "UNRECORDED"
            for row in rows
        )
        variability[field] = dict(sorted(counter.items()))
    return {
        "numeric_field_availability": availability,
        "raw_variability_class_counts": variability,
        "interpretation_boundary": (
            "Variability class strings and numeric values are reported as supplied by SPLICES. "
            "No variability significance threshold, quality cut, distance cut or YSO classifier is applied."
        ),
    }


def analyze(root: Path) -> dict:
    root = Path(root)
    input_report_path = root / "yso_population_recon.json"
    candidate_path = root / "candidate_sources_all_regions.csv"
    report = read_json(input_report_path)
    candidates = read_csv(candidate_path)
    input_validation = _check_input_report(report, candidates)
    source_ids = _source_id_audit(candidates)
    label_overlap = _label_overlap(candidates)
    regional, exposures = _region_summaries(root, report, candidates)
    global_exposure_ids = {
        str(row.get("planeid") or "").strip()
        for row in exposures if nonempty(row.get("planeid"))
    }
    exposure_membership = defaultdict(set)
    for row in exposures:
        plane_id = str(row.get("planeid") or "").strip()
        if plane_id:
            exposure_membership[plane_id].add(str(row.get("recon_region") or ""))
    cross_region_planes = {
        plane_id: sorted(regions)
        for plane_id, regions in exposure_membership.items() if len(regions) > 1
    }
    result = {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_validation": input_validation,
        "source_identity_audit": source_ids,
        "label_overlap_audit": label_overlap,
        "candidate_data_quality": _field_quality(candidates),
        "regional_candidate_and_coverage_summaries": regional,
        "cross_region_exposure_overlap": {
            "exposure_rows_across_regions": len(exposures),
            "unique_plane_ids_across_regions": len(global_exposure_ids),
            "plane_ids_in_multiple_region_queries": len(cross_region_planes),
            "plane_id_region_memberships": cross_region_planes,
            "interpretation": (
                "A repeated plane ID indicates that one archive footprint intersects multiple "
                "predeclared region-centre polygons. It is not a repeated observation."
            ),
        },
        "candidate_selection_definition": (
            "Candidate union rows satisfy at least one of YSO_PUB non-null, CLASS_1 containing YSO, "
            "or STYPE_ML containing YSO in the archived region query. This is a catalogue query "
            "definition, not a newly validated physical classifier."
        ),
        "scientific_boundary": [
            "No source is promoted to a newly discovered YSO by this audit.",
            "Published YSO, harmonised CLASS_1 and STYPE_ML labels remain separate fields.",
            "The report's candidate label overlaps are not independent validation.",
            "No completeness, contamination, selection function, population rate or star-formation rate is estimated.",
            "Regional exposure-polygon rows do not establish which individual candidate has source-level epoch coverage.",
            "No spectra were extracted or reclassified in this inventory audit.",
            "The six-region high-latitude cone is a comparison region, not a matched control sample.",
        ],
    }
    result["report_sha256"] = sha256_json(result)
    return result


def write_candidate_inventory(rows: list[dict], path: Path) -> None:
    """Write all original rows plus explicit, separate label flags."""
    path.parent.mkdir(parents=True, exist_ok=True)
    output = []
    for row in rows:
        flags = label_flags(row)
        output.append({**row, **flags})
    columns = sorted({key for row in output for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    report = analyze(args.root)
    candidate_rows = read_csv(args.root / "candidate_sources_all_regions.csv")
    write_candidate_inventory(
        candidate_rows, args.root / "candidate_label_inventory.csv"
    )
    report_path = args.root / "candidate_label_audit.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "report": str(report_path),
        "report_sha256": report["report_sha256"],
        "candidate_rows": report["source_identity_audit"]["candidate_rows"],
        "unique_source_ids": report["source_identity_audit"]["unique_nonempty_source_ids"],
        "duplicate_source_id_groups": report["source_identity_audit"]["duplicate_source_id_groups"],
        "label_pattern_counts": report["label_overlap_audit"]["three_label_intersection_patterns"],
        "cross_region_exposure_planes": report["cross_region_exposure_overlap"]["plane_ids_in_multiple_region_queries"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
