# SPHEREx DR1 / SPLICES regional catalogue reconnaissance — 2026-11-25

**Scope:** predeclared query of the public IRSA `spherex.splices` catalogue and spatial SPHEREx DR1 Level-2 exposure footprints across five star-forming regions and one high-latitude control. This is catalogue reconnaissance, not source reclassification or a YSO population discovery.

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

| Region | Radius | Catalogue rows | YSO_PUB not null | CLASS_1 containing YSO | STYPE_ML containing YSO | Candidate union rows | DR1 footprint rows |
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

The 1,540 Level-2 footprint rows are likewise **not** claimed to be 1,540 unique exposures: spatial overlap between regions has not been deduplicated here. The rows describe archive footprint coverage, not source-level extracted spectra, visits for each candidate, or epoch completeness.

## Labels were not merged into a single truth class

The three YSO-related fields retain distinct meanings:

- `YSO_PUB`: a non-null literature-reference field in SPLICES.
- `CLASS_1`: the catalogue's harmonised class field.
- `STYPE_ML`: the machine-learning source-type label.

The observed sums are 1,490 rows with `YSO_PUB` non-null, 1,490 rows whose `CLASS_1` text contains YSO, and 1,165 rows whose `STYPE_ML` text contains YSO. In the current output, the first two counts coincide region-by-region; this is a property of this returned catalogue and query definition, not a demonstration that the two label-generation processes are independent. The ML label is not independent confirmation of a published label.

The 2,421 candidate-union rows are records matching at least one of the three fields. They are not 2,421 new YSOs, not 2,421 spectroscopically confirmed YSOs, and not independent unique objects after cross-region overlap resolution.

## Query implementation corrections

The first live query iteration used a spatial aggregate form rejected by the IRSA TAP service. That workflow was not accepted as a result. The final query implementation:
- uses an IRSA-compatible spatial predicate for the SPLICES cone query;
- retrieves a bounded row table and computes label counts locally instead of relying on unsupported geometric `COUNT()` / `GROUP BY` aggregation;
- keeps candidate details, full catalogue rows, and exposure-footprint rows separate;
- uses the published SPHEREx exposure-polygon pattern to test whether each exposure footprint intersects the predeclared region;
- records per-query errors and returns a non-zero exit status if any required query fails;
- records whether the query cap was reached; counts are described as exact for a completed query below the cap and as lower bounds if the cap is reached.

The candidate table includes source identifiers, coordinates, published/harmonised/ML labels, probabilities, infrared photometry and variability fields, parallax/distance and neighbourhood fields where available. The CSVs are retained in the workflow artifact; the source IDs and per-field rows are not duplicated into this summary.

## What this does and does not establish

**Established:** the current IRSA TAP service returned the archived catalogue and Level-2 footprint rows for all six predeclared regions under the recorded query definitions; the live query completed without errors; the region-level returned counts are below their declared caps.

**Not established:** an unbiased YSO census, physical classification of every candidate, independent verification of machine-learning classifications, completeness or contamination rates, a regional YSO formation rate, unique exposure counts after spatial overlap removal, source-level temporal coverage, or any new astronomical discovery.

Before a population estimate, the project still needs a frozen source inclusion rule, independent validation of candidate classes, a selection function, source-level epoch coverage, completeness and contamination estimates, null/control modelling, overlap deduplication, and a preregistered statistical analysis. Any later discovery claim needs independent astronomical reproduction and review.
