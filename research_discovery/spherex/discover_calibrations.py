#!/usr/bin/env python3
"""Discover versioned public SPHEREx calibration products in IRSA directories.

The directory path follows the official IRSA guide: release/product/version-or-
processing-date/detector-number/file. Detector folders are numeric ("1".."6"),
not named "D1". Returned files are candidates only; provenance compatibility
must be established from the actual exposure and calibration metadata.
"""
from __future__ import annotations
import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = "https://irsa.ipac.caltech.edu/ibe/data/spherex/"
PRODUCTS = {
    "spectral_wcs": ("spectral_wcs/", True),
    "epsf": ("epsf/", True),
    "nonfunctional": ("nonfunc_v2/", True),
    "aurora": ("aurora_template/", True),
    "helium": ("he_template/", True),
    "shuttle_glow": ("shuttle_glow_template/", True),
    "dichroic": ("dichroic/", True),
    "gain": ("abs_gain_matrix/", True),
    "dark": ("dark/", True),
    "readnoise": ("readnoise_pars/", True),
    "nonlinearity": ("nonlinear_pars/", True),
    "solid_angle": ("solid_angle_pixel_map/", True),
    "spectral_channels": ("spectral_channels/", False),
    "sip": ("sip/", True),
    "gain_factors": ("gain_factors/", False),
    "flux_corrections": ("l3_flux_corrections/", True),
    "zodi": ("zodi_scaling_v2/", True),
}

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def _list(url: str, timeout: int = 60) -> list[str]:
    import requests
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    parser = Links()
    parser.feed(response.text)
    return sorted({urljoin(url, href) for href in parser.links
                   if href not in ("../", "/") and not href.startswith("?C=")})


def find_products(product: str, detector: int | None = None, *, release: str = "dr1",
                  processing_date: str | None = None, version: str | None = None,
                  crosstalk_type: int = 1) -> list[str]:
    if release not in {"dr1", "qr3"}:
        raise ValueError("release must be dr1 or qr3; QR2 is not part of the current SIA2 search")
    if product == "crosstalk":
        if crosstalk_type not in {1, 2, 3}:
            raise ValueError("crosstalk_type must be 1, 2 or 3")
        relative, needs_detector = (f"xtalk_class{crosstalk_type}/", True)
    else:
        if product not in PRODUCTS:
            raise ValueError(f"Unknown product {product}; choose {sorted([*PRODUCTS, 'crosstalk'])}")
        relative, needs_detector = PRODUCTS[product]
    if needs_detector and detector is None:
        raise ValueError(f"{product} requires --detector 1..6")
    if detector is not None and detector not in range(1, 7):
        raise ValueError("detector must be from 1 through 6")
    base = urljoin(ROOT, f"{release}/{relative}")
    found: list[str] = []
    for product_version_url in _list(base):
        if not product_version_url.endswith("/"):
            continue
        path = urlparse(product_version_url).path
        if processing_date and processing_date not in path:
            continue
        if version and f"v{version}-" not in path and f"v{version}/" not in path:
            continue
        if needs_detector:
            detector_dirs = [urljoin(product_version_url, f"{detector}/")]
        else:
            detector_dirs = [product_version_url]
        for directory in detector_dirs:
            try:
                files = _list(directory)
            except Exception:
                continue
            found.extend(u for u in files if urlparse(u).path.lower().endswith((".fits", ".ecsv", ".yaml")))
    return sorted(set(found))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("product", choices=sorted([*PRODUCTS, "crosstalk"]))
    p.add_argument("--release", choices=("dr1", "qr3"), default="dr1")
    p.add_argument("--detector", type=int, choices=range(1, 7))
    p.add_argument("--processing-date", help="Filter by exact archive processing-date substring, e.g. 2026-191")
    p.add_argument("--version", help="Filter product version string, e.g. 1 or 2")
    p.add_argument("--crosstalk-type", type=int, choices=(1, 2, 3), default=1)
    p.add_argument("--out", type=Path, default=Path("calibration_candidates.json"))
    a = p.parse_args()
    urls = find_products(a.product, a.detector, release=a.release,
        processing_date=a.processing_date, version=a.version, crosstalk_type=a.crosstalk_type)
    data = {"product": a.product, "release": a.release, "detector": a.detector,
        "processing_date_filter": a.processing_date, "version_filter": a.version,
        "candidate_urls": urls, "candidate_count": len(urls),
        "warning": "Candidates only. Match release, detector, product version, calibration processing date, provenance and science-pipeline metadata before use.",
        "official_directory_root": ROOT + a.release + "/"}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, indent=2))
    print(f"Found {len(urls)} candidate files; saved {a.out}")

if __name__ == "__main__":
    main()
