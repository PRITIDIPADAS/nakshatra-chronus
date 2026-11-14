# Methods

All thresholds are frozen in `backend/pipeline.py` (`TH`) and recorded in every investigation.

## Fair pairs

Two exposures are fair when they come from the same array, their colors differ by at most half a channel (single exposures) and they share one release. Two visits form a fair co add pair when the mean color offset over their exposures is at most 0.35 of a channel and the worst is at most 0.6. Color offsets are measured in channel widths, λ / R.

## Registration and gains

Each exposure is resampled (cubic for the image, linear for the variance, nearest for flags) onto a reference TAN grid with its WCS and a Gaia star anchor shift. The sky level is the median of good pixels. The star ensemble gain of an exposure is the median ratio of catalog star fluxes against the median of its fair partners. Co adds weight by inverse variance after the gain.

## The catalog method (P)

The white light image of a visit is the sum of the six array co adds, each divided by its pixel noise. A matched filter with the PSF gives a detection map; peaks above 5 sigma get a PSF centroid. Detections link across visits within 1.5 pixels.

* **Astrometric floor.** The extra position error that makes bright sources seen in every visit agree with a fixed position, from a trimmed mean corrected for the trim.
* **Motion court.** Fixed position against linear motion in x and y, with errors that include the floor. ΔBIC = χ²(fixed) − χ²(linear) − 2 ln(2n). Motion is claimed when ΔBIC > 10 and the motion is 5 sigma.
* **Photometric floor.** The fractional brightness scatter of catalog stars between visits, per array. Brightness change z = (χ² − dof) / √(2 dof) with errors that include the floor.
* **Presence.** A source bright (above 7 sigma) in some visits and absent (below 2 sigma) in others.

## The difference method (D)

For a fair co add pair on one array, D = I2 − k I1 after the gain. The noise is σ² = σ1² + σ2² + (f s)², where s is the local brightness (5 pixel maximum) and f is the 84th percentile of |D| / s at catalog star positions: the resampling error of an undersampled PSF, measured. A matched filter turns D into significance; arrays combine as Σ Z / √n. A positive and a negative peak within 3.2 pixels form a dipole, the mark of a small motion.

## The anomaly ensemble (A)

Every exposure minus the mean of its fair partners in other visits, as matched filter significance. Per pixel features: largest residual, share of exposures above 3 sigma, strongest visit mean, single exposure dominance (signed), share of the strongest array, sign coherence, deep brightness, flag share. Features are scaled by median and MAD. An isolation forest, a local outlier factor and a minimum covariance determinant model rank the pixels; the mean rank is the score and the spread is kept. Peaks above rank 0.95 with a residual above 4.5 sigma are detections.

## Five hypotheses

Classes: H1 moving, H2 variable, H3 transient, H4 artefact, H5 no established change. Model: multinomial logistic regression on 22 standardized features (signed log for heavy tails), class weights for balance, L2 strength C = 0.5. A temperature T is fitted on the training fields by negative log likelihood. Priors are equal; the page lets the reader change them, which multiplies P(H | D) by P(H) and renormalizes. The verdict is unknown (H5) when the top probability is under 0.55, or when the Mahalanobis distance of the fingerprint from the training set (Ledoit Wolf covariance) passes its 99.5 percent quantile, or when fewer than two visits measured the place.

## Self questioning

Tests are chosen by the leading hypothesis and none of them is an engine feature.

* Moving: star drift between the first and last visit; leave one visit out (weakest fit above 2 sigma, direction within 45 degrees); arrays that see the source in two or more visits; catalog motion pull; neighbor within 3 pixels.
* Variable: change against the star scatter; seen in a fair pair; arrays with a 3 sigma change; moving neighbor; release.
* Transient: exposures inside the bright visits that show it; Gaussian width against the PSF; the partner array at the same moment; flags; position jump inside a visit (a fast asteroid).
* Artefact: the partner array; detector position spread; a bright catalog star 64 or 128 columns away on the same row; width; flags; share of one array.

## Counterfactuals

Eleven states: baseline, flagged pixels kept, a local 11 pixel median background, the worst measured noise factor, star anchors moved by their error, PSF 15 percent wider, each visit left out, and a 6 sigma threshold. The statistic follows the hypothesis: motion significance, brightness z, visit contrast, or the strongest change measure. Status: worth further investigation when no test argues against and at least 75 percent of the states keep the claim.

## Oracle

Priority = normalized entropy of the posterior × min(1, signal / 10) + 0.3 for a sky hypothesis. The next measurement is chosen by the two leading hypotheses. For a mover, the motion error after one more visit, 182.6 days after the last, comes from the Fisher information of the visit times.

## Planet X lab

Radius R = M^0.55 (Earth units), H from the diameter and albedo, reflected light at opposition m = H + 10 log10(d), thermal glow of a blackbody sphere at 4.5 micron, parallax 206265 / d arcseconds, orbital drift from Kepler speed. The depth limit is the reader's choice, minus 0.5 magnitude within 10 degrees of the galactic plane.

## Whole sky tiles

The sky is cut into 48 equal area HEALPix tiles (nside 2). Each tile gets three practice fields at its center: a science field, a null twin with nothing planted, and an injection twin with twelve planted changes. Depth follows the SPHEREx scan (six visits within 30 degrees of the ecliptic poles, four elsewhere) and crowding follows the Galaxy (more stars near the galactic plane). The corrected rate of a tile is (called sky changes minus the called changes of the null twin) divided by the completeness of the injection twin, with a floor of 0.2, per square degree. The truth of the science field is used only to score the map, never to correct it. Script: scripts/make_sky_tiles.py.

## Injection into real exposures

Visits: a new visit starts after a gap of more than 30 days, and in continuous coverage near the ecliptic poles a visit also ends after 30 days. 
scripts/inject_real.py loads real SPHEREx exposures of a field, runs CHRONOS once to record the field's own candidates, then plants movers, variables and transients at free places with the PSF of each file (a Gaussian when a file has no PSF), in the units of the file. Each trial reruns the whole pipeline. Planted sources give completeness by kind and brightness on real noise and the accuracy of the engine on real backgrounds. With --retrain, the rows of the planted sources join practice rows and the engine is fitted again; its score comes from fields held out one at a time. Code: backend/inject.py.

## Citizen study

Every participant sees the same twelve cases in the same order, after three practice cases with feedback. Four cases come back later, at least four cases apart, to measure test retest consistency. Each answer has a confidence (sure, fairly sure, guess) and a response time. scripts/analyse_citizen_study.py pools the exported answers: Fleiss kappa between participants, retest consistency, crowd majority against the practice truth, engine against the truth, and crowd against the engine. Code: backend/study.py.

## Cross match with other surveys

In live mode, the dossier asks the ALeRCE broker TAP service for Rubin LSST DIA objects within 12 arcseconds (table alerce_tap.lsst_dia_object), and the JPL Small Body Identification service for known asteroids and comets. Each service can fail alone. A match is a lead to check: Rubin sees optical light at other times.

