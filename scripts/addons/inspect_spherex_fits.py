"""Print FITS HDU names, shapes, table columns and selected header metadata."""
import argparse
from astropy.io import fits

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("fits_path");args=ap.parse_args()
    with fits.open(args.fits_path,memmap=True) as hdul:
        print(f"File: {args.fits_path}\nHDU count: {len(hdul)}")
        for i,h in enumerate(hdul):
            print(f"\n[{i}] {h.name or 'PRIMARY'}")
            if h.data is not None:
                print("  shape:",getattr(h.data,"shape",None)); names=getattr(getattr(h.data,"dtype",None),"names",None)
                if names:print("  columns:",list(names))
            for k in ("DETECTOR","OBSID","VERSION","BLANKCH","BUNIT","CRPIX1A","CRPIX2A","FINAST"):
                if k in h.header:print(f"  {k}: {h.header[k]}")
if __name__=="__main__":main()
