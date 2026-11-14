# Official public SPHEREx observation example

IRSA's tutorial *Understanding and Extracting the ePSF Extension in a SPHEREx Cutout* demonstrates a public Level-2 image at this archive path:

```text
https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W18_1B/l2b-v27-2026-196/4/level2_2025W18_1B_0023_2D4_spx_l2b-v27-2026-196.fits
```

The tutorial uses the sky position RA `305.59875000000005` degrees, Dec `41.14888888888889` degrees, and a `0.01` degree cutout. Its example cutout is only 6×6 pixels, so use it to verify FITS structure, header parsing and ePSF extraction logic, **not** as the independent injection/recovery field.

## Download the tutorial cutout

```bash
curl -L --fail \
  'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W18_1B/l2b-v27-2026-196/4/level2_2025W18_1B_0023_2D4_spx_l2b-v27-2026-196.fits?center=305.59875000000005,41.14888888888889d&size=0.01' \
  -o spherex_irsa_tutorial_cutout.fits
sha256sum spherex_irsa_tutorial_cutout.fits
```

For larger fields, query SIA2 using `discover_dr1.py` or use the official IRSA Data Explorer. A full Level-2 MEF is about 70 MB. Save the original FITS, query URL, observation ID, detector, time metadata and SHA-256 before transforming it.

## Why this is real archive evidence but not a CHRONOS result

The cited tutorial opens the cutout from IRSA, inspects the `IMAGE`, `FLAGS`, `VARIANCE`, `ZODI`, `EPSF` and `WCS-WAVE` HDUs, and shows how to select the local ePSF binary-table row. This is an official example of a real public archive product and a useful reproducibility target. The file was **not downloaded into this response's runtime**, and no measurements from it are claimed here. The prior CHRONOS browser-demo observations remain synthetic until replaced by actual FITS-derived measurements.

## References

- [IRSA SPHEREx ePSF extraction tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/)
- [IRSA SPHEREx Data Access](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/)
- [IRSA SPHEREx Data Products](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/)
