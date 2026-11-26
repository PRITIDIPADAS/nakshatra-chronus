# Orion A four-epoch SPHEREx source-photometry pilot

**Snapshot:** 26 November 2026  
**Branch:** `chronos-5-causal-sky-twin`  
**Status at snapshot:** workflow #11 / run 45751641495 is processing the four native DR1 D2 products; no accepted multi-epoch series is claimed yet.

## Purpose and scope

This is a narrowly scoped feasibility test of native, source-level SPHEREx photometry. It asks whether one SPLICES catalogue candidate can be measured consistently in four preselected DR1 D2 Level-2 exposures using the delivered science and variance data, exact CWAVE/CBAND wavelength calibration, a detector-matched solid-angle map, and the native ePSF.

It is not a population sample, YSO discovery, variability claim, blind benchmark, or CHRONOS performance comparison. The catalogue classification fields are preserved as supplied but are **not independent YSO confirmation**.

## Frozen source record

| Field | Value |
|---|---|
| SPLICES source ID | `1914414087643594754` |
| Designation | `J053131.05-060841.7` |
| ICRS RA / Dec | 82.879379° / −6.144907° |
| Region | Orion A |
| Published YSO label | `yso_pub=7.0` |
| Harmonised class | `YSO_D` |
| ML class / probability field | `Class II YSO` / 0.8856 |
| Classification status | Catalogue metadata only; not independently confirmed |

Selection provenance is the SPLICES/DR1/QR3 reconnaissance artifact 15060892188 from [workflow run 45694565745](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45694565745). The source-to-product association was made using spherical gnomonic point-in-polygon tests against IRSA SIAv2 `s_region` metadata. That operation establishes only that the catalogue coordinate falls within returned exposure footprints; it does not establish usable flux, spectrum quality, temporal cadence or identity.

The one-source catalogue row is preserved separately in [`data/spherex_orion_source_catalogue_snapshot.json`](../data/spherex_orion_source_catalogue_snapshot.json). The frozen product roster and exact selection metadata are in [`data/spherex_source_timeseries_pilot.orion_candidate.json`](../data/spherex_source_timeseries_pilot.orion_candidate.json).

## Frozen native exposure roster

All four rows are DR1, detector D2, bandpass SPHEREx-D2 Level-2 science-image products. They are distinct observation IDs sorted by MJD and span 187.041154 days.

| Observation ID | MJD start | MJD end | MJD midpoint | Exact native URI |
|---|---:|---:|---:|---|
| `2025W36_2B_0638_1` | 60925.595112 | 60925.596444 | 60925.595778 | [Level-2 MEF](https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W36_2B/l2b-v27-2026-234/2/level2_2025W36_2B_0638_1D2_spx_l2b-v27-2026-234.fits) |
| `2025W37_2A_0601_1` | 60932.183896 | 60932.185228 | 60932.184562 | [Level-2 MEF](https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W37_2A/l2b-v27-2026-236/2/level2_2025W37_2A_0601_1D2_spx_l2b-v27-2026-236.fits) |
| `2026W10_1A_0337_2` | 61102.726292 | 61102.727624 | 61102.726958 | [Level-2 MEF](https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2026W10_1A/l2b-v27-2026-229/2/level2_2026W10_1A_0337_2D2_spx_l2b-v27-2026-229.fits) |
| `2026W11_2A_0253_1` | 61112.636266 | 61112.637598 | 61112.636932 | [Level-2 MEF](https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2026W11_2A/l2b-v27-2026-234/2/level2_2026W11_2A_0253_1D2_spx_l2b-v27-2026-234.fits) |

The roster is a fixed, non-random feasibility subset selected from metadata footprint matches. It is not a completeness-selected or representative YSO sample. No product substitution or flux-based epoch selection is allowed.

## Per-epoch validation and measurement protocol

For each frozen URI the workflow:

1. Retrieves the exact native Level-2 MEF and verifies the returned URI, observation ID, detector and release against the frozen manifest.
2. Runs the native MEF structure audit and the exposure-specific calibration-compatibility audit. The spectral-WCS and absolute-gain provenance relations must be exact; the solid-angle map is explicitly supplemental where the archive has no direct provenance foreign key.
3. Checks native FITS `MJD-OBS` and `EXPTIME` against the SIAv2 start/end/midpoint bounds. The maximum allowed discrepancy is five seconds.
4. Samples the source position using the exposure's celestial WCS, reads the matching native CWAVE/CBAND values and solid-angle map, extracts the position-specific ePSF stamp, and performs the local PSF-flux fit.
5. Uses the delivered Level-2 VARIANCE as a diagonal covariance for the flux fit. It does not multiply the science IMAGE by the absolute-gain map a second time, does not add another source-Poisson term, and does not use the pending gain-to-electron conversion for this measurement.
6. Records each failed, incompatible or review-required epoch without replacing it or imputing a flux. The exact science, spectral-WCS, solid-angle, native audit, catalogue snapshot and ePSF bytes are bound by hashes.

## Temporal comparability gate

Four visits alone are not enough to call a temporal flux series. Native CWAVE centres and CBAND widths are used to form passband intervals. At least one repeated wavelength cluster must have a common interval spanning at least **50% of the narrowest native band**, across at least four distinct observation/MJD epochs. The threshold is frozen in the pilot manifest.

If the four visits sample disjoint or insufficiently overlapping native wavelength intervals, the output remains a set of source-photometry measurements and is **not** called a temporal series. This avoids confusing wavelength-dependent source structure with time variability.

## Known limitations

- The catalogue source identity and its YSO class are not independently confirmed.
- The sample contains one source and four manually frozen exposures; it is not population representative.
- The source fit is local ePSF photometry at the mapped source position; crowded-source deblending and extended-source structure are not modelled.
- Flux covariance uses the delivered variance as diagonal; correlated detector/background noise and PSF systematic covariance are not included.
- The absolute-gain-to-electron conversion remains pending independent instrument review for the separate source-Poisson injection work.
- Even a verified four-epoch, common-passband series would be a measurement feasibility result, not a variability discovery or population inference.

## Reproducibility

- Frozen roster: [`data/spherex_source_timeseries_pilot.orion_candidate.json`](../data/spherex_source_timeseries_pilot.orion_candidate.json)
- Source catalogue snapshot: [`data/spherex_orion_source_catalogue_snapshot.json`](../data/spherex_orion_source_catalogue_snapshot.json)
- Runner: [`research_discovery/spherex/run_source_timeseries_pilot.py`](../research_discovery/spherex/run_source_timeseries_pilot.py)
- Workflow: [`.github/workflows/spherex-source-timeseries-pilot.yml`](../.github/workflows/spherex-source-timeseries-pilot.yml)
- Current workflow at snapshot time: [#11 / run 45751641495](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45751641495)

The run's uploaded per-epoch audit records and `pilot_summary.json` must be inspected before its status can be updated. No source fluxes, successful multi-epoch series or scientific discovery are asserted in this document.
