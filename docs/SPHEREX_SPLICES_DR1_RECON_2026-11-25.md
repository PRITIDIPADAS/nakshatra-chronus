# SPHEREx DR1 / QR3 and SPLICES regional reconnaissance — 25 November 2026

**Scientific status:** completed descriptive archive reconnaissance across five predeclared star-forming regions and one high-latitude control. Source-to-product association is now measured from returned SIAv2 footprint metadata. This is not source photometry, a validated time series, a YSO population estimate, or a discovery.

## Reproducible live run

- GitHub Actions: [run 45648715196](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648715196), workflow run **#38**.
- Code revision: cb66210536713df52e5530a05185d6fe1353c6e3.
- Conclusion: success; catalogue, Level-2 region-centre coverage, four SIAv2 collection searches, local source-footprint matching, cube metadata inventory, candidate audit and artifact upload completed.
- Artifact ID 15038898474, 6,123,743 bytes; ZIP SHA-256 6be5058a25ec68f94492bc61ebd895a818d67276da01ba31a0b194d01f5df81f.
- Reconnaissance JSON: 708,876 bytes; raw SHA-256 d3d00040375ea04b1da5546e74020460492b136d281a6ac03a25e44c24d07a22; embedded canonical SHA-256 b8bbbfec64a24d4eaf514282e496ee6948dd2acf73ceb414aa98dd7bcaa1d646, independently recomputed and matched.
- Candidate audit JSON: 37,762 bytes; raw SHA-256 a18c65bcae35ff57c8c86bb5bd4e646ee49feaaa1a8e1cbe6d4f138110258d51; embedded canonical SHA-256 4ca24f0558e74173b20771fa26242fe8148db8c562ea5f83b95fd1ad23662850, independently recomputed and matched.
- Schema chronos-spllices-yso-recon/1.1; 2,421 candidate records; required catalogue and region-centre queries succeeded.

Run #38 executed on revision cb66210536713df52e5530a05185d6fe1353c6e3, which includes the local SIAv2 source-footprint matcher and the regression tests for its spherical geometry. The updated tests passed separately (run #897: 316 passed, 7 warnings) and with the M101 real-field job (run #896: 316 passed, 12 warnings).

## Regional catalogue and archive results

The catalogue query returned 16,663 regional SPLICES rows. The candidate union contains 2,421 rows satisfying at least one of YSO_PUB, CLASS_1 containing YSO, or STYPE_ML containing YSO. Region-centre Level-2 queries returned 1,540 rows summed across six region centres. Four DR1/QR3 SIAv2 spectral-image collections returned 6,214 product metadata rows.

| Region | Catalogue | Candidates | DR1 SIAv2 | QR3 SIAv2 | Centre-point Level-2 | Sources with footprint matches | Source–product pairs | Median metadata time span (days) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Taurus / Auriga | 4,176 | 237 | 962 | 481 | 242 | 237 / 237 | 84,669 | 379.463 |
| Perseus / NGC 1333 | 849 | 189 | 471 | 244 | 241 | 189 / 189 | 68,086 | 389.055 |
| Orion A | 4,990 | 1,337 | 857 | 472 | 237 | 1,337 / 1,337 | 519,120 | 393.851 |
| Rho Ophiuchi | 2,617 | 482 | 626 | 335 | 297 | 482 / 482 | 186,980 | 400.534 |
| Lupus III | 4,016 | 176 | 504 | 234 | 235 | 176 / 176 | 65,588 | 404.269 |
| High-latitude control | 15 | 0 | 1,012 | 16 | 288 | 0 candidates | 0 | — |
| **Regional sums** | **16,663** | **2,421** | **4,432** | **1,782** | **1,540** | **2,421 / 2,421** | **924,443** | — |

All four SIAv2 collections completed below maxrec=20,000 in every region. All 6,214 returned spectral-image rows report calib_level=2, dataproduct_type=image, dataproduct_subtype=science and algorithm_name=exposure. There are 6,214 distinct obs_publisher_did values and 2,448 distinct obs_id values. Product rows are not one-to-one with observation IDs.

The 1,540 Level-2 rows are a separate centre-point query: they test whether the fixed region centre is inside an exposure polygon. They are not source-to-product associations or a globally deduplicated visit count.

## Source-to-product footprint association

The former direct TAP join from SPLICES to spherex.artifact was removed after IRSA rejected its table metadata resolution. The replacement does not retry or disguise the failed join. It uses the four successful SIAv2 collection outputs, parses each returned ICRS s_region polygon and tests candidate coordinates locally with the spherical-gnomonic-pip/1.0 point-in-polygon algorithm. Candidate membership in each predeclared cone is checked separately.

- Candidate summaries: 2,421, one row per candidate.
- Candidate sources with at least one returned product-footprint match: 2,421 / 2,421 in the five star-forming regions.
- Geometric candidate–product pairs: 924,443.
- Invalid or unsupported product polygons: 0.
- Candidate rows with invalid coordinates: 0.
- All four SIAv2 collections: complete below row cap in all six regions.

This is a geometry result: a catalogue coordinate lies inside a returned SPHEREx Level-2 product polygon. Median metadata time spans are derived from SIAv2 t_min/t_max fields. They are metadata summaries only. No detector pixels were opened for these sources; no calibrated source flux, spectral quality, usable visit cadence, validated epoch series, light curve or physical YSO class was measured. This completes archive-footprint metadata linkage, not source-level temporal-coverage validation.

## Catalogue labels and source-ID audit

Across the 2,421-row union:
- 1,490 rows have non-null YSO_PUB.
- 1,490 rows have CLASS_1 containing YSO.
- 1,165 rows have STYPE_ML containing YSO.
- YSO_PUB and CLASS_1 flags have identical membership in this export.
- Patterns: 1,256 published/harmonised-only; 931 ML-only; 234 all-three-label rows.
- All 2,421 candidate rows have non-empty source IDs; zero repeated source-ID groups.

These are catalogue-field overlaps, not independent physical classifications. The 931 ML-only rows are candidates for independent review, not newly confirmed YSOs. Exact membership equality between two catalogue fields does not establish independent provenance or astrophysical truth.

## DR1 All-Sky Cube metadata inventory

The spherex_dr1_cube query was run as six POS-circle searches, one per predeclared region. It returned 32 metadata rows: Taurus/Auriga 8, Perseus 4, Orion A 6, Rho Ophiuchi 4, Lupus III 4 and high-latitude control 6. The rows have 32 distinct obs_publisher_did values and 32 distinct access URLs. Every regional query completed below the 20,000-row cap with no query errors.

This is a complete metadata result for the six searched cones, not a complete all-sky inventory. The product is nominally a 102-channel spatial-spectral cube over 0.75–5.0 µm. Native cube data were not downloaded and these rows are not temporal exposures.

## Scientific boundary

**Established:** the six-region catalogue, centre-point Level-2 and four-collection SIAv2 searches completed; all 2,421 candidates in the star-forming regions were geometrically associated with at least one returned Level-2 product polygon; per-region and aggregate pairs, source IDs, label overlaps and the 32 field-cone cube records are checksummed.

**Not established:** extracted/calibrated flux, validated temporal epochs or light curves, usable source cadence, an unbiased YSO census, independent ML-label validation, completeness/contamination, a population rate, a complete all-sky cube inventory, or a discovery.

Remaining scientific work includes source-level image extraction and quality evaluation, a frozen YSO selection function, independent class review, selection/completeness/contamination modelling, null/control analysis, preregistered population inference, an independent four-method blind benchmark on custodian-held real SPHEREx fields, and external astronomical reproduction/review.

## 26 November 2026 — strict source/product manifest integrity rerun

The latest completed refreshed archive audit is [workflow 45677731011](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45677731011), artifact 15052808730 (70,934,685 bytes; ZIP SHA-256 `9fb16d20ff2a621a4882a61275efc3591921f942f3521404bbd9e5fd0a3af08b`). The six regional manifest checks are all `available=true`, `valid=true`, status `passed`, with empty error arrays.

| Region | Candidate source IDs | Unique source/product pairs | SIAv2 products in regional inventory |
|---|---:|---:|---:|
| Taurus / Auriga | 237 | 84,669 | 1,443 |
| Perseus / NGC 1333 | 189 | 68,086 | 715 |
| Orion A | 1,337 | 519,120 | 1,329 |
| Rho Ophiuchi | 482 | 186,980 | 961 |
| Lupus III | 176 | 65,588 | 738 |
| High-latitude comparison | 0 | 0 | 1,028 |
| **Total** | **2,421** | **924,443** | **6,214** |

Across all regions, the audit found zero duplicate source/product pairs, zero source IDs outside each region’s candidate set, zero pair product IDs absent from the regional SIAv2 inventory, zero missing required archive metadata, zero product metadata mismatches, zero per-source matched-product count discrepancies and zero per-source sorted product-ID digest discrepancies. The control field’s zero pairs is expected because the query-selected candidate table returned no control-field candidates.

**Scientific limit:** a valid point-in-product-polygon manifest does not demonstrate that a source is detected in the image, that its spectral/photometric data are valid, or that multiple products are independent temporal epochs. No calibrated source fluxes, source light curves or YSO population estimate are produced here.
