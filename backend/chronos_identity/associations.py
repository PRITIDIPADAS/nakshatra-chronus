"""Proper-motion-aware positional associations with an explicit no-match option.

The resulting probabilities are conditional on the supplied positional errors,
prior match probability, catalogue density and search radius.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import math
from chronos_addons.catalogs import angular_separation_arcsec

def _propagate(row: Mapping[str, Any], target_epoch: float):
    ra = float(row["ra"])
    dec = float(row["dec"])
    epoch = float(row.get("epoch_year", target_epoch))
    dt = target_epoch - epoch
    pmra = float(row.get("pmra_cosdec_masyr", 0.0))
    pmdec = float(row.get("pmdec_masyr", 0.0))
    cos_dec = math.cos(math.radians(dec))
    if abs(cos_dec) < 1e-6 and abs(pmra) > 0:
        raise ValueError("cannot propagate RA proper motion close to the celestial pole with this approximation")
    ra2 = (ra + (pmra * dt / 3_600_000.0) / cos_dec) % 360.0
    dec2 = dec + pmdec * dt / 3_600_000.0
    if not -90 <= dec2 <= 90:
        raise ValueError("proper-motion propagation left the valid declination range")
    return ra2, dec2, {"epoch_from": epoch, "epoch_to": target_epoch, "pmra_cosdec_masyr": pmra, "pmdec_masyr": pmdec}

def probabilistic_associations(candidate: Mapping[str, Any], catalogue_rows: Sequence[Mapping[str, Any]], *,
                                search_radius_arcsec: float = 10.0,
                                background_density_per_arcsec2: float = 0.001,
                                prior_match_probability: float = 0.9,
                                minimum_secure_probability: float = 0.8) -> dict[str, Any]:
    required = ("ra", "dec", "epoch_year")
    if any(k not in candidate for k in required):
        raise ValueError("candidate requires ra, dec and epoch_year")
    if search_radius_arcsec <= 0 or background_density_per_arcsec2 <= 0:
        raise ValueError("search radius and background density must be positive")
    if not 0 < prior_match_probability < 1 or not 0 < minimum_secure_probability < 1:
        raise ValueError("probabilities must be strictly between zero and one")
    cand_ra, cand_dec = float(candidate["ra"]), float(candidate["dec"])
    cand_epoch = float(candidate["epoch_year"])
    cand_sigma = float(candidate.get("position_sigma_arcsec", 0.5))
    if cand_sigma <= 0:
        raise ValueError("candidate position uncertainty must be positive")
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
        motion_sigma = math.hypot(pmra_err, pmdec_err) * abs(cand_epoch - source_epoch) / 1000.0
        combined = math.sqrt(cand_sigma ** 2 + source_sigma ** 2 + motion_sigma ** 2)
        if combined <= 0 or not math.isfinite(combined):
            continue
        density = math.exp(-0.5 * (separation / combined) ** 2) / (2.0 * math.pi * combined ** 2)
        likelihood_ratio = prior_odds * density / background_density_per_arcsec2
        ranked.append({
            "catalogue_index": index,
            "source_id": source.get("source_id", source.get("id", str(index))),
            "separation_arcsec": separation,
            "combined_sigma_arcsec": combined,
            "likelihood_ratio": likelihood_ratio,
            "propagated_position": {"ra_deg": ra, "dec_deg": dec},
            "proper_motion": motion,
            "catalogue_row": dict(source),
        })
    denominator = 1.0 + sum(x["likelihood_ratio"] for x in ranked)
    for item in ranked:
        item["association_probability"] = item["likelihood_ratio"] / denominator
    ranked.sort(key=lambda x: x["association_probability"], reverse=True)
    p_none = 1.0 / denominator
    top = ranked[0]["association_probability"] if ranked else 0.0
    runner = ranked[1]["association_probability"] if len(ranked) > 1 else 0.0
    ambiguous = top < minimum_secure_probability or (len(ranked) > 1 and top - runner < 0.15)
    return {
        "candidate_id": candidate.get("candidate_id"),
        "status": "ambiguous" if ambiguous and ranked else ("no_supported_counterpart" if not ranked else "probable_counterpart"),
        "matches": ranked,
        "no_counterpart_probability": p_none,
        "search_radius_arcsec": search_radius_arcsec,
        "assumptions": {
            "prior_match_probability": prior_match_probability,
            "background_density_per_arcsec2": background_density_per_arcsec2,
            "minimum_secure_probability": minimum_secure_probability,
            "proper_motion_convention": "pmra_cosdec_masyr is mu_alpha*cos(dec); first-order tangent-plane propagation",
        },
        "limitations": [
            "Probabilities are conditional on the supplied prior, local background density and uncertainty model.",
            "Parallax, binary motion, acceleration, source colours, crowding-dependent completeness and catalogue selection are not modelled.",
            "A high positional association probability is not proof of a shared physical source.",
        ],
    }
