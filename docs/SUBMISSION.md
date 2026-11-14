# Submission text

Copy each field into the Space Apps form.

## Project Title

Nakshatra CHRONOS: an observatory that asks what changed in the SPHEREx sky, and tries to prove itself wrong

## High Level Project Summary

You cannot blink SPHEREx. Each pixel of each exposure sees its own color of infrared light, so two pictures of one star differ even when the sky did not change. Nakshatra CHRONOS is an open web observatory that finds real change in SPHEREx images without falling for this trap. It compares only fair pairs (same array, matched color, one release), then searches with three independent methods: a PSF catalog method, a difference image method and an anomaly ensemble. Their disagreement is treated as a measurement: on unseen practice fields, a change seen by all three methods is real in 91 percent of cases, a change seen only by the anomaly model in 5 percent. A calibrated engine ranks five hypotheses (moving, variable, transient, artefact, unknown), a self questioning machine runs the tests that could break its answer, and every sentence of the report points to a measurement. It serves SPHEREx scientists who screen candidates, students and citizen scientists who want to check a claim, and anyone searching for faint movers such as a distant Planet X, with honest limits stated.

## Link to Final Project

* Live observatory: https://pritidipadas.github.io/nakshatra-chronus/
* Source code: https://github.com/PRITIDIPADAS/nakshatra-chronus

## Link to Project Demo

* Video (30 seconds): https://pritidipadas.github.io/nakshatra-chronus/media/chronos_demo.mp4
* Slides (7): https://pritidipadas.github.io/nakshatra-chronus/deck.html (PDF: https://pritidipadas.github.io/nakshatra-chronus/media/CHRONOS_deck.pdf)
* The story of one star, in English and Bangla: https://pritidipadas.github.io/nakshatra-chronus/story.html

## Detailed Project Description

**The scientific problem.** SPHEREx maps the whole sky from 0.75 to 5 micron in 102 channels with a linear variable filter on each of six arrays. The filter gives every pixel its own color, and the sky moves across the filter from one exposure to the next. A star therefore changes measured brightness between two exposures when the color changes. Surveys 3 and 4 sit half a channel away from surveys 1 and 2. A naive difference of two SPHEREx images shows many false changes. The challenge asks for a way to find real changes in this data, which is also the way to find faint movers such as a distant planet.

**What CHRONOS does.** For one field of the sky it:

1. Reads every exposure with all its parts: IMAGE, FLAGS, VARIANCE, ZODI, PSF, WCS-WAVE and the detector map (WCS A).
2. Checks the noise of each exposure against empty sky, because the VARIANCE plane can understate it.
3. Anchors every exposure to Gaia stars and puts all exposures on one grid.
4. Measures a star ensemble gain for every exposure and runs a calibration guardian: a release change or a gain step is shown and never becomes a discovery.
5. Builds fair pairs only: same array, color within 0.35 of a channel, same release.
6. Searches with three methods that fail in different ways. P, the catalog method: matched filter detection in every visit, PSF centroids, links across visits, a motion court (fixed position against linear motion, by BIC), brightness and presence tests. Position and brightness floors are measured on the catalog stars of the field, never assumed. D, the difference method: fair co adds of two visits, significance Z = (I2 − k I1) / √(σ1² + k² σ2² + (f s)²), where f is the resampling error measured on catalog stars, summed over arrays. A, the anomaly ensemble: eight time features per pixel against its fair partners, ranked by an isolation forest, a local outlier factor and a robust covariance model, with the spread of the three models kept.
7. Joins the detections into candidates and keeps their agreement pattern. Disagreement is a signal with a measured meaning.
8. Computes a fingerprint of 22 features (motion, brightness change, presence, single exposure dominance, array concentration, shape against the PSF, flags, the simultaneous array behind the dichroic, agreement pattern) and runs the five hypothesis engine: a multinomial logistic model trained on practice fields with a known truth, with equal priors, a fitted temperature, and the right to say unknown when the top probability is low or the fingerprint is unlike the training set.
9. Runs the self questioning machine: tests that the engine did not use, chosen to break the leading explanation. For a mover: star drift between visits, leave one visit out, catalog motion, a blend with a neighbor. For an artefact: the partner array at the same moment, a fixed detector position, crosstalk geometry two readout channels away, a shape sharper than the optics. A failed test changes the status to contested.
10. Runs the counterfactual universe: the whole analysis again with flagged pixels kept, a local background, the worst measured noise, star anchors moved by their error, a wider PSF, each visit left out, and a stricter threshold. The robustness profile counts the choices under which the claim survives.
11. Holds a debate of three analysts (motion, photometry, instrument) who each read different measurements, and records unresolved disagreement.
12. Writes a report where each sentence carries references to an evidence table, builds the memory of the place (an event chain by visit), an identity network with catalog matches, a spectral fingerprint F(λ, t), and a next observation oracle that names the measurement that would separate the two leading hypotheses.
13. Seals inputs, thresholds, code hashes, versions and outputs with SHA 256 so the investigation can be reproduced.

**The observatory.** The web page has thirteen chapters: a sky and time explorer with a temporal cube I(α, δ, t), blink, six arrays, Gaia and AllWISE overlays, adjustable field of view, coordinate search and coordinate based links; fair pairs and the calibration guardian; the difference microscope with six layers of correction and a count of the spots that survive each; the candidate table and population map; the dossier, with a cross match against Rubin alerts and known small bodies in live mode; the motion cartographer; validation; open research questions with falsification rules; the Planet X laboratory with the ladder from prediction to discovery; a citizen lab with a fixed citizen study (instructions, practice cases with feedback, blind repeats, confidence) and a human and machine disagreement archive; the black box recorder, which can publish the sealed package to a Hugging Face dataset; a whole sky change map in 48 equal area tiles, corrected for coverage; and the architecture. A plain language box turns questions such as "evidence against C01" or "brightness changed more than 20 percent" into structured queries and shows them. A bilingual story page (English and Bangla) walks one star through the fair blink; the hosted page replays it from answers recorded in the full app.

**Evidence that it works.** Practice fields follow the SPHEREx rules and hide a known truth. On 109 unseen fields (512 candidates) the engine is right in 98.8 percent of the cases where it decides and says unknown in 1.8 percent; Brier score 0.021, expected calibration error 0.007. Every glitch, hot pixel and crosstalk ghost (117 cases) was called artefact or unknown. Empty fields give 0.375 false candidates per field. None of 840 catalog stars with no motion was called moving. Moving sources are found at 97 percent at AB 15 and 45 percent at AB 18. In the practice field, a moving source of 1.7 arcsec per year (0.4 pixel over the whole baseline, invisible to the eye) is measured at 6 sigma, and the difference microscope reduces 27 raw false changes to 1. These numbers hold for the practice sky only; real data will be harder.

**Whole sky tiles.** The sky is cut into 48 equal area tiles, each with a science field, a null twin for false alarms and an injection twin for completeness. In the deep tiles near the ecliptic poles the raw count finds only 45 to 50 percent of the planted changes, so a raw map would show the survey, not the sky. Corrected with the completeness of each kind of tile, the whole sky comes to 106 percent of the truth and every tile agrees within two errors.

**On real SPHEREx data.** The injection tool ran on real QR3 files from IRSA (GitHub Actions). 120 known sources were planted in five real fields; 29 became candidates (24 percent, against 97 percent in the practice sky). The engine trained on practice fields said unknown for every real candidate instead of making a false claim. Retrained with the real rows and scored on held out fields, it decided 17 of 29 and was right in 12. Real data is harder: QR3 holds about two months of each place, which is short for slow movers. In live mode the dossier asks the ALeRCE broker for Rubin LSST alerts and JPL for known small bodies; NEO Surveyor joins when its data is public.

**Tools.** Python, NumPy, SciPy, Astropy, astroquery, astropy healpix, scikit learn, FastAPI, Uvicorn, Pillow, the Hugging Face Hub client; a plain JavaScript front end with canvas charts; pytest (73 tests, including the live archive path and the real data injection offline with files in the IRSA layout); GitHub Pages for the static observatory; Docker for the full app.

## Space Agency Data

* **NASA SPHEREx Quick Release spectral images, QR2 and QR3, at NASA IRSA** (DOI 10.26131/IRSA652 for QR2). Found with the IRSA SIA2 service (collections spherex_qr3 and spherex_qr2), read through the IRSA cutout service. CHRONOS uses IMAGE (sky), FLAGS (masks, contamination counts, flag names from the MP keywords), VARIANCE (noise model, checked on empty sky), ZODI (background level), PSF (photometry; QR2 and QR3 layouts), WCS-WAVE (the color of each pixel) and the alternate WCS A (detector positions for the hot pixel and crosstalk tests). Release names feed the calibration guardian.
* **ESA Gaia DR3** through astroquery: star anchors, star ensemble gains, catalog motions and parallaxes for cross matching and for the target positions.
* **NASA AllWISE at IRSA** (TAP service): catalog overlay in live mode.
* **NASA JPL Small Body Identification API**: known small bodies near a candidate in live mode.
* **NASA Science, Planet X page**: the statement that Planet X has not been discovered, used in the Planet X lab.
* **NASA NEO Surveyor** (planned, launch no earlier than September 2027): named in the cross match, joins when its detections are public.
* Other data: Rubin LSST alerts (NSF and DOE Vera C. Rubin Observatory) through the ALeRCE broker TAP service, cross match in live mode.
* The practice sky follows the published SPHEREx design: band edges and resolving powers (Bock et al.), the crosstalk model two readout channels away (Crill et al., SPHEREx Sky Simulator), flag names (Akeson et al.).

## Hackathon Journey

I chose this challenge because SPHEREx breaks the oldest tool of change detection, the blink comparator that found Pluto, and because a Planet X search is a search for change in exactly this kind of data. I also wanted a tool that a careful amateur could trust: in Bangladesh, variable star observers like Radhagobinda Chandra of Jessore recorded the changing sky by eye for decades, and checking a claim mattered more to them than making one.

My approach was to start from the instrument. Before any detection I asked what makes two SPHEREx exposures comparable at all, which gave the fair pair rule. Then I built three detectors on purpose that fail in different ways, and measured what their agreement and disagreement mean on fields with a known truth. Last, I made the system argue against itself: tests the engine never used, counterfactual reanalysis, and a debate that may stay unresolved.

What I learned: the hardest part was not finding change, it was refusing false change. Noise planes can understate noise. Resampling an undersampled PSF leaves residue around bright stars that looks exactly like variability. A half channel color offset can mimic a brightness change. A crosstalk copy of a bright star fooled all three of my detectors at once, which taught me that agreement is not proof. I also learned to state probabilities only where I can calibrate them.

Difficulties: the archive services could not be reached directly from my build environment, so I tested the full live path on files built in the documented IRSA layout and added a button that checks the live archive. I then read one real IRSA SIA2 answer (spherex_qr3, Barnard's Star) through a web reader: the files exist in the expected layout, and arrays 3 and 6 share one exposure and one start time, as my practice sky assumes. A test now keeps that layout. Later the full live path ran on real QR3 files on GitHub Actions; it found two parsing faults (a self description table first, and column IDs in place of names) and the QR3 EPSF table format, all fixed and tested. Early versions had a parallax sign error, a centroid that locked onto a neighbor star, and a noise estimate polluted by star wings; tests now guard each of them.

## References

**Data and services**
* NASA IRSA, SPHEREx mission page and Quick Release overview. https://irsa.ipac.caltech.edu/Missions/spherex.html
* SPHEREx Quick Release Spectral Images QR2, DOI 10.26131/IRSA652. https://www.ipac.caltech.edu/doi/10.26131/IRSA652
* SPHEREx Explanatory Supplement (QR). https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp_QR.pdf
* SPHEREx archive documentation, data products. https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/
* IRSA tutorials: Introduction to SPHEREx Spectral Images; SPHEREx cutouts; SPHEREx PSF. https://caltech-ipac.github.io/irsa-tutorials/
* IRSA Simple Image Access (SIA2) and TAP services. https://irsa.ipac.caltech.edu/
* ESA Gaia DR3 archive. https://gea.esac.esa.int/archive/
* AllWISE Source Catalog at IRSA. https://irsa.ipac.caltech.edu/Missions/wise.html
* ALeRCE broker TAP service for Rubin LSST alerts, table alerce_tap.lsst_dia_object. https://tap.alerce.online/tableinfo/alerce_tap.lsst_dia_object
* NEO Surveyor mission page, NASA JPL. https://www.jpl.nasa.gov/missions/near-earth-object-surveyor
* Górski et al. 2005, HEALPix, ApJ 622, 759; astropy healpix. https://astropy-healpix.readthedocs.io/
* Fleiss 1971, Measuring nominal scale agreement among many raters, Psychological Bulletin 76, 378.
* Hugging Face Hub client library. https://huggingface.co/docs/huggingface_hub
* JPL Small Body Identification API. https://ssd-api.jpl.nasa.gov/doc/sb_ident.html
* NASA Science, Planet X. https://science.nasa.gov/solar-system/planet-x

**Papers**
* Bock et al., The SPHEREx Satellite Mission, arXiv 2511.02985.
* Crill et al., The SPHEREx Sky Simulator, arXiv 2505.24856 (crosstalk model, depth).
* Akeson et al., The SPHEREx Image and Spectrophotometry Processing Pipeline, arXiv 2511.15823 (flags).
* A bestiary of low level electrical artifacts in SPHEREx flight data, arXiv 2608.09862 (crosstalk types and flags).
* Liu, Ting and Zhou, Isolation Forest, ICDM 2008. Breunig et al., LOF, SIGMOD 2000. Rousseeuw and Van Driessen, minimum covariance determinant, Technometrics 1999.
* Guo et al., On calibration of modern neural networks, ICML 2017 (temperature scaling, calibration error).
* Wilson, Probable inference, the law of succession, and statistical inference, JASA 1927 (intervals).
* Batygin and Brown, Evidence for a distant giant planet in the Solar System, AJ 151, 22 (2016).
* Target values: Gaia DR3; McCaughrean et al. A&A 413, 1029; Luhman and Esplin as quoted in arXiv 2510.24575; Rodriguez et al. ApJ (RW Aurigae); BAA Variable Star Section (R Draconis). Full list in docs/CITATIONS.md.

**History and outreach**
* The discovery of Pluto with a blink comparator, American Astronomical Society. https://aas.org/posts/news/2017/02/month-astronomical-history-discovery-pluto
* Radhagobinda Chandra, variable star observer: Biswas et al., arXiv 1102.2383.
* Backyard Worlds: Planet 9 (citizen science context). https://backyardworlds.org

**Software and assets**
* Python, NumPy, SciPy, Astropy, astroquery, scikit learn, FastAPI, Uvicorn, Pillow, Requests, Matplotlib, pytest, Playwright, FFmpeg.
* EB Garamond font (SIL Open Font License) through Fontsource.
* All images in the project are made by the project code from simulated data or from the listed archives. No outside images are used.
