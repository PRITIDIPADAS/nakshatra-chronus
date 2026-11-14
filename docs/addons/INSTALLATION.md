# Local installation and integration

## Important

This pack has **not** been pushed to GitHub and makes no remote repository changes. The installer operates only on a local checkout and never runs Git. Review all diffs and test output before deciding what you want to commit yourself.

## Requirements

The original CHRONOS `requirements.txt` already includes the principal runtime dependencies (FastAPI, NumPy, SciPy, Astropy, scikit-learn and pytest). `requirements-addons.txt` lists a minimal standalone set. The browser interface uses vanilla HTML/CSS/JavaScript.

## Install into a local CHRONOS checkout

```bash
python integration/apply_additions.py /path/to/nakshatra-chronus
```

The installer:

- copies `backend/chronos_addons/` into the checkout;
- copies `chronos-lab.html`, `.css` and `.js` into `frontend/` and `site/`;
- adds the optional router import and registration to `backend/app.py`;
- adds a link to the research lab in `frontend/index.html` and `site/index.html` when the original link is present;
- backs up the edited entry-point files under `.chronos_addons_backup/`.

It refuses to overwrite an existing add-on folder or page file. If it cannot patch an expected anchor, it stops and restores backed-up entry points.

## Undo local installation

```bash
python integration/undo_additions.py /path/to/nakshatra-chronus
```

This restores backed-up entry points and removes the named add-on files/folder. It does not run Git.

## Run tests before integration

From this extension folder:

```bash
python scripts/test_addons.py
```

Current bundled test suite: **19 tests**. The test suite uses synthetic fixtures; it does not prove correctness on real SPHEREx archive files.

## Run the optional API

After installing and mounting the router, start the existing CHRONOS backend normally. The research page is `/chronos-lab.html`. API routes:

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/addons/status` | Extension health |
| POST | `/api/addons/spectral/compare` | Compare two spectra |
| POST | `/api/addons/forensics/diagnose` | Transparent instrument triage |
| POST | `/api/addons/forensics/calibration-ablation` | Compare candidate sets across correction variants |
| POST | `/api/addons/observations/plan` | Rank supplied forecasts by information gain |
| POST | `/api/addons/passport/create` | Create sealed evidence package |
| POST | `/api/addons/passport/verify` | Verify evidence package integrity |
| POST | `/api/addons/validation/recovery` | Score injection/recovery positions |
| POST | `/api/addons/validation/probabilities` | Brier/ECE/coverage metrics |
| POST | `/api/addons/spectral/feature` | Measure pre-specified equivalent width |
| POST | `/api/addons/catalog/crossmatch` | Positional catalogue match |
| POST | `/api/addons/planet/orbit-track` | Low-precision scenario track |
| POST | `/api/addons/validation/selection-correction` | Completeness/null-corrected tile counts |
| POST | `/api/addons/citizen/aggregate` | Human-review statistics |

## GitHub Pages distinction

The current project Pages workflow uploads `site/`; it does not run the FastAPI backend. On static Pages the interface's local demonstration tools work, but backend API calls will not connect unless the API is deployed separately. Keep the static/offline and backend-connected modes visibly distinct. `scripts/build_static.py` copies the contents of `frontend/` to `site/`, so the research page will be included after the local installer has copied it into `frontend/`.

## Before using real science data

Read `SPHEREX_DR1_ADAPTER_GUIDE.md`. In particular:

- `NHITS` is not variance;
- All-Sky Cube uncertainty is not inferred by this pack;
- scientific wavelength assignment must use `CWAVE/CBAND`;
- full-frame calibration products must be aligned to the exposure/cutout using verified detector WCS;
- incompatible release/calibration groups are never silently combined;
- a positional catalogue match or low-precision orbit track is not confirmation.
