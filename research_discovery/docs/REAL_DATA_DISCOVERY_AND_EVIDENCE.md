# CHRONOS: real-data discovery and evidence report

**Evidence cutoff:** 14 November 2026 (UTC). **Status:** research discovery complete; real-file execution blocked in this session by unavailable external data access from the container.

## 1. SPHEREx release status

IRSA's release notice is dated 12 November 2026. DR1 contains reprocessed Survey 1 and Survey 2 spectral images; QR3 contains Survey 3 and Survey 4 spectral images, and IRSA instructs users to treat DR1 and QR3 as the uniformly processed current set. The DR1 All-Sky Cube is a new higher-level product built from the DR1 Spectral Images. The current SIA2 collection names are:

- `spherex_dr1`: DR1 wide-survey Level-2 MEFs
- `spherex_dr1_deep`: DR1 deep-survey Level-2 MEFs
- `spherex_dr1_cube`: DR1 All-Sky Cube FITS files
- `spherex_qr3`: QR3 wide-survey Level-2 MEFs
- `spherex_qr3_deep`: QR3 deep-survey Level-2 MEFs

For broad, fairly uniform sky coverage, use `spherex_dr1` and `spherex_qr3`, adding the deep collections only when the science case benefits from the extra depth/redundancy. QR2 is no longer searchable and is only retained for direct download until February 2027; avoid mixing QR2 with DR1/QR3 unless a specific calibration compatibility decision supports it.

### Why individual MEFs are the primary moving-source data

A DR1/QR3 Level-2 MEF is an individual calibrated 2040×2040 detector exposure. It retains its own time, WCS, variance and flags. The All-Sky Cube is a combined full-sky product. It is useful for static spectral context and finding a field, but it is not a substitute for time-tagged source astrometry. The moving-object search should measure candidate positions separately in individual MEFs and only use the cube as a contextual spectrum/reference layer.

SPHEREx's survey strategy samples the whole sky multiple times during the two-year mission. The mission describes a complete sky sampling twice per year, with a given region typically completed over a few days. The exact timestamps and exposure sequence must be taken from the SIA/MEF metadata, not inferred from that summary cadence.

## 2. Product semantics established from IRSA documentation

### Level-2 spectral-image MEF

| HDU | Published meaning | Use in CHRONOS |
|---|---|---|
| `IMAGE` | Calibrated surface brightness, MJy/sr; zodiacal light not subtracted in this layer | Measurement input |
| `FLAGS` | Per-pixel bit mask | Preserve the raw bits; decode with the matching official flag table |
| `VARIANCE` | Variance in (MJy/sr)² | Pixel-level uncertainty weighting |
| `ZODI` | Empirical modeled zodiacal background; not subtracted from `IMAGE` | First-order background component; not a complete local-background model |
| `EPSF` | DR1/QR3 spatially varying effective PSF | Source-specific PSF photometry |
| `WCS-WAVE` | Visualization-grade wavelength lookup | Not the science wavelength solution |

The individual image is not zodiacal-subtracted. The All-Sky Cube `IMAGE` is zodiacal-subtracted and has a different measurement history. Do not compare their raw flux values as if they were identical image products.

### Science wavelength calibration

The separate spectral-WCS calibration MEF has three extensions: `CWAVE`, `CBAND` and `WCS-WAVE`. `CWAVE` gives central wavelength in microns at each detector pixel; `CBAND` gives bandwidth in microns. IRSA explicitly recommends `CWAVE` / `CBAND` for science analysis. The standalone product is ~32 MB per detector and the arrays are 2040×2040.

### All-Sky Cube

The archive describes 12,288 HEALPix order-5 NESTED tiles. Each FITS tile is 512×512×102; the `IMAGE` has MJy/sr, `NHITS` is the count of contributing input image pixels, and `FLAGS` is a propagated quality mask. Channels 51 and 52 are blank. The FITS cube is for science; the HiPS PNGs are visualization products. **NHITS is not a variance plane.**

### Calibration families and their geometry

The IRSA user guide lists detector calibration families by version/date directory. Examples include `epsf/`, `spectral_wcs/`, `nonfunc_v2/`, `aurora_template/`, `he_template/`, `shuttle_glow_template/`, `dichroic/`, `abs_gain_matrix/`, `dark/`, `nonlinear_pars/`, `readnoise_pars/`, `solid_angle_pixel_map/`, `spectral_channels/`, `sip/`, `xtalk_class1/`, and `zodi_scaling_v2/`.

Calibration files are **not exposed through SIA2**. IRSA directs users to the browsable directories for these products. `discover_calibrations.py` therefore crawls those documented directories; it returns candidate URLs only. It does not claim that a latest-version product is necessarily the appropriate calibration for every older exposure.

## 3. Detector-template alignment: explicit coordinate chain

A detector map is not an all-sky image. Never attach a detector template to celestial coordinates just because both arrays happen to be 2040×2040.

The projection implemented here is:

1. Choose a target pixel `(x_out, y_out)` in the output celestial WCS.
2. Convert it to sky coordinates through `output_wcs.pixel_to_world`.
3. Convert that sky coordinate into the science MEF's celestial pixel coordinates with `science_wcs.world_to_pixel`.
4. If the science MEF is a cutout, convert cutout pixel coordinates to original detector coordinates using IRSA's documented convention:

   `x_detector = 1 + x_cutout - CRPIX1A`

   `y_detector = 1 + y_cutout - CRPIX2A`

   `CRPIX1A` / `CRPIX2A` are FITS 1-based header values; Astropy pixel coordinates are 0-based.
5. Interpolate the detector-template sample at `(x_detector, y_detector)`.

Binary masks use nearest-neighbour sampling. Continuous templates use bilinear interpolation by default. Pixels outside the detector footprint remain NaN. The routine rejects a detector-ID mismatch and refuses a cutout when its origin keywords are missing. It also requires the caller to explicitly assert `--template-frame detector-native` after checking the exact product's coordinate convention, and it rejects headers with a conflicting non-native `DETCOORD`. This is not cosmetic: the official ePSF tutorial shows a `DETCOORD='sky'` product and documents an MWIR X flip to match the SWIR view. The current generic reprojection routine does not guess such product-specific rotations/flips. For a full native detector map, the science image must explicitly indicate 2040×2040 dimensions.

**Important:** this produces a resampled layer, not proof of scientific alignment. Each candidate product must still pass independent checks: detector identity, detector dimensions, product version and processing-date provenance, science pipeline metadata, expected morphology and empirical alignment against actual detector-fixed patterns or stars. The FITS audit reports structural consistency and explicitly leaves product compatibility unresolved until this provenance review is done.

## 4. Reproducible real-sky validation design

A real-world score must be measured on real fields that were not used to set thresholds. The `injection_recovery.py` runner now supports the following experiment:

- Input the actual Level-2 `IMAGE`, `VARIANCE`, `FLAGS`.
- Run `extract_epsf_stamp.py` on the same DR1/QR3 science MEF with a source position in the image. It selects the nearest `EPSF` binary-table zone using `XCENTER` / `YCENTER`, then evaluates the oversampled model at that exact sub-pixel phase and normalizes the native-pixel output. Do not directly use the 33×33 oversampled table cell as a 33×33 detector-pixel stamp, and do not use a hand-drawn Gaussian as the final PSF.
- Apply an explicit published flag policy. `spherex/flag_policy.py` encodes the Level-2 flag bit positions. The official suggested photometry mask is `SUR_ERROR`, `NONFUNC`, `MISSING_DATA`, `HOT`, `COLD`, `NONLINEAR`, and `PERSIST`; the official background-estimation mask additionally includes `OVERFLOW`, `OUTLIER`, `SOURCE`, and `TRANSIENT`. The default `conservative-photometry` policy adds `DICHROIC`, whose description says those pixels are not useful for photometry. The code erodes the usable-pixel mask by the full PSF footprint before scoring detections. Raw flag values are not altered.
- Select injection positions with a pre-registered seed, excluding flagged pixels, image boundaries and detected-source cores. In the CLI, positions are restricted to a local 30-pixel radius around the PSF stamp's reference position and retain its fractional-pixel phase. Use multiple local runs across detector zones for spatial coverage.
- For physically integrated source flux in Jy, supply the detector-aligned solid-angle pixel map and `--flux-unit Jy`. Without this map, the `image_sum` mode uses the sum of image pixel values and is **not** an integrated Jy flux.
- Subtract the aligned `ZODI` model by default, then run a variance-weighted matched filter and local-maximum detector using a fixed threshold. `ZODI` is an empirical zodiacal-light model and is not the full background. The official forced-photometry workflow performs a source-masked local background estimate in a 15×15-pixel box before PSF fitting. For the most faithful comparison, prepare and supply an equivalent source-masked residual background map; do not describe simple ZODI subtraction as identical to that pipeline step.
- Match detections to injection locations within a declared pixel tolerance.
- Report completeness by flux level, field, detector, band and observing epoch. Report confidence intervals (Wilson or bootstrap) in the downstream analysis.
- Compare new unmatched peaks with the no-injection baseline to avoid labelling known astrophysical sources as false positives.

### Independent test set

Partition by sky field and observing period before choosing a threshold. Tune on calibration fields only. Freeze the code and thresholds. Evaluate once on blind held-out fields. Include negative controls (empty sky / artifact-dominated regions), positive controls (known stationary point sources) and blind injections. Report:

- recovery fraction vs injected flux;
- astrometric residual and bias;
- flux bias and uncertainty calibration;
- false alarms per detector area and per image;
- completeness stratified by background, crowding, detector, wavelength channel and flags;
- field-to-field variation and bootstrap confidence intervals;
- cross-match rate against independent catalogs, keeping unmatched candidates distinct from verified moving objects.

Do not call a score "independent" when the field, PSF, detector, flux threshold or detection tuning was reused from training.

## 5. Data-access execution status

The archive metadata, exact calibration directory layout, cutout coordinate convention and ePSF table structure were confirmed against current official IRSA documentation and tutorial material. The official tutorial identifies a public Level-2 MEF and demonstrates a cutout, EPSF zone selection and Photutils `ImagePSF` evaluation. A command to retrieve that sample is in `REAL_SAMPLE_OBSERVATION.md`. The container could not resolve the IRSA or CaltechDATA hosts during this execution, so no SPHEREx FITS or Planet Nine CSV bytes were downloaded or inspected here. The prior browser-demo examples remain synthetic.

The **research discovery and reproducible workflow design** are complete. The **real-data execution and empirical claims** are not: run the code on downloaded FITS files, verify the selected calibration products' provenance, inspect alignment residuals and freeze an independent held-out benchmark before reporting performance. A real citizen-science study and a validated Planet Nine ephemeris cannot be manufactured from code; see `CITIZEN_SCIENCE_STUDY_PROTOCOL.md` and `PLANET_X_EPHEMERIS_ASSESSMENT.md`.

## 6. Official archive directory layout and calibration provenance

The current IRSA guide documents the following directory shape below `/ibe/data/spherex/{dr1|qr3}/`:

- `epsf/cal-epsf-v[Version]-[Processing Date]/[Detector]/`
- `spectral_wcs/cal-wcs-v[Version]-[Processing Date]/[Detector]/`
- `nonfunc_v2/base-[Processing Date]/[Detector]/`
- `aurora_template/base-[Processing Date]/[Detector]/`
- `he_template/base-[Processing Date]/[Detector]/`
- `shuttle_glow_template/base-[Processing Date]/[Detector]/`
- `abs_gain_matrix/cal-agm-v[Version]-[Processing Date]/[Detector]/`
- `dark/cal-drk-v[Version]-[Processing Date]/[Detector]/`
- `dichroic/base-[Processing Date]/[Detector]/`
- `nonlinear_pars/base-[Processing Date]/[Detector]/`
- `readnoise_pars/base-[Processing Date]/[Detector]/`
- `solid_angle_pixel_map/cal-sapm-v[Version]-[Processing Date]/[Detector]/`
- `spectral_channels/cal-sch-v[Version]-[Processing Date]/`
- `sip/cal-sip-v[Version]-[Processing Date]/[Detector]/`
- `gain_factors/base-[Processing Date]/`
- `l3_flux_corrections/cal-flxc-v[Version]-[Processing Date]/[Detector]/`
- `zodi_scaling_v2/cal-zodi-v[Version]-[Processing Date]/[Detector]/`
- `xtalk_class[1|2|3]/base-[Processing Date]/[Detector]/`

The detector subdirectory is the numeric detector identifier (`1` through `6`), not `D1` or `D2`. The updated discovery script follows this structure and supports release, detector, processing-date and version filters. A returned URL is still only a candidate. Do not pair a calibration product with an observation solely because both are under `dr1/`, or because the detector number matches. Review the image's processing version, calibration HISTORY/provenance, the corresponding version/date directories and any relevant release notes.

## 7. Reproducibility references

1. [IRSA SPHEREx Data Access, 12 November 2026](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/): release directories, SIA2 collections and supported data-access layers.
2. [IRSA SPHEREx Data Products, 12 November 2026](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/): MEF HDUs, All-Sky Cube layers, calibration product semantics and filename patterns.
3. [IRSA Understanding and Extracting the ePSF Extension in a SPHEREx Cutout](https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/), updated 17 September 2026: actual public Level-2 cutout, parent-frame conversion, EPSF binary-table columns, local zone selection, oversampling and Photutils rendering.
4. [CaltechDATA Planet Nine reference population v3](https://data.caltech.edu/records/8fjad-x7y61): 100,000 synthetic orbital samples with ZTF, DES and Pan-STARRS constraints; record DOI `10.22002/8fjad-x7y61`.
5. [NASA Science, Hypothetical Planet X](https://science.nasa.gov/solar-system/planet-x/): current scientific status, including that the planet has not been discovered.
6. [Socas-Navarro & Trujillo (2026)](https://doi.org/10.33232/001c.155004): 98-square-degree targeted parallax search and its explicit non-detection limits.
