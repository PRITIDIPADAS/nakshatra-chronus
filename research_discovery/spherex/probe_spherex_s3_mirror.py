#!/usr/bin/env python3
"""Probe the public NASA/IPAC IRSA SPHEREx S3 mirror for calibration keys."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
import requests
import xml.etree.ElementTree as ET

BUCKET = "nasa-irsa-spherex"
REGION = "us-east-1"
BASE = f"https://{BUCKET}.s3.{REGION}.amazonaws.com"
PREFIXES = [
    "dr1/spectral_wcs/",
    "dr1/solid_angle_pixel_map/",
    "dr1/abs_gain_matrix/",
    "dr1/level2/2025W19_2B/l2b-v27-2026-198/2/",
]


def main():
    out = Path("data/spherex_s3_mirror_probe")
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    report = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "bucket": BUCKET, "region": REGION, "prefix_results": [], "errors": []}
    for prefix in PREFIXES:
        params = {"list-type": "2", "prefix": prefix, "delimiter": "/"}
        url = BASE + "/?" + urlencode(params)
        item = {"prefix": prefix, "url": url}
        try:
            response = session.get(url, timeout=60)
            item.update({"status_code": response.status_code,
                         "content_type": response.headers.get("Content-Type"),
                         "sample": response.text[:4000]})
            if response.ok:
                root = ET.fromstring(response.content)
                ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
                item["common_prefixes"] = [
                    x.findtext("s3:Prefix", namespaces=ns)
                    for x in root.findall("s3:CommonPrefixes", ns)
                ]
                item["keys"] = [
                    {"key": x.findtext("s3:Key", namespaces=ns),
                     "size": x.findtext("s3:Size", namespaces=ns),
                     "etag": x.findtext("s3:ETag", namespaces=ns),
                     "last_modified": x.findtext("s3:LastModified", namespaces=ns)}
                    for x in root.findall("s3:Contents", ns)
                ]
                item["is_truncated"] = root.findtext("s3:IsTruncated", namespaces=ns)
                item["next_continuation_token"] = root.findtext("s3:NextContinuationToken", namespaces=ns)
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        report["prefix_results"].append(item)

    exact_key = (
        "dr1/level2/2025W19_2B/l2b-v27-2026-198/2/"
        "level2_2025W19_2B_0346_1D2_spx_l2b-v27-2026-198.fits"
    )
    try:
        response = session.head(f"{BASE}/{exact_key}", timeout=60)
        report["science_object_head"] = {
            "url": f"{BASE}/{exact_key}", "status_code": response.status_code,
            "content_length": response.headers.get("Content-Length"),
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        }
    except Exception as exc:
        report["science_object_head"] = {"error": f"{type(exc).__name__}: {exc}"}

    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    target = out / "spherex_s3_mirror_probe.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "bucket": BUCKET,
        "prefix_results": [{
            "prefix": x["prefix"], "status_code": x.get("status_code"),
            "common_prefixes": x.get("common_prefixes"),
            "keys": x.get("keys", [])[:40], "is_truncated": x.get("is_truncated"),
            "error": x.get("error"), "sample": x.get("sample", "")[:900]
        } for x in report["prefix_results"]],
        "science_object_head": report["science_object_head"],
        "output": str(target)
    }, indent=2))


if __name__ == "__main__":
    main()
