# CHRONOS 5.0 Sessions 12–16 implementation notes

**Scope:** calibrated spectrotemporal reconstruction, resolution-aware feature measurements, epoch-aware counterpart association, candidate-specific follow-up ranking, and reproducible investigation export.

**Status:** software implementation on the `chronos-5-causal-sky-twin` branch. The software tests use synthetic fixtures. This document does not claim a completed real-data calibration, a molecular identification, a confirmed source identity, a validated telescope visibility calculation, or an independently reproduced astronomical result.

## Implementation status

| Session | Software implemented | Still required for scientific acceptance |
|---|---|---|
| 12 | Local F(lambda,t) generalized least-squares smoother, full measurement covariance input, shared multiplicative calibration covariance, native source indices, linear coefficients, uncertainty components and missing-cell retention | Exposure-specific covariance from calibration data, real source epochs, validated correlated systematics and independent reproduction |
| 13 | Equivalent width with linear continuum uncertainty, LSF FWHM or resolving-power diagnostics, native sampling per resolution element, source URI/hash record, possible-blend interval screen and per-epoch reports | Verified LSF product for the same detector/release, actual LSF convolution or deblending, resolution-matched real spectra and independent feature review |
| 14 | Proper-motion propagation plus differential annual parallax from barycentric Earth positions, parallax uncertainty contribution, local source-density likelihood ratio, alternatives and no-match probability | Real catalogue astrometry and covariance, radial velocity/binary acceleration where relevant, survey selection/epoch compatibility and independent validation |
| 15 | Expected information gain for supplied forecasts, verified/unverified feasibility status, exact external source and timestamp, optional visibility window and ranking sensitivity under alternative priors | Actual model forecasts and a verified external visibility/availability calculator for the relevant telescope, array or archive |
| 16 | ZIP investigation export, evidence graph, analysis, environment, code commit, reproduction command, exact source URIs/checksums, optional source bytes, member-level integrity manifest and external ZIP checksum | Second-person reproduction from the original archive inputs and independent calibration; SHA-256 remains an integrity check, not proof of authorship or truth |

---

## Session 12 — Spectrotemporal reconstruction and covariance

The reconstruction function is in `backend/chronos_spectrotemporal/reconstruction.py`.

For each supported grid cell, the local Gaussian kernel is combined with the supplied covariance in a generalized least-squares local-constant estimator. With diagonal covariance, the weights reduce to the original kernel divided by measurement variance.

Two uncertainty components are now returned:

- `sigma_measurement`: propagated supplied statistical covariance.
- `sigma_shared_calibration`: propagated shared calibration-group systematic.
- `sigma_total`: quadrature result from the full covariance used by the estimator.

The optional `measurement_covariance` is aligned with the original input sample order. The covariance is subset only after invalid/masked observations are removed. The selected matrix must be symmetric, positive definite and have a diagonal consistent with the row-level sigma values.

The optional `shared_calibration_fractional_sigma` models one fully correlated multiplicative offset within the selected calibration group:

`C_cal = outer(f * flux, f * flux)`

This is a transparent rank-one approximation, not a substitute for a measured instrument covariance. The response includes covariance matrix digests, row/source ordering and the linear coefficient of each input measurement in every reconstructed cell. It preserves unsupported cells as missing; there is no extrapolation outside the observed wavelength/time envelope.

API: `POST /api/v5/spectrotemporal/reconstruct`.

The response's `linear_weights` make each grid estimate traceable to the rows used. The source measurement and covariance records supplied to the call must still be retained by the investigator; the digest alone cannot reconstruct a missing matrix.

## Session 13 — Spectral feature evolution and resolution

The equivalent-width measurement is in `backend/chronos_addons/molecular.py`; the epoch tracker is in `backend/chronos_spectrotemporal/feature_evolution.py`.

A resolution record may supply either:

- `lsf_fwhm_um`, or
- `resolving_power`, from which the FWHM is calculated at the feature interval centre.

If both are supplied, they must agree within the configured 25% consistency tolerance. The report includes median native wavelength spacing, samples per FWHM, resolution elements across the predeclared feature interval, and whether the source URI and 64-character digest were recorded.

Potential neighboring feature intervals can be supplied. Intervals within half an LSF FWHM of the declared feature are marked as possible blends. This is a screening flag only. The implementation does not convolve a laboratory spectrum with the full LSF, fit blended components or deblend observations. An absent resolution record remains explicitly `not_supplied`; it is not silently assumed.

Every EW remains tied to the user-supplied feature interval and continuum sidebands. The method does not identify molecules.

API: `POST /api/v5/spectrotemporal/feature-evolution`.

## Session 14 — Probabilistic source identity

The association module is `backend/chronos_identity/associations.py`.

Catalogue coordinates are first propagated using the declared proper-motion convention. When a parallax measurement is supplied, a differential annual-parallax offset is computed from the barycentric Earth positions at the catalogue reference epoch and candidate epoch. The report stores the parallax value/error, epoch baseline, projected east/north shifts and parallax uncertainty contribution.

The likelihood ratio also retains the supplied position uncertainties, local background density, prior match probability, survey epoch, bandpass, wavelength range and angular resolution where the catalogue provides them. Multiple counterparts and a no-counterpart probability remain visible. The result label is a positional association status, not proof of shared physical identity.

The astrometric propagation is a first-order tangent-plane approximation. It does not model radial velocity, binary motion, acceleration, crowding selection or correlated catalogue systematics. Parallax is applied only when supplied; it is not inferred from positional similarity.

API: `POST /api/v5/identity/associate`.

## Session 15 — Candidate-specific next-best-observation planner

The planner is `backend/chronos_addons/planner.py`.

Each forecast candidate may include time, wavelength, detector, array configuration and measurement type. Its information gain is computed from the supplied hypothesis-specific means and uncertainty values. The response records the predictive uncertainty, measurement uncertainty, prior entropy, expected posterior entropy and information gain.

A feasibility record is considered verified only when it has:
- an explicit `status: verified` and boolean `feasible`,
- an exact HTTPS `source_uri`,
- a timezone-aware ISO-8601 `checked_utc`,
- and, when a window is supplied, both timezone-aware start and end with end later than start.

Without this record, a measurement can still be information-ranked, but the response is labelled `forecast_ranked_feasibility_unverified`. No visibility window is invented. Alternative prior sets can be supplied to show how the ranking changes.

API: `POST /api/v5/observations/plan`.

The planner does not schedule or command a telescope. Its information gain is only as sound as the supplied model forecasts and measurement error.

## Session 16 — Evidence graph and reproducible investigation package

The package helper is `backend/chronos_causal/investigation_package.py`.

The ZIP contains:
- candidate and processing metadata,
- the analysis output,
- the evidence graph,
- exact source-product URI, product family, release, detector, archive ID, SHA-256 and byte count,
- software environment and code commit where provided,
- a copy-ready reproduction command,
- failed or unresolved checks,
- a package integrity manifest containing SHA-256 and byte count for every member.

When source bytes are requested, each local source file is re-hashed against the provided manifest before it is embedded. Metadata-only packages retain exact source URIs and hashes but state that the original bytes are external. The HTTP route accepts metadata only; local bytes must be embedded from a local workflow, not by supplying arbitrary server paths.

The verifier checks the external ZIP checksum sidecar, expected member set, every member size and every member digest. This proves byte consistency of the exported package, not authorship, source authenticity, calibration compatibility or scientific truth.

API: `POST /api/v5/evidence/package/export`.

Example local workflow:

```python
from chronos_causal.investigation_package import (
    create_investigation_package,
    verify_investigation_package,
)

created = create_investigation_package(
    "investigation.zip",
    candidate_id="candidate-001",
    analysis=analysis_report,
    evidence_graph=evidence_graph,
    source_files=source_manifest_rows,
    reproduction_command="python reproduce.py --manifest archive_manifest.json",
    code_commit="the exact checked-out commit SHA",
    processing_configuration=processing_configuration,
    failed_checks=failed_checks,
    include_source_bytes=True,
)
verification = verify_investigation_package("investigation.zip")
assert verification["valid"]
```

The example is a usage pattern, not a populated real-data run.

## Current evidence boundary

- Sessions 12–16 have code paths and synthetic/software tests in this branch.
- No real SPHEREx source/calibration set is declared compatible by this document.
- No real-data F(lambda,t) result, feature identification, or counterpart identity is claimed.
- No real telescope visibility or archive availability has been established here.
- No independent reproduction of a real observation package has been completed.

The full empirical acceptance gates remain open until the exact science MEFs and matching calibration products are retrieved, audited, processed and independently reproduced.
