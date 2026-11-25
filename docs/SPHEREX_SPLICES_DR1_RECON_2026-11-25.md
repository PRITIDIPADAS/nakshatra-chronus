# SPHEREx DR1 / QR3 and SPLICES regional reconnaissance — 25 November 2026

**Scientific status:** completed descriptive archive reconnaissance across five predeclared star-forming regions and one high-latitude control. This is not a YSO population estimate, source reclassification, or discovery.

## Reproducible run

- GitHub Actions: [run 45641583599](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45641583599), workflow run #36.
- Code revision: `ab5b82fe11d1d592985fbfda5d4eb643584708f3`.
- Conclusion: success; catalogue, Level-2 region-centre coverage, four SIAv2 spectral-image collections, candidate audit and artifact upload completed.
- Artifact ID `15035548163`, 4,946,716 bytes; ZIP SHA-256 `61ef8c6674d7d9f4c82ad65d3384f41504d2a6882de5bc688cdd2e542ca36a34`.
- Report `data/yso_population_recon/yso_population_recon.json`, 3,235,795 bytes; raw SHA-256 `fdeac3345932a63f7b5e279249e338f57903199c026ced1fd62aa7fc22b26cfc`; embedded canonical SHA-256 `fa48a33ccea8b87a1b408bf3dee2de7c85865fd7f316048560b10abc3deebf47`, independently recomputed and matched.
- Candidate inventory audit, 37,321 bytes; raw SHA-256 `d59415f855bf063f95befa50ba1a214e19b7c5d66e9db004fdbfe95c4206c400`; embedded canonical SHA-256 `25bffb561289de44bd53e88b8336a4e907f50ee3c7e193880c56c08ffd2acedc`, independently recomputed and matched.
- Schema `chronos-spllices-yso-recon/1.1`; 2,421 candidate records; no required query errors.

## Regional archive results

The query returned 16,663 regional catalogue rows and a 2,421-row union defined by at least one of `YSO_PUB`, `CLASS_1` YSO label or `STYPE_ML` YSO label. Region-centre Level-2 queries returned 1,540 rows summed over six regions. Four SIAv2 spectral-image collections returned 6,214 product rows (DR1 and QR3; deep collections returned zero).

| Region | Catalogue | Candidate union | YSO_PUB / CLASS_1 YSO | STYPE_ML YSO | DR1 SIAv2 | QR3 SIAv2 | Level-2 centre-point |
|---|---:|---:|---:|---:|---:|---:|---:|
| Taurus / Auriga | 4,176 | 237 | 58 | 208 | 962 | 481 | 242 |
| Perseus / NGC 1333 | 849 | 189 | 130 | 120 | 471 | 244 | 241 |
| Orion A | 4,990 | 1,337 | 1,083 | 342 | 857 | 472 | 237 |
| Rho Ophiuchi | 2,617 | 482 | 167 | 366 | 626 | 335 | 297 |
| Lupus III | 4,016 | 176 | 52 | 129 | 504 | 234 | 235 |
| High-latitude control | 15 | 0 | 0 | 0 | 1,012 | 16 | 288 |
| **Sum of regional returns** | **16,663** | **2,421** | **1,490** | **1,165** | **4,432** | **1,782** | **1,540** |

Each of the four SIAv2 queries succeeded for each region below the 20,000-row cap. The 6,214 SIAv2 rows are archive spectral-image product metadata, not Level-2 visits or usable source epochs. The audit reports 2,448 distinct archive product IDs across those rows, with no ID appearing in more than one regional query. They must not be interpreted as 2,448 observations or temporal visits.

The 1,540 Level-2 rows use the fixed region-centre point inside an exposure polygon. The audit found 1,540 plane IDs with no plane ID repeated across the six centre-point queries. These are not source-to-exposure matches or cadence measurements.

## Catalogue label overlap

In the 2,421 candidate rows, 1,490 carry non-null `YSO_PUB`, 1,490 have `CLASS_1` containing YSO, and 1,165 have `STYPE_ML` containing YSO. `YSO_PUB` and `CLASS_1` membership was identical across all 2,421 candidate rows. Pattern counts: 1,256 published/harmonised-only, 931 ML-only and 234 all-three-label rows. All candidate rows have a non-empty source ID and there are zero duplicate source-ID groups in this export.

These are catalogue-field overlaps, not independent physical classifications. The 931 ML-only rows are follow-up candidates, not newly confirmed YSOs. Exact equality between two fields in this returned export does not establish independent label provenance.

## Source-level exposure and epoch linkage unavailable

The optional candidate-source-to-Level-2 exposure query failed in all six regions at the IRSA TAP metadata resolver:

`DALQueryError: UsageFault: BAD_REQUEST: get_table_metadata(), unknown datasource / table: spherex_postgres / splices`.

The audit records `match_row_count: null`, an observed lower bound of zero, zero regions with a completed source-level query and six with unavailable queries. The null is intentional. It is not zero measured matches, zero visits or zero cadence.

## DR1 All-Sky Cube inventory

The separate `spherex_dr1_cube` SIAv2 query returned 1,000 metadata rows at `maxrec=1000`, so `query_complete_below_row_cap=false`. The report is metadata-only; no native cube was downloaded and no temporal epoch series was constructed. The nominal product description is 102 spectral channels over 0.75–5.0 µm. The 1,000 returned rows are a capped sample, not a complete inventory.

## Scientific boundary and remaining work

The live catalogue, region-centre Level-2 and six-region DR1/QR3 SIAv2 queries completed without required errors. The labels, source IDs, regional counts, archive metadata and report hashes are preserved in the artifact.

This does not establish an unbiased YSO census, independent ML-label validation, contamination/completeness, source-level visit/cadence coverage, a population rate, complete All-Sky Cube inventory or a discovery. Remaining work includes fixing and validating the source-to-exposure association, paginating the cube metadata query if a complete inventory is required, freezing the sample selection rule, independent class verification, estimating selection/contamination, preregistering population analysis and obtaining independent astronomical review.