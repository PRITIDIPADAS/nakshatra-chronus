# SPHEREx source-level time-series import and verification

**Status:** implemented importer and native-product validator; no new real source time series is claimed by this commit.

## Why this path is needed

SIAv2 source-to-product matches are geometric archive-footprint associations. They identify products that overlap a catalogue position; they do not contain extracted source fluxes or independently usable epochs. The SPHEREx All-Sky Cube is a spectral map, not a repeated-exposure light curve.

The official IRSA [SPHEREx Spectrophotometry Tool](https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html) provides source-targeted measurements with fields including wavelength (\`wavelength\`, µm), flux and uncertainty (\`flux\`, \`flux_err\`, µJy), bandwidth (\`lambda_width\`), fit/background diagnostics (\`fit_ql\`, \`flux_bkg\`), flags, LVF exposure ID, detector, deep flag, MJD, data collection, image coordinates and sky coordinates. Its measurements are position-targeted/forced photometry: an imported row is not an independent blind source detection. The flags, fit quality, background, and native exposure identity still need explicit review. ([IRSA tool output documentation](https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html)).

SPHEREx's LVF scan obtains wavelength-dependent measurements over multiple exposure times; a usable time series must retain the actual per-measurement MJD and exact exposure identity, not infer cadence from an archive time span. IRSA currently limits one Spectrophotometry Tool job to 20 target sources; split larger catalogues into explicit batches of 20 or fewer and retain a separate job ID and configuration record for each batch. ([SPHEREx mission overview](https://www.ipac.caltech.edu/project/spherex)).

## Implemented path

1. Download the IRSA Spectrophotometry Tool VOTable/XML or CSV result and retain the original bytes.
2. Limit each IRSA job to 20 targets. For larger catalogues, submit explicit non-overlapping batches of 20 or fewer, and record every job ID separately. Prepare a JSON sidecar that binds each \`(lvf_id, det_id, data_collection)\` tuple to one exact archive product ID, observation ID, detector, release and calibration group. Include the local science MEF, spectral-WCS, ePSF and solid-angle files with archive URIs and SHA-256 digests.
3. Identify the source catalogue and explicit source coordinates/classification references. Ambiguous source-coordinate matches are rejected rather than assigned by nearest-name heuristics.
4. Freeze the quality policy before inspecting source outcomes: named SPHEREx flag mask, maximum \`fit_ql\`, and maximum background fraction \`abs(flux_bkg) / max(abs(flux), flux_err)\`.
5. Declare whether the tool's \`x_image\`/\`y_image\` values are zero- or one-based. No coordinate-origin guess is made.
6. Run the adapter. It converts µJy to Jy exactly once, retains MJD, wavelength, bandwidth, flux, uncertainty, flags, fit/background values, coordinates, LVF ID, detector, release and exact product mapping. Rows failing the frozen quality policy are retained in the import audit and excluded from the analysis manifest.
7. Run the existing assembler. It verifies the local file hashes and archive/product/calibration bindings, checks the supplied sky position against the native IMAGE celestial WCS, samples the native CWAVE and CBAND maps at the declared sub-pixel position, and validates IMAGE/VARIANCE/solid-angle pixels. It assembles per-source measurements into time series only after those checks pass.

The assembler accepts either a version-controlled extractor with a full commit SHA or a hosted-service record. The latter records the IRSA tool URI, declared service version, job ID, retrieval timestamp and configuration digest. It does not pretend that a hosted service has a Git commit.

## Command

From the repository root, after downloading source and native products:

\`\`\`bash
PYTHONPATH=backend python -m research_discovery.spherex.irsa_spectrophotometry \\
  irsa_spectrophotometry_export.vot \\
  --sidecar irsa_source_product_sidecar.json \\
  --out data/source_timeseries/verified_source_timeseries.json \\
  --minimum-epochs 2
\`\`\`

The command fails closed if native files are absent, hashes disagree, the source-product mapping is ambiguous, the declared coordinate origin is missing, the image WCS position is inconsistent, or the row wavelength/bandwidth do not match native CWAVE/CBAND at that position.

## Sidecar contract

The following is a **schema illustration**, not a real archive manifest. Replace every placeholder with an exact retrieved value. Hashes must be calculated from the actual bytes and decision records.

\`\`\`json
{
  "schema": "chronos-irsa-spherex-photometry-import/1.0",
  "service": {
    "tool_uri": "https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html",
    "job_id": "<IRSA job identifier>",
    "version": "<declared service version>",
    "retrieved_utc": "<UTC timestamp>",
    "configuration_sha256": "<64 hex characters>",
    "flux_unit": "uJy"
  },
  "source_catalogue": {
    "uri": "<exact HTTPS catalogue URI>",
    "local_path": "<local source-catalogue file>",
    "sha256": "<catalogue file SHA-256>"
  },
  "sources": [{
    "source_id": "<stable catalogue source ID>",
    "ra_deg": 0.0,
    "dec_deg": 0.0,
    "sample_class": "young_stellar_object",
    "classification_reference": "<external classification reference>",
    "selection_covariates": {
      "flux_jy": 0.0001,
      "wavelength_um": 3.1,
      "crowding_index": 0.2,
      "background_rms": 0.01,
      "epoch_count": 3,
      "detector_zone": "center"
    }
  }],
  "products": [{
    "lvf_id": "<exact LVF ID>",
    "detector": "D2",
    "release": "DR1",
    "archive_product_id": "<exact archive publisher dataset ID>",
    "observation_id": "<exact archive obs_id>",
    "mjd": 60000.0,
    "calibration_group": "<reviewed compatibility group>",
    "science": {
      "uri": "<exact science MEF URI>",
      "local_path": "<downloaded local science MEF>",
      "sha256": "<science SHA-256>"
    },
    "spectral_wcs": {
      "uri": "<exact spectral-WCS URI>",
      "local_path": "<downloaded local CWAVE/CBAND file>",
      "sha256": "<spectral-WCS SHA-256>"
    },
    "epsf": {
      "uri": "<exact ePSF URI>",
      "local_path": "<downloaded local ePSF file>",
      "sha256": "<ePSF SHA-256>"
    },
    "solid_angle": {
      "uri": "<exact solid-angle URI>",
      "local_path": "<downloaded local solid-angle file>",
      "sha256": "<solid-angle SHA-256>"
    },
    "native_mef_audit_sha256": "<native audit report SHA-256>",
    "compatibility_decision": {
      "status": "compatible",
      "sha256": "<compatibility decision SHA-256>",
      "science_sha256": "<same science SHA-256>",
      "spectral_wcs_sha256": "<same spectral-WCS SHA-256>",
      "solid_angle_sha256": "<same solid-angle SHA-256>"
    }
  }],
  "photometry_quality_policy": {
    "policy_id": "<predeclared policy version>",
    "flag_policy": "photometry",
    "fit_ql_max": 1.5,
    "max_abs_background_to_flux_ratio": 0.2
  },
  "image_pixel_origin": 0,
  "source_position_tolerance_arcsec": 0.5,
  "image_wcs_tolerance_pixels": 0.5
}
\`\`\`

The numeric values above are placeholders for schema demonstration, not recommended universal thresholds. The actual quality limits, matching tolerance and pixel convention must be declared before the source outcomes are inspected and justified for the target data.

## Output and interpretation

The adapter emits a normalized \`chronos-spherex-source-photometry/1.0\` manifest plus an audit of accepted and excluded rows. The assembler returns a separate verified source-time-series report with per-source epoch count, wavelength coverage, cadence baseline and provenance.

Important boundaries:

- IRSA tool rows remain forced photometry at supplied positions; this is not a blind source-detection benchmark.
- The adapter does not create missing archive products, source classifications, pixel coordinates or calibration compatibility decisions.
- The assembler verifies submitted measurement positions and native wavelength maps; it does not independently reimplement IRSA's photometry fitter.
- An ePSF product is provenance-bound, but the adapter does not re-fit the original pixel data.
- A verified per-source time series is necessary but not sufficient for a YSO population result.
- Source-selection completeness, event-detection completeness, contamination/null controls, clustering, field covariance and independent source classifications remain separate gates.
- No real catalogue export or source-level product roster was supplied to this implementation run. Therefore no usable real YSO time series or population sample is claimed.

## Related code and tests

- \`research_discovery/spherex/irsa_spectrophotometry.py\`
- \`research_discovery/spherex/source_timeseries.py\`
- \`research_discovery/spherex/flag_policy.py\`
- \`research_discovery/tests/test_irsa_spectrophotometry.py\`
- \`research_discovery/tests/test_source_timeseries.py\`



## Native ePSF source extraction

The repository also provides \`research_discovery.spherex.source_photometry.extract_source_photometry\` for a native single-exposure measurement from a supplied catalogue source position. It extracts the detector ePSF, fits amplitude plus a local planar background using the delivered VARIANCE plane, applies the solid-angle map and reports integrated Jy with a formal variance-weighted uncertainty.

Before accepting the result, it verifies the actual local native-MEF audit JSON bytes and exact science, CWAVE/CBAND and solid-angle file digests. The output is one source in one exposure. Do not call this a light curve; repeat across independent exposures and combine only after source identity, observation/LVF ID, MJD and calibration grouping have been validated. The fit uncertainty is conditional on the delivered variance and PSF/background model; it does not automatically include correlated calibration or PSF-model systematics.
