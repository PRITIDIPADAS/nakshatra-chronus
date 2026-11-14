# data folder

## SPHEREx Quick Release spectral images (NASA IRSA)

* Search: IRSA SIA2, `https://irsa.ipac.caltech.edu/SIA`, `COLLECTION=spherex_qr3` and `spherex_qr2`, `POS=CIRCLE ra dec r`.
* Cutouts: the IRSA cutout service, `?center=RA,DEC&size=` on each file, as the IRSA tutorials show.
* Extensions read: IMAGE (MJy/sr), FLAGS (bit names from the MP keywords of each file), VARIANCE, ZODI (median level), PSF (QR2 cube with zone centers; QR3 layout), WCS-WAVE (color at each pixel, distortion off as the tutorial requires), alternate WCS A (detector pixels).
* Header keywords used: DETECTOR, OBSID, VERSION, FINAST.
* QR2 citation: DOI 10.26131/IRSA652.

## Gaia DR3 (ESA)

`gaiadr3.gaia_source` cone search through astroquery, stars brighter than G 17 with RUWE under 1.4: positions at epoch 2016.0, proper motions and parallaxes. Uses: anchors, gains, cross match, overlay.

## AllWISE (NASA IRSA)

TAP table `allwise_p3as_psd`, W1 and W2 magnitudes. Use: overlay in live mode.

## JPL Small Body Identification

`https://ssd-api.jpl.nasa.gov/sb_ident.api` with a surface observer. Use: known asteroids near a candidate in the story page.

## Rubin LSST alerts (ALeRCE broker)

TAP table `alerce_tap.lsst_dia_object` at `https://tap.alerce.online/tap`. Use: cross match in the dossier, live mode.

## The practice sky

`backend/sky.py` renders fields with the SPHEREx rules and a truth list. Every practice image carries the label SIMULATION.

## Files in data/

* `engine.json`: the frozen five hypothesis model (feature names, scaling, coefficients, temperature, training distance limit).
* `validation.json`: every score in docs/VALIDATION.md.
* `sky_tiles.json`: the whole sky tiles (scripts/make_sky_tiles.py): per tile the science field, null twin and injection twin counts, and the map summary.
* `study.json`: the citizen study cases, written by scripts/build_static.py from the practice fields.
* `real_injection.json` and `engine_real.json`: written by scripts/inject_real.py on real QR3 files (workflow real_injection on GitHub Actions). Real images, noise and stars; planted sources. engine_real.json is the engine retrained with these rows; the app does not use it.
