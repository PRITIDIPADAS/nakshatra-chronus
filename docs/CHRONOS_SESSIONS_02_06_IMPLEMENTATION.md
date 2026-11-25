# CHRONOS Sessions 02–06: archive, calibration, coordinates and injection

This implementation adds the software contracts for Sessions 02–06. It does **not** claim that a real SPHEREx exposure was retrieved or independently audited in this development environment. A real-data acceptance gate remains open until an actual Level-2 MEF and its exact calibration files are retrieved and their checksums are recorded.

## Session 02: versioned archive manifest

Files:
- research_discovery/spherex/archive_manifest.schema.json
- research_discovery/spherex/archive_manifest.py
- research_discovery/spherex/discover_dr1.py
- research_discovery/spherex/fetch_native_mefs.py
- research_discovery/spherex/fetch_calibration.py

Standard science retrieval uses the uniformly processed DR1 and QR3 collections, including both wide and deep SIA2 collections: spherex_dr1, spherex_dr1_deep, spherex_qr3 and spherex_qr3_deep. IRSA states that DR1 and QR3 together supersede QR2 and are the uniformly processed set. Calibration files are not exposed through SIA2; retrieve them from the browsable archive directories. [IRSA data access](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/) · [IRSA release guidance](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-releases/). SIA2 records retain the archive publisher identifier when present; otherwise the exact original native URI is the product identity. TAP retrieval preserves the artifact URI and does not invent a publisher ID.

Example SIA2 query and retrieval:

    python research_discovery/spherex/discover_dr1.py       --ra <RA_DEG> --dec <DEC_DEG> --radius 0.05       --collections spherex_dr1 spherex_dr1_deep spherex_qr3 spherex_qr3_deep       --download --limit 2 --out data/spherex_dr1

Example native-MEF query (release is explicit):

    python -m research_discovery.spherex.fetch_native_mefs       --field M101,210.80227,54.34895       --release dr1 --bandpass SPHEREx-D2       --limit-per-field 2 --out data/spherex_native

Both retrieval paths write a canonical archive_manifest.json and separate validation output. The validator reports duplicate URIs or publisher IDs, missing fields, malformed SHA-256 values, missing downloaded bytes, byte-count changes and checksum changes. Re-run validation after moving files:

    python -m research_discovery.spherex.archive_manifest       data/spherex_dr1/archive_manifest.json       --out data/spherex_dr1/archive_manifest.rechecked.json --verify-local

The empty manifest at data/spherex_archive_manifest.empty.json is a schema template only. It contains no exposure IDs, URIs, hashes or calibration matches.

## Session 03: native-MEF audit

native_mef_audit.py inspects the original MEF without editing it. It reports named HDUs, extension shapes, BUNIT values, detector/observation/pipeline metadata, WCS headers, alternate WCS A and cutout origin, raw MP_ flag definitions, variance validity, and SHA-256 for each input. It requires a native 2040×2040 IMAGE array for the native-MEF gate.

    python -m research_discovery.spherex.native_mef_audit       <native_level2_mef.fits> <detector_spectral_wcs_calibration.fits>       --solid-angle <detector_solid_angle_map.fits>       --science-uri <exact_science_archive_uri>       --spectral-wcs-uri <exact_calibration_archive_uri>       --out data/audits/field_mef_audit.json       --summary data/audits/field_mef_audit.md

The audit fails for missing required extensions, misaligned arrays, non-native image shape, invalid WCS or missing CWAVE/CBAND. Missing provenance or a missing solid-angle product stays review_required. The script preserves its inputs and writes a machine-readable report plus a concise Markdown summary.

## Session 04: calibration compatibility and wavelength authority

fetch_calibration.py downloads only an explicitly supplied HTTPS IRSA URI. A downloaded calibration is labelled candidate_only; it is not automatically paired with a science exposure.

    python -m research_discovery.spherex.fetch_calibration       <exact_IRSA_calibration_uri> --release dr1       --product spectral_wcs --detector 2       --out data/calibration/D2_spectral_wcs.fits       --manifest data/calibration/D2_spectral_wcs.download.json

The compatibility decision requires explicit release, detector, pipeline version, processing date and coordinate frame. It also checks CWAVE and CBAND maps plus a separate detector-matched solid-angle product with native shape, arcsec-squared units, URI and SHA-256. A missing item leaves the pair unresolved. The compatibility input is JSON with science_exposures and calibration_candidates arrays. Each row has id, uri and metadata. A spectral-WCS candidate metadata object contains release, detector, pipeline_version, processing_date, coordinate_frame, and either full cwave/cband arrays or a local audit report reference. It also contains a solid_angle_map object copied from the actual solid-angle audit: status, detector, shape, bunit, uri and sha256. Example pipeline:

    python -m research_discovery.spherex.merge_archive_manifests data/spherex_native/archive_manifest.json data/calibration/D2_spectral_wcs.archive_manifest.json data/calibration/D2_solid_angle.archive_manifest.json --out data/calibration/merged_manifest.json

    python -m research_discovery.spherex.calibration_matrix data/calibration/compatibility_inputs.json --out data/calibration/compatibility_matrix.json

    python -m research_discovery.spherex.apply_compatibility_matrix data/calibration/merged_manifest.json data/calibration/compatibility_matrix.json --out data/calibration/compatible_manifest.json

Scientific wavelength values are obtained from the detector-matched CWAVE and CBAND calibration maps, in microns. The in-file WCS-WAVE table is reported for inspection but is never substituted for these science maps. The MEF auditor slices the native calibration grid to the science image using the documented cutout origin. Invalid calibration pixels remain masked; there is no silent interpolation or extrapolation.

## Session 05: sky and detector coordinates

coordinate_transform.py is the shared conversion path. It handles native-frame identity, cutout-origin offsets from CRPIX1A/CRPIX2A, detector mismatch rejection, sky-to-detector and detector-to-sky transformations, and optional positional-covariance propagation in the local east/north tangent plane.

Detector landmark audits use a JSON file containing the independent catalogue source URI and rows with landmark_id, ra_deg, dec_deg, detector_x, detector_y, and optional position_sigma_arcsec:

    python -m research_discovery.spherex.coordinate_landmark_audit       <science_mef.fits> <independent_landmarks.json>       --out data/audits/detector_coordinate_residuals.json

The landmark file itself is hashed. At least three rows and a traceable HTTPS source are required for the report to say validated_against_external_landmarks. The residual report still does not establish detector persistence; it only tests the supplied coordinate mapping against those external landmarks.

## Session 06: source photon noise

The research_discovery/validation/injection_recovery.py path normalizes the supplied PSF, preserves its supplied subpixel phase, requires the full patch to remain inside the image, refuses excluded flagged pixels, draws Poisson counts in electron units, converts the realization back to IMAGE units, and increments VARIANCE by the corresponding source shot-noise term. It uses the detector-specific 2040×2040 abs_gain_matrix, sliced to the exact science footprint without interpolation. For each pixel, C = exposure_time_s / G_abs, where G_abs is in (MJy/sr)/(e-/s); expected source electrons are S × C, the realized source signal is Poisson(S × C) / C, and the added variance is S / C. The deterministic path remains available when no verified conversion exists.

A numeric gain by itself is rejected. The signed-off electron-calibration-record must identify the exact science-file SHA-256, OBSID, detector, IMAGE unit, exact calibration URI and local calibration-file path/hash, plus the derivation method and sign-off metadata. The CLI checks the science identity and re-hashes the local calibration bytes before allowing source Poisson noise.

The machine-readable contract is research_discovery/spherex/electron_calibration_record.schema.json. Required record fields:

    {
      "verification_status": "verified",
      "calibration_product": "abs_gain_matrix",
      "calibration_bunit": "<exact BUNIT read from the absolute-gain FITS header>",
      "exposure_time_s": 0.0,
      "science_file_sha256": "<native science MEF SHA-256>",
      "science_native_file_sha256": "<same native science MEF SHA-256>",
      "science_cutout_sha256": "<exact cutout byte SHA-256; required by GUI injection>",
      "science_observation_id": "<original archive OBSID, without detector suffix>",
      "science_source_uri": "<exact native HTTPS archive URI>",
      "detector": "D2",
      "image_unit": "MJy/sr",
      "calibration_uri": "<exact HTTPS absolute-gain calibration URI>",
      "calibration_file_path": "data/calibration/D2_abs_gain_matrix.fits",
      "calibration_sha256": "<64 lowercase hex characters>",
      "conversion_method": "e-/image-unit = exposure_time_s / abs_gain_matrix; see official supplement",
      "verified_by": "<reviewer>",
      "verified_utc": "<ISO-8601 UTC timestamp>"
    }

The example values above are placeholders, not SPHEREx instrument constants. A real conversion must be derived from the correct exposure and calibration product. Do not fill the record with guessed values. Set exposure_time_s from the exact exposure record, not by assumption. science_file_sha256 identifies the native MEF; the GUI cutout workflow additionally requires science_cutout_sha256 for the exact cutout bytes. Do not store a scalar gain in this record: the runtime derives the pixel-dependent conversion map directly from abs_gain_matrix and exposure_time_s. The science_file_sha256 identifies the exact bytes injected: the native MEF for the research-discovery CLI, or the exact cutout bytes retained by the browser-backed connector. Both records retain the original native archive URI. The CLI requires --science-uri <exact native HTTPS archive URI> alongside --electron-calibration-record <record.json> and --exposure-time-s <exact SIA2 exposure time in seconds>.

The legacy backend/inject.py path now carries the loaded cutout's original archive URI, original OBSID, exact cutout-byte SHA-256, detector and IMAGE unit. A record must match the exposure identity, detector, unit, cutout hash and native source URI; its local calibration bytes are re-hashed. A scalar gain is rejected. The GUI path derives its own cutout-shaped conversion map from abs_gain_matrix, the exact exposure time and the validated cutout origin. Exposures with no such record stay deterministic, with a note attached to the exposure.

## Current evidence status

| Gate | Software | Real-data evidence |
|---|---|---|
| S02 manifest and retrieval | Implemented | Not populated in this development run; no original MEF downloads or complete archive records available |
| S03 native-MEF audit | Implemented | Blocked until an actual native MEF and matching calibration are retrieved |
| S04 calibration compatibility | Implemented | No exposure/calibration pair has been marked compatible |
| S05 coordinate transform | Implemented | Unit-tested coordinate math; no independent real detector-landmark residual report |
| S06 photon-noise injection | Implemented with strict provenance gate | Deterministic mode is the only defensible mode until an exposure-specific calibration record and calibration bytes are supplied |

A synthetic FITS fixture or unit test can test the code path, but it does not pass the real-file acceptance gate. Do not publish a real-data validation claim from this software-only tranche.


## Official archive references checked for this implementation

- [SPHEREx Data Access, IRSA](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/): confirms SIA2 access to DR1 and QR3 science MEFs, the four wide/deep collections, and that calibration files must be retrieved from browsable directories rather than SIA2.
- [SPHEREx Data Releases, IRSA](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-releases/): confirms DR1 plus QR3 are the uniformly processed set and supersede QR2.
- [SPHEREx Explanatory Supplement v2.1](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf): documents the absolute gain matrix format, detector dimensions and physical units.

The archive manifest stores the exact query and original product URI. The calibration retrieval command deliberately accepts only an explicitly selected URI, because SIA2 does not return calibration products. Do not treat a nearby filename or detector number as a match.
