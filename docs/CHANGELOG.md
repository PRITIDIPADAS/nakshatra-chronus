## CHRONOS 4D (2026-11-14)

- Ten laboratories (backend/lab.py, lab.html, /api/lab, scripts/build_lab.py, tests/test_lab.py).
- Live default collections DR1 + QR3; QR2 mixing refused without flux corrections.
- Evidence passports verifiable with sha256sum or in the browser.
- Kaggle notebooks in notebooks/kaggle; Planet Nine notebook works offline with attached data.

# Change log

## Version 5: next steps built

* Whole sky tiles: a change map corrected for coverage, with a null twin and an injection twin per tile (chapter XII).
* Citizen study mode: written instructions, practice cases with feedback, a fixed case order, blind repeats, confidence and response time, export, and a pooling script with Fleiss kappa.
* Cross match with Rubin alerts (ALeRCE broker) and known small bodies (JPL) in the dossier, live mode.
* Injection into real SPHEREx exposures and retraining on real noise (scripts/inject_real.py), tested offline.
* The sealed package can be published to a Hugging Face dataset.
* Plain words in the story come only from the computed numbers.
* First run on real QR3 files (GitHub Actions): 120 planted sources in five fields, 29 found; the practice engine said unknown for all real candidates; a retrained engine is kept apart.
* Fixed on real data: the results table of the IRSA answer, column names, the QR3 EPSF table, a PSF fit that failed on bad pixels, visits in continuous coverage.
* The story in English and Bangla plays on the hosted page from recorded answers.

## Version 4: the observatory

The project grew from one star to a whole field, and from one method to an investigation.

* Practice observatory fields with a hidden truth: movers, variables, flares, appearing and vanishing sources, glitches, hot pixels, crosstalk copies of bright stars, flagged blobs and a calibration step between releases. Two arrays behind the dichroic share each moment, as in SPHEREx.
* Three detectors (catalog, difference, anomaly ensemble) and candidates that keep their agreement pattern.
* Measured astrometric and photometric floors from the catalog stars of each field.
* The five hypothesis engine, trained on 251 fields and scored on 109 unseen fields, with temperature calibration and an unknown rule.
* The self questioning machine, the artefact court, the counterfactual universe, the debate, the memory of a place, the identity network, the spectral fingerprint, the oracle and the evidence linked report.
* Field controls: a null twin of every practice field, static stars, time shuffle, alignment stress.
* The observatory page with twelve chapters, the temporal cube, the difference microscope, the Planet X lab, the citizen lab and the black box recorder.
* Static build for GitHub Pages, four notebooks, figures, a deck and a video.
* Live connectors now read the detector map (WCS A), group simultaneous exposures, and add AllWISE.

### Errors found and fixed in version 4

* The first photometric floor was trimmed and too small, so bright static stars looked variable. The floor now uses all catalog stars.
* The anomaly model compared an exposure with partners that contained the same glitch with the opposite sign. Single exposure dominance now follows the sign of the strongest residual.
* Artefacts were placed in pixel coordinates mirrored against the sky. They now sit at a sky position.
* Per image display stretch could make a blink show a change that was only in the display. All visits of one family now share one stretch.
* The first static star control counted real movers. It now counts catalog stars far from every planted change.

## Version 3

Every file was run and tested. The page became one story.

### Errors found and fixed

* The motion fit locked onto a neighbor star and failed to recover an injected motion. The star fit now stays inside a small box, and the practice sky keeps stars away from the target path.
* The parallax factors had the wrong sign. A real star would have given a negative parallax.
* Aperture photometry lost about one fifth of the flux. Photometry is now a PSF fit.
* The practice sky had no WCS, so the line up code never ran. Every practice picture now has its own WCS, and the same code runs for practice and real data.
* The practice sky repeated the same six colors in every visit, so every pair looked fair. It now steps the color as SPHEREx does.
* The injection test set its alarm level on the wings of bright stars. Sources are now hidden with a radius that grows with brightness.
* The ratio spectrum called a steady star variable, because of a half channel color shift. The color term of the false change meter now removes this.
* The JPL query used the geocentric observer code, which the service does not accept.
* The flag bits were fixed numbers. They are now read from each file.
* The wavelength lookup did not switch off the distortion terms, as the IRSA tutorial requires.
* A file with an unknown color could form a fair pair. It no longer can.
* The Planet X search used eight trial distances and missed planets between them. It now uses about one hundred.

### New

* False change meter.
* Noise reality check on empty sky, applied to all errors.
* Sky or camera test for any spot in a picture.
* Motion court with parallax in one fit.
* Forecast on the coverage plot before any measurement.
* Live archive check that names the failing step.
* Tests of the real data path that need no internet.
* Verified values for the five targets, with sources.
* One page story in five steps, in English and Bangla, for phone and desktop.
* The frozen rules file has a seal and no clock value.

### Removed

* Clock values in the downloaded files.
