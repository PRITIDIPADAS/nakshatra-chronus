# Planet X / Planet Nine: what can and cannot be predicted

**Status: posterior sky ensemble is scientifically possible; a validated ephemeris for a discovered Planet Nine is not.**

## Evidence state

- NASA's public Planet X page states that Planet Nine has not been discovered and that its existence remains debated. The original 2016 proposal was based on patterns in distant trans-Neptunian-object orbits, not a direct observation of the planet.
- CaltechDATA hosts *Planet Nine reference population, Version 3.0*, published 5 April 2023. It contains 100,000 **synthetic** orbital-element and physical-property samples drawn from the distributions in Brown & Batygin (2021a), with the ZTF search results, DES constraints and Pan-STARRS search constraints incorporated into the collection. This is a model reference population, not a catalog of observed Planet Nine positions.
- A January 2026 targeted parallax search covered about 98 square degrees near a high-probability region, reached an average Sloan-r sensitivity of about 21.3 mag at 85% confidence and found no credible candidate in that field and magnitude range. This is a meaningful non-detection constraint, not proof that Planet Nine cannot exist.

## Correct CHRONOS output

The defensible product is a model-conditional *candidate-sky probability map* for a specified epoch, posterior population, orbit-element convention and dynamical approximation. It must state:

1. which posterior/reference population was propagated;
2. the exact README-defined orbital columns, units, reference frame, epoch and anomaly convention;
3. how posterior weights were handled and whether any samples were discarded;
4. which solar-system ephemeris supplied Earth's location;
5. what dynamical and astrometric effects were omitted;
6. the date/time scale and the output coordinate frame;
7. the survey footprint, cadence, limiting magnitude and known masks against which detectability is evaluated.

The included `ensemble_ephemeris.py` uses an explicit column map and TDB element epoch. It performs vectorized two-body Kepler propagation, samples Earth from the selected Astropy ephemeris backend and applies iterative per-sample light-time correction. It is a screening tool only. It omits gravitational perturbations from the giant planets on the hypothetical object, the Galactic tide, full relativistic/astrometric corrections, and a full orbit-fitting treatment. It must not be labelled a validated ephemeris.

## Mandatory independent checks

- First inspect and archive the actual CaltechDATA `README.TXT` and CSV. Do not run the propagator until column meanings, units, epoch and coordinate frame are verified from the README.
- Preserve the CaltechDATA record URL, DOI, file hashes and dataset version. The v3 population is from 2023 and cannot be silently treated as the current consensus of all later literature.
- Compare separate published dynamical hypotheses rather than mixing unrelated orbital distributions into one unweighted sample. A posterior generated under one model is conditional on that model.
- Validate the numerical propagator on known minor planets using independently exported JPL Horizons ephemerides over a comparable time span. A successful known-object test validates the numerical implementation only; it does not validate a hypothetical orbit.
- Fold the predicted ensemble through each survey's actual footprint and magnitude-dependent completeness. An orbital-position density by itself is not a detection probability.
- Report null results and model disagreement. A position map should show where the chosen model says to look, not imply that a planet is there.

## Current implementation boundary

The scripts can download and inspect the public CaltechDATA file in a network-enabled environment, propagate a documented sample ensemble and compare exported positions. The data file was not downloaded in this session because the container could not resolve the CaltechDATA host. No Planet Nine prediction from the reference population is therefore reported as a computed scientific result here.

## Primary references

- NASA Science, [Hypothetical Planet X](https://science.nasa.gov/solar-system/planet-x/).
- CaltechDATA, [Planet Nine reference population, Version 3.0](https://data.caltech.edu/records/8fjad-x7y61), DOI: `10.22002/8fjad-x7y61`.
- Socas-Navarro & Trujillo (2026), [A targeted, parallax-based search for Planet Nine](https://doi.org/10.33232/001c.155004), *The Open Journal of Astrophysics* 9.
