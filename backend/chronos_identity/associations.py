"""Epoch-aware probabilistic source associations with optional annual parallax.

Probabilities remain conditional on the supplied catalogue, uncertainties,
local source density and search policy. Association is not physical identity.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import math

from chronos_addons.catalogs import angular_separation_arcsec


def _earth_position_au(epoch_year: float):
    """Return a barycentric Earth position in ICRS AU for an epoch."""
    try:
        from astropy.coordinates import get_body_barycentric
        from astropy.time import Time
    except ImportError as exc:
        raise RuntimeError("Astropy is required for parallax propagation") from exc
    position = get_body_barycentric(
        "earth", Time(float(epoch_year), format="jyear", scale="tdb")
    )
    return position.xyz.to_value("au")


def _parallax_shift_mas(ra_deg: float, dec_deg: float, parallax_mas: float,
                        epoch_from: float, epoch_to: float):
    """Differential annual parallax shift between two catalogue epochs."""
    import numpy as np

    r0 = _earth_position_au(epoch_from)
    r1 = _earth_position_au(epoch_to)
    baseline = np.asarray(r1, dtype=float) - np.asarray(r0, dtype=float)
    alpha = math.radians(ra_deg)
    delta = math.radians(dec_deg)
    east = np.asarray([-math.sin(alpha), math.cos(alpha), 0.0])
    north = np.asarray([
        -math.sin(delta) * math.cos(alpha),
        -math.sin(delta) * math.sin(alpha),
        math.cos(delta),
    ])
    east_shift = -float(parallax_mas) * float(np.dot(baseline, east))
    north_shift = -float(parallax_mas) * float(np.dot(baseline, north))
    return east_shift, north_shift, float(np.linalg.norm(baseline))


def _propagate(row: Mapping[str, Any], target_epoch: float):
    ra = float(row["ra"])
    dec = float(row["dec"])
    if not math.isfinite(ra) or not math.isfinite(dec) or not -90 <= dec <= 90:
        raise ValueError("catalogue coordinates must be finite with declination in [-90, 90]")
    epoch = float(row.get("epoch_year", target_epoch))
    if not math.isfinite(epoch) or not math.isfinite(float(target_epoch)):
        raise ValueError("catalogue and target epochs must be finite")
    dt = float(target_epoch) - epoch
    pmra = float(row.get("pmra_cosdec_masyr", 0.0))
    pmdec = float(row.get("pmdec_masyr", 0.0))
    if not math.isfinite(pmra) or not math.isfinite(pmdec):
        raise ValueError("proper motions must be finite")
    cos_dec = math.cos(math.radians(dec))
    if abs(cos_dec) < 1e-6 and abs(pmra) > 0:
        raise ValueError("cannot propagate RA proper motion close to the celestial pole with this approximation")
    ra2 = (ra + (pmra * dt / 3_600_000.0) / cos_dec) % 360.0
    dec2 = dec + pmdec * dt / 3_600_000.0
    if not -90 <= dec2 <= 90:
        raise ValueError("proper-motion propagation left the valid declination range")

    parallax_was_supplied = row.get("parallax_mas") is not None
    parallax = row.get("parallax_mas")
    parallax_error = row.get("parallax_error_mas")
    if parallax is None:
        parallax = 0.0
    parallax = float(parallax)
    if not math.isfinite(parallax):
        raise ValueError("parallax_mas must be finite")
    if parallax_error is None:
        parallax_error = 0.0
    parallax_error = float(parallax_error)
    if not math.isfinite(parallax_error) or parallax_error < 0:
        raise ValueError("parallax_error_mas must be finite and non-negative")

    parallax_applied = parallax_was_supplied and dt != 0.0
    if parallax_applied:
        east_shift, north_shift, baseline_norm = _parallax_shift_mas(
            ra, dec, parallax, epoch, float(target_epoch)
        )
        cos_dec2 = math.cos(math.radians(dec2))
        if abs(cos_dec2) < 1e-8 and abs(east_shift) > 0:
            raise ValueError("parallax RA shift is singular close to the celestial pole")
        ra2 = (ra2 + east_shift / (3_600_000.0 * cos_dec2)) % 360.0
        dec2 += north_shift / 3_600_000.0
        if not -90 <= dec2 <= 90:
            raise ValueError("parallax propagation left the valid declination range")
    else:
        east_shift = 0.0
        north_shift = 0.0
        baseline_norm = 0.0

    return ra2, dec2, {
        "epoch_from": epoch,
        "epoch_to": float(target_epoch),
        "pmra_cosdec_masyr": pmra,
        "pmdec_masyr": pmdec,
        "proper_motion_interval_years": dt,
        "parallax_mas": parallax,
        "parallax_error_mas": parallax_error,
        "parallax_applied": bool(parallax_applied),
        "parallax_baseline_au": baseline_norm,
        "parallax_shift_east_mas": east_shift,
        "parallax_shift_north_mas": north_shift,
    }


def probabilistic_associations(
    candidate: Mapping[str, Any],
    catalogue_rows: Sequence[Mapping[str, Any]],
    *,
    search_radius_arcsec: float = 10.0,
    background_density_per_arcsec2: float = 0.001,
    prior_match_probability: float = 0.9,
    minimum_secure_probability: float = 0.8,
) -> dict[str, Any]:
    required = ("ra", "dec", "epoch_year")
    if any(key not in candidate for key in required):
        raise ValueError("candidate requires ra, dec and epoch_year")
    if (
        not math.isfinite(search_radius_arcsec) or search_radius_arcsec <= 0
        or not math.isfinite(background_density_per_arcsec2)
        or background_density_per_arcsec2 <= 0
    ):
        raise ValueError("search radius and background density must be finite and positive")
    if (
        not 0 < prior_match_probability < 1
        or not 0 < minimum_secure_probability < 1
    ):
        raise ValueError("probabilities must be strictly between zero and one")

    cand_ra, cand_dec = float(candidate["ra"]), float(candidate["dec"])
    cand_epoch = float(candidate["epoch_year"])
    if not math.isfinite(cand_ra) or not math.isfinite(cand_dec) or not -90 <= cand_dec <= 90:
        raise ValueError("candidate coordinates must be finite with declination in [-90, 90]")
    cand_sigma = float(candidate.get("position_sigma_arcsec", 0.5))
    if not math.isfinite(cand_sigma) or cand_sigma <= 0:
        raise ValueError("candidate position uncertainty must be finite and positive")

    ranked = []
    prior_odds = prior_match_probability / (1.0 - prior_match_probability)
    for index, source in enumerate(catalogue_rows):
        try:
            ra, dec, motion = _propagate(source, cand_epoch)
            separation = angular_separation_arcsec(cand_ra, cand_dec, ra, dec)
        except (KeyError, TypeError, ValueError):
            continue
        if separation > search_radius_arcsec:
            continue

        source_sigma = float(source.get("position_sigma_arcsec", 0.5))
        pmra_err = float(source.get("pmra_error_masyr", 0.0))
        pmdec_err = float(source.get("pmdec_error_masyr", 0.0))
        source_epoch = float(source.get("epoch_year", cand_epoch))
        parallax_err = float(source.get("parallax_error_mas", 0.0) or 0.0)
        if (
            not math.isfinite(source_sigma) or source_sigma <= 0
            or not math.isfinite(pmra_err) or pmra_err < 0
            or not math.isfinite(pmdec_err) or pmdec_err < 0
            or not math.isfinite(parallax_err) or parallax_err < 0
        ):
            continue
        motion_sigma_arcsec = math.hypot(pmra_err, pmdec_err) * abs(cand_epoch - source_epoch) / 1000.0
        parallax_sigma_arcsec = (
            parallax_err * motion["parallax_baseline_au"] / 1000.0
            if motion["parallax_applied"] else 0.0
        )
        combined = math.sqrt(
            cand_sigma ** 2 + source_sigma ** 2
            + motion_sigma_arcsec ** 2 + parallax_sigma_arcsec ** 2
        )
        if combined <= 0 or not math.isfinite(combined):
            continue

        density = math.exp(-0.5 * (separation / combined) ** 2) / (2.0 * math.pi * combined ** 2)
        likelihood_ratio = prior_odds * density / background_density_per_arcsec2
        ranked.append({
            "catalogue_index": index,
            "source_id": source.get("source_id", source.get("id", str(index))),
            "separation_arcsec": separation,
            "combined_sigma_arcsec": combined,
            "proper_motion_sigma_arcsec": motion_sigma_arcsec,
            "parallax_sigma_arcsec": parallax_sigma_arcsec,
            "likelihood_ratio": likelihood_ratio,
            "propagated_position": {"ra_deg": ra, "dec_deg": dec},
            "proper_motion_and_parallax": motion,
            "survey_metadata": {
                "survey": source.get("survey"),
                "bandpass": source.get("bandpass"),
                "wavelength_range_um": source.get("wavelength_range_um"),
                "angular_resolution_arcsec": source.get("angular_resolution_arcsec"),
                "reference_uri": source.get("reference_uri"),
                "observation_epoch": source.get("epoch_year"),
            },
            "catalogue_row": dict(source),
        })

    denominator = 1.0 + sum(item["likelihood_ratio"] for item in ranked)
    for item in ranked:
        item["association_probability"] = item["likelihood_ratio"] / denominator
    ranked.sort(key=lambda item: item["association_probability"], reverse=True)
    p_none = 1.0 / denominator
    top = ranked[0]["association_probability"] if ranked else 0.0
    runner_up = ranked[1]["association_probability"] if len(ranked) > 1 else 0.0
    ambiguous = top < minimum_secure_probability or (len(ranked) > 1 and top - runner_up < 0.15)

    return {
        "candidate_id": candidate.get("candidate_id"),
        "status": "ambiguous" if ambiguous and ranked else (
            "no_supported_counterpart" if not ranked else "probable_counterpart"
        ),
        "matches": ranked,
        "no_counterpart_probability": p_none,
        "search_radius_arcsec": search_radius_arcsec,
        "assumptions": {
            "prior_match_probability": prior_match_probability,
            "background_density_per_arcsec2": background_density_per_arcsec2,
            "minimum_secure_probability": minimum_secure_probability,
            "proper_motion_convention": "pmra_cosdec_masyr is mu_alpha*cos(dec); first-order tangent-plane propagation",
            "parallax_method": "differential barycentric Earth-position projection between catalogue epoch and candidate epoch",
        },
        "limitations": [
            "Probabilities are conditional on the supplied prior, local background density and uncertainty model.",
            "Parallax is applied only when supplied; missing parallax is not inferred.",
            "The parallax propagation uses a first-order tangent-plane approximation and does not model radial velocity, binary motion or acceleration.",
            "Catalogue selection, wavelength-dependent centroid offsets, crowding-dependent completeness and correlated astrometric systematics are not modelled.",
            "A high positional association probability is not proof of a shared physical source.",
        ],
    }
