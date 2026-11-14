# Published IRAS–AKARI Planet Nine candidate: independent coordinate diagnostic

## Data source and identity

The 2025 paper *A Search for Planet Nine with IRAS and AKARI Data* lists this candidate pair:

| Survey source | RA (ICRS) | Dec (ICRS) |
|---|---:|---:|
| IRAS F02211-4844 | 35.74075° | −48.5125° |
| AKARI-MUSL J0220440-491247 | 35.18379° | −49.2135° |

The paper reports an angular separation of 47.4586 arcminutes. The local script `planet9/published_candidate_diagnostic.py` independently recomputes this from the tabulated coordinates.

## Recomputed geometry

- Great-circle separation: **47.458561 arcmin**.
- Initial position angle: **207.386°**, measured clockwise from north through east.
- Net tangent-plane displacement from the IRAS position to the AKARI position: approximately −1309.874 arcsec east and −2528.420 arcsec north, i.e. westward and southward.
- The IRAS survey observations span 26 June through 1 September 1983; AKARI detections discussed by the paper include two scans on 26 December 2006. Because the IRAS position is not an instantaneous observation with a single epoch, a midpoint epoch is only an illustration.
- Mean angular motion across plausible endpoints of that IRAS interval is approximately **121.162–122.115 arcsec/year**. The midpoint estimate is **121.630 arcsec/year**.

The paper's simple motion scaling (42 arcmin over 23 years for an assumed 700 AU) can be algebraically inverted to an approximate 651–655 AU range for the adopted interval. This number is **not** a distance measurement: no parallax, orbit fit, covariance propagation, or independent dynamical solution is included.

## Why this is not a new detection or ephemeris

The paper itself says that two IRAS/AKARI detections are not enough to determine the candidate's full orbit. It raises uncertainty in the AKARI flux and calls for follow-up observations. The authors refer to nine detections as a target for a robust linked-orbit assessment.

A real Planet Nine ephemeris would require a confirmed object identity, multiple precise astrometric observations, timing and reference-frame metadata, covariance-aware orbit fitting, perturbation modelling, and independent prediction checks against later observations. None of those can be reconstructed from this two-point published pair alone.

## Output

The numerical result is stored in `data/planet9_published_candidate_motion.json`. Re-run with:

```bash
python -m research_discovery.planet9.published_candidate_diagnostic \
  --out research_discovery/data/planet9_published_candidate_motion.json
```

**Conclusion:** this is a reproduced angular-separation diagnostic for a published candidate pair. It is not a Planet Nine discovery, a fitted orbit, a measured heliocentric distance, or a validated ephemeris.

## Reference

DOI: [10.1017/pasa.2025.10024](https://doi.org/10.1017/pasa.2025.10024)
