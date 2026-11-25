# CHRONOS real-data research discovery pack

**Research audit date: 25 November 2026.** This folder contains executable SPHEREx archive retrieval, FITS and calibration audits, native-detector reprojection, calibrated Jy injection/recovery, SPLICES catalogue reconnaissance, a citizen-science pilot interface and a Planet Nine orbital-ensemble workflow.

## What is now established from primary sources

1. **SPHEREx DR1 is publicly released.** IRSA announced it on 12 November 2026. Use the DR1 Level-2 spectral images together with QR3 for uniformly processed current spectral-image analysis. The all-sky cube is a different, combined product.
2. **The calibration products are public, but are not retrieved by the SIA2 image query.** IRSA says to use the browsable calibration directories. The files are detector-specific, and the science wavelength solution should use `CWAVE` and `CBAND` in the separate Spectral WCS calibration product.
3. **Detector-template projection can be performed without pretending a detector map has a sky WCS.** The new reprojection routine maps output sky pixels through the science MEF celestial WCS back into a native detector map. It uses IRSA's documented `CRPIX1A` / `CRPIX2A` cutout-origin relation, requires an explicit native-frame declaration and refuses cutouts without required origin metadata or headers declaring a different frame.
4. **The Level-2 flag meanings and masking policies are encoded.** `flag_policy.py` records the published bit positions and separates the official suggested photometry and background-estimation masks. The default CLI uses a conservative photometry mask that also excludes DICHROIC pixels; all original flag values remain in the input.
5. **A single-field real-data pilot has completed.** The M101 SPHEREx DR1 D2 run retrieved a native Level-2 MEF and detector-matched calibration products, verified provenance and FITS structure, and completed 60 deterministic Jy-domain source injections in one local ePSF zone. Recovery was 5/20, 13/20 and 19/20 across three flux levels in that historical run. A new gain-derived source-Poisson mode is implemented with a strict pending-independent-review record and is undergoing a fresh real-data rerun. Neither run is blind or a survey-wide completeness estimate; see `docs/SPHEREX_M101_DR1_D2_REAL_DATA_PILOT_2026-11-25.md`.
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
- `spherex/run_real_field_audit.py`: retrieve one native Level-2 exposure and its calibration candidates, verify exact provenance links, audit MEF structure and run the local Jy injection pilot when prerequisites pass.
- `spherex/run_provenance_calibration_audit.py`: query IRSA `spherex.provenance_input`, retrieve linked calibration artifacts and preserve byte counts, archive checksums and SHA-256 records.
- `spherex/psf_physicality.py`: fail-closed bounded handling of tiny negative ePSF interpolation ringing; the raw stamp is preserved and the corrected unit-sum stamp is separately hashed.
- `spherex/yso_population_recon.py`: predeclared SPLICES label and DR1 Level-2 regional coverage reconnaissance, with literature and ML classifications retained separately.
- `spherex/run_multifield_jy_pilot.py`: sequential six-region real D2 field runner; each field is eligible only if the native MEF audit, exact calibration provenance, bounded calibration-mask policy, completed Jy injection and gain-derived source-Poisson evidence all pass.
- `validation/injection_recovery.py`: inject ePSF-derived sources into real images and measure conditional completeness; optionally converts integrated Jy to MJy/sr using a detector-aligned solid-angle map.
- `citizen_science/build_task_manifest.py`: construct randomized, blinded tasks from actual epoch cutouts.
- `citizen_science/review.html`: offline participant review interface; no server, identity collection or upload.
- `planet9/inspect_reference_population.py`: retrieve/inspect the published CaltechDATA reference population.
- `planet9/ensemble_ephemeris.py`: propagate a documented orbital sample as a sky-position ensemble (not an ephemeris for a discovered object).
- `planet9/published_candidate_diagnostic.py`: reproduce the angular separation and epoch-baseline sensitivity of a published IRAS/AKARI candidate pair; it explicitly does not fit an orbit.
- `planet9/compare_horizons.py`: compare a prediction table against independently exported JPL Horizons positions.
- `.github/workflows/spherex-real-field-audit.yml`: reproducible M101 native-data retrieval and calibration audit.
- `.github/workflows/spherex-yso-population-recon.yml`: predeclared SPLICES and SPHEREx DR1 regional coverage query workflow.
- `.github/workflows/spherex-multifield-jy-pilot.yml`: sequential multi-region D2 calibrated-Jy pilot, with JSON evidence and logs only.
- `docs/SPHEREX_SPLICES_DR1_RECON_2026-11-25.md`: exact live six-region catalogue and Level-2 footprint results, report and artifact hashes, and interpretation limits.
- `docs/SPHEREX_M101_DR1_D2_REAL_DATA_PILOT_2026-11-25.md`: archive identifiers, product hashes, calibration findings, injection metrics and scientific limits.
- `docs/EMPIRICAL_ACCEPTANCE_STATUS_2026-11-25.md`: authoritative gate-by-gate scientific status.
- `docs/`: protocol, evidence, workflow and limitations, including the historical 14 November environment blocker, Planet Nine candidate coordinate diagnostic, and why a solo AI audit is not citizen science.

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

## Real-data execution: M101 SPHEREx DR1 D2 — 25 November 2026

The M101 run retrieved a native 2040 × 2040 DR1 D2 Level-2 MEF and detector-specific calibration products from IRSA. The exact Spectral-WCS and absolute-gain files have `spherex.provenance_input` links to the selected science plane. The solid-angle map passed detector, grid, units and SHA-256 checks but is explicitly treated as a supplemental product, not as a direct provenance child. The native-MEF audit passed structure and compatibility checks.

The local Jy injection/recovery experiment completed 60 deterministic injections at 54.198, 108.396 and 216.792 microJy; recoveries were 5/20, 13/20 and 19/20. The local nominal 5-sigma reference sensitivity was 108.396 microJy. The raw ePSF stamp was retained, a separate bounded-correction stamp was hashed, and no science or calibration image pixels were altered. Full archive identities, hashes, uncertainty intervals and limitations are in `docs/SPHEREX_M101_DR1_D2_REAL_DATA_PILOT_2026-11-25.md`.

## SPLICES / YSO reconnaissance boundary

The live predeclared query completed for Taurus/Auriga, Perseus/NGC 1333, Orion A, Rho Ophiuchi, Lupus III and a high-latitude control. It returned 16,663 catalogue rows and 2,421 candidate-union rows across regional results; 1,490 rows had non-null `YSO_PUB`, and 1,165 rows had `STYPE_ML` containing YSO. `CLASS_1` was counted separately. All queries completed below their caps. These are catalogue-label counts, not confirmed YSOs or unique population counts; see `docs/SPHEREX_SPLICES_DR1_RECON_2026-11-25.md`.

## Honest completion boundary

The 14 November execution-attempt note is a historical record of an earlier environment that lacked dependencies and archive access; it is not the current data-access status. The historical M101 single-exposure pilot is complete, but it is not a blind benchmark, multi-field performance test, four-method comparison or YSO population result. Its reported 60 injections were deterministic and did not add source Poisson variance. A gain-derived, provenance-bound Poisson mode has now passed a fresh M101 real-data run (60 source injections; recovery 5/20, 14/20 and 17/20). Its conversion remains labelled pending independent human review. The six-region D2 Jy workflow has completed: six distinct fields passed post-hoc strict provenance and source-Poisson checks. The field-specific results and Lupus III 0/20 anomaly are documented in `docs/SPHEREX_MULTIFIELD_JY_REVALIDATION_2026-11-25.md`. The gain-to-electron conversion still requires independent instrument/calibration review.

The independent blind benchmark still requires a real external custodian, a genuinely held-out field set, a verifiable external preregistration receipt and the same frozen four-method run on identical inputs. No independent astronomer has yet reproduced or reviewed the result. The SPLICES/DR1 reconnaissance is an input to study design, not a population analysis. The citizen-science workflow is prepared but not conducted; it requires ethics review, recruitment, informed consent and actual participant responses. The Planet Nine workflow produces a hypothesis-conditional sky ensemble, not a validated ephemeris or confirmed object. The validated scientific release gate remains closed.


## Executed SPLICES / DR1 reconnaissance

The first valid live IRSA reconnaissance is documented in `docs/SPHEREX_SPLICES_DR1_RECON_2026-11-25.md`. Workflow run 45619403576 completed all six regional catalogue queries and all six SPHEREx Level-2 exposure-footprint queries. No query error occurred and no query cap was reached. The output is descriptive only: it is not a source census, YSO population rate or discovery.

## Multi-field calibrated Jy evaluation

The sequential six-region D2 DR1 workflow completed on run 45624461435. Six distinct observations and six distinct native science hashes were recovered. Its six raw summaries were revalidated against the current 20-check field gate; all six passed the integrity, direct-provenance, archive-MD5, Poisson-noise and pending-review checks. This is an exploratory multi-field evaluation only. Lupus III had zero recoveries in all three bins and remains a field-level anomaly for investigation. The full results, intervals, hashes and post-hoc revalidation distinction are in `docs/SPHEREX_MULTIFIELD_JY_REVALIDATION_2026-11-25.md`. The absolute-gain conversion is still pending independent human review.


## Latest SPLICES / DR1 query boundary — 25 November 2026

The latest live run [45636514684](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45636514684) completed its catalogue, candidate-label and region-centre footprint queries. Its candidate export has 2,421 rows with unique source IDs; the three label fields overlap as described in `docs/SPHEREX_SPLICES_DR1_RECON_2026-11-25.md`. The optional full-region intersection and candidate-source-to-exposure queries were rejected by IRSA TAP. Candidate source-level exposure matches and cadence therefore remain unmeasured. These catalogue labels do not establish a YSO population or discovery.
