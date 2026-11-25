"""Fail-closed admission checks for scientific wavelength measurements.

Real CHRONOS measurements must be traced to CWAVE/CBAND from a checksum-linked,
compatible Spectral WCS calibration and its native-MEF audit. WCS-WAVE is
display-grade and is never an accepted science wavelength source. Synthetic
challenge fixtures are admitted only when explicitly labelled as synthetic.
"""
from __future__ import annotations

import math
import re
from typing import Any, Mapping

SCIENCE_SOURCE = "CWAVE/CBAND"
SYNTHETIC_SOURCE = "synthetic_fixture"
UNITS = {"um", "micron", "microns", "micrometer", "micrometers"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _require_sha256(value: Any, field: str, prefix: str) -> None:
    if not isinstance(value, str) or not SHA256.fullmatch(value.lower()):
        raise ValueError(prefix + f"wavelength provenance requires a valid {field}")


def _validate_common(row: Mapping[str, Any], *, index: int | None = None) -> None:
    prefix = f"observation {index}: " if index is not None else ""
    source = str(row.get("wavelength_source", "")).strip()
    unit = str(row.get("wavelength_unit", "")).strip().lower()
    group = str(row.get("calibration_group", "")).strip()

    if unit not in UNITS:
        raise ValueError(prefix + "wavelength_unit must explicitly declare microns")
    if row.get("wavelength_validated") is not True:
        raise ValueError(prefix + "wavelength is not marked as validated against its source")
    if not group:
        raise ValueError(prefix + "calibration_group is required")

    if source == SYNTHETIC_SOURCE:
        if row.get("synthetic_fixture") is not True or not group.startswith("SYNTHETIC"):
            raise ValueError(prefix + "synthetic wavelengths require an explicit SYNTHETIC fixture label and group")
        return

    if source != SCIENCE_SOURCE:
        raise ValueError(prefix + f"science wavelength source must be CWAVE/CBAND; rejected {source or 'missing source'}")

    evidence = row.get("wavelength_provenance")
    if not isinstance(evidence, Mapping):
        raise ValueError(prefix + "CWAVE/CBAND measurements require wavelength_provenance")
    if evidence.get("decision") != "compatible":
        raise ValueError(prefix + "the science/calibration compatibility decision must be compatible")
    if str(evidence.get("compatibility_group", "")) != group:
        raise ValueError(prefix + "wavelength provenance calibration_group does not match the measurement")
    for key in ("science_sha256", "calibration_sha256", "native_mef_audit_sha256",
                "solid_angle_sha256"):
        _require_sha256(evidence.get(key), key, prefix)
    for key in ("science_uri", "calibration_uri", "solid_angle_uri"):
        value = evidence.get(key)
        if not isinstance(value, str) or not value.startswith("https://"):
            raise ValueError(prefix + f"wavelength provenance requires an exact HTTPS {key}")
    if evidence.get("pixel_valid") is not True:
        raise ValueError(prefix + "this pixel is invalid in CWAVE/CBAND or not confirmed by the audit")


def validate_science_wavelength(row: Mapping[str, Any], *, index: int | None = None) -> None:
    """Validate one scalar wavelength observation before causal inference/reconstruction."""
    prefix = f"observation {index}: " if index is not None else ""
    _validate_common(row, index=index)
    try:
        wavelength = float(row.get("wavelength_um"))
    except (TypeError, ValueError):
        raise ValueError(prefix + "wavelength_um must be numeric") from None
    if not math.isfinite(wavelength) or not (wavelength > 0):
        raise ValueError(prefix + "wavelength_um must be finite and positive")


def validate_spectral_epoch(epoch: Mapping[str, Any], *, index: int | None = None) -> None:
    """Validate provenance and per-pixel masks for a complete epoch spectrum."""
    prefix = f"epoch {index}: " if index is not None else ""
    _validate_common(epoch, index=index)
    try:
        wavelength = list(epoch["wavelength_um"])
        flux = list(epoch["flux"])
        mjd = float(epoch["mjd"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(prefix + "finite mjd, wavelength_um and flux arrays are required") from None
    if not math.isfinite(mjd):
        raise ValueError(prefix + "mjd must be finite")
    if not wavelength or len(wavelength) != len(flux):
        raise ValueError(prefix + "wavelength and flux arrays must be non-empty and equal length")
    valid = epoch.get("valid")
    if valid is None:
        valid = [True] * len(wavelength)
    if len(valid) != len(wavelength):
        raise ValueError(prefix + "valid mask must align with wavelength and flux arrays")
    sigma = epoch.get("sigma")
    if sigma is not None:
        sigma = list(sigma)
        if len(sigma) != len(wavelength):
            raise ValueError(prefix + "sigma must align with wavelength and flux arrays")
    for position, (value, flux_value, is_valid) in enumerate(zip(wavelength, flux, valid)):
        if not is_valid:
            continue
        try:
            number = float(value)
            flux_number = float(flux_value)
        except (TypeError, ValueError):
            raise ValueError(prefix + f"valid wavelength and flux pixel {position} must be numeric") from None
        if not math.isfinite(number) or not (number > 0):
            raise ValueError(prefix + f"valid wavelength pixel {position} must be finite and positive")
        if not math.isfinite(flux_number):
            raise ValueError(prefix + f"valid flux pixel {position} must be finite")
        if sigma is not None:
            try:
                sigma_number = float(sigma[position])
            except (TypeError, ValueError):
                raise ValueError(prefix + f"valid sigma pixel {position} must be numeric") from None
            if not math.isfinite(sigma_number) or sigma_number <= 0:
                raise ValueError(prefix + f"valid sigma pixel {position} must be finite and positive")
