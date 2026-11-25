# CHRONOS 5 Sessions 12–20: remaining work status — 26 November 2026

This status note distinguishes implemented software from real-data acceptance and independent external work. It supersedes no earlier run record; see the date-stamped notes linked in the [20-session workflow](CHRONOS_5_20_SESSION_WORKFLOW.md) and [capability ledger](CHRONOS_5_CAPABILITY_LEDGER.md).

| Session | Current implementation status | Scientific / acceptance status | Remaining prerequisite |
|---|---|---|---|
| 12 — source-level \(F(\lambda,t)\) | Covariance-aware reconstruction, provenance-aware source-series assembler, IRSA source-photometry export adapter and sub-pixel native wavelength/WCS verification implemented | No real multi-epoch source-series file has yet been supplied and validated in this run | Download IRSA source measurements and exact native products; complete per-source product mapping and verify multiple independent epochs |
| 13 — feature evolution | Equivalent-width/continuum covariance, resolution/LSF sampling and blend checks implemented | No independently reviewed real feature-evolution measurement | Real verified source spectra, exact LSF and independent feature review |
| 14 — identity graph | Probabilistic cross-match, proper-motion/parallax propagation and no-match probability implemented | No real source counterpart accepted | External catalogue covariance/epoch validation and independent counterpart review |
| 15 — next observation | Information-gain ranking and signed feasibility evidence checks implemented | No production telescope/availability attestation | External service query plus deployment-pinned signer; no telescope action is performed |
| 16 — evidence package | Provenance graph, manifest and checksum-verified package export implemented | No second-person reproduction of original real data recorded | Independent reproducer follows Session 20 protocol |
| 17 — workspaces | Four workspaces and API-backed views exist | Contract/syntax tests are not an independent browser accessibility or usability review | Browser e2e, keyboard/accessibility checks and researcher usability review |
| 18 — blind four-baseline evaluation | Custodian blind-split, freeze/unblind and evaluator infrastructure exists | No custodian-controlled blind run on common held-out real fields is claimed | Independent custodian, frozen configuration, all four method outputs, common operating point, controls, ablations and field-level results |
| 19 — YSO population investigation | Source-photometry import/verification path, multidimensional fixed-bin selection-function model, field-cluster uncertainty, recovery-evidence validation, per-field trial-count binding and preregistration digest binding implemented | **No YSO population result or discovery.** No real selection calibration or source-series sample is available from this run. The rate endpoint remains an exploratory field-level event-rate model, not a source-selection-corrected population estimator. | Real repeated source-level photometry, independent YSO classes, representative injections, retained detector output/truth/peak logs, independent fields, null controls, external preregistration and a source-linked event likelihood |
| 20 — independent reproduction/release | External reproduction protocol and release-gate documentation prepared | **NOT SATISFIED.** No external astronomical researcher report was obtained | An independent astronomer must reproduce original measurements, calibration, selection curve, blind benchmark and any proposed population result; then the release gate can be reconsidered |

## Scientific boundaries

- The 2,421-source, 924,443-pair SIAv2 reconnaissance is a positional metadata association, not extracted source flux or usable cadence.
- All-Sky Cube metadata are not independent temporal visits.
- An IRSA Spectrophotometry Tool row is forced/position-targeted photometry, not a blind detection. It must be attached to the exact LVF product and checked against local native FITS.
- Source-selection completeness and transient/event-detection completeness are different quantities. The current event-rate estimator uses aggregate field completeness and null-control assumptions; it does not yet apply a source-level inverse-probability event likelihood.
- The field-cluster selection interval is conditional on the supplied independent-group labels and fixed bins; it is not a full hierarchical model or a substitute for independent custody.
- SHA-256 fields are evidence references. A hash does not prove the scientific correctness or authenticity of bytes that have not been independently obtained and inspected.

## Relevant operating documents

- [Source-level SPHEREx import](SPHEREX_SOURCE_TIMESERIES_IMPORT_2026-11-26.md)
- [Multidimensional selection-function specification](CHRONOS_5_SELECTION_FUNCTION_SPEC.md)
- [Independent astronomical reproduction protocol](CHRONOS_5_INDEPENDENT_REPRODUCTION_PROTOCOL.md)

**Release decision:** Keep Session 18, Session 19 scientific acceptance and Session 20 open. Do not tag a validated scientific release or claim a YSO discovery.
