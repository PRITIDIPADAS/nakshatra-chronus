# CHRONOS empirical execution report — 14 November 2026

## Executive status

This run completed a source-based archive discovery and a numerical diagnostic using catalogue coordinates published in a 2025 Planet Nine candidate paper. It did **not** complete SPHEREx byte-level analysis, calibration matching, detector reprojection on real calibration arrays, a real-sky completeness benchmark, a human citizen-science study, or a Planet Nine orbit determination.

The limiting factor for the SPHEREx tasks was execution infrastructure: the container's DNS resolver could not resolve IRSA, CaltechDATA, or PyPI. FITS downloads and the package installation therefore could not start. This report deliberately separates the verified public documentation from work that requires the actual files.

## Attempts made in this runtime

| Attempt | Result |
|---|---|
| Inspect `/mnt/data` for `.fits`, `.fit`, `.fts` | 0 files found |
| Import Astropy | Not installed |
| Import Photutils | Not installed |
| Import Astroquery | Not installed |
| Import PyVO | Not installed |
| `pip install astropy photutils astroquery pyvo` | Failed: repeated `Temporary failure in name resolution` reaching `pypi.org/simple/astropy/` |
| Resolve / request `irsa.ipac.caltech.edu` from the container | Failed before HTTP response: temporary name-resolution failure |
| Resolve / request `data.caltech.edu` from the container | Failed before HTTP response: temporary name-resolution failure |
| Open official `.fits` binary URLs through the web reader | Not accessible; binary payload was not delivered |
| Attempt direct binary download | Failed because a valid opened binary resource was unavailable to the downloader |

No partial FITS downloads were retained. No package installation was completed. No scientific measurement was calculated from NASA SPHEREx pixels in this session.

## What was established from primary public sources

1. IRSA announced SPHEREx DR1 on 12 November 2026 and documents directory, SIA2, AWS and Python access routes. The Level-2 product directory is versioned by planning period, pipeline version/processing date and numeric detector folder.
2. The Level-2 MEF is approximately 70 MB for a native full frame. Its science extensions include `IMAGE`, `FLAGS`, `VARIANCE`, `ZODI`, `EPSF` and `WCS-WAVE`; the full image is 2040×2040 MJy/sr and has not had zodiacal light subtracted.
3. `WCS-WAVE` is described as suitable for visualization; IRSA directs scientific wavelength analysis to the standalone Spectral WCS product's `CWAVE` and `CBAND` extensions.
4. IRSA's public tutorial demonstrates a TAP query joining `spherex.artifact` and `spherex.plane`, using a spherical `CONTAINS(POINT(...), p.poly)` predicate. Its M101 / SPHEREx-D2 example returned 84 image records. The tutorial prints four failed cutout URLs in its serial download example; this is not evidence that this runtime downloaded any of them.
5. The public tutorial shows the detector-specific QR3 D2 ePSF file path. For DR1/QR3, the Level-2 MEF itself has an `EPSF` extension, which is preferred for that exposure over an unrelated external calibration file.

## New local tooling added

- `spherex/fetch_native_mefs.py`: executes the documented IRSA TAP query and retrieves the underlying native MEF URI (`a.uri`), not only the cutout URL. It saves the query table, per-file provenance, HTTP metadata, byte count, FITS signature and SHA-256. Default limit is four MEFs per requested field to prevent accidental multi-gigabyte downloads.
- `planet9/published_candidate_diagnostic.py`: reproducibly calculates the angular separation, position angle, east/north displacement and epoch-baseline sensitivity for the published IRAS/AKARI candidate pair.
- `data/planet9_published_candidate_motion.json`: output of that diagnostic.
- `data/official_real_data_inventory.json`: archive locator and environment-status record.

## Planet Nine candidate diagnostic result

Using the two positions printed in the 2025 IRAS–AKARI paper:

- IRAS F02211-4844: RA 35.74075°, Dec −48.5125°.
- AKARI-MUSL J0220440-491247: RA 35.18379°, Dec −49.2135°.
- Recalculated great-circle separation: 47.458561 arcmin, matching the paper's 47.4586 arcmin to rounding.
- Position angle from celestial north, eastward: 207.386°.
- Using the midpoint of the published IRAS scan interval as an illustrative epoch and 26 December 2006 for AKARI gives a mean angular rate of about 121.630 arcsec/year. Varying the IRAS epoch from 26 June to 1 September 1983 gives about 121.162–122.115 arcsec/year.
- Inverting the paper's simplified 42-arcmin / 23-year / 700-AU scaling gives about 651.2–654.6 AU. **This is not a measured distance**: it simply re-expresses the assumed motion law and must not be treated as parallax or an orbit fit.

The paper explicitly says the two survey detections are insufficient to determine a full Keplerian orbit and recommends follow-up observations. It discusses nine detections as a requirement for a reliable linked-orbit evaluation. This is an analysis of a published candidate pair, not a discovery by CHRONOS.

## Why the requested end state is not claimable yet

### SPHEREx calibration and detector-template validation

No science MEF or calibration bytes were available to read. Consequently, no `CWAVE`/`CBAND` values, product HISTORY, checksums, detector WCS transforms, residual shifts, rotation/shear, matched landmarks or calibration provenance were measured. A template header's detector label or array shape is not sufficient to establish compatibility.

### Completeness benchmark

No injection/recovery run against a real SPHEREx field occurred. The current runner's output is conditional on the actual field, background model, PSF zone, masks, flux grid and detection threshold. A credible benchmark must also model injected-source noise appropriately, stratify detector zones and sky backgrounds, quantify false alarms in no-injection controls, and use held-out fields that were not used for threshold tuning. A synthetic-fixture unit test cannot substitute for any of those measurements.

### Citizen science

A single AI or researcher cannot conduct a citizen-science study alone. It can perform an exploratory machine-assisted or single-annotator audit after real images are available, but that cannot estimate inter-person disagreement, volunteer learning effects or human review reproducibility. No participant responses have been created or simulated as if real.

### Planet Nine ephemeris

There is no confirmed Planet Nine with an observed orbit. A propagated synthetic reference population can provide a model-conditional search-region distribution, but not a validated ephemeris for a discovered body. The published IRAS/AKARI pair remains a candidate requiring follow-up; it cannot be upgraded into a discovery by extrapolating two catalogue coordinates.

## Next execution on a network-enabled workstation

Install the dependencies, then retrieve actual native MEFs:

```bash
python -m pip install -r research_discovery/requirements-research.txt
python -m research_discovery.spherex.fetch_native_mefs \
  --field M101,210.80227,54.34895 \
  --field M31,10.6847,41.2692 \
  --field LMC,80.8939,-69.7561 \
  --bandpass SPHEREx-D2 --limit-per-field 4 --out data/spherex_native
```

Repeat the query across detectors and pre-registered fields. Discover the corresponding `spectral_wcs` and `solid_angle` products, download the exact candidate products, inspect their headers/HISTORY and verify their pipeline provenance before running `audit_mef_calibration.py`. The detector transform must then be tested against real WCS/landmarks, and the injection/recovery benchmark must be frozen and run on held-out fields.

The citizen review interface should be opened only after real paired epoch cutouts exist and study ethics/consent are handled. For a solo first pass, report it as a machine-assisted screening analysis, not citizen science.

No GitHub write, commit or push was performed; no remote repository was changed.
