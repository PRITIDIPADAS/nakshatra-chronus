#!/usr/bin/env python3
"""Predeclared SPLICES/DR1 field reconnaissance for a future YSO population study.

This script does not claim a YSO discovery. It separates published catalogue
labels from SPLICES machine-learning classes, retains comparison classes, and
measures SPHEREx DR1 Level-2 archive coverage for the same predeclared fields.
"""
from __future__ import annotations

import csv
import hashlib
import json
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
    return {
        "catalogue_sources": catalogue_sql,
        "candidate_sources": candidate_sql,
        "dr1_level2_exposures": exposure_sql,
    }


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
    for name, sql in query_definitions.items():
        try:
            query_results[name] = query_rows(sql)
        except Exception as exc:
            query_results[name] = {
                "query": sql,
                "error": f"{type(exc).__name__}: {exc}",
                "row_count": None,
                "rows": [],
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
    counts["source_level_epoch_coverage_measured"] = False

    query_errors = {
        name: result["error"]
        for name, result in query_results.items()
        if result.get("error")
    }
    return {
        "region": region,
        "counts": counts,
        "queries": query_results,
        "query_sha256": digest_json(query_definitions),
        "query_errors": query_errors,
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    summaries = []
    all_candidates = []
    all_classes = []
    all_label_disagreements = []
    errors = []
    for region in REGIONS:
        print(f"Querying SPLICES and DR1 coverage: {region['name']}", flush=True)
        try:
            result = inspect_region(region)
            summaries.append({
                "region": region,
                "counts": result["counts"],
                "query_sha256": result["query_sha256"],
                "query_errors": result["query_errors"],
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
            region_dir = OUTPUT / region["name"]
            for name, query_result in result["queries"].items():
                if "rows" in query_result and name in {
                    "catalogue_sources", "candidate_sources", "class_distribution",
                    "label_disagreement_candidates", "dr1_level2_exposures"
                }:
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
    report = {
        "schema": "chronos-spllices-yso-recon/1.0",
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "catalogue": "IRSA spherex.splices",
        "catalogue_release": "SPLICES v8.6 according to IRSA release notes; actual TAP response is retained",
        "predeclared_regions": list(REGIONS),
        "region_results": summaries,
        "candidate_record_count": len(all_candidates),
        "class_distribution_record_count": len(all_classes),
        "label_disagreement_candidate_count": len(all_label_disagreements),
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
            "The DR1 exposure query tests whether each fixed region-centre coordinate lies inside an exposure polygon; it does not enumerate every exposure intersecting the full region cone.",
            "The DR1 row-cap check establishes only that the centre-point query returned fewer than 20000 rows; it does not establish survey-wide or source-level coverage completeness.",
            "No source-level candidate-to-exposure matching or extracted spectra/epoch completeness is measured by this reconnaissance.",
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
