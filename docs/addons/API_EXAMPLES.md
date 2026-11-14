# Optional API examples

All endpoints are local to the CHRONOS backend. No endpoint in this pack fetches a remote service.

## Compare two spectra

```bash
curl -X POST http://127.0.0.1:8000/api/addons/spectral/compare \
  -H 'Content-Type: application/json' \
  -d '{
    "reference": {"wavelength_um":[1,2,3],"flux":[1,2,3],"sigma":[0.1,0.1,0.1]},
    "comparison": {"wavelength_um":[1,2,3],"flux":[1,2.2,3],"sigma":[0.1,0.1,0.1]},
    "min_overlap": 3
  }'
```

## Instrument forensics

```bash
curl -X POST http://127.0.0.1:8000/api/addons/forensics/diagnose \
  -H 'Content-Type: application/json' \
  -d '{"evidence":{"candidate_id":"CAND-EXAMPLE","candidate_snr":7.1,"flagged_fraction":0.12,"psf_reduced_chi2":1.4,"noise_scale":1.1,"partner_snr":5.8,"same_detector_position_scatter_pixels":1.6,"release_mismatch":false}}'
```

## Follow-up information gain

```bash
curl -X POST http://127.0.0.1:8000/api/addons/observations/plan \
  -H 'Content-Type: application/json' \
  -d '{"measurement_sigma":0.3,"candidates":[
    {"time":"candidate epoch A","predictions":{"moving":{"mean":0.5,"sigma":0.2},"variable":{"mean":0.1,"sigma":0.4}}},
    {"time":"candidate epoch B","predictions":{"moving":{"mean":2.0,"sigma":0.2},"variable":{"mean":0.1,"sigma":0.4}}}
  ]}'
```

The time labels and forecast numbers above are synthetic examples. A valid application must provide real physical forecasts and visibility constraints.

## Verify a passport

Save a passport created by `/api/addons/passport/create` as JSON, then:

```bash
python scripts/verify_passport.py passport.json
```

A valid SHA-256 seal confirms only that the bytes/values match the sealed package. It does not authenticate the named analyst or prove a scientific conclusion.
