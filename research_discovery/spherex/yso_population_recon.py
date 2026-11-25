#!/usr/bin/env python3
"""Predeclared SPLICES/DR1 field reconnaissance for a future YSO population study.

This script does not claim a YSO discovery. It separates published catalogue
labels from SPLICES machine-learning classes, retains comparison classes, and
measures SPHEREx DR1 + QR3 Level-2 archive coverage for the same predeclared fields.
Full-region footprint intersection uses IRSA SIAv2 POS searches; source-to-exposure
associations use an ADQL point-in-polygon predicate in WHERE.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astroquery.ipac.irsa import Irsa

REGIONS = (
    {"name": "Taurus_Auriga", "ra_deg": 65.7, "dec_deg": 26.0, "radius_deg": 2.0, "role": "star_forming_region"},
    {"name": "Perseus_NGC1333", "ra_deg": 52.30, "dec_deg": 31.30, "radius_deg": 0.85, "role": "star_forming_region"},
    {"name": "Orion_A", "ra_deg": 83.80, "dec_deg": -5.40, "radius_deg": 1.50, "role": "star_forming_region"},
    {"name": "Rho_Ophiuchi", "ra_deg": 246.75, "dec_deg": -24.60, "radius_deg": 0.90, "role": "star_forming_region"},
    {"name": "Lupus_III", "ra_deg": 242.10, "dec_deg": -39.10, "radius_deg": 0.90, "role": "star_forming_region"},
    {"name": "HighLatitude_Control", "ra_deg": 180.0, "dec_deg": 60.0, "radius_deg": 1.50, "role": "control"},
)
OUTPUT = Path("data/yso_population_recon")
CANDIDATE_LIMIT = 5000
DR1_BANDS = tuple(f"SPHEREx-D{i}" for i in range(1, 7))
SIA_COLLECTIONS = (
    "spherex_dr1",
    "spherex_dr1_deep",
    "spherex_qr3",
    "spherex_qr3_deep",
)
SIA_COLLECTION_RELEASE = {
    "spherex_dr1": "dr1",
    "spherex_dr1_deep": "dr1",
    "spherex_qr3": "qr3",
    "spherex_qr3_deep": "qr3",
}


def scalar(value: Any) -> Any:
    if value is None or getattr(value, "mask", False):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return str(value)


def query_rows(query: str) -> dict:
    result = Irsa.query_tap(query)
    table = result.to_table() if hasattr(result, "to_table") else result
    rows = [
        {str(name): scalar(row[name]) for name in table.colnames}
        for row in table
    ]
    return {
        "query": query,
        "columns": list(table.colnames),
        "row_count": len(rows),
        "rows": rows,
    }


def query_region_footprints_sia(region: dict, collection: str) -> dict:
    """Search SIAv2 spectral-image products whose footprints overlap a region."""
    if collection not in SIA_COLLECTIONS:
        raise ValueError(f"unsupported SPHEREx SIAv2 collection: {collection}")
    position = (
        float(region["ra_deg"]),
        float(region["dec_deg"]),
        float(region["radius_deg"]),
    )
    table = Irsa.query_sia(
        pos=position,
        collection=collection,
        maxrec=COVERAGE_ROW_LIMIT,
    )
    table = table.to_table() if hasattr(table, "to_table") else table
    rows = []
    for row in table:
        item = {str(name): scalar(row[name]) for name in table.colnames}
        item["_chronos_collection"] = collection
        item["_chronos_release"] = SIA_COLLECTION_RELEASE[collection]
        item["_chronos_dataset_class"] = "real"
        item["_chronos_region"] = region["name"]
        rows.append(item)
    return {
        "service": "IRSA SIAv2",
        "pos_circle_deg": list(position),
        "collection": collection,
        "release": SIA_COLLECTION_RELEASE[collection],
        "maxrec": COVERAGE_ROW_LIMIT,
        "columns": list(table.colnames),
        "row_count": len(rows),
        "rows": rows,
        "query_complete_below_row_cap": len(rows) < COVERAGE_ROW_LIMIT,
    }


def digest_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def region_predicate(region: dict, ra_col: str = "ra", dec_col: str = "dec") -> str:
    # Follow IRSA's TAP ADQL examples literally: geometry constructors without
    # coordinate-system strings (deprecated in ADQL 2.1), and CONTAINS(...) = 1.
    return (
        "CONTAINS("
        f"POINT({ra_col}, {dec_col}), "
        f"CIRCLE({region['ra_deg']:.8f}, {region['dec_deg']:.8f}, {region['radius_deg']:.5f})"
        ") = 1"
    )


CATALOGUE_ROW_LIMIT = 50000
COVERAGE_ROW_LIMIT = 20000
SOURCE_EPOCH_ROW_LIMIT = 200000


def build_region_queries(region: dict) -> dict[str, str]:
    """Return exact, bounded TAP SQL used for the predeclared sky region.

    IRSA's TAP documentation warns that COUNT() is unsupported in queries
    with geometric constraints. Return rows and calculate summaries locally.
    SPLICES literature, harmonised and ML labels remain independent columns.
    """
    where = region_predicate(region)
    catalogue_sql = (
        f"SELECT TOP {CATALOGUE_ROW_LIMIT} source_id, designation, ra, dec, "
        "sel_type, class_1, yso_pub, stype_ml "
        f"FROM spherex.splices WHERE {where} ORDER BY source_id"
    )
    candidate_sql = (
        f"SELECT TOP {CANDIDATE_LIMIT} source_id, designation, ra, dec, sel_type, class_1, yso_pub, "
        "stype_ml, stype_ml_prob1, stype_ml_prob2, mc, mc_los, mc_dist, av, "
        "plx, e_plx, gaiadist, e_dist_upper, e_dist_lower, "
        "w1, w1err, w2, w2err, w3, w3err, w4, w4err, "
        "w1var, w1var_class, w2var, w2var_class, "
        "numgaianb, mingaiadist, numiracnbors, mindistirac "
        f"FROM spherex.splices WHERE {where} "
        "AND (yso_pub IS NOT NULL OR UPPER(class_1) LIKE '%YSO%' "
        "OR UPPER(stype_ml) LIKE '%YSO%') ORDER BY source_id"
    )
    # This follows the official SPHEREx TAP footprint pattern. Unlike a
    # catalogue cone search, POINT(center) is tested against the exposure
    # polygon; IRSA's own SPHEREx notebook uses the ICRS constructor here.
    exposure_sql = (
        f"SELECT TOP {COVERAGE_ROW_LIMIT} p.planeid, a.uri, p.energy_bandpassname, "
        "p.time_bounds_lower, p.time_bounds_upper "
        "FROM spherex.artifact a JOIN spherex.plane p ON p.planeid = a.planeid "
        "WHERE 1 = CONTAINS("
        f"POINT('ICRS', {region['ra_deg']:.8f}, {region['dec_deg']:.8f}), p.poly) "
        "AND (LOWER(a.uri) LIKE '%/dr1/level2/%' AND p.energy_bandpassname IN ("
        + ", ".join(f"'{band}'" for band in DR1_BANDS)
        + ")) ORDER BY p.time_bounds_lower"
    )
    # Optional source-to-exposure coverage: the only spatial predicate is
    # the supported POINT-in-exposure-POLYGON test. A conservative RA/Dec
    # bounding box limits candidate rows to this region; exact great-circle
    # cone membership is checked locally after TAP returns.
    centre_dec_rad = math.radians(float(region["dec_deg"]))
    radius_rad = math.radians(float(region["radius_deg"]))
    ra_half_width = math.degrees(
        math.asin(min(1.0, math.sin(radius_rad) / max(math.cos(centre_dec_rad), 1e-12)))
    )
    ra_min = float(region["ra_deg"]) - ra_half_width
    ra_max = float(region["ra_deg"]) + ra_half_width
    if ra_min < 0:
        ra_condition = f"(s.ra >= {ra_min + 360.0:.8f} OR s.ra <= {ra_max:.8f})"
    elif ra_max >= 360:
        ra_condition = f"(s.ra >= {ra_min:.8f} OR s.ra <= {ra_max - 360.0:.8f})"
    else:
        ra_condition = f"s.ra BETWEEN {ra_min:.8f} AND {ra_max:.8f}"
    dec_min = max(-90.0, float(region["dec_deg"]) - float(region["radius_deg"]))
    dec_max = min(90.0, float(region["dec_deg"]) + float(region["radius_deg"]))
    source_epoch_sql = (
        f"SELECT TOP {SOURCE_EPOCH_ROW_LIMIT} s.source_id, s.designation, s.ra, s.dec, "
        "s.yso_pub, s.class_1, s.stype_ml, p.planeid, p.obsid, a.uri, "
        "p.energy_bandpassname, p.time_bounds_lower, p.time_bounds_upper "
        "FROM spherex.splices s "
        # Keep explicit joins so IRSA TAP's metadata resolver can resolve each
        # schema-qualified table. The cross join is restricted by the single
        # geometry predicate in WHERE plus a conservative RA/Dec bounding box.
        "JOIN spherex.artifact a ON 1 = 1 "
        "JOIN spherex.plane p ON p.planeid = a.planeid "
        "WHERE CONTAINS(POINT('ICRS', s.ra, s.dec), p.poly) = 1 "
        "AND ("
        f"{ra_condition} "
        f"AND s.dec BETWEEN {dec_min:.8f} AND {dec_max:.8f} "
        "AND (s.yso_pub IS NOT NULL OR UPPER(s.class_1) LIKE '%YSO%' "
        "OR UPPER(s.stype_ml) LIKE '%YSO%') "
        "AND (LOWER(a.uri) LIKE '%/dr1/level2/%' OR LOWER(a.uri) LIKE '%/qr3/level2/%') "
        "AND p.energy_bandpassname IN ("
        + ", ".join(f"'{band}'" for band in DR1_BANDS)
        + ")) ORDER BY s.source_id, p.time_bounds_lower"
    )
    return {
        "catalogue_sources": catalogue_sql,
        "candidate_sources": candidate_sql,
        "dr1_level2_exposures": exposure_sql,
        "candidate_source_exposure_matches": source_epoch_sql,
    }


def great_circle_separation_deg(ra1: float, dec1: float,
                                ra2: float, dec2: float) -> float:
    """Exact spherical separation in degrees, with RA wrap handled."""
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    cosine = (
        math.sin(d1) * math.sin(d2)
        + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def release_from_uri(uri: Any) -> str:
    """Identify DR1/QR3 only when the archive URI explicitly names the release."""
    value = str(uri or "").lower()
    if "/dr1/" in value:
        return "dr1"
    if "/qr3/" in value:
        return "qr3"
    return "unknown"


def summarize_candidate_source_epochs(
    region: dict, candidate_rows: list[dict], match_rows: list[dict],
) -> tuple[list[dict], list[dict], dict]:
    """Filter the conservative TAP bounding box and summarise exact source-plane matches."""
    candidate_by_id = {
        str(row.get("source_id")).strip(): row
        for row in candidate_rows if row.get("source_id") not in (None, "")
    }
    matched_by_source = {}
    seen_pairs = set()
    accepted_rows = []
    centre_ra = float(region["ra_deg"])
    centre_dec = float(region["dec_deg"])
    radius = float(region["radius_deg"])
    for row in match_rows:
        source_id = str(row.get("source_id") or "").strip()
        plane_id = str(row.get("planeid") or "").strip()
        ra, dec = row.get("ra"), row.get("dec")
        try:
            separation = great_circle_separation_deg(
                float(ra), float(dec), centre_ra, centre_dec
            )
        except (TypeError, ValueError):
            continue
        if not source_id or not plane_id or separation > radius:
            continue
        pair = (source_id, plane_id)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        candidate = candidate_by_id.get(source_id, {})
        accepted = {
            **row,
            "data_release": release_from_uri(row.get("uri")),
            "dataset_class": "real",
            "angular_separation_from_region_centre_deg": separation,
            "within_predeclared_region_radius": True,
            "candidate_row_present_in_bounded_query": source_id in candidate_by_id,
            "region": region["name"],
            "region_role": region["role"],
        }
        accepted_rows.append(accepted)
        matched_by_source.setdefault(source_id, []).append(accepted)

    summaries = []
    for source_id, observations in sorted(matched_by_source.items()):
        first_times = []
        last_times = []
        for row in observations:
            for key, bucket in (
                ("time_bounds_lower", first_times),
                ("time_bounds_upper", last_times),
            ):
                try:
                    value = float(row.get(key))
                    if math.isfinite(value):
                        bucket.append(value)
                except (TypeError, ValueError):
                    pass
        exemplar = candidate_by_id.get(source_id) or observations[0]
        summaries.append({
            "source_id": source_id,
            "designation": exemplar.get("designation"),
            "ra": exemplar.get("ra"),
            "dec": exemplar.get("dec"),
            "yso_pub": exemplar.get("yso_pub"),
            "class_1": exemplar.get("class_1"),
            "stype_ml": exemplar.get("stype_ml"),
            "region": region["name"],
            "region_role": region["role"],
            "unique_level2_plane_count": len({row["planeid"] for row in observations}),
            "unique_release_count": len({
                row["data_release"] for row in observations
                if row["data_release"] != "unknown"
            }),
            "releases": ";".join(sorted({
                row["data_release"] for row in observations
                if row["data_release"] != "unknown"
            })),
            "unique_observation_count": len({
                str(row.get("obsid") or "").strip() for row in observations
                if row.get("obsid") not in (None, "")
            }),
            "unique_band_count": len({
                str(row.get("energy_bandpassname") or "") for row in observations
            }),
            "bands": ";".join(sorted({
                str(row.get("energy_bandpassname") or "") for row in observations
            })),
            "first_mjd": min(first_times) if first_times else None,
            "last_mjd": max(last_times) if last_times else None,
            "exposure_plane_ids": ";".join(sorted({row["planeid"] for row in observations})),
        })
    candidate_ids = set(candidate_by_id)
    matched_ids = set(matched_by_source)
    report = {
        "candidate_source_id_count": len(candidate_ids),
        "candidate_source_ids_with_level2_footprint_match": len(matched_ids),
        "candidate_source_ids_without_level2_footprint_match": len(candidate_ids - matched_ids),
        "source_exposure_pair_rows_after_cone_filter_and_plane_dedup": len(accepted_rows),
        "source_epoch_query_row_count_before_cone_filter": len(match_rows),
        "source_epoch_query_row_cap": SOURCE_EPOCH_ROW_LIMIT,
        "source_epoch_query_at_cap": len(match_rows) >= SOURCE_EPOCH_ROW_LIMIT,
        "candidate_query_complete": len(candidate_rows) < CANDIDATE_LIMIT,
        "interpretation": (
            "A match means the catalogue source coordinate lies inside a returned DR1 or QR3 Level-2 exposure polygon. "
            "It is a geometric archive-coverage match, not proof of valid extracted flux, spectrum quality, "
            "usable epoch cadence, or an astrophysical classification."
        ),
    }
    return accepted_rows, summaries, report


def _is_yso_like(row: dict) -> bool:
    class_1 = str(row.get("class_1") or "").upper()
    ml_class = str(row.get("stype_ml") or "").upper()
    return (
        row.get("yso_pub") is not None
        or "YSO" in class_1
        or "YSO" in ml_class
    )


def label_profile(row: dict) -> dict:
    """Compare independent catalogue label columns without promoting ML labels to truth."""
    published = row.get("yso_pub") is not None
    harmonised = "YSO" in str(row.get("class_1") or "").upper()
    machine = "YSO" in str(row.get("stype_ml") or "").upper()
    sources = [
        name for name, present in (
            ("published_yso_pub", published),
            ("harmonised_class_1", harmonised),
            ("machine_stype_ml", machine),
        ) if present
    ]
    if all((published, harmonised, machine)):
        profile = "published_harmonised_ml_agree"
    elif machine and not published and not harmonised:
        profile = "ml_only"
    elif (published or harmonised) and not machine:
        profile = "non_ml_label_without_ml_yso"
    elif machine and (published or harmonised):
        profile = "partial_multi_source_agreement"
    else:
        profile = "not_yso_labelled"
    return {
        "source_id": row.get("source_id"),
        "designation": row.get("designation"),
        "ra": row.get("ra"),
        "dec": row.get("dec"),
        "yso_pub": row.get("yso_pub"),
        "class_1": row.get("class_1"),
        "stype_ml": row.get("stype_ml"),
        "stype_ml_prob1": row.get("stype_ml_prob1"),
        "stype_ml_prob2": row.get("stype_ml_prob2"),
        "published_yso_label": published,
        "harmonised_class1_yso_label": harmonised,
        "machine_yso_label": machine,
        "independent_label_source_count": len(sources),
        "label_profile": profile,
        "machine_only_candidate": profile == "ml_only",
        "multi_source_label_support": len(sources) >= 2,
        "interpretation": (
            "ML-only candidate for independent review"
            if profile == "ml_only"
            else "Catalogue label concordance descriptor; not an independently confirmed YSO"
        ),
    }


def summarise_label_concordance(rows: list[dict]) -> dict:
    profiles = {}
    profiled = [label_profile(row) for row in rows]
    for row in profiled:
        key = row["label_profile"]
        profiles[key] = profiles.get(key, 0) + 1
    return {
        "source_row_count": len(rows),
        "published_yso_pub_count": sum(row["published_yso_label"] for row in profiled),
        "harmonised_class_1_yso_count": sum(row["harmonised_class1_yso_label"] for row in profiled),
        "machine_stype_ml_yso_count": sum(row["machine_yso_label"] for row in profiled),
        "all_three_label_sources_agree_count": profiles.get("published_harmonised_ml_agree", 0),
        "ml_only_label_count": profiles.get("ml_only", 0),
        "non_ml_label_without_ml_yso_count": profiles.get("non_ml_label_without_ml_yso", 0),
        "partial_multi_source_agreement_count": profiles.get("partial_multi_source_agreement", 0),
        "multi_source_label_support_count": sum(row["multi_source_label_support"] for row in profiled),
        "label_profiles": profiles,
        "interpretation": (
            "Counts describe concordance among catalogue label fields. They are not independent "
            "validation, a contamination-corrected YSO census, or a population-rate estimate."
        ),
    }


def inspect_region(region: dict) -> dict:
    """Execute TAP queries and derive counts without unsupported spatial COUNT()."""
    query_definitions = build_region_queries(region)
    query_results = {}
    optional_query_errors = {}
    for name, sql in query_definitions.items():
        try:
            query_results[name] = query_rows(sql)
        except Exception as exc:
            error_record = {
                "query": sql,
                "error": f"{type(exc).__name__}: {exc}",
                "row_count": None,
                "rows": [],
            }
            if name == "candidate_source_exposure_matches":
                error_record["optional"] = True
                optional_query_errors[name] = error_record["error"]
            else:
                error_record["optional"] = False
            query_results[name] = error_record

    optional_sia_errors = {}
    for collection in SIA_COLLECTIONS:
        name = f"region_footprints_sia_{collection}"
        try:
            query_results[name] = query_region_footprints_sia(region, collection)
        except Exception as exc:
            optional_sia_errors[collection] = f"{type(exc).__name__}: {exc}"
            query_results[name] = {
                "service": "IRSA SIAv2",
                "collection": collection,
                "release": SIA_COLLECTION_RELEASE[collection],
                "maxrec": COVERAGE_ROW_LIMIT,
                "row_count": None,
                "rows": [],
                "error": optional_sia_errors[collection],
                "optional": True,
            }

    catalogue_result = query_results["catalogue_sources"]
    catalogue_rows = catalogue_result.get("rows", [])
    catalogue_error = catalogue_result.get("error")
    catalogue_complete = (
        not catalogue_error and len(catalogue_rows) < CATALOGUE_ROW_LIMIT
    )
    counts = {
        "catalogue_rows_returned": len(catalogue_rows) if not catalogue_error else None,
        "catalogue_row_limit": CATALOGUE_ROW_LIMIT,
        "catalogue_query_complete": catalogue_complete,
        "total_catalogue_rows": len(catalogue_rows) if catalogue_complete else None,
        "published_yso_label_rows": sum(row.get("yso_pub") is not None for row in catalogue_rows) if not catalogue_error else None,
        "class_1_yso_rows": sum("YSO" in str(row.get("class_1") or "").upper() for row in catalogue_rows) if not catalogue_error else None,
        "ml_yso_rows": sum("YSO" in str(row.get("stype_ml") or "").upper() for row in catalogue_rows) if not catalogue_error else None,
    }
    counts["label_counts_are_lower_bounds"] = not catalogue_complete

    class_counter = {}
    for row in catalogue_rows:
        key = (
            str(row.get("class_1") or "NULL"),
            str(row.get("yso_pub") if row.get("yso_pub") is not None else "NULL"),
            str(row.get("stype_ml") or "NULL"),
        )
        class_counter[key] = class_counter.get(key, 0) + 1
    class_rows = [
        {"class_1": key[0], "yso_pub": key[1], "stype_ml": key[2], "n": count}
        for key, count in sorted(class_counter.items(), key=lambda item: (-item[1], item[0]))
    ]
    query_results["class_distribution"] = {
        "method": "local counts over catalogue_sources rows returned by bounded spatial query",
        "source_row_count": len(catalogue_rows),
        "source_query_complete": catalogue_complete,
        "row_count": len(class_rows),
        "rows": class_rows,
    }

    candidate_result = query_results["candidate_sources"]
    candidate_rows = candidate_result.get("rows", [])
    candidate_error = candidate_result.get("error")
    counts["candidate_rows_returned"] = len(candidate_rows) if not candidate_error else None
    counts["candidate_query_limit"] = CANDIDATE_LIMIT
    counts["candidate_query_complete"] = (
        not candidate_error and len(candidate_rows) < CANDIDATE_LIMIT
    )
    candidate_profiles = [label_profile(row) for row in candidate_rows]
    query_results["label_disagreement_candidates"] = {
        "method": "row-wise concordance across yso_pub, class_1 and stype_ml",
        "source_query": query_definitions["candidate_sources"],
        "source_row_count": len(candidate_rows),
        "rows": candidate_profiles,
    }
    label_summary = summarise_label_concordance(catalogue_rows) if not catalogue_error else {
        "source_row_count": None, "status": "unavailable_due_to_catalogue_query_error"
    }
    counts["label_concordance"] = label_summary
    counts["ml_only_candidate_rows_in_bounded_candidate_query"] = sum(
        row["machine_only_candidate"] for row in candidate_profiles
    )

    source_epoch_result = query_results["candidate_source_exposure_matches"]
    source_epoch_error = source_epoch_result.get("error")
    source_epoch_rows = source_epoch_result.get("rows", [])
    if source_epoch_error:
        matched_source_exposure_rows = []
        source_epoch_summaries = []
        source_epoch_summary = {
            "status": "unavailable_due_to_optional_query_error",
            "error": source_epoch_error,
            "candidate_source_id_count": None,
            "candidate_source_ids_with_level2_footprint_match": None,
            "candidate_source_ids_without_level2_footprint_match": None,
        }
    else:
        matched_source_exposure_rows, source_epoch_summaries, source_epoch_summary = (
            summarize_candidate_source_epochs(region, candidate_rows, source_epoch_rows)
        )
        source_epoch_summary["status"] = (
            "lower_bound_at_declared_row_cap"
            if source_epoch_summary["source_epoch_query_at_cap"]
            else "complete_below_declared_row_cap"
        )
    counts["candidate_source_exposure_query_complete"] = (
        not source_epoch_error
        and not source_epoch_summary.get("source_epoch_query_at_cap", False)
        and bool(counts["candidate_query_complete"])
    )
    counts["candidate_source_exposure_match_rows"] = (
        len(matched_source_exposure_rows) if not source_epoch_error else None
    )
    counts["candidate_unique_source_ids_with_level2_footprint_match"] = (
        source_epoch_summary.get("candidate_source_ids_with_level2_footprint_match")
    )
    counts["candidate_unique_source_ids_without_level2_footprint_match"] = (
        source_epoch_summary.get("candidate_source_ids_without_level2_footprint_match")
    )
    counts["candidate_source_footprint_matches_measured"] = not bool(source_epoch_error)
    counts["source_level_epoch_coverage_measured"] = False
    query_results["candidate_source_exposure_matches"]["rows"] = (
        matched_source_exposure_rows if not source_epoch_error else []
    )
    query_results["candidate_source_epoch_summary"] = {
        "method": "great-circle cone filter and unique SPLICES source ID / Level-2 plane ID pairs",
        "summary": source_epoch_summary,
        "rows": source_epoch_summaries,
    }

    exposure_result = query_results["dr1_level2_exposures"]
    exposure_rows = exposure_result.get("rows", [])
    exposure_error = exposure_result.get("error")
    by_band = {}
    for row in exposure_rows:
        band = str(row.get("energy_bandpassname") or "UNKNOWN")
        record = by_band.setdefault(band, {
            "exposure_rows": 0, "first_time": None, "last_time": None,
        })
        record["exposure_rows"] += 1
        lo, hi = row.get("time_bounds_lower"), row.get("time_bounds_upper")
        record["first_time"] = min(record["first_time"], lo) if record["first_time"] is not None else lo
        record["last_time"] = max(record["last_time"], hi) if record["last_time"] is not None else hi
    counts["dr1_level2_exposure_rows_by_band"] = None if exposure_error else by_band
    counts["dr1_level2_exposure_rows_total"] = None if exposure_error else len(exposure_rows)
    query_below_cap = (
        not exposure_error and len(exposure_rows) < COVERAGE_ROW_LIMIT
    )
    counts["dr1_level2_query_complete_under_declared_row_cap"] = query_below_cap
    # Keep the original key for existing readers, but explicitly scope it to
    # query completeness, not survey-wide or source-level completeness.
    counts["dr1_level2_coverage_complete"] = query_below_cap
    counts["dr1_level2_coverage_query_semantics"] = (
        "region_center_point_inside_exposure_polygon"
    )

    full_region_counts = {}
    full_region_rows = []
    dr1_collections = ("spherex_dr1", "spherex_dr1_deep")
    for collection in SIA_COLLECTIONS:
        result = query_results[f"region_footprints_sia_{collection}"]
        if result.get("error"):
            continue
        rows = result.get("rows", [])
        full_region_rows.extend(rows)
        full_region_counts[collection] = {
            "release": SIA_COLLECTION_RELEASE[collection],
            "product_rows": len(rows),
            "row_cap": COVERAGE_ROW_LIMIT,
            "query_complete_below_row_cap": len(rows) < COVERAGE_ROW_LIMIT,
        }
    successful_collections = [
        collection for collection in SIA_COLLECTIONS
        if not query_results[f"region_footprints_sia_{collection}"].get("error")
    ]
    counts["region_footprint_sia_collection_count_requested"] = len(SIA_COLLECTIONS)
    counts["region_footprint_sia_collection_count_succeeded"] = len(successful_collections)
    counts["region_footprint_sia_collection_count_failed"] = len(SIA_COLLECTIONS) - len(successful_collections)
    counts["region_intersecting_spectral_image_rows_by_collection"] = (
        full_region_counts if successful_collections else None
    )
    counts["region_intersecting_spectral_image_rows_total"] = (
        len(full_region_rows) if successful_collections else None
    )
    counts["region_intersecting_spectral_image_queries_complete_below_row_cap"] = (
        len(successful_collections) == len(SIA_COLLECTIONS)
        and all(item["query_complete_below_row_cap"] for item in full_region_counts.values())
    )
    counts["region_intersecting_spectral_image_query_semantics"] = (
        "IRSA SIAv2 POS circle; returned spectral-image footprint overlaps the predeclared region"
    )
    dr1_rows = [row for row in full_region_rows if row.get("_chronos_release") == "dr1"]
    dr1_available = all(
        not query_results[f"region_footprints_sia_{collection}"].get("error")
        for collection in dr1_collections
    )
    counts["dr1_level2_exposures_intersecting_full_region_total"] = (
        len(dr1_rows) if dr1_available else None
    )
    counts["dr1_level2_full_region_query_complete_under_declared_row_cap"] = (
        dr1_available
        and all(
            len(query_results[f"region_footprints_sia_{collection}"].get("rows", [])) < COVERAGE_ROW_LIMIT
            for collection in dr1_collections
        )
    )
    counts["dr1_level2_full_region_coverage_query_semantics"] = (
        "IRSA SIAv2 POS circle across DR1 wide and deep spectral-image collections"
    )
    counts["dr1_level2_full_region_optional_query_error"] = {
        collection: optional_sia_errors[collection]
        for collection in dr1_collections if collection in optional_sia_errors
    } or None
    counts["region_footprint_sia_optional_query_errors"] = optional_sia_errors
    counts["source_level_epoch_coverage_measured"] = False

    query_errors = {
        name: result["error"]
        for name, result in query_results.items()
        if result.get("error") and not result.get("optional")
    }
    return {
        "region": region,
        "counts": counts,
        "queries": query_results,
        "query_sha256": digest_json(query_definitions),
        "query_errors": query_errors,
        "optional_query_errors": optional_query_errors,
        "optional_sia_errors": optional_sia_errors,
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    summaries = []
    all_candidates = []
    all_classes = []
    all_label_disagreements = []
    all_source_exposure_matches = []
    all_source_epoch_summaries = []
    all_region_sia_footprints = []
    errors = []
    for region in REGIONS:
        print(f"Querying SPLICES and DR1/QR3 coverage: {region['name']}", flush=True)
        try:
            result = inspect_region(region)
            summaries.append({
                "region": region,
                "counts": result["counts"],
                "query_sha256": result["query_sha256"],
                "query_errors": result["query_errors"],
                "optional_query_errors": result["optional_query_errors"],
                "optional_sia_errors": result["optional_sia_errors"],
            })
            if result["query_errors"]:
                errors.append({
                    "region": region,
                    "query_errors": result["query_errors"],
                })
            for row in result["queries"]["candidate_sources"]["rows"]:
                all_candidates.append({**row, "recon_region": region["name"], "region_role": region["role"]})
            for row in result["queries"]["class_distribution"]["rows"]:
                all_classes.append({**row, "recon_region": region["name"], "region_role": region["role"]})
            for row in result["queries"]["label_disagreement_candidates"]["rows"]:
                all_label_disagreements.append({
                    **row, "recon_region": region["name"], "region_role": region["role"]
                })
            all_source_exposure_matches.extend(
                result["queries"]["candidate_source_exposure_matches"]["rows"]
            )
            all_source_epoch_summaries.extend(
                result["queries"]["candidate_source_epoch_summary"]["rows"]
            )
            for name, query_result in result["queries"].items():
                if name.startswith("region_footprints_sia_"):
                    all_region_sia_footprints.extend(query_result.get("rows", []))
            region_dir = OUTPUT / region["name"]
            for name, query_result in result["queries"].items():
                if "rows" in query_result and name in {
                    "catalogue_sources", "candidate_sources", "class_distribution",
                    "label_disagreement_candidates", "dr1_level2_exposures",
                    "candidate_source_exposure_matches",
                    "candidate_source_epoch_summary"
                } or name.startswith("region_footprints_sia_"):
                    write_csv(region_dir / f"{name}.csv", query_result["rows"])
            (region_dir / "query_record.json").write_text(
                json.dumps(result, indent=2, default=str), encoding="utf-8"
            )
        except Exception as exc:
            errors.append({
                "region": region,
                "error": f"{type(exc).__name__}: {exc}",
            })
    write_csv(OUTPUT / "candidate_sources_all_regions.csv", all_candidates)
    write_csv(OUTPUT / "class_distribution_all_regions.csv", all_classes)
    write_csv(OUTPUT / "label_disagreement_candidates_all_regions.csv", all_label_disagreements)
    write_csv(OUTPUT / "candidate_source_exposure_matches_all_regions.csv", all_source_exposure_matches)
    write_csv(OUTPUT / "candidate_source_epoch_summary_all_regions.csv", all_source_epoch_summaries)
    write_csv(OUTPUT / "region_intersecting_footprints_sia_all_regions.csv", all_region_sia_footprints)
    report = {
        "schema": "chronos-spllices-yso-recon/1.1",
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "catalogue": "IRSA spherex.splices",
        "catalogue_release": "SPLICES v8.6 according to IRSA release notes; actual TAP response is retained",
        "spectral_image_archive": {
            "source": "NASA/IPAC IRSA SPHEREx",
            "releases": ["DR1", "QR3"],
            "siav2_collections": list(SIA_COLLECTIONS),
            "coverage_search": "POS-circle footprint overlap; wide and deep collections preserved separately",
            "data_class": "real",
        },
        "dr1_all_sky_cube": {
            "collection": "spherex_dr1_cube",
            "nominal_channels": 102,
            "wavelength_range_um": [0.75, 5.0],
            "role": "spatial-spectral context, not a temporal epoch sequence",
            "queried_in_this_reconnaissance": False,
        },
        "predeclared_regions": list(REGIONS),
        "region_results": summaries,
        "candidate_record_count": len(all_candidates),
        "class_distribution_record_count": len(all_classes),
        "label_disagreement_candidate_count": len(all_label_disagreements),
        "candidate_source_exposure_match_row_count": len(all_source_exposure_matches),
        "candidate_source_epoch_summary_row_count": len(all_source_epoch_summaries),
        "region_intersecting_spectral_image_footprint_row_count": len(all_region_sia_footprints),
        "region_footprint_sia_collections": list(SIA_COLLECTIONS),
        "optional_query_errors": {
            item["region"]["name"]: item.get("optional_query_errors", {})
            for item in summaries if item.get("optional_query_errors")
        },
        "optional_sia_errors": {
            item["region"]["name"]: item.get("optional_sia_errors", {})
            for item in summaries if item.get("optional_sia_errors")
        },
        "label_profile_counts_by_region": {
            item["region"]["name"]: item["counts"].get("label_concordance")
            for item in summaries
        },
        "ml_only_candidate_rows": [
            row for row in all_label_disagreements if row.get("machine_only_candidate")
        ],
        "errors": errors,
        "scientific_boundary": [
            "SPLICES is a broad ice-source target compilation, not a census of confirmed YSOs.",
            "Published YSO labels (CLASS_1/YSO_PUB) and ML labels (STYPE_ML/STYPE_ML_PROB*) are retained separately.",
            "Machine-learning classification is not treated as independent confirmation.",
            "The regional counts are not a population rate; selection functions and contamination must be modelled.",
            "This reconnaissance does not establish a new YSO discovery.",
            "The centre-point DR1 TAP query tests whether each fixed region-centre coordinate lies inside an exposure polygon.",
            "Full-region footprint coverage uses SIAv2 POS-circle searches over DR1 and QR3 wide/deep spectral-image collections; each collection and row cap is preserved separately.",
            "The DR1 All-Sky Cube is a distinct 102-channel spatial-spectral product and is not treated as a sequence of independent temporal exposures.",
            "DR1 and QR3 are the current uniformly processed spectral-image set; QR2 is not combined into this analysis.",
            "The row-cap checks establish only that each completed query returned fewer than 20000 rows; they do not establish survey-wide or source-level coverage completeness.",
            "The candidate-source TAP query matches SPLICES coordinates to DR1/QR3 Level-2 exposure polygons; this is geometric archive footprint coverage, not extracted-flux validity, spectrum quality, usable epoch cadence or source-level epoch completeness.",
        ],
        "report_sha256": None,
    }
    report["report_sha256"] = digest_json({k: v for k, v in report.items() if k != "report_sha256"})
    (OUTPUT / "yso_population_recon.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({
        "regions": summaries,
        "candidate_record_count": len(all_candidates),
        "errors": errors,
        "report": str(OUTPUT / "yso_population_recon.json"),
        "report_sha256": report["report_sha256"],
    }, indent=2, default=str))
    # Preserve the full report/artifact, but make any incomplete survey visible
    # as a failed CI job instead of a misleading green workflow.
    if errors:
        raise SystemExit(f"{len(errors)} region(s) had failed TAP queries; inspect the uploaded report artifact.")


if __name__ == "__main__":
    main()
