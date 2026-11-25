# SPHEREx DR1 / SPLICES regional catalogue reconnaissance — 2026-11-25

**Scope:** predeclared query of the public IRSA `spherex.splices` catalogue and SPHEREx DR1 Level-2 exposures whose detector footprint contains each predeclared region-centre coordinate, across five star-forming regions and one high-latitude control. This is catalogue reconnaissance, not source reclassification or a YSO population discovery.

## Reproducible run

- GitHub Actions: [run 45619403576](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45619403576)
- Commit: `bf94adc459164916c9cd42173d2d7cd768bf3bb4`
- Conclusion: `success`; the job ran the predeclared regional catalogue and SPHEREx footprint queries without TAP errors.
- Artifact: `15023987147` (`spherex-yso-population-recon`), 1,783,173 bytes, retained by Actions until 2026-12-25.
- Artifact SHA-256: `f7ddddf549720623a914416336a908b20d6f7f68423a3a3d0d4cbb9381e16863`.
- Machine report: `data/yso_population_recon/yso_population_recon.json`.
- Machine-report SHA-256: `96e7d9539bb52bac6697c5dbde329e27b44a047e7d0c9bae860d16f3035a22de`.
- Catalogue: IRSA `spherex.splices`; the report records SPLICES v8.6 as the release returned by the service.

The query plan is archived per region, with catalogue rows, candidate rows, class distributions and Level-2 footprint rows kept as separate tables. Each query has a recorded SHA-256. A query failure is a workflow failure; a failed query is not converted into a count of zero.

## Predeclared regions and returned rows

| Region | Radius | Catalogue rows | YSO_PUB not null | CLASS_1 containing YSO | STYPE_ML containing YSO | Candidate union rows | DR1 exposures covering region centre |
|---|---:|---:|---:|---:|---:|---:|---:|
| Taurus / Auriga | 2.00° | 4,176 | 58 | 58 | 208 | 237 | 242 |
| Perseus / NGC 1333 | 0.85° | 849 | 130 | 130 | 120 | 189 | 241 |
| Orion A | 1.50° | 4,990 | 1,083 | 1,083 | 342 | 1,337 | 237 |
| Rho Ophiuchi | 0.90° | 2,617 | 167 | 167 | 366 | 482 | 297 |
| Lupus III | 0.90° | 4,016 | 52 | 52 | 129 | 176 | 235 |
| High-latitude control | 1.50° | 15 | 0 | 0 | 0 | 0 | 288 |
| **Total of regional query returns** | — | **16,663** | **1,490** | **1,490** | **1,165** | **2,421** | **1,540** |

All catalogue query results were below the 50,000-row cap; all candidate rows were below the 5,000-row cap; and all footprint rows were below the 20,000-row cap. No regional count in this table is a truncated lower bound.

The total row is a sum of regional query returns, not a count of unique objects across the whole sky. Regions are predeclared cones, and any catalogue source lying in overlapping cones would be counted in each regional result. The high-latitude control is a comparison region, not a matched control sample with identical extinction, completeness or observing history.

The 1,540 Level-2 rows are exposures whose native footprints contain the single predeclared region-centre coordinate used by each query. They are **not** all exposures intersecting each circular region: the query does not test overlap with the full cone. They are also not claimed to be 1,540 unique exposures; the same exposure can cover more than one region centre, and cross-region plane-ID deduplication is handled by the separate candidate-inventory audit. These centre-point counts do not establish which individual catalogue source lies in an exposure, source-level visits, or epoch completeness. A row count below the declared 20,000-row cap means only that the centre-point query completed below that cap, not that full survey coverage is complete.

## Full-region footprint-query extension

The live reconnaissance above records the **centre-point** query only. The current workflow now also issues a separate optional ADQL shape-intersection query using `INTERSECTS(CIRCLE('ICRS', ra, dec, radius), p.poly)` to count Level-2 exposure polygons overlapping the entire predeclared circular region. This follows the IRSA SPHEREx ADQL help, which documents `INTERSECTS` for two geometry regions ([IRSA SPHEREx help](https://irsa.ipac.caltech.edu/onlinehelp/spherex/help.pdf?id=2073b24); [ADQL 2.1 specification](https://www.ivoa.net/documents/ADQL/20210528/PR-ADQL-2.1-20210528.html)).

The new full-region query has a separate row-cap check, CSV, and cross-region plane-ID audit. It is optional and non-fatal: if the live TAP service rejects the shape-intersection expression, the error is recorded in `optional_query_errors`; the analyzer does not treat the failed query as zero coverage and ignores any stale full-region CSV. No full-region-intersection counts are added to the historical 1,540 centre-point rows in this report until a new live workflow run successfully returns and validates them.

## Labels were not merged into a single truth class

The three YSO-related fields retain distinct meanings:

- `YSO_PUB`: a non-null literature-reference field in SPLICES.
- `CLASS_1`: the catalogue's harmonised class field.
- `STYPE_ML`: the machine-learning source-type label.

The observed sums are 1,490 rows with `YSO_PUB` non-null, 1,490 rows whose `CLASS_1` text contains YSO, and 1,165 rows whose `STYPE_ML` text contains YSO. In the exported 2,421-row candidate union, a row-by-row overlap audit found that the `YSO_PUB` and `CLASS_1` flags have identical membership on all 2,421 rows. This is an observed property of the returned catalogue/query, not evidence that the underlying label-generation processes are independent.

The three-field intersection patterns in the exported candidate union are:

| YSO_PUB present | CLASS_1 contains YSO | STYPE_ML contains YSO | Candidate rows |
|---|---|---|---:|
| Yes | Yes | No | 1,256 |
| No | No | Yes | 931 |
| Yes | Yes | Yes | 234 |
| **Total** |  |  | **2,421** |

No row in this candidate export has a disagreement between the `YSO_PUB` and `CLASS_1` YSO flags. The 931 ML-only records are candidates for independent review, not newly confirmed YSOs. The 234 rows with all three labels are catalogue-field agreement, not independent astrophysical confirmation.

All 2,421 exported candidate rows have a non-empty source ID, and the source IDs are unique within this five-region-plus-control export (2,421 unique IDs, zero repeated IDs). This says nothing about uniqueness outside the queried catalogue and sky regions.

The 2,421 candidate-union rows are records matching at least one of the three fields. They are not 2,421 new YSOs, not 2,421 spectroscopically confirmed YSOs, and not a selection-function-corrected population.

## Query implementation corrections

The first live query iteration used a spatial aggregate form rejected by the IRSA TAP service. That workflow was not accepted as a result. The final query implementation:
- uses an IRSA-compatible spatial predicate for the SPLICES cone query;
- retrieves a bounded row table and computes label counts locally instead of relying on unsupported geometric `COUNT()` / `GROUP BY` aggregation;
- keeps candidate details, full catalogue rows, and exposure-footprint rows separate;
- uses the published SPHEREx exposure-polygon pattern to test whether the fixed predeclared region-centre coordinate lies inside each returned exposure footprint;
- records per-query errors and returns a non-zero exit status if any required query fails;
- records whether the query cap was reached; counts are described as exact for a completed query below the cap and as lower bounds if the cap is reached.

The candidate table includes source identifiers, coordinates, published/harmonised/ML labels, probabilities, infrared photometry and variability fields, parallax/distance and neighbourhood fields where available. The CSVs are retained in the workflow artifact; the source IDs and per-field rows are not duplicated into this summary.

## What this does and does not establish

**Established:** the current IRSA TAP service returned the archived catalogue rows and Level-2 exposure rows covering each of the six fixed region-centre coordinates under the recorded query definitions; the live query completed without errors; the returned counts are below their declared row caps.

**Not established:** an unbiased YSO census, physical classification of every candidate, independent verification of machine-learning classifications, completeness or contamination rates, a regional YSO formation rate, all exposures intersecting each full region cone, unique exposure counts after cross-region overlap removal, source-level temporal coverage, or any new astronomical discovery.

Before a population estimate, the project still needs a frozen source inclusion rule, independent validation of candidate classes, a selection function, source-level epoch coverage, completeness and contamination estimates, null/control modelling, overlap deduplication, and a preregistered statistical analysis. Any later discovery claim needs independent astronomical reproduction and review.


## Updated live reconnaissance and candidate-inventory audit — 25 November 2026

The latest audited rerun is [GitHub Actions run 45636514684](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45636514684), code revision `a7d6647fb772987d3e3761445efa9e9be993653a`. Artifact ID `15033905878` has SHA-256 `32f080fe543063381eca4453f1df691312be8fcb9`. The catalogue, bounded candidate, region-centre Level-2 exposure and candidate-inventory audit steps completed successfully.

The candidate union contains 2,421 rows; all 2,421 have non-empty source IDs and there are zero repeated source-ID groups within this export. The candidate label overlap is:
- 1,490 rows with a non-null `YSO_PUB` field and 1,490 with `CLASS_1` containing YSO; those two flags had identical membership in this candidate export.
- 1,165 rows with `STYPE_ML` containing YSO.
- 1,256 rows with published/harmonised labels but no ML YSO label.
- 931 ML-only YSO-labelled rows.
- 234 rows with all three fields indicating YSO.

These are catalogue-field overlaps, not independently confirmed astrophysical classifications. The 931 ML-only rows are review candidates, not newly discovered YSOs.

The six regional query returns sum to 16,663 catalogue rows, 2,421 candidate-union rows and 1,540 centre-point Level-2 footprint rows. The 1,540 figure is a sum of regional centre-point queries, not a globally deduplicated unique-exposure count. The exposure query tests whether the single predeclared region-centre point is inside the exposure polygon; it is not a full-region intersection or source-visit count.

**Source-level epoch coverage remains unavailable.** The optional candidate-source-to-exposure query still fails at the IRSA TAP metadata resolver (`unknown datasource / table: spherex / spherex.artifact`) after an explicit-join attempt. The optional full-region circle/polygon query is also rejected as an invalid/unsupported ADQL query. These outputs are null/unmeasured, not zero. Do not infer individual source exposure matches, visit counts or usable cadence from the centre-point footprint rows.

This follow-up remains descriptive reconnaissance only. It does not establish a contamination-corrected YSO census, source-level time-domain completeness, a regional formation rate or a discovery.
