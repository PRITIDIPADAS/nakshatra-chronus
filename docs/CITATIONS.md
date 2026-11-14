# Sources

Web addresses contain hyphens because the addresses are written that way.

## SPHEREx data and documents

* NASA IPAC Infrared Science Archive, SPHEREx mission page. https://irsa.ipac.caltech.edu/Missions/spherex.html
* SPHEREx Data Products (archive documentation). https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/
* SPHEREx Cutout Tool. https://irsa.ipac.caltech.edu/data/SPHEREx/docs/cutout_tool.html
* SPHEREx Explanatory Supplement for Quick Release products. https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp_QR.pdf
* Note on the PSF header error in QR2 files. https://irsa.ipac.caltech.edu/data/SPHEREx/docs/psfhdrerr.html
* IRSA tutorial, Introduction to SPHEREx Spectral Images. https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/
* IRSA tutorial, SPHEREx Source Discovery Tool demo. https://caltech-ipac.github.io/irsa-tutorials/spherex-source-discovery-tool-demo/
* IRSA Simple Image Access service. https://irsa.ipac.caltech.edu/SIA
* Akeson et al., The SPHEREx Image and Spectrophotometry Processing Pipeline. arXiv 2511.15823. Source of the flag names and the astrometry grade.
* Bock et al., The SPHEREx Satellite Mission. arXiv 2511.02985. Source of the band edges, resolving powers and survey depth.
* Crill et al., The SPHEREx Sky Simulator. arXiv 2505.24856. Source of the single picture depth that the practice sky assumes.
* Gagne, Faherty et al., A SPHEREx Pipeline and Spectral Library for Ultracool Dwarfs. arXiv 2604.22012.
* Rustamkulov, Kirkpatrick et al., SPHEREx Spectra for a Sequence of Nearby Brown Dwarfs. arXiv 2607.00543.
* arXiv 2608.08908. Source of the flag recipe for photometry.

## Targets

* Barnard's Star. Gaia DR3 source 4472832130942575872. Position at epoch 2016.0, proper motion and parallax as printed in ESO science paper eso2414, Table 1.
* Epsilon Indi B. Proper motion and the separation of Ba and Bb (0.732 arcseconds) from McCaughrean et al., Astronomy and Astrophysics 413, 1029. Position as given by the challenge. The parallax in app.py is from memory and needs a check.
* WISE 0855. Proper motion and parallax (0.449 arcseconds) from Luhman and Esplin, as quoted in arXiv 2510.24575. Position from the JWST pointing in the same paper. Kirkpatrick et al. give a parallax of 0.439 arcseconds. Blending with a background star: arXiv 1409.5899.
* RW Aurigae. Separation of A and B (1.49 arcseconds) from Rodriguez et al., The Astrophysical Journal, doi 10.3847/1538-4357/aac08f. Recent dimming: Lisse et al., Research Notes of the AAS 9, 278.
* R Draconis. Period of 245.6 days and magnitude range from the Variable Star Section of the British Astronomical Association. Position as given by the challenge.
* The brightness models in app.py (the values named sed) are approximate and come from memory of catalog magnitudes. They feed the forecast only.

## Services and software

* Gaia Data Release 3, European Space Agency, through astroquery.
* JPL Small Body Identification API. https://ssd-api.jpl.nasa.gov/doc/sb_ident.html
* Aladin Lite, Centre de Donnees astronomiques de Strasbourg (used by one Lab tool).
* Astropy, NumPy, SciPy, FastAPI, Uvicorn, Pillow, Requests.

## New tools

* Rubin Observatory alert stream opened to the community through brokers: Lasair and Babamul announcements. https://www.rubin.ac.uk/news/2026-02-25-lasair-success
* ALeRCE broker TAP service, table alerce_tap.lsst_dia_object. https://tap.alerce.online/tableinfo/alerce_tap.lsst_dia_object
* Förster et al. 2021, The Automatic Learning for the Rapid Classification of Events (ALeRCE) alert broker, AJ 161, 242.
* NEO Surveyor mission page, NASA JPL (launch no earlier than September 2027). https://www.jpl.nasa.gov/missions/near-earth-object-surveyor
* Górski et al. 2005, HEALPix: a framework for high resolution discretization and fast analysis of data distributed on the sphere, ApJ 622, 759; astropy-healpix. https://astropy-healpix.readthedocs.io/
* Fleiss 1971, Measuring nominal scale agreement among many raters, Psychological Bulletin 76, 378.
* Hugging Face Hub client library. https://huggingface.co/docs/huggingface_hub

## History

* The discovery of Pluto with a blink comparator at Lowell Observatory: American Astronomical Society, This Month in Astronomical History. https://aas.org/posts/news/2017/02/month-astronomical-history-discovery-pluto
* Radhagobinda Chandra of Jessore, variable star observer for the AAVSO. Biswas et al., arXiv 1102.2383, count 37215 observations. A letter of the AAVSO Recorder quoted in arXiv 1104.1391 says well over 50000. The page says tens of thousands, which agrees with both.

## Observatory version

* SPHEREx Quick Release Spectral Images QR2, DOI 10.26131/IRSA652. https://www.ipac.caltech.edu/doi/10.26131/IRSA652
* SPHEREx Quick Release overview at IRSA. https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_qr.html
* Crill et al., The SPHEREx Sky Simulator, arXiv 2505.24856: electrical crosstalk is strongest between readout channels two apart, at about one part in ten thousand. The practice crosstalk copy sits 128 columns away.
* A bestiary of low level electrical artifacts in SPHEREx flight data, arXiv 2608.09862: crosstalk types and their flags in the L2 flag layer.
* IRSA SPHEREx Spectrophotometry Tool help page. https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html
* IRSA Moving Object Search Tool (MOST). CHRONOS does not replace it.
* NASA Science, Planet X: Planet X has not been discovered and its existence is debated. https://science.nasa.gov/solar-system/planet-x
* Batygin and Brown, Evidence for a distant giant planet in the Solar System, AJ 151, 22.
* AllWISE Source Catalog at IRSA, TAP table allwise_p3as_psd.
* Liu, Ting and Zhou, Isolation Forest. Breunig, Kriegel, Ng and Sander, LOF. Rousseeuw and Van Driessen, a fast algorithm for the minimum covariance determinant estimator. Pedregosa et al., Scikit learn: Machine Learning in Python, JMLR 12.
* Guo, Pleiss, Sun and Weinberger, On calibration of modern neural networks (temperature scaling, expected calibration error). Brier, Verification of forecasts expressed in terms of probability.
* Cohen, A coefficient of agreement for nominal scales (citizen lab).
* Ledoit and Wolf, a well conditioned estimator for large dimensional covariance matrices (distance from the training set).
* Fontsource package of EB Garamond (SIL Open Font License).

## Methods

* Wilson score interval for a proportion.
* Split conformal quantile for the alarm level.
* Bayesian information criterion for the choice of the motion model.
