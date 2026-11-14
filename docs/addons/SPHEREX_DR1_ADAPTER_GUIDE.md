# SPHEREx DR1 integration and scientific data handling

**Purpose:** add an explicitly labelled DR1 spectral-analysis path without replacing the existing CHRONOS pipeline.

## Official archive references

The pack was prepared against the archive documentation available on **14 November 2026**. The IRSA release guidance says DR1 and QR3 supersede QR2 for new analysis; QR2 is no longer searchable, although direct downloads remain available through the documented transition period. Check the live archive documentation before any future release-specific work.

- [SPHEREx archive data products](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/)
- [SPHEREx data releases](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-releases/)
- [DR1 overview](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_dr1.html)
- DR1 Spectral Images DOI: `10.26131/IRSA678`
- DR1 All-Sky Cube DOI: `10.26131/IRSA679`

## All-Sky Cube

The documented All-Sky Cube is a DR1 product with 12,288 NESTED HEALPix order-5 tiles. Each tile has a 512 × 512 spatial grid and 102 spectral channels.

| HDU | Meaning | CHRONOS handling |
|---|---|---|
| `IMAGE` | MJy/sr; zodiacal light already subtracted | Read and preserve units |
| `NHITS` | Number of contributing input image pixels | Contributor-count diagnostic only; never variance |
| `FLAGS` | Propagated quality bit mask | Preserve raw bits; interpret only from official matching definitions |
| `SPECTRAL_CHANNELS` | Channel centres/edges | Read actual table columns; pass `wavelength_column` if ambiguous |
| `WCS-WAVE` | Spectral lookup mapping | Keep for visualization/context, not the science wavelength solution |

Channels 51 and 52 are documented as blank in the cube and must remain missing. Atmospheric emission, including the He feature near 1.083 μm, and strong extended-source features can produce stripe-like structures. Use the FITS cube for science, not a display PNG.

### Load and extract a spectrum

```python
from chronos_addons.spectral import load_allsky_cube, extract_cube_spectrum

cube = load_allsky_cube("/path/to/Npix4659_cube.fits")
spectrum = extract_cube_spectrum(
    cube,
    x=240,
    y=260,
    radius=1,
    excluded_flag_bits=0,  # set only after checking official flag meanings
    minimum_hits=1,
)
print(spectrum.metadata)
```

The aperture extraction is a simple unweighted spatial mean, not PSF photometry. It deliberately returns no `sigma`: `NHITS` is not a variance estimate. Consequently, a comparison with an All-Sky Cube spectrum can show flux differences, but cannot claim statistical significance until a separately validated uncertainty model is supplied.

The channel-table column names may differ between archive products. Inspect `SPECTRAL_CHANNELS` with `scripts/inspect_spherex_fits.py` and pass the actual central-wavelength column name rather than guessing.

## DR1 / QR3 Level-2 spectral-image MEF

The documented Level-2 MEF provides `IMAGE`, `FLAGS`, `VARIANCE`, `ZODI`, `EPSF` and `WCS-WAVE`. The individual image is calibrated surface brightness; zodiacal light has not necessarily been subtracted from the individual `IMAGE` extension. The effective PSF is spatially varying and should be used where applicable.

For scientific wavelength assignment, use `CWAVE` and `CBAND` from the separate Spectral WCS calibration product. The existing CHRONOS connector uses the `WCS-WAVE` lookup for display-grade wavelength information; do not silently treat its `exposure.lam` as a science-grade wavelength.

```python
from chronos_addons.spectral import load_spectral_image_mef

mef = load_spectral_image_mef(
    "/data/level2_observation_D2.fits",
    "/data/spectral_wcs_D2.fits",
)
print(mef.image.shape, mef.cwave_um.shape, mef.cband_um.shape)
```

This helper raises if the image and calibration maps do not have matching shapes. A full-detector calibration map must not be assumed to align with a cutout. Crop or reproject using the cutout's detector WCS metadata and verify the mapping first.

## Building source-specific F(λ,t)

The original CHRONOS `core.photometry` returns forced PSF/ePSF flux, uncertainty and flagged-core-pixel count for each exposure. `chronos_addons.bridge.measure_candidate_exposures` reuses that photometry but requires a science wavelength solution for every exposure.

1. Load the official Spectral WCS calibration product for the detector.
2. Use alternate WCS A to map the candidate's cutout pixel to detector pixel coordinates.
3. Sample `CWAVE` and `CBAND` at that detector coordinate using `sample_cwave`.
4. Supply an explicit calibration group for each exposure. The group must correspond to genuinely compatible releases/calibration processing.
5. Pass the exposure list and wavelength solutions to `measure_candidate_exposures`.
6. Assemble time-binned channel spectra with the official `SPECTRAL_CHANNELS` centre grid using `assemble_channel_epochs`.

```python
from chronos_addons.archive import load_spectral_wcs
from chronos_addons.bridge import sample_cwave, measure_candidate_exposures, assemble_channel_epochs

# exposures: actual Exposure objects from the existing CHRONOS connector
# detector_xy_by_id: computed from WCS A for each candidate/exposure
# cwave_by_detector: detector -> load_spectral_wcs(...) result
# calibration_group_by_id: a release/calibration compatibility label per exposure
solutions = {}
for exposure in exposures:
    dx, dy = detector_xy_by_id[exposure.id]
    product = cwave_by_detector[exposure.det]
    point = sample_cwave(product["cwave_um"], product["cband_um"], dx, dy)
    solutions[exposure.id] = {
        **point,
        "calibration_group": calibration_group_by_id[exposure.id],
    }

measurements = measure_candidate_exposures(
    exposures,
    solutions,
    source_id="CANDIDATE-ID",
)
source_cube = assemble_channel_epochs(measurements, official_channel_centres_um)
```

The bridge never substitutes the existing `exposure.lam`. Calibration groups are kept separate. Missing spectral channels remain `NaN`; they are not interpolated or extrapolated.

## Instrument and calibration products

The archive documentation lists additional detector and calibration products. They are potential inputs for forensics, not automatically interchangeable image masks.

| Product family | Possible use |
|---|---|
| Aurora emission templates | Candidate overlap with atmospheric emission structure |
| He emission templates | Candidate overlap with He-related emission patterns |
| Shuttle-glow templates | Spacecraft glow pattern diagnostics |
| Nonfunctional-pixel maps | Detector-fixed bad-pixel checks |
| Nonlinearity parameters | Flux-response diagnostics using documented model |
| Read-noise parameters | Noise-model comparison |
| Crosstalk ECSV parameters | Detector geometry/parameter checks; parse as a table, not an image |
| Zodiacal-scaling ECSV parameters | Background-scaling review; parse as a table |
| Dichroic impact maps | Detector/band-specific contamination checks |
| Absolute gain matrix | Gain-calibration review |
| Level-3 flux corrections | Only where the official release guidance explicitly permits cross-release combination |

The `archive.py` helpers load explicitly named HDUs and ECSV tables. They do not infer flag meanings, project a full-frame map into an exposure cutout, or turn ECSV parameter values into a pixel mask. Confirm detector, product version, processing date and coordinate grid before using a product in a candidate diagnostic.

## Required provenance on every result

Record which product was used:

- `SPHEREx DR1 All-Sky Cube` (zodiacal-subtracted; no variance HDU), or
- `SPHEREx DR1 / QR3 Level-2 Spectral Image MEF` (individual exposure; variance present; per-exposure calibration and background semantics),
- detector, observation ID, release and processing version/date,
- Spectral WCS calibration product/version,
- flag-mask choices and excluded pixels,
- PSF/ePSF product and fitting method,
- calibration-group definition.

Do not combine the All-Sky Cube and individual spectral-image products as if they were identical measurements.
