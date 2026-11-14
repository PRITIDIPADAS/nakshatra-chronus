# CHRONOS real-data research discovery pack

**Research audit date: 14 November 2026.** This folder converts the earlier open research items into documented, reproducible workflows. It includes real archive discovery, FITS auditing, detector-template reprojection, blind injection/recovery, a citizen-science pilot interface and a Planet Nine orbital-ensemble workflow.

## What is now established from primary sources

1. **SPHEREx DR1 is publicly released.** IRSA announced it on 12 November 2026. Use the DR1 Level-2 spectral images together with QR3 for uniformly processed current spectral-image analysis. The all-sky cube is a different, combined product.
2. **The calibration products are public, but are not retrieved by the SIA2 image query.** IRSA says to use the browsable calibration directories. The files are detector-specific, and the science wavelength solution should use `CWAVE` and `CBAND` in the separate Spectral WCS calibration product.
3. **Detector-template projection can be performed without pretending a detector map has a sky WCS.** The new reprojection routine maps output sky pixels through the science MEF celestial WCS back into a native detector map. It uses IRSA's documented `CRPIX1A` / `CRPIX2A` cutout-origin relation, requires an explicit native-frame declaration and refuses cutouts without required origin metadata or headers declaring a different frame.
4. **The Level-2 flag meanings and masking policies are encoded.** `flag_policy.py` records the published bit positions and separates the official suggested photometry and background-estimation masks. The default CLI uses a conservative photometry mask that also excludes DICHROIC pixels; all original flag values remain in the input.
5. **A real-sky performance test is now executable.** It uses actual `IMAGE`, `VARIANCE`, `FLAGS` and an ePSF-derived PSF stamp, injects blind sources and estimates conditional completeness. Flagged or invalid PSF footprints are excluded from detection scoring. The script does not report an all-sky metric from a single field.
6. **A citizen-science pilot workflow is prepared, not conducted.** It keeps the answer key private, offers an offline annotation UI and documents blinding, control cases, ethics and analysis. No volunteers were recruited and no human responses were fabricated.
7. **A single validated Planet X ephemeris cannot exist today.** NASA says Planet Nine has not been discovered. The scientifically supportable output is a probability distribution over candidate sky positions generated from an explicitly sourced orbital reference population, with model and dynamical uncertainties reported.

## Files

- `spherex/discover_dr1.py`: query IRSA SIA2 for `spherex_dr1` and `spherex_qr3`, save query metadata and optionally download Level-2 MEFs with checksums.
- `spherex/fetch_native_mefs.py`: use IRSA TAP (`spherex.artifact` + `spherex.plane`) to retrieve full, native Level-2 MEFs rather than small cutouts; save immutable SHA-256 provenance records.
- `spherex/discover_calibrations.py`: browse the public calibration directory families and list candidate files. It deliberately does not declare a candidate compatible with a given exposure.
- `spherex/audit_mef_calibration.py`: inspect MEF HDUs, shapes, variance domain, detector metadata, and the `CWAVE` / `CBAND` product.
- `spherex/reproject_detector_template.py`: resample native detector calibration templates onto the science MEF sky grid using the image celestial WCS and the documented cutout origin.
- `spherex/extract_epsf_stamp.py`: select the closest detector-zone EPSF row and render a sub-pixel-phase-aware native-pixel stamp with Photutils.
- `spherex/flag_policy.py`: named Level-2 flag bit positions plus official background/photometry masks and a conservative DICHROIC-aware option.
- `validation/injection_recovery.py`: inject ePSF-derived sources into real images and measure conditional completeness; optionally converts integrated Jy to MJy/sr using a detector-aligned solid-angle map.
- `citizen_science/build_task_manifest.py`: construct randomized, blinded tasks from actual epoch cutouts.
- `citizen_science/review.html`: offline participant review interface; no server, identity collection or upload.
- `planet9/inspect_reference_population.py`: retrieve/inspect the published CaltechDATA reference population.
- `planet9/ensemble_ephemeris.py`: propagate a documented orbital sample as a sky-position ensemble (not an ephemeris for a discovered object).
- `planet9/published_candidate_diagnostic.py`: reproduce the angular separation and epoch-baseline sensitivity of a published IRAS/AKARI candidate pair; it explicitly does not fit an orbit.
- `planet9/compare_horizons.py`: compare a prediction table against independently exported JPL Horizons positions.
- `docs/`: protocol, evidence, workflow and limitations, including the actual execution blocker log, Planet Nine candidate coordinate diagnostic, and why a solo AI audit is not citizen science.

## Installation

```bash
python -m pip install -r research_discovery/requirements-research.txt
```

For a full local package, install the base add-on requirements as well:

```bash
python -m pip install -r requirements-addons.txt
python -m pip install -r research_discovery/requirements-research.txt
```

## Minimal workflow

```bash
# 1. Discover actual SPHEREx observations near a field (ICRS degrees).
python research_discovery/spherex/discover_dr1.py \
  --ra 180.0 --dec -30.0 --radius 0.25 \
  --collections spherex_dr1 spherex_qr3 --download --limit 8

# 2. Discover calibration candidates for the detector in one of those MEFs.
python research_discovery/spherex/discover_calibrations.py spectral_wcs --detector 1
python research_discovery/spherex/discover_calibrations.py epsf --detector 1 --release dr1

# 3. Audit the downloaded science / spectral-WCS files.
python research_discovery/spherex/audit_mef_calibration.py \
  path/to/level2_D1.fits path/to/spectral_wcs_D1.fits --out audit.json

# 4. Extract a source-position-specific ePSF as a native-pixel PSF stamp.
python research_discovery/spherex/extract_epsf_stamp.py path/to/level2_D1.fits \
  --x 1000.25 --y 1001.75 --out native_epsf_stamp.fits

# 5. Run recovery in the local PSF zone; choose Jy only with the matching
#    detector solid-angle map (the map is in arcsec^2 by default).
python research_discovery/validation/injection_recovery.py \
  path/to/level2_D1.fits native_epsf_stamp.fits \
  --solid-angle-map path/to/solid_angle_D1.fits --flux-unit Jy \
  --background-hdu ZODI --flag-policy conservative-photometry \
  --flux 0.001 0.002 0.004 0.008 0.016 \
  --n 100 --out validation_run

# 6. Inspect the Planet Nine reference-population schema before assigning columns.
python research_discovery/planet9/inspect_reference_population.py \
  --download-to data/planet9_reference
```

**Do not run the orbital propagation until the CaltechDATA README has been read and the actual column names, units, element epoch, reference plane and anomaly convention have been verified.** Create the explicit JSON column map only after that inspection.

## Updated empirical execution boundary

The latest execution attempt is recorded in `docs/EXECUTION_ATTEMPT_2026-11-14.md`. The runtime contained no FITS files, did not have Astropy/Photutils/Astroquery/PyVO, and could not resolve IRSA or PyPI. A fresh TAP-native downloader was added for use from a network-enabled workstation. It has not been run against IRSA from this container.

The published IRAS/AKARI Planet Nine candidate pair was numerically rechecked from the paper's tabulated positions. The computed 47.458561 arcmin separation matches the published 47.4586 arcmin. The motion and simplified distance scaling are diagnostics only; no orbit has been fitted.

## Honest completion boundary

The research discovery, source review, data-access paths and local reproducibility workflows are prepared. The official IRSA tutorial also provides a concrete public Level-2 file path and demonstrates actual `EPSF` table structure and sub-pixel-aware rendering. However, this execution environment could not resolve the IRSA or CaltechDATA hosts from the container, and no FITS/CSV bytes were downloaded or inspected here. Therefore this pack does **not** contain real NASA measurements, does not report a real-field completeness score, does not claim a citizen-science study has been conducted, and does not claim a validated Planet Nine ephemeris.

The detector reprojection, ePSF extraction and injection/recovery code is implemented but still requires execution on real data and independent empirical checks. The official ePSF product example declares `DETCOORD='sky'` and describes an MWIR X flip; the generic detector-map reprojection does not guess product-specific orientation transforms. A real citizen-science study requires ethics review, participant recruitment, informed consent and actual responses. A Planet Nine model can produce only a hypothesis-conditional sky ensemble, because no object has been discovered and there is no observed orbit to validate. The synthetic browser demo remains clearly synthetic.

All scripts preserve source URLs and checksums where downloaded. They do not invoke Git commands. No repository has been pushed, committed or modified remotely.
