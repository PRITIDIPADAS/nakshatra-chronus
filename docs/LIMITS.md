# Limits

Read this before you trust a result.

## Real data

* The real data path ran on real QR3 files on GitHub Actions. Search, cutouts, keywords, the color of each pixel (WCS-WAVE), the QR3 EPSF table and Gaia anchors work. Two faults of the first real run are fixed and tested: the IRSA answer starts with a self description table, and astropy named the columns col_0, col_1 and so on.
* QR3 holds about two months of each place. At low ecliptic latitude that is one visit (Barnard's Star, RW Aurigae, Epsilon Indi B), so no change can be seen there with QR3 alone. The QR2 search returned no files at these places. WISE 0855 returned no QR3 files.
* Near the ecliptic poles SPHEREx sees a field almost every day. CHRONOS then cuts time into visits of 30 days. A baseline of two months is short: slow movers and slow variables barely change.
* On real noise only 24 percent of planted sources were found, against 97 percent of movers at AB 15 in the practice sky. Every probability in the validation chapter holds for the practice sky only.
* The engine trained on the practice sky says unknown for real candidates. The retrained engine (data/engine_real.json) rests on 29 real rows; it is not used by the app.
* The EPSF oversampling is not in the file header that CHRONOS reads; it is estimated from NEFF_MEAN (5 for the files seen).
* The IMAGE header carries SIP distortion terms without the SIP suffix in CTYPE. Astropy applies them, as the IRSA tutorials expect.
* The color at the star comes from the lookup table inside each file. IRSA calls this table display grade. For science, use the CWAVE and CBAND calibration products.
* Pictures from QR2 and QR3 use different gains. CHRONOS does not apply the official flux correction product. A pair across releases is never called fair. The brightness check uses reference stars to remove the gain difference.
* The PSF zone is taken from the keywords of the file. QR3 has a separate ePSF product that CHRONOS does not read yet.
* SPHEREx pixels are 6.15 arcseconds wide. Epsilon Indi Ba and Bb are one dot. RW Aurigae A and B are one dot.
* R Draconis and Barnard's Star are very bright. Saturated pictures carry the OVERFLOW flag and CHRONOS leaves them out. Few pictures can remain.
* WISE 0855 is near the single picture limit even in the longest band. A nondetection is the expected result in most colors.
* The brightness models that feed the forecast are approximate.
* The reference stars are Gaia stars brighter than magnitude 17. A crowded field can pull the star fit toward a neighbor.

## Methods

* The difference picture is for the eye only. Lining up an undersampled picture is never exact. Near bright stars the difference picture is less sensitive.
* The false change meter assumes a smooth spectrum between neighbor colors. A narrow molecular band can break this. The error of the meter grows when the fit is poor.
* The parallax fit uses the position of the Earth, not the position of the spacecraft. The difference is far below one pixel for stars.
* The known asteroid check uses an observer on the ground. A main belt object can be off by about one pixel.
* The Planet X tools are estimates on a practice sky. The depth limit is an assumption. A parallax shift can be larger than a small cutout.
* The blind test uses practice images and is a small pilot.

## The observatory and the engine

* The five hypothesis engine is trained and scored on the practice sky. Its probabilities are calibrated there and nowhere else. On real SPHEREx data, use its ranking and its unknown flag, not its percentages, until it is retrained on injections into real images.
* Practice camera effects are glitches, hot pixels, crosstalk copies and flagged blobs. Real SPHEREx data has more kinds (snowballs, blooming, persistence, other crosstalk types). An unknown kind should land in H5 unknown, but that is not proven.
* The crosstalk test looks for a bright catalog star one or two readout channels (64 or 128 columns) away on the same row. It needs the detector map of WCS A in the file.
* The anomaly ensemble ranks pixels within one field. A field with many real changes moves the ranks.
* The difference method uses fair pairs only. A change between visits with no fair color match is seen by the catalog method alone. CHRONOS says so in the disagreement panel.
* The wavelength changes slowly across a cutout (less than half a channel over five arcminutes). Fair pairs are judged at the center.
* Live mode needs at least four usable exposures in two visits. Many places on the sky have fewer so far.
* The plain language box maps fixed phrases to fixed queries. It does not understand free grammar, and it says so when it cannot map a question.
* The citizen lab stores answers in the browser only. It is a pilot for study design, not a validation.
* The hosted page holds prepared practice fields. Any coordinate, any field of view and live data need the full app.

## Software

* The story page keeps one loaded star in memory and serves one user at a time. The observatory caches each investigation on disk.
* The cache folder has no size limit.
* The Bangla text needs a review by a second native reader.

## New tools

* Planted sources in real exposures get no photon noise of their own. For faint sources the error is small; for bright ones it makes them a little too easy.
* The whole sky tiles sample each tile with one small practice field. The map shows the method of correction, not the real sky.
* The engine was trained on four visit fields. In the six visit tiles near the ecliptic poles it says unknown more often, so the completeness there is lower. Retraining with deep fields would fix this.
* The citizen study has not been run with real participants. One person in a browser is not a study.
* A Rubin match is a lead, not a confirmation: Rubin sees optical light, SPHEREx infrared, at other times.

