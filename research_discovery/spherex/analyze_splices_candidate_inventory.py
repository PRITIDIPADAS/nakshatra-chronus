#!/usr/bin/env python3
"""Audit SPLICES candidate-label overlap, IDs, missingness and DR1/QR3 footprints.

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


SCHEMA = "chronos-splices-candidate-inventory/1.1"
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
    supported_schemas = {
        "chronos-spllices-yso-recon/1.0",
        "chronos-spllices-yso-recon/1.1",
    }
    if report.get("schema") not in supported_schemas:
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


def _summarize_exposure_rows(rows: list[dict]) -> tuple[dict, set[str]]:
    by_band: dict[str, list[dict]] = defaultdict(list)
    plane_ids = set()
    for exposure in rows:
        band = str(exposure.get("energy_bandpassname") or "UNKNOWN")
        by_band[band].append(exposure)
        plane_id = str(exposure.get("planeid") or "").strip()
        if plane_id:
            plane_ids.add(plane_id)
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
    return band_summary, plane_ids


def _summarize_sia_products(rows: list[dict]) -> dict:
    """Summarize SIAv2 image-product metadata without treating products as epochs."""
    by_collection: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_collection[str(row.get("_chronos_collection") or "UNKNOWN")].append(row)
    result = {}
    for collection, members in sorted(by_collection.items()):
        identifiers = {
            str(row.get("obs_publisher_did") or row.get("access_url")
                or row.get("obs_id") or row.get("obsid") or row.get("uri")
                or row.get("ID") or "").strip()
            for row in members
        }
        identifiers.discard("")
        result[collection] = {
            "release": next((str(row.get("_chronos_release")) for row in members
                             if nonempty(row.get("_chronos_release"))), "unknown"),
            "product_rows": len(members),
            "unique_archive_product_ids": len(identifiers),
            "products_with_access_uri": sum(
                nonempty(row.get("access_url") or row.get("uri")) for row in members
            ),
        }
    return result


def _region_summaries(root: Path, report: dict, candidate_rows: list[dict]):
    region_rows = []
    centre_point_exposures = []
    full_region_products = []
    candidate_source_exposure_matches = []
    candidate_source_epoch_summaries = []
    use_siav2 = report.get("schema") == "chronos-spllices-yso-recon/1.1"

    for result in report.get("region_results", []):
        region = result.get("region") or {}
        name = str(region.get("name") or "")
        regional_candidates = [
            row for row in candidate_rows if str(row.get("recon_region") or "") == name
        ]
        candidate_ids = {
            str(row.get("source_id") or "").strip()
            for row in regional_candidates if nonempty(row.get("source_id"))
        }
        flags_counter = Counter()
        for row in regional_candidates:
            flags_counter[pattern_key(label_flags(row))] += 1

        centre_path = root / name / "dr1_level2_exposures.csv"
        source_match_path = root / name / "candidate_source_exposure_matches.csv"
        source_summary_path = root / name / "candidate_source_epoch_summary.csv"
        source_product_path = root / name / "candidate_source_product_matches.csv"
        exposures = read_csv(centre_path)
        optional_errors = result.get("optional_query_errors") or {}
        source_epoch_error = optional_errors.get("candidate_source_exposure_matches")
        source_match_rows = []
        source_summary_rows = []
        if not source_epoch_error:
            if source_match_path.is_file() and source_summary_path.is_file():
                source_match_rows = read_csv(source_match_path)
                source_summary_rows = read_csv(source_summary_path)
            else:
                # Optional query outputs are not silently interpreted as empty matches.
                source_epoch_error = "optional source-to-exposure query output CSV missing"

        if use_siav2:
            optional_sia_errors = dict(result.get("optional_sia_errors") or {})
            collections = (
                "spherex_dr1", "spherex_dr1_deep",
                "spherex_qr3", "spherex_qr3_deep",
            )
            collection_rows = {}
            for collection in collections:
                csv_path = root / name / f"region_footprints_sia_{collection}.csv"
                if optional_sia_errors.get(collection):
                    # A current error always wins over any stale file on disk.
                    collection_rows[collection] = []
                elif not csv_path.is_file():
                    optional_sia_errors[collection] = "SIAv2 query output CSV missing"
                    collection_rows[collection] = []
                else:
                    collection_rows[collection] = read_csv(csv_path)
            full_region_rows = []
            collection_counts = {}
            reported_counts = (
                (result.get("counts") or {}).get("region_intersecting_spectral_image_rows_by_collection")
                or {}
            )
            for collection, rows in collection_rows.items():
                release = "dr1" if collection.startswith("spherex_dr1") else "qr3"
                failed = bool(optional_sia_errors.get(collection))
                reported = reported_counts.get(collection) or {}
                collection_counts[collection] = {
                    "release": release,
                    "product_rows": None if failed else len(rows),
                    "reported_product_rows": None if failed else reported.get("product_rows", len(rows)),
                    "query_status": "unavailable" if failed else "returned",
                    "query_error": optional_sia_errors.get(collection),
                    "query_complete_below_row_cap": (
                        False if failed else reported.get("query_complete_below_row_cap", False)
                    ),
                }
                full_region_rows.extend({
                    **row,
                    "recon_region": name,
                    "_chronos_collection": row.get("_chronos_collection") or collection,
                    "_chronos_release": row.get("_chronos_release") or release,
                } for row in rows)

            dr1_failed = any(optional_sia_errors.get(key) for key in (
                "spherex_dr1", "spherex_dr1_deep"
            ))
            qr3_failed = any(optional_sia_errors.get(key) for key in (
                "spherex_qr3", "spherex_qr3_deep"
            ))
            any_sia_failed = dr1_failed or qr3_failed
            dr1_rows = sum(len(collection_rows[key]) for key in (
                "spherex_dr1", "spherex_dr1_deep"
            ))
            qr3_rows = sum(len(collection_rows[key]) for key in (
                "spherex_qr3", "spherex_qr3_deep"
            ))
            full_region_error = {
                key: value for key, value in optional_sia_errors.items()
            } or None
            full_query_status = (
                "partial_optional_queries_failed" if any_sia_failed
                else "all_four_collections_returned"
            )
            full_band_summary = _summarize_sia_products(full_region_rows)
            full_plane_ids = set()
        else:
            full_region_path = root / name / "dr1_level2_exposures_full_region.csv"
            full_region_error = optional_errors.get("dr1_level2_exposures_full_region")
            full_region_rows = []
            if not full_region_error:
                if full_region_path.is_file():
                    full_region_rows = read_csv(full_region_path)
                else:
                    # A missing optional query artifact is unavailable, not zero coverage.
                    full_region_error = "optional full-region query output CSV missing"
            full_band_summary, full_plane_ids = _summarize_exposure_rows(full_region_rows)
            collection_counts = {}
            dr1_rows = len(full_region_rows) if not full_region_error else None
            qr3_rows = None
            full_query_status = (
                "unavailable" if full_region_error
                else "returned_below_or_at_declared_row_cap"
            )
            optional_sia_errors = {}
            if source_epoch_error:
                source_match_rows = []
                source_summary_rows = []

        if source_epoch_error:
            source_match_rows = []
            source_summary_rows = []

        source_product_rows = []
        source_product_error = None
        if use_siav2:
            if source_product_path.is_file():
                source_product_rows = read_csv(source_product_path)
            else:
                source_product_error = "candidate source/product match manifest missing"

        centre_point_exposures.extend({**row, "recon_region": name} for row in exposures)
        full_region_products.extend(
            {**row, "recon_region": name} for row in full_region_rows
        )
        candidate_source_exposure_matches.extend(
            {**row, "recon_region": name} for row in source_match_rows
        )
        candidate_source_epoch_summaries.extend(
            {**row, "recon_region": name} for row in source_summary_rows
        )

        centre_band_summary, centre_plane_ids = _summarize_exposure_rows(exposures)
        source_counts = result.get("counts") or {}
        source_query_complete = source_counts.get("candidate_source_exposure_query_complete")
        if use_siav2:
            source_match_error = source_epoch_error or source_product_error
            matched_source_ids = {
                str(row.get("source_id") or "").strip()
                for row in source_match_rows
                if nonempty(row.get("source_id"))
                and str(row.get("has_archive_footprint_match", "true")).lower() not in {"false", "0"}
            }
            source_product_pair_count = len(source_product_rows) if not source_product_error else None
            observation_id_count = (
                sum(int(float(row.get("unique_archive_observation_id_count") or 0))
                    for row in source_match_rows)
                if not source_match_error else None
            )
            band_counts = Counter()
            release_source_counts = Counter()
            for row in source_match_rows:
                try:
                    parsed = json.loads(row.get("band_product_counts_json") or "{}")
                except (TypeError, ValueError, json.JSONDecodeError):
                    parsed = {}
                for band, count in parsed.items():
                    band_counts[str(band)] += int(count)
                for release in str(row.get("data_releases") or "").split(";"):
                    if release:
                        release_source_counts[release] += 1
            source_band_summary = {
                "matched_archive_product_pair_count": source_product_pair_count,
                "archive_observation_id_count_summed_per_source": observation_id_count,
                "product_rows_by_band": dict(sorted(band_counts.items())),
                "matched_source_rows_by_release": dict(sorted(release_source_counts.items())),
                "interpretation": "Metadata-only product associations; obs_id and time bounds are not validated independent epochs",
            } if not source_match_error else None
            source_plane_ids = set()
            source_match_status = (
                "unavailable" if source_match_error
                else source_counts.get("candidate_source_exposure_query_status")
                or ("complete_below_declared_row_cap" if source_query_complete is True
                    else "observed_lower_bound")
            )
        else:
            source_match_error = source_epoch_error
            source_band_summary, source_plane_ids = _summarize_exposure_rows(source_match_rows)
            matched_source_ids = {
                str(row.get("source_id") or "").strip()
                for row in source_match_rows if nonempty(row.get("source_id"))
            }
            source_product_pair_count = len(source_match_rows)
            observation_id_count = sum(
                int(float(row.get("unique_observation_count") or 0))
                for row in source_summary_rows
            )
            source_match_status = (
                "unavailable" if source_match_error
                else "complete_below_declared_row_cap" if source_query_complete is True
                else "lower_bound_or_candidate_query_incomplete"
            )
        region_rows.append({
            "region": name,
            "role": region.get("role"),
            "catalogue_rows": source_counts.get("catalogue_rows_returned"),
            "candidate_rows": len(regional_candidates),
            "candidate_unique_source_ids": len(candidate_ids),
            "label_patterns": [
                {"pattern": key, "rows": count}
                for key, count in sorted(flags_counter.items(), key=lambda item: (-item[1], item[0]))
            ],
            "dr1_level2_region_centre_exposure_rows": len(exposures),
            "dr1_level2_region_centre_unique_plane_ids": len(centre_plane_ids),
            "dr1_level2_region_centre_by_band": centre_band_summary,
            "region_centre_query_semantics": "fixed_region_centre_point_inside_exposure_polygon",
            "dr1_level2_full_region_intersection_query_status": full_query_status,
            "dr1_level2_full_region_intersection_query_error": full_region_error,
            "dr1_level2_full_region_intersection_exposure_rows": (
                None if use_siav2 or full_region_error else len(full_region_rows)
            ),
            "dr1_level2_full_region_intersection_unique_plane_ids": (
                None if use_siav2 or full_region_error else len(full_plane_ids)
            ),
            "dr1_level2_full_region_intersection_by_band": (
                None if use_siav2 or full_region_error else full_band_summary
            ),
            "dr1_level2_full_region_spectral_image_products_by_collection": (
                collection_counts if use_siav2 else None
            ),
            "dr1_level2_full_region_spectral_image_product_rows": (
                None if not use_siav2 or dr1_failed else dr1_rows
            ),
            "qr3_level2_full_region_spectral_image_product_rows": (
                None if not use_siav2 or qr3_failed else qr3_rows
            ),
            "all_release_full_region_spectral_image_product_rows": (
                None if not use_siav2 or any_sia_failed else dr1_rows + qr3_rows
            ),
            "full_region_query_semantics": (
                "IRSA SIAv2 POS-circle product-footprint overlap; metadata rows, not epoch counts"
                if use_siav2 else "region_circle_intersects_exposure_polygon"
            ),
            "candidate_source_exposure_query_status": source_match_status,
            "candidate_source_exposure_query_error": source_match_error,
            "candidate_source_product_match_rows": (
                None if source_match_error else source_product_pair_count
            ),
            "candidate_source_product_match_error": source_product_error,
            "candidate_source_exposure_match_rows": (
                None if source_match_error else len(source_match_rows)
            ),
            "candidate_sources_with_any_level2_footprint_match": (
                None if source_match_error else len(matched_source_ids)
            ),
            "candidate_sources_without_level2_footprint_match": (
                None if source_match_error
                else max(0, len(candidate_ids) - len(matched_source_ids))
            ),
            "candidate_source_exposure_unique_plane_ids": (
                None if use_siav2 or source_match_error else len(source_plane_ids)
            ),
            "candidate_source_matched_archive_product_pair_count": (
                None if source_match_error else source_product_pair_count
            ),
            "candidate_source_archive_observation_id_count_summed_per_source": observation_id_count,
            "candidate_source_exposure_by_band": (
                None if source_match_error else source_band_summary
            ),
            "candidate_source_epoch_summary_rows": (
                None if source_match_error else len(source_summary_rows)
            ),
            "source_coverage_interpretation": (
                "Spherical SIAv2 s_region positional associations and archive metadata only. "
                "Product rows, obs_id values and MJD bounds are not validated independent visits, "
                "extracted flux, calibrated photometry, light curves or YSO identity."
                if use_siav2 else
                "Geometric source-coordinate to Level-2 exposure-polygon matches only. "
                "Extracted flux validity, spectrum quality and usable epoch cadence are not assessed."
            ),
        })
    return (
        region_rows,
        centre_point_exposures,
        full_region_products,
        candidate_source_exposure_matches,
        candidate_source_epoch_summaries,
    )



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
    cube_metadata_path = root / "dr1_all_sky_cube_sia_metadata.csv"
    cube_metadata_rows = (
        read_csv(cube_metadata_path)
        if report.get("schema") == "chronos-spllices-yso-recon/1.1" and cube_metadata_path.is_file()
        else []
    )
    cube_raw = report.get("dr1_all_sky_cube_inventory") or {}
    cube_summary = {
        **(report.get("dr1_all_sky_cube") or {}),
        "metadata_rows_verified_against_csv": (
            None if cube_raw.get("query_errors") else len(cube_metadata_rows)
        ),
        "observed_metadata_rows_in_csv": len(cube_metadata_rows),
        "metadata_access_uri_rows": (
            None if cube_raw.get("query_errors") else sum(
                nonempty(row.get("access_url") or row.get("uri")) for row in cube_metadata_rows
            )
        ),
        "native_cube_downloaded": cube_raw.get("native_cube_downloaded", False),
        "temporal_epoch_series": cube_raw.get("temporal_epoch_series", False),
    } if report.get("schema") == "chronos-spllices-yso-recon/1.1" else None
    label_overlap = _label_overlap(candidates)
    (
        regional,
        centre_point_exposures,
        full_region_exposures,
        candidate_source_exposure_matches,
        candidate_source_epoch_summaries,
    ) = _region_summaries(root, report, candidates)

    def overlap_summary(
        exposures: list[dict], semantics: str, *, archive_products: bool = False
    ) -> dict:
        if archive_products or any(row.get("_chronos_collection") for row in exposures):
            products = defaultdict(set)
            unidentified = 0
            for row in exposures:
                product_id = str(
                    row.get("obs_publisher_did") or row.get("access_url")
                    or row.get("obs_id") or row.get("obsid") or row.get("uri") or row.get("ID") or ""
                ).strip()
                if product_id:
                    products[product_id].add(str(row.get("recon_region") or ""))
                else:
                    unidentified += 1
            cross_region = {
                product_id: sorted(regions)
                for product_id, regions in products.items() if len(regions) > 1
            }
            return {
                "product_rows_across_regions": len(exposures),
                "unique_archive_product_ids_across_regions": len(products),
                "products_with_unidentified_archive_id": unidentified,
                "archive_products_in_multiple_region_queries": len(cross_region),
                "archive_product_region_memberships": cross_region,
                "query_semantics": semantics,
                "interpretation": (
                    "SIAv2 rows are archive spectral-image products returned by regional POS-circle queries. "
                    "Repeated product IDs are reported across region searches; rows are not epoch counts."
                ),
            }
        plane_membership = defaultdict(set)
        for row in exposures:
            plane_id = str(row.get("planeid") or "").strip()
            if plane_id:
                plane_membership[plane_id].add(str(row.get("recon_region") or ""))
        cross_region = {
            plane_id: sorted(regions)
            for plane_id, regions in plane_membership.items() if len(regions) > 1
        }
        return {
            "exposure_rows_across_regions": len(exposures),
            "unique_plane_ids_across_regions": len(plane_membership),
            "plane_ids_in_multiple_region_queries": len(cross_region),
            "plane_id_region_memberships": cross_region,
            "query_semantics": semantics,
            "interpretation": (
                "A repeated plane ID means the same archive exposure satisfies the same "
                "spatial query for multiple predeclared regions. It is not a repeated observation "
                "and does not establish per-source coverage."
            ),
        }

    centre_overlap = overlap_summary(
        centre_point_exposures,
        "fixed_region_centre_point_inside_exposure_polygon",
    )
    full_region_overlap = overlap_summary(
        full_region_exposures,
        (
            "IRSA SIAv2 POS-circle spectral-image products; metadata rows, not epochs"
            if report.get("schema") == "chronos-spllices-yso-recon/1.1"
            else "region_circle_intersects_exposure_polygon"
        ),
        archive_products=report.get("schema") == "chronos-spllices-yso-recon/1.1",
    )
    if report.get("schema") == "chronos-spllices-yso-recon/1.1":
        source_pair_membership = defaultdict(set)
        for region_item in regional:
            if region_item.get("candidate_source_product_match_error"):
                continue
            region_name = str(region_item.get("region") or "")
            product_path = root / region_name / "candidate_source_product_matches.csv"
            if not product_path.is_file():
                continue
            for row in read_csv(product_path):
                source_id = str(row.get("source_id") or "").strip()
                product_id = str(row.get("archive_product_id") or "").strip()
                if source_id and product_id:
                    source_pair_membership[(source_id, product_id)].add(region_name)
        cross_region_source_pairs = {
            f"{source_id}|{product_id}": sorted(regions)
            for (source_id, product_id), regions in source_pair_membership.items()
            if len(regions) > 1
        }
        candidate_source_footprint_overlap = {
            "source_archive_product_match_rows": (
                None if any(row.get("candidate_source_product_match_error") for row in regional)
                else sum(row.get("candidate_source_product_match_rows") or 0 for row in regional)
            ),
            "unique_source_archive_product_pairs_observed": len(source_pair_membership),
            "source_product_pairs_in_multiple_region_queries": len(cross_region_source_pairs),
            "source_archive_product_region_memberships": cross_region_source_pairs,
            "interpretation": (
                "Exact source-to-SIAv2 product positional associations from the per-region manifest; "
                "these are metadata links, not extracted flux or independent epochs."
            ),
        }
    else:
        source_pair_membership = defaultdict(set)
        for row in candidate_source_exposure_matches:
            source_id = str(row.get("source_id") or "").strip()
            plane_id = str(row.get("planeid") or "").strip()
            if source_id and plane_id:
                source_pair_membership[(source_id, plane_id)].add(
                    str(row.get("recon_region") or "")
                )
        cross_region_source_pairs = {
            f"{source_id}|{plane_id}": sorted(regions)
            for (source_id, plane_id), regions in source_pair_membership.items()
            if len(regions) > 1
        }
        candidate_source_footprint_overlap = {
            "source_exposure_match_rows": len(candidate_source_exposure_matches),
            "unique_source_plane_pairs": len(source_pair_membership),
            "source_plane_pairs_in_multiple_region_queries": len(cross_region_source_pairs),
            "source_plane_pair_region_memberships": cross_region_source_pairs,
            "interpretation": (
                "Rows are exact cone-filtered source-coordinate to Level-2 exposure-polygon matches. "
                "Repeated source-plane pairs across region queries are reported, not collapsed."
            ),
        }
    result = {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_validation": input_validation,
        "source_identity_audit": source_ids,
        "label_overlap_audit": label_overlap,
        "candidate_data_quality": _field_quality(candidates),
        "regional_candidate_and_coverage_summaries": regional,
        "cross_region_exposure_overlap": centre_overlap,
        "cross_region_full_region_exposure_overlap": full_region_overlap,
        "cross_region_spectral_image_product_overlap": (
            full_region_overlap if report.get("schema") == "chronos-spllices-yso-recon/1.1"
            else None
        ),
        "dr1_all_sky_cube_inventory": cube_summary,
        "candidate_source_exposure_coverage": {
            "matched_source_summary_row_count": len(candidate_source_exposure_matches),
            "matched_archive_product_pair_count": (
                sum(row.get("candidate_source_product_match_rows") or 0 for row in regional)
                if report.get("schema") == "chronos-spllices-yso-recon/1.1"
                and not any(row.get("candidate_source_product_match_error") for row in regional)
                else None if report.get("schema") == "chronos-spllices-yso-recon/1.1"
                else len(candidate_source_exposure_matches)
            ),
            "product_match_manifest_rows_observed": sum(
                row.get("candidate_source_product_match_rows") or 0 for row in regional
            ),
            "match_row_count": (
                None if report.get("schema") == "chronos-spllices-yso-recon/1.1"
                and any(row.get("candidate_source_exposure_query_status") == "unavailable"
                        for row in regional)
                else len(candidate_source_exposure_matches)
            ),
            "observed_match_row_count_lower_bound": len(candidate_source_exposure_matches),
            "source_summary_row_count": (
                None if report.get("schema") == "chronos-spllices-yso-recon/1.1"
                and any(row.get("candidate_source_exposure_query_status") == "unavailable"
                        for row in regional)
                else len(candidate_source_epoch_summaries)
            ),
            "regions_with_completed_query": sum(
                row.get("candidate_source_exposure_query_status") in {
                    "complete_below_declared_row_cap", "complete_below_declared_caps"
                }
                for row in regional
            ),
            "regions_with_unavailable_query": sum(
                row.get("candidate_source_exposure_query_status") == "unavailable"
                for row in regional
            ),
            "matching_method": (
                "SIAv2 spherical s_region point-in-polygon"
                if report.get("schema") == "chronos-spllices-yso-recon/1.1"
                else "legacy TAP source-to-plane geometry"
            ),
            "metadata_only": report.get("schema") == "chronos-spllices-yso-recon/1.1",
            "source_level_epoch_coverage_measured": False,
            "source_level_calibrated_flux_measured": False,
            "interpretation": "Archive positional associations only; not extracted spectra, calibrated flux, validated light curves or independent epochs.",
        },
        "cross_region_candidate_source_exposure_overlap": candidate_source_footprint_overlap,
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
            "Centre-point TAP rows count exposures whose polygon contains the fixed region-centre coordinate; they are not a full-region product inventory.",
            (
                "SIAv2 POS-circle rows are archive spectral-image products whose footprints overlap the region; they are not per-source epoch counts."
                if report.get("schema") == "chronos-spllices-yso-recon/1.1"
                else "Legacy full-region TAP rows count exposure polygons intersecting the region circle; they are not per-source epoch counts."
            ),
            "The optional source-coordinate join measures candidate-to-Level-2 exposure polygon matches within the exact cone; it is not a validated spectral time series.",
            "The DR1 All-Sky Cube is a separate spatial-spectral archive product; its wavelength channels are not time epochs.",
            "No extracted spectra, image quality flags, flux measurements, completeness or usable-epoch cadence are evaluated in this inventory audit.",
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
