# CHRONOS real-data research completion ledger

**Cutoff:** 14 November 2026. This ledger separates literature/archive discovery, software readiness and results that require actual measurements or human participants.

| Work package | Completed here | Evidence still required before scientific claim |
|---|---|---|
| SPHEREx DR1/QR3 discovery | Official release, SIA2 collections, TAP table join, 84-row M101/D2 tutorial query, MEF/cube semantics, calibration directory families and exact sample artifact path identified; native-URI TAP downloader added | Execute TAP and preserve the returned observation table, native FITS files and SHA-256 hashes |
| Real SPHEREx file inspection | Reproducible FITS audit and a tiny 6×6 tutorial-cutout retrieval recipe prepared | Download and inspect a Level-2 MEF; the 6×6 tutorial crop is only a structure smoke test, not a benchmark field |
| Calibration matching | Version/date/detector-aware candidate discovery, `CWAVE`/`CBAND` audit, ePSF and solid-angle procedures documented | Inspect each actual FITS header/HISTORY and prove release, pipeline, detector, coordinate-frame and processing-date compatibility |
| Detector-template reprojection | WCS-to-sky-to-parent-detector resampling implemented with fail-closed cutout-origin and detector-ID checks; requires explicit detector-native frame declaration and rejects conflicting `DETCOORD` | Confirm each calibration product's axis/frame convention and compare against real detector landmarks; no empirical residuals measured |
| ePSF extraction | Official IRSA 33×33 / 5× oversampled binary-table workflow implemented with spatial-zone selection and phase-aware rendering | Execute on a real MEF and compare rendered profiles/photometry with IRSA's forced-photometry implementation |
| Flag policy | Official bit indices and background/photometry mask subsets encoded; conservative DICHROIC-aware option provided | Confirm the exact release's flag-header definitions and justify any project-specific additions before freezing benchmark settings |
| Injection/recovery | Variance-weighted runner, background model input, flag-footprint exclusion, source avoidance, Jy conversion and Wilson intervals implemented; synthetic fixture tests pass | Run multiple held-out real fields and report completeness, false alarms, flux bias, astrometry, calibration coverage and field-to-field uncertainty |
| Independent validation | Preregisterable split/metric protocol and executable test harness prepared | Blind, field-level held-out evaluation on real archive exposures, not reused for tuning |
| Citizen science | Adult-only pilot protocol, preregistration and consent drafts plus offline review UI and blind task manifest prepared | Institutional ethics approval, participant recruitment, approved consent process, genuine annotations and expert adjudication |
| Planet Nine/Planet X | Public reference population and 2026 non-detection context identified; published IRAS/AKARI candidate coordinates independently recomputed to 47.458561 arcmin separation; baseline-dependent angular-rate diagnostic saved | Download and inspect the full CaltechDATA CSV/README before any ensemble propagation; obtain follow-up astrometry for the published candidate. No validated ephemeris exists without a confirmed object and observed orbit |

## Execution facts

- Container DNS resolution to IRSA, CaltechDATA and PyPI failed during this session. A browser-open attempt against the actual FITS URL also failed; therefore **no raw FITS or Planet Nine CSV bytes were obtained**.
- The Python environment did not include Astropy, Photutils, Astroquery or PyVO. An explicit pip installation attempt failed because DNS resolution to PyPI failed. The FITS/WCS/ePSF command-line workflows compiled syntactically but could not be run against FITS in this runtime.
- The complete local suite reports **41 passing tests** after adding the native-MEF retrieval helper contract and published Planet Nine coordinate diagnostic. These use synthetic arrays / fixtures or published tabulated positions; they are not real SPHEREx pixel tests and do not constitute real-sky scientific validation.
- The example observations in the browser demo remain synthetic. The separate official IRSA sample observation is documented but was not downloaded or measured.
- No volunteers or responses exist. The solo AI/researcher alternative is documented as exploratory screening only, not citizen science. No Planet Nine predictions have been computed from the CaltechDATA sample file in this session; the separate IRAS/AKARI calculation is a two-coordinate diagnostic, not an orbit.
- No GitHub write, commit, push or remote change was made.

## Acceptance criteria for closure

Do not mark the empirical items complete until the evidence in the final column is archived with source URLs, versions, hashes, commands, parameter files and reviewable result tables. A code path or successful synthetic unit test is not a scientific result.
