# Reproduce every result

Written for an astronomer outside the project. Each step names the command and the number it should give. Nothing needs a login: SPHEREx data come from the public NASA IRSA archive.

## 1. The code and its tests (5 minutes)

```bash
git clone https://github.com/PRITIDIPADAS/nakshatra-chronus && cd nakshatra-chronus
pip install -r requirements.txt -r research_discovery/requirements-research.txt
python -m pytest tests research_discovery/tests -q        # 464 tests pass
```

## 2. The MATLAB cross-check (2 minutes, needs GNU Octave)

```bash
python -m pytest tests/test_matlab_crosscheck.py -q        # Python and MATLAB agree
octave --eval "addpath('matlab'); export_lvf_curves('/tmp/lvf.json')"
```

## 3. The practice-sky engine (about 40 minutes on 2 cores)

```bash
python scripts/calibrate_engine.py      # writes data/validation.json
```

Expect 98.4 percent right when it decides, 0 of 118 camera effects called a sky change. The random seeds are fixed, so the numbers repeat exactly.

## 4. The seven real DR1 fields (about 40 minutes, needs internet)

```bash
python -m research_discovery.spherex.run_multifield_jy_pilot --out /tmp/pilot
python -m research_discovery.spherex.summarize_injection_diagnostics /tmp/pilot --json /tmp/pilot/diag.json
python scripts/check_reproduction.py /tmp/pilot/diag.json  # compares with data/injection_diagnostics.json
```

The archive files are checked against IRSA's own MD5 sums and kept with SHA-256 hashes, so a different file is detected rather than silently used. The same run is on GitHub Actions as "SPHEREx multi-field calibrated Jy pilot".

## 5. The held-out test

`docs/PREREGISTRATION_SKY_AWARE_NOISE_2026-11-26.md` states the predictions before the run. Rerun with `--field-set holdout`.

## What to send back

The output of step 4's check, the commit you ran, and anything that differs. An issue on the repository is the easiest place.
