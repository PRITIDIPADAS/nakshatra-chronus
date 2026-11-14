# Nakshatra CHRONOS: research extension roadmap

## Mission

Extend CHRONOS into an instrument-aware, reproducible observatory for investigating changes in the infrared sky. The primary path is measurement-first: PSF photometry, calibration-aware wavelength assignment, robust statistics, explicit null controls, physical model comparison and uncertainty propagation. Existing machine-learning detectors remain comparison methods; they do not override missing evidence or an `unknown` conclusion.

## Included implementation

| Capability | Code | State |
|---|---|---|
| DR1 All-Sky Cube reader | `backend/chronos_addons/spectral.py` | Implemented; requires local archive FITS |
| Level-2 MEF + `CWAVE/CBAND` reader | `spectral.py`, `archive.py` | Implemented; strict shape checks |
| Spectral comparison | `spectral.py` | Implemented; significance only with supplied valid sigma |
| Source-specific `F(λ,t)` bridge | `bridge.py` | Implemented; reuses CHRONOS photometry when installed beside backend |
| Instrument triage | `forensics.py` | Implemented as transparent rules, not a classifier |
| Named calibration/HDU/ECSV loading | `archive.py` | Implemented; no automatic detector-grid reprojection |
| Calibration ablation accounting | `forensics.py` | Implemented candidate-count/position overlap only |
| Expected-information-gain planner | `planner.py` | Implemented for supplied Gaussian forecasts |
| Evidence passport | `passport.py` | Implemented SHA-256 content seal; not identity authentication |
| Injection/recovery and probability metrics | `validation.py` | Implemented one-to-one matching, Wilson intervals, coverage and field splits |
| Spectral equivalent width | `molecular.py` | Implemented for user-specified feature and sidebands; no species identification |
| Positional catalogue cross-match | `catalogs.py` | Implemented; no proper-motion propagation or physical association probability |
| Orbit visualization sandbox | `orbits.py` | Implemented low-precision two-body scenario; not a validated ephemeris |
| Completeness/null corrected tile counts | `selection.py` | Implemented; excludes tiles below a stated completeness floor |
| Citizen review aggregation | `citizen.py` | Implemented statistics; not a completed human-subject study |
| Optional HTTP API | `api.py` | Implemented; must be mounted into `backend/app.py` |
| Research laboratory browser page | `frontend/chronos-lab.*` | Implemented local tools; examples are synthetic |

## Research architecture: position × time × wavelength × evidence

For each source, the desired scientific object is:

`F(λ,t), σ(λ,t), quality(λ,t), provenance(λ,t)`

The All-Sky Cube provides a spectral reference; individual exposures provide the time axis. Do not describe the All-Sky Cube itself as a time series. A valid time-resolved spectrum must come from individual measurements with science-grade `CWAVE/CBAND` wavelength assignments and measurement uncertainties.

## Work that still requires research/data integration

These are next-stage research goals, not functionality claimed complete by this code pack.

### 1. Full detector-template diagnostics

Project official aurora, helium, shuttle-glow, nonfunctional-pixel, nonlinearity, read-noise, crosstalk and zodiacal-scaling products into each exposure's detector grid. For a candidate, compare detector-coordinate persistence, template overlap, profile residuals, partner-array behaviour and epoch consistency. Keep evidence for and against instrumental explanations separately. This pack loads products, but does not automatically map every template into cutouts.

### 2. Real-data blind benchmark

Inject sources into independent real exposures with source-appropriate photon noise, spatially varying ePSFs, actual flags and detector geometry. Blind source positions/class labels from the detection pipeline. Split train/test by sky field, never by random pixels or candidates from the same field. Publish completeness and false alarms by magnitude, motion, detector, wavelength, visit count, crowding and ecliptic latitude.

### 3. Physically grounded observation planner

The planner ranks supplied predictive distributions by expected entropy reduction. It does not calculate telescope visibility, weather, solar elongation, slew constraints or an orbit ephemeris. Add those from validated external tools before claiming an observing schedule.

### 4. SPLICES and molecular case studies

Add a versioned SPLICES catalogue adapter and validated feature definitions. Spectral feature measurement must remain separate from variability detection. Molecular identification requires calibrated wavelength, resolution/line-spread modelling, blend handling, uncertainty and independent confirmation.

### 5. Human review study

Run a consent-based blind review pilot with independent participants. Pre-register the protocol, include practice and repeat cases, define an independently supported answer key, collect confidence, and publish anonymized results. The code aggregates responses; it does not mean the study has happened.

### 6. Outer Solar System investigation

Separate theoretical orbital prediction, observational candidate, statistically supported detection and confirmed discovery. Replace the low-precision orbit sandbox with validated ephemerides and astrometric covariance before using tracks as scientific evidence. Model survey selection effects before interpreting an apparent orbital population.

## Scientific acceptance criteria

Do not mark a feature complete until it:

1. Runs on actual archive files with versioned data provenance.
2. States units, calibration product and uncertainty semantics.
3. Has negative controls and an independent held-out test.
4. Keeps incompatible release/calibration groups separate.
5. Has reproducible tests and a verifiable evidence passport.
6. Discloses failure modes, missing data and what the evidence cannot establish.

## Non-claims

This pack does not claim a Planet X discovery, a new transient, a new molecule, an astrophysical interpretation of any particular real candidate, or validated full-sky performance. No NASA archive files are bundled. Demo spectra, forecasts and interface examples are synthetic.
