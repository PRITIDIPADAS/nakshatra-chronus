"""Spectral measurements and conservative SPHEREx DR1 FITS adapters.

Guardrails:
* The All-Sky Cube NHITS extension is a contributor count, not variance.
* All-Sky Cube spectra therefore have no statistical sigma unless a separate,
  validated uncertainty model is supplied.
* For spectral-image science wavelengths, use CWAVE/CBAND from the separate
  Spectral WCS calibration product. WCS-WAVE is a display mapping.
* Missing channels are retained as missing; no interpolation fills gaps.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
import math, os
import numpy as np

EXPECTED_CHANNELS = 102

@dataclass
class Spectrum:
    wavelength_um: np.ndarray
    flux: np.ndarray
    sigma: np.ndarray | None = None
    valid: np.ndarray | None = None
    flags: np.ndarray | None = None
    hits: np.ndarray | None = None
    metadata: dict[str, Any] | None = None

    def normalized(self) -> "Spectrum":
        wave = np.asarray(self.wavelength_um, dtype=float).reshape(-1)
        flux = np.asarray(self.flux, dtype=float).reshape(-1)
        if not wave.size or flux.size != wave.size:
            raise ValueError("wavelength_um and flux must be non-empty arrays of equal length")
        if np.any(~np.isfinite(wave)) or np.any(wave <= 0):
            raise ValueError("wavelengths must be finite and positive")
        order = np.argsort(wave)
        wave, flux = wave[order], flux[order]
        if np.any(np.diff(wave) <= 0):
            raise ValueError("wavelengths must be unique; combine duplicate wavelengths first")
        sigma = None
        if self.sigma is not None:
            sigma = np.asarray(self.sigma, dtype=float).reshape(-1)
            if sigma.size != wave.size:
                raise ValueError("sigma must have the same length as wavelength_um")
            sigma = sigma[order]
            sigma = np.where(np.isfinite(sigma) & (sigma > 0), sigma, np.nan)
        valid = np.ones(wave.size, bool) if self.valid is None else np.asarray(self.valid, dtype=bool).reshape(-1)
        if valid.size != wave.size:
            raise ValueError("valid must have the same length as wavelength_um")
        valid = valid[order] & np.isfinite(flux)
        if sigma is not None:
            valid &= np.isfinite(sigma) & (sigma > 0)
        flags = None if self.flags is None else np.asarray(self.flags).reshape(-1)
        hits = None if self.hits is None else np.asarray(self.hits).reshape(-1)
        if flags is not None:
            if flags.size != wave.size: raise ValueError("flags length mismatch")
            flags = flags[order]
        if hits is not None:
            if hits.size != wave.size: raise ValueError("hits length mismatch")
            hits = hits[order]
        return Spectrum(wave, flux, sigma, valid, flags, hits, dict(self.metadata or {}))


def _channel_axis(data: np.ndarray, n_channels: int = EXPECTED_CHANNELS) -> int:
    axes = [i for i, size in enumerate(data.shape) if size == n_channels]
    if len(axes) != 1:
        raise ValueError(f"cannot identify a unique {n_channels}-channel axis in {data.shape}")
    return axes[0]


def _parse_blank_channels(value: Any, n_channels: int) -> list[int]:
    if value in (None, "", "None"): return []
    raw = list(value) if isinstance(value, (tuple, list, np.ndarray)) else str(value).replace("[", "").replace("]", "").replace(";", ",").split(",")
    out = []
    for item in raw:
        try: n = int(str(item).strip())
        except (ValueError, TypeError): continue
        if 1 <= n <= n_channels: out.append(n - 1)
    return sorted(set(out))


def _wavelength_column(table: Any, requested: str | None = None) -> np.ndarray:
    names = list(getattr(getattr(table, "dtype", None), "names", None) or [])
    lookup = {n.upper(): n for n in names}
    if requested:
        if requested.upper() not in lookup: raise ValueError(f"wavelength column {requested!r} absent; columns={names}")
        return np.asarray(table[lookup[requested.upper()]], float).reshape(-1)
    for candidate in ("WAVELENGTH", "WAVELENGTH_UM", "WAVE", "WAVE_UM", "LAMBDA", "LAM_CEN", "WAVE_CEN", "WAVECEN", "CENTER"):
        if candidate in lookup:
            arr = np.asarray(table[lookup[candidate]], float).reshape(-1)
            if arr.size == EXPECTED_CHANNELS and np.all(np.isfinite(arr)): return arr
    raise ValueError(f"cannot identify central wavelength column; inspect columns={names}, then pass wavelength_column")

@dataclass
class AllSkyCube:
    image: np.ndarray
    nhits: np.ndarray
    flags: np.ndarray
    wavelength_um: np.ndarray
    valid_channel: np.ndarray
    blank_channels: list[int]
    header: dict[str, Any]
    source_path: str


def load_allsky_cube(path: str, wavelength_column: str | None = None) -> AllSkyCube:
    """Load IMAGE/NHITS/FLAGS/SPECTRAL_CHANNELS and normalize to [channel,y,x]."""
    try: from astropy.io import fits
    except ImportError as exc: raise RuntimeError("Astropy is required to read FITS files") from exc
    if not os.path.isfile(path): raise FileNotFoundError(path)
    with fits.open(path, memmap=True) as hdul:
        by_name = {str(h.name).upper(): h for h in hdul}
        missing = [n for n in ("IMAGE", "NHITS", "FLAGS", "SPECTRAL_CHANNELS") if n not in by_name or by_name[n].data is None]
        if missing: raise ValueError(f"not a supported All-Sky Cube; missing {missing}")
        image = np.asarray(by_name["IMAGE"].data, float)
        axis = _channel_axis(image)
        image = np.moveaxis(image, axis, 0)
        hits = np.moveaxis(np.asarray(by_name["NHITS"].data), axis, 0)
        flags = np.moveaxis(np.asarray(by_name["FLAGS"].data), axis, 0)
        if image.shape != hits.shape or image.shape != flags.shape: raise ValueError("IMAGE/NHITS/FLAGS shapes differ")
        wave = _wavelength_column(by_name["SPECTRAL_CHANNELS"].data, wavelength_column)
        if wave.size != image.shape[0]: raise ValueError("wavelength table length differs from cube channel count")
        header = dict(hdul[0].header)
        header.update({k:v for k,v in by_name["IMAGE"].header.items() if k not in header})
        blank = _parse_blank_channels(header.get("BLANKCH", by_name["IMAGE"].header.get("BLANKCH")), image.shape[0])
    valid = np.isfinite(wave)
    if blank: valid[blank] = False
    return AllSkyCube(image, hits, flags, wave, valid, blank, header, os.path.abspath(path))

@dataclass
class SpectralImageMEF:
    image: np.ndarray
    flags: np.ndarray
    variance: np.ndarray
    zodi: np.ndarray
    cwave_um: np.ndarray
    cband_um: np.ndarray
    header: dict[str, Any]
    source_path: str
    calibration_path: str


def load_spectral_image_mef(path: str, spectral_wcs_path: str) -> SpectralImageMEF:
    """Load Level-2 IMAGE/FLAGS/VARIANCE/ZODI plus separate CWAVE/CBAND maps."""
    try: from astropy.io import fits
    except ImportError as exc: raise RuntimeError("Astropy is required to read FITS files") from exc
    for p in (path, spectral_wcs_path):
        if not os.path.isfile(p): raise FileNotFoundError(p)
    with fits.open(path, memmap=True) as hdul, fits.open(spectral_wcs_path, memmap=True) as whdul:
        def get(hdus, name):
            hits = [h for h in hdus if str(h.name).upper() == name]
            if not hits or hits[0].data is None: raise ValueError(f"missing {name} extension")
            return np.asarray(hits[0].data)
        image = np.asarray(get(hdul, "IMAGE"), float); flags = get(hdul, "FLAGS")
        variance = np.asarray(get(hdul, "VARIANCE"), float); zodi = np.asarray(get(hdul, "ZODI"), float)
        cwave = np.asarray(get(whdul, "CWAVE"), float); cband = np.asarray(get(whdul, "CBAND"), float)
        if not (image.shape == flags.shape == variance.shape == zodi.shape == cwave.shape == cband.shape):
            raise ValueError("MEF image, variance, flags, zodi, CWAVE and CBAND shapes must match; crop/reproject explicitly")
        header = dict(hdul[0].header)
        header.update({k:v for k,v in hdul["IMAGE"].header.items() if k not in header})
    return SpectralImageMEF(image, flags, variance, zodi, cwave, cband, header, os.path.abspath(path), os.path.abspath(spectral_wcs_path))


def extract_cube_spectrum(cube: AllSkyCube, x: int, y: int, radius: int = 1,
                          excluded_flag_bits: int = 0, minimum_hits: int = 1) -> Spectrum:
    """Simple unweighted aperture mean; NHITS is only a contributor diagnostic.

    No sigma is returned: NHITS is not a variance estimate and this is not PSF photometry.
    """
    if radius < 0 or minimum_hits < 0: raise ValueError("radius and minimum_hits must be non-negative")
    nc, ny, nx = cube.image.shape
    if not (0 <= x < nx and 0 <= y < ny): raise ValueError("pixel lies outside cube")
    ys = slice(max(0,y-radius), min(ny,y+radius+1)); xs = slice(max(0,x-radius), min(nx,x+radius+1))
    flux = np.full(nc, np.nan); valid = np.zeros(nc, bool); hit_sum = np.zeros(nc)
    for c in range(nc):
        im = cube.image[c,ys,xs]; nh = np.asarray(cube.nhits[c,ys,xs], float); fl = cube.flags[c,ys,xs]
        good = np.isfinite(im) & (nh >= minimum_hits)
        if excluded_flag_bits: good &= (np.asarray(fl,dtype=np.int64) & int(excluded_flag_bits)) == 0
        if not cube.valid_channel[c] or not np.any(good): continue
        flux[c] = float(np.mean(im[good])); hit_sum[c] = float(np.sum(nh[good])); valid[c] = True
    return Spectrum(cube.wavelength_um, flux, sigma=None, valid=valid, hits=hit_sum,
                    metadata={"origin":"SPHEREx DR1 All-Sky Cube", "x":x,"y":y,"aperture_radius_pixels":radius,
                              "uncertainty_available":False,"nhits_semantics":"contributor count, not variance"})


def compare_spectra(reference: Spectrum, comparison: Spectrum, min_overlap: int = 5) -> dict[str, Any]:
    a,b = reference.normalized(), comparison.normalized()
    lo=max(float(a.wavelength_um[0]),float(b.wavelength_um[0])); hi=min(float(a.wavelength_um[-1]),float(b.wavelength_um[-1]))
    if not lo < hi: raise ValueError("spectra have no wavelength overlap")
    grid=a.wavelength_um[(a.wavelength_um>=lo)&(a.wavelength_um<=hi)]
    if grid.size < min_overlap: raise ValueError(f"only {grid.size} native reference samples overlap; at least {min_overlap} are required")
    av=np.interp(grid,a.wavelength_um,a.flux); bv=np.interp(grid,b.wavelength_um,b.flux)
    va=np.interp(grid,a.wavelength_um,a.valid.astype(float)) >= .999
    vb=np.interp(grid,b.wavelength_um,b.valid.astype(float)) >= .999
    valid=va&vb&np.isfinite(av)&np.isfinite(bv); sigma_diff=z=chi2=None
    if a.sigma is not None and b.sigma is not None:
        sa=np.interp(grid,a.wavelength_um,np.nan_to_num(a.sigma,nan=0)); sb=np.interp(grid,b.wavelength_um,np.nan_to_num(b.sigma,nan=0))
        sigma_diff=np.sqrt(sa**2+sb**2); valid &= np.isfinite(sigma_diff)&(sigma_diff>0)
        z=np.full(grid.size,np.nan); z[valid]=(bv[valid]-av[valid])/sigma_diff[valid]
        if np.any(valid): chi2=float(np.mean(z[valid]**2))
    return {"wavelength_um":grid.tolist(),"reference_flux":av.tolist(),"comparison_flux":bv.tolist(),
            "difference_flux":(bv-av).tolist(),"ratio":np.divide(bv,av,out=np.full_like(bv,np.nan),where=np.abs(av)>1e-15).tolist(),
            "valid":valid.tolist(),"n_valid":int(valid.sum()),"overlap_um":[lo,hi],
            "sigma_difference":None if sigma_diff is None else sigma_diff.tolist(),
            "significance_z":None if z is None else z.tolist(),"mean_squared_significance":chi2,
            "significance_available":z is not None,
            "interpretation":"Flux differences only; no significance without validated sigma." if z is None else
              "Significance is a measurement diagnostic, not proof of astrophysical variation; inspect calibration, flags and independent epochs."}


def spectrum_to_dict(s: Spectrum) -> dict[str, Any]:
    s=s.normalized()
    return {"wavelength_um":s.wavelength_um.tolist(),"flux":s.flux.tolist(),"sigma":None if s.sigma is None else s.sigma.tolist(),
            "valid":s.valid.tolist(),"flags":None if s.flags is None else s.flags.tolist(),"hits":None if s.hits is None else s.hits.tolist(),"metadata":s.metadata or {}}
