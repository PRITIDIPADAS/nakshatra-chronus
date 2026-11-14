"""Fill the cache for the five targets so the demo works with a weak connection. Run: python prefetch.py"""
import connectors as cn
from app import TARGETS

for key, target in TARGETS.items():
    try:
        n = len(cn.live_exposures(target, "spherex_qr3+spherex_qr2", 48, det=target["band"]))
        print(key, "band", target["band"], n, "exposures cached.", cn.REPORT.get("failed") or "")
    except Exception as err:
        print(key, "failed:", err)
