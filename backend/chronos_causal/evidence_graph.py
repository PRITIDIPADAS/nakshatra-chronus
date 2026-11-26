"""Evidence graph linking archive inputs, calibration, measurements, tests and conclusions.

Each measurement row has its own deterministic node identity. Multiple
spectral samples from one exposure retain their shared observation_id without
colliding into one graph node.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import hashlib
import json


def _seal(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False, default=str,
    ).encode()).hexdigest()


def _append_node(nodes: list[dict[str, Any]], node_ids: set[str], node: dict[str, Any]) -> None:
    node_id = str(node.get("id", "")).strip()
    if not node_id:
        raise ValueError("evidence graph node IDs must be non-empty")
    if node_id in node_ids:
        raise ValueError(f"duplicate evidence graph node ID: {node_id}")
    node_ids.add(node_id)
    nodes.append(node)


def _unique_record_id(record: Mapping[str, Any], key: str, fallback: int, label: str) -> str:
    value = str(record.get(key, fallback)).strip()
    if not value:
        raise ValueError(f"{label} IDs must be non-empty")
    return value


def build_evidence_graph(
    *,
    candidate_id: str,
    observations: Sequence[Mapping[str, Any]],
    analysis: Mapping[str, Any],
    manifest: Mapping[str, Any] | None = None,
    model_runs: Sequence[Mapping[str, Any]] = (),
    counterfactuals: Sequence[Mapping[str, Any]] = (),
    failed_tests: Sequence[Mapping[str, Any]] = (),
    environment: Mapping[str, Any] | None = None,
    code_commit: str | None = None,
):
    if not isinstance(candidate_id, str) or not candidate_id.strip() or not observations:
        raise ValueError("candidate_id and observations are required")
    if not isinstance(analysis, Mapping) or "verdict" not in analysis:
        raise ValueError("analysis must contain verdict")
    if manifest is not None and not isinstance(manifest, Mapping):
        raise ValueError("manifest must be an object")

    root = f"candidate:{candidate_id}"
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    edges: list[dict[str, Any]] = []
    archive: dict[str, str] = {}

    _append_node(nodes, node_ids, {
        "id": root,
        "type": "candidate",
        "label": candidate_id,
    })

    if manifest:
        files = manifest.get("files", [])
        if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
            raise ValueError("manifest.files must be a sequence of file records")
        for index, file in enumerate(files):
            if not isinstance(file, Mapping):
                raise ValueError(f"manifest file {index} must be an object")
            archive_id = _unique_record_id(file, "archive_id", index, "archive product")
            node_id = f"archive:{archive_id}"
            _append_node(nodes, node_ids, {
                "id": node_id,
                "type": "archive_product",
                "label": archive_id,
                "product_type": file.get("product_type"),
                "release": file.get("release"),
                "detector": file.get("detector"),
                "native_uri": file.get("native_uri"),
                "sha256": file.get("sha256"),
                "calibration_group": file.get("calibration_group"),
            })
            archive[archive_id] = node_id
            edges.append({"source": node_id, "target": root, "relation": "input_product_for"})
            if "cal" in str(file.get("product_type", "")).lower():
                calibration_id = f"calibration:{archive_id}"
                _append_node(nodes, node_ids, {
                    "id": calibration_id,
                    "type": "calibration_product",
                    "label": archive_id,
                    "sha256": file.get("sha256"),
                })
                edges.append({
                    "source": calibration_id,
                    "target": node_id,
                    "relation": "calibrates_or_supports",
                })

    measurement_keys: set[str] = set()
    for index, row in enumerate(observations):
        if not isinstance(row, Mapping):
            raise ValueError(f"observation {index} must be an object")
        observation_id = str(row.get("observation_id", "")).strip()
        measurement_id = str(row.get("measurement_id", "")).strip()
        record_sha = _seal(dict(row))
        # Prefer an explicit row-level measurement ID. Otherwise derive a
        # deterministic identity from the observation ID and complete row.
        # This allows many wavelength samples to share one observation_id.
        identity = measurement_id or f"{observation_id or 'row'}:{record_sha}"
        node_id = f"measurement:{identity}"
        if identity in measurement_keys:
            raise ValueError(f"duplicate measurement identity: {identity}")
        measurement_keys.add(identity)
        _append_node(nodes, node_ids, {
            "id": node_id,
            "type": "measurement",
            "label": measurement_id or observation_id or f"measurement row {index}",
            "observation_id": observation_id or None,
            "measurement_id": measurement_id or None,
            "record_sha256": record_sha,
            "mjd": row.get("mjd"),
            "wavelength_um": row.get("wavelength_um"),
            "flux": row.get("flux"),
            "sigma": row.get("sigma"),
            "detector_id": row.get("detector_id", row.get("detector")),
            "calibration_group": row.get("calibration_group"),
            "calibration_product_id": row.get("calibration_product_id"),
        })
        edges.append({
            "source": node_id,
            "target": root,
            "relation": "measures_candidate",
        })
        calibration_product_id = row.get("calibration_product_id")
        if calibration_product_id:
            calibration_node = archive.get(str(calibration_product_id))
            if calibration_node is not None:
                edges.append({
                    "source": calibration_node,
                    "target": node_id,
                    "relation": "calibration_for_measurement",
                })

    for index, run in enumerate(model_runs):
        if not isinstance(run, Mapping):
            raise ValueError(f"model run {index} must be an object")
        run_id = _unique_record_id(run, "run_id", index, "model run")
        node_id = f"model_run:{run_id}"
        _append_node(nodes, node_ids, {
            "id": node_id,
            "type": "model_run",
            "label": run_id,
            "record_sha256": _seal(dict(run)),
            "model": run.get("model"),
            "score": run.get("score"),
            "score_type": run.get("score_type"),
        })
        edges.append({"source": root, "target": node_id, "relation": "evaluated_by_model"})

    analysis_id = "analysis:" + _seal(dict(analysis))
    _append_node(nodes, node_ids, {
        "id": analysis_id,
        "type": "analysis",
        "label": str(analysis.get("verdict")),
        "record_sha256": _seal(dict(analysis)),
        "leading_model": analysis.get("leading_model"),
        "relative_model_support": analysis.get("relative_model_support"),
    })
    edges.append({"source": root, "target": analysis_id, "relation": "conclusion_recorded_as"})

    for index, counterfactual in enumerate(counterfactuals):
        if not isinstance(counterfactual, Mapping):
            raise ValueError(f"counterfactual {index} must be an object")
        counterfactual_id = _unique_record_id(counterfactual, "id", index, "counterfactual")
        node_id = f"counterfactual:{counterfactual_id}"
        _append_node(nodes, node_ids, {
            "id": node_id,
            "type": "counterfactual",
            "label": counterfactual_id,
            "intervention": counterfactual.get("intervention"),
            "record_sha256": _seal(dict(counterfactual)),
        })
        edges.append({"source": analysis_id, "target": node_id, "relation": "challenged_by"})

    for index, test in enumerate(failed_tests):
        if not isinstance(test, Mapping):
            raise ValueError(f"failed test {index} must be an object")
        test_id = _unique_record_id(
            test, "test_id", test.get("name", index), "failed test"
        )
        node_id = f"failed_test:{test_id}"
        _append_node(nodes, node_ids, {
            "id": node_id,
            "type": "failed_or_null_test",
            "label": str(test.get("name", test_id)),
            "status": test.get("status", "failed_or_unresolved"),
            "reason": test.get("reason"),
            "record_sha256": _seal(dict(test)),
        })
        edges.append({"source": node_id, "target": analysis_id, "relation": "qualifies_or_contradicts"})

    if manifest:
        manifest_id = "manifest:" + _seal(dict(manifest))
        _append_node(nodes, node_ids, {
            "id": manifest_id,
            "type": "provenance_manifest",
            "label": "Archive/calibration manifest",
            "record_sha256": _seal(dict(manifest)),
            "manifest_sha256": manifest.get("manifest_sha256"),
        })
        edges.append({"source": manifest_id, "target": root, "relation": "documents_inputs_for"})

    if environment:
        if not isinstance(environment, Mapping):
            raise ValueError("environment must be an object")
        environment_id = "environment:" + _seal(dict(environment))
        _append_node(nodes, node_ids, {
            "id": environment_id,
            "type": "software_environment",
            "label": "Software environment",
            "environment": dict(environment),
            "record_sha256": _seal(dict(environment)),
        })
        edges.append({"source": environment_id, "target": analysis_id, "relation": "executed_in"})

    if code_commit:
        commit_id = str(code_commit).strip()
        if not commit_id:
            raise ValueError("code_commit must be non-empty when supplied")
        node_id = f"commit:{commit_id}"
        _append_node(nodes, node_ids, {
            "id": node_id,
            "type": "code_commit",
            "label": commit_id,
        })
        edges.append({"source": node_id, "target": analysis_id, "relation": "implemented_by"})

    known_ids = {node["id"] for node in nodes}
    for index, edge in enumerate(edges):
        if edge["source"] not in known_ids or edge["target"] not in known_ids:
            raise ValueError(f"evidence graph edge {index} references a missing node")

    return {
        "schema": "chronos-evidence-graph/2.0",
        "candidate_id": candidate_id,
        "nodes": nodes,
        "edges": edges,
        "claim": {
            "verdict": analysis.get("verdict"),
            "leading_model": analysis.get("leading_model"),
            "abstention_reasons": analysis.get("abstention_reasons", []),
            "status": (
                "unresolved" if analysis.get("verdict") == "unknown"
                else "model_selected_not_confirmed"
            ),
            "support_type": "relative model support, not calibrated posterior probability",
        },
        "graph_sha256": _seal({"nodes": nodes, "edges": edges}),
        "limitations": [
            "Hashes detect changes but do not prove authorship, identity or source authenticity.",
            "A selected model is not a confirmed astronomical discovery.",
            "The graph does not independently validate calibration or physical identity.",
            "Multiple spectral samples from one exposure are represented as distinct row nodes linked by their shared observation_id.",
            "Records with duplicate explicit measurement, archive, run, counterfactual or test identities are rejected.",
        ],
    }
