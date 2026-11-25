# CHRONOS archive manifest schema

Schema version **1.0.0**. The JSON Schema file is `archive_manifest.schema.json`; the implementation and validator are in `archive_manifest.py`.

The canonical manifest preserves the archive publisher identifier when SIA2 supplies `obs_publisher_did`. When it does not, the exact original URI is the product identity. A guessed identifier is never created. Product type, release, detector, MJD bounds, pipeline version and processing date are taken from returned metadata or parsed only when a documented filename pattern matches. Missing information stays null.

A completed download records the source URI, local path, byte count and SHA-256. Failed or interrupted transfers remain rows with `failed` or `partial` status. Discovery-only rows have `discovered_not_downloaded`. Each downloaded file can be re-hashed with `--verify-local`. Duplicate product URIs and publisher IDs, malformed digests, missing fields, file-size changes and changed bytes are errors.

Calibration candidates are deliberately not automatically paired with exposures. A downloaded calibration begins as `candidate_only`; a compatibility group is assigned only after the explicit compatibility checks pass.
