#!/usr/bin/env python3
"""Named SPHEREx Level-2 flag bits and explicit mask policies.

Bit positions are taken from Table 10 of the SPHEREx Explanatory Supplement.
The recommended photometry/background subsets follow its flag-usage section.
DICHROIC is offered as an additional conservative photometry exclusion because
its description says these pixels are not useful for photometry.
"""
from __future__ import annotations

FLAG_BITS = {
    "TRANSIENT": 0,
    "OVERFLOW": 1,
    "SUR_ERROR": 2,
    "NONFUNC": 6,
    "DICHROIC": 7,
    "MISSING_DATA": 9,
    "HOT": 10,
    "COLD": 11,
    "FULLSAMPLE": 12,
    "PHANMISS": 14,
    "NONLINEAR": 15,
    "PERSIST": 17,
    "OUTLIER": 19,
    "SOURCE": 21,
}

BACKGROUND_ESTIMATION_FLAGS = (
    "OVERFLOW", "SUR_ERROR", "NONFUNC", "MISSING_DATA", "HOT", "COLD",
    "NONLINEAR", "PERSIST", "OUTLIER", "SOURCE", "TRANSIENT",
)
PHOTOMETRY_FLAGS = (
    "SUR_ERROR", "NONFUNC", "MISSING_DATA", "HOT", "COLD", "NONLINEAR", "PERSIST",
)
CONSERVATIVE_PHOTOMETRY_FLAGS = PHOTOMETRY_FLAGS + ("DICHROIC",)

POLICIES = {
    "none": (),
    "background": BACKGROUND_ESTIMATION_FLAGS,
    "photometry": PHOTOMETRY_FLAGS,
    "conservative-photometry": CONSERVATIVE_PHOTOMETRY_FLAGS,
}


def flag_mask(names: tuple[str, ...] | list[str]) -> int:
    """Return the integer bitmask for a list of flag names."""
    mask = 0
    for name in names:
        key = str(name).upper()
        if key not in FLAG_BITS:
            raise ValueError(f"Unknown SPHEREx flag {name!r}; known flags: {sorted(FLAG_BITS)}")
        mask |= 1 << FLAG_BITS[key]
    return mask


def policy_mask(policy: str) -> tuple[int, tuple[str, ...]]:
    """Return (bitmask, flag names) for a named mask policy."""
    if policy not in POLICIES:
        raise ValueError(f"Unknown flag policy {policy!r}; choose {sorted(POLICIES)}")
    names = POLICIES[policy]
    return flag_mask(names), names
