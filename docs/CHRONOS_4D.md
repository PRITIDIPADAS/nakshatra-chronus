# CHRONOS 4D: space × time × wavelength × evidence

Page: `lab.html` (static site) or `/lab.html` with `python run.py`. API: `GET /api/lab?key=demo`. Code: `backend/lab.py`. Build: `python scripts/build_lab.py`. Tests: `tests/test_lab.py`.

CHRONOS does not merely search for changes. It investigates whether they are real, explains how they could have occurred, and names the evidence that would prove it wrong.

| Laboratory | What it computes | Honest limit |
|---|---|---|
| 01 Sky and releases | Release registry: DR1 (`spherex_dr1`, `spherex_dr1_deep`, cube `spherex_dr1_cube`), QR3, QR2 (superseded, not searchable, download until Feb 2027). Refuses to mix QR2 with QR3/DR1 without the L3 flux corrections. Live default is now `spherex_dr1+spherex_qr3`. | The registry follows the IRSA documentation of November 2026. |
| 02 Spectral universe | F(λ, t) and σ(λ, t) on the 102 DR1 channels; channels 51 and 52 are marked "no data in DR1 cube", never filled. Heatmap, time slider, difference view (z), uncertainty surface, feature explorer (He I 1.083 contamination, Paβ, Brγ, CO, H₂O, CH₄, ices), detector comparison, spectral stability score, spectral residual court (can the wavelength sampling explain the change?), calibration warnings, CSV export. | Wavelengths come from the display-grade WCS-WAVE table (or the simulation) until CWAVE/CBAND files are used; the page says so. |
| 03 Instrument forensics | Ten modules (crosstalk, aurora, helium, shuttle glow, dead pixels, nonlinearity, read noise, gain, zodiacal light, PSF) plus the simultaneous array. Each gives a measured value, a verdict (explains / possible / does not explain / cannot test) and the official calibration product that would confirm it. Calibration impact experiment: candidate counts after each correction. | Without the template FITS files, aurora/helium/shuttle glow tests use band and channel geometry only. |
| 04 Case studies | 3I/ATLAS, SPLICES (`splices_query`), RW Aur, brown dwarfs, R Dra; DR1 cube reader `read_allsky_cube`. | Live data needed; not run in this build. |
| 05 Scientific court | Six separate confidences: detection, position, motion, brightness, spectral, interpretation. Never one percentage. | |
| 06 Planet X lab | Published IRAS–AKARI pair re-measured (47.46 arcmin over 23 years → about 480 au if on a circular orbit); motion sensitivity by distance; survey-selection simulation under stated assumptions; falsification rule; discovery ladder. | Two positions do not determine an orbit. Nothing here is a discovery. |
| 07 Ice and molecule lab | Band depth τ = −ln(F/F_c) for H₂O, CO₂, CO, CH₃OH, OCN⁻ with errors and named blends. | Schematic continuum; compare with laboratory spectra. SPLICES targets need live data. |
| 08 Observation optimizer | Monte Carlo expected information gain (bits) for four next measurements, with the reason, and approximate SPHEREx visibility windows. | Visibility is a ±90° solar-longitude approximation. |
| 09 Validation observatory | Benjamini–Hochberg false-discovery control, expected chance candidates (0.375 per empty field), negative controls, sensitivity tables, real versus simulated: 29 of 120 real QR3 injections recovered (24 %, 17–33 %) against 98.8 % on the simulated sky. | |
| 10 Human observatory | English–Bangla glossary, Cohen and Fleiss kappa for blind repeats. | Bangla terms need expert review; no participant study has been run. |
| 11 Evidence passport | Canonical JSON body per candidate, section hashes, seal. Verify in the browser (Web Crypto), with `sha256sum`, or with `scripts/verify_passport.py`. Compare two versions by section hash. | SHA-256 detects change; it does not prove authorship or truth. |

Generative-AI free: no language model produces any result. The observatory's five-hypothesis engine is a small logistic model trained on the simulated sky; the 4D labs are classical calculations.

## Real-data notebooks (need Kaggle; this build could not reach IRSA)

`notebooks/kaggle/SPHEREx_DR1_Real_Data_Validation_Kaggle.ipynb` (DR1 MEF audit, ePSF, Gaia alignment, injection/recovery) and `notebooks/kaggle/PlanetNine_Candidate_Assessment_Kaggle.ipynb` (Caltech reference population, IRAS–AKARI triage). The Planet Nine notebook now runs offline if `reference_population.csv` is attached as a Kaggle input, and skips the VizieR crossmatch when there is no internet.
