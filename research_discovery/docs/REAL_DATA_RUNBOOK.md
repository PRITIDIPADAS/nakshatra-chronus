# CHRONOS real-data runbook

This runbook takes the discovery package from archive metadata to an auditable real-sky benchmark. It is intentionally gated: do not skip a gate if the provenance or calibration compatibility has not been established.

## Gate 0 — prepare the environment

```bash
python -m pip install -r requirements-addons.txt
python -m pip install -r research_discovery/requirements-research.txt
```

Use a network-enabled machine with adequate disk space. A full Level-2 MEF is about 70 MB; downloading many detectors and epochs grows quickly. Keep original files immutable and write derived files elsewhere.

## Gate 1 — discover and download actual science exposures

```bash
python research_discovery/spherex/discover_dr1.py \
  --ra 305.59875 --dec 41.1488889 --radius 0.25 \
  --collections spherex_dr1 spherex_qr3 \
  --maxrec 1000 --download --limit 20 --out data/field_a
```

For deeper coverage, add `spherex_dr1_deep` and `spherex_qr3_deep`. Inspect the returned table's observation IDs, detector number, timestamps, bandpass and `access_url`; do not infer visit cadence from survey-level summaries. Keep each input file's source URL and SHA-256 from `download_manifest.json`.

The tiny IRSA tutorial cutout in `REAL_SAMPLE_OBSERVATION.md` is a parser smoke test only. Use full native MEFs or appropriately sized cutouts for photometry, source recovery and astrometric validation.

## Gate 2 — retrieve and audit the exact calibration families

For every science detector, retrieve candidates separately:

```bash
python research_discovery/spherex/discover_calibrations.py spectral_wcs --release dr1 --detector 4
python research_discovery/spherex/discover_calibrations.py solid_angle --release dr1 --detector 4
python research_discovery/spherex/discover_calibrations.py nonfunctional --release dr1 --detector 4
```

Use the actual science file's detector and version/provenance. Review each candidate calibration file's HISTORY and headers. The script lists URLs; it does not declare them compatible. Check `CWAVE` and `CBAND`, their dimensions and valid-value fraction; verify that the solid-angle map is for the same detector; preserve each calibration checksum. For DR1/QR3 Level-2 MEFs, prefer the exposure's own embedded `EPSF` HDU. Do not substitute the standalone QR3 D2 ePSF URL shown in the tutorial for a DR1 product merely because the detector number matches; that URL is a format example, not a provenance match for the sample DR1 exposure.

```bash
python research_discovery/spherex/audit_mef_calibration.py \
  path/to/level2_D4.fits path/to/spectral_wcs_D4.fits \
  --template path/to/solid_angle_D4.fits --out audit_D4.json
```

Do not proceed if detector identity or coordinate assumptions fail. A same-size array is not proof of matching version or origin.

## Gate 3 — test detector-template mapping

The reprojection adapter maps output sky pixels through the science MEF celestial WCS and back into the native detector grid. It uses the unshifted origin for full 2040×2040 frames and `CRPIX1A` / `CRPIX2A` only for cutouts. Before scientific use:

- inspect the FITS WCS selected by the script;
- verify at least several sky-coordinate-to-pixel transformations against the official IRSA cutout tutorial or an independent catalog;
- compare the resampled template with its native detector image at known landmarks;
- quantify residual shifts and rotation/shear rather than relying on a visual overlay;
- record detector ID, product URL, product hash, WCS key, interpolation method and output hash.

The CLI now fails closed unless `--template-frame detector-native` is explicitly supplied after reviewing the exact calibration product. It also rejects a non-native `DETCOORD` header. This is intentional: the official ePSF example itself records `DETCOORD='sky'` and describes an MWIR X flip to match the SWIR view. Do not treat an ePSF array or other sky-oriented calibration product as a native detector map. The package does not infer a universal flip/rotation for every calibration family; a product-specific transform must be established and tested first.

## Gate 4 — render the position-specific PSF

Choose a real source or target detector position and render its ePSF:

```bash
python research_discovery/spherex/extract_epsf_stamp.py \
  path/to/level2_D4.fits --x 1000.25 --y 1001.75 \
  --out psf_D4_x1000_y1001.fits
```

The output is an 11×11 native-pixel stamp with the source's subpixel phase in its FITS header. It is local to that detector zone. Repeat at other positions for a spatially stratified study; do not reuse a single stamp across the full detector.

## Gate 5 — run a local, real-image injection/recovery experiment

Use a real science MEF, the rendered stamp, and the matching detector solid-angle map. With `--flux-unit Jy`, flux levels are integrated source flux densities; the map is converted from square arcseconds to steradians. Without it, the `image_sum` mode is just the sum of `IMAGE` sample values and is not Jy.

```bash
python research_discovery/validation/injection_recovery.py \
  path/to/level2_D4.fits psf_D4_x1000_y1001.fits \
  --solid-angle-map path/to/solid_angle_D4.fits --flux-unit Jy \
  --background-hdu ZODI --flag-policy conservative-photometry \
  --flux 0.001 0.002 0.004 0.008 0.016 \
  --n 100 --seed 20261114 \
  --out validation_D4_zone_1
```

Set flag bits from the official release flag definition. The default conservative policy masks the official photometry-exclusion flags plus DICHROIC (a documented low-throughput region); use `--flag-policy photometry` for the exact official recommended list or `background` when estimating background masks. The script avoids invalid/flagged PSF footprints and pre-existing source cores, preserves the PSF sub-pixel phase, restricts injections to a 30-pixel radius around the PSF extraction position and reports Wilson intervals plus local astrometric offsets. `ZODI` subtraction is only a first-order zodiacal correction; the official forced-photometry procedure additionally estimates local background in a 15×15 box after source masking. Run separate local experiments across detector zones, backgrounds, fields and epochs. Do not combine results until the grouping and weighting plan is registered.

## Gate 6 — independent held-out performance

Before looking at held-out results, freeze the code, parameter file, fields, calibration choices, thresholds and seed. Partition by sky field and observation period to prevent adjacent cutouts from leaking across splits. Report per-field and aggregate completeness, Wilson intervals, false alarms, centroid errors, flux bias, uncertainty coverage and performance by detector, background, crowding, wavelength and flags. Use a field-level bootstrap for transfer uncertainty. A test set used to adjust parameters is no longer a blind test set.

## Gate 7 — citizen-science pilot

The provided task generator and HTML interface are local prototypes. Before human participation, obtain institutional ethics review, complete `CITIZEN_CONSENT_TEMPLATE.md`, preregister the study using `CITIZEN_PREREGISTRATION_TEMPLATE.md`, implement data retention and withdrawal rules, recruit adult volunteers and collect genuine blinded annotations. Preserve raw labels and analyze disagreement. No human study result exists until this is done.

## Gate 8 — Planet Nine model assessment

Download the CaltechDATA v3 CSV and `README.TXT`:

```bash
python research_discovery/planet9/inspect_reference_population.py \
  --download-to data/planet9_reference \
  --out data/planet9_reference/inspection.json
```

Read and archive the complete README before creating a column map. Confirm the element epoch, coordinate plane, anomaly definition, units and weights. Only then propagate the model-conditional ensemble. Validate numerical orbit propagation on known minor planets against independently exported JPL Horizons data. The model ensemble is not a probability that Planet Nine exists, and known-object validation does not turn it into a confirmed Planet Nine ephemeris.

## Native-MEF retrieval using the official TAP query

For a full 2040×2040 science frame rather than a small cutout, run the new TAP helper. Its SQL mirrors the official IRSA tutorial's `spherex.artifact` / `spherex.plane` join and sky-polygon test, but writes `a.uri` directly instead of appending the cutout-service query string:

```bash
python -m pip install -r research_discovery/requirements-research.txt
python -m research_discovery.spherex.fetch_native_mefs \
  --field M101,210.80227,54.34895 \
  --field M31,10.6847,41.2692 \
  --field LMC,80.8939,-69.7561 \
  --bandpass SPHEREx-D2 --limit-per-field 4 --out data/spherex_native
```

The downloader records TAP query text, time bounds, artifact URI, URL, byte count, HTTP metadata and SHA-256. It checks the FITS `SIMPLE  ` signature and writes downloads atomically. A successful download still does **not** establish matching spectral-WCS or solid-angle calibration provenance. Inspect `native_mef_manifest.json` before proceeding. Increase `--limit-per-field` only after estimating disk requirements; a native MEF is about 70 MB.

For a metadata-only check, add `--discover-only`. To query another detector, use the corresponding official bandpass label (for example `SPHEREx-D1` through `SPHEREx-D6`). The M101 example is grounded in IRSA's published tutorial; other fields must be confirmed by the actual TAP result before they count toward a benchmark.

## Completeness benchmark cautions

The included injection/recovery runner is an experiment engine, not a pre-certified all-sky benchmark. Its results are conditional on each actual field and the supplied PSF/background/mask. For a defensible publication-grade result:

- use ePSFs from the MEF's own `EPSF` extension and repeat injections over multiple zones on each detector;
- test and record background estimation choices, including local-background residuals and crowding; `ZODI` alone is not the full astrophysical background;
- define whether injected sources include an additional photon-noise term; without a validated detector conversion, the current deterministic signal injection leaves the supplied `VARIANCE` unchanged and must be labelled accordingly;
- retain no-injection controls to measure false-positive density, and report flux bias, centroid offsets, uncertainty coverage and completeness with binomial intervals;
- lock all thresholds and model choices before evaluating held-out sky fields and later observing periods.

Do not call the result an independent real-sky validation until the held-out measurements have been computed and published with file hashes and the frozen run configuration.
