"""Trace a candidate claim back to source observations and analysis settings."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import hashlib
import json

def _seal(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     allow_nan=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def build_evidence_graph(*, candidate_id: str, observations: Sequence[Mapping[str, Any]],
                         analysis: Mapping[str, Any], manifest: Mapping[str, Any] | None = None):
    if not candidate_id.strip():
        raise ValueError("candidate_id is required")
    if not observations:
        raise ValueError("at least one observation is required")
    if not isinstance(analysis, Mapping) or "verdict" not in analysis:
        raise ValueError("analysis must contain a verdict")
    graph_nodes = []
    graph_edges = []
    candidate_node = f"candidate:{candidate_id}"
    graph_nodes.append({"id": candidate_node, "type": "candidate", "label": candidate_id})
    for index, row in enumerate(observations):
        observation_id = str(row.get("observation_id", index))
        node_id = f"observation:{observation_id}"
        snapshot = dict(row)
        graph_nodes.append({
            "id": node_id,
            "type": "measurement",
            "label": observation_id,
            "record_sha256": _seal(snapshot),
            "mjd": row.get("mjd"),
            "wavelength_um": row.get("wavelength_um"),
            "detector_id": row.get("detector_id"),
            "calibration_group": row.get("calibration_group"),
        })
        graph_edges.append({
            "source": node_id,
            "target": candidate_node,
            "relation": "measures_candidate",
        })
    analysis_node = "analysis:" + _seal(dict(analysis))
    graph_nodes.append({
        "id": analysis_node,
        "type": "analysis",
        "label": str(analysis.get("verdict", "unresolved")),
        "record_sha256": _seal(dict(analysis)),
        "leading_model": analysis.get("leading_model"),
        "interpretation_note": analysis.get("interpretation_note"),
    })
    graph_edges.append({
        "source": candidate_node,
        "target": analysis_node,
        "relation": "evaluated_by",
    })
    manifest_node = None
    if manifest is not None:
        manifest_node = "manifest:" + _seal(dict(manifest))
        graph_nodes.append({
            "id": manifest_node,
            "type": "provenance_manifest",
            "label": "Input and calibration provenance",
            "record_sha256": _seal(dict(manifest)),
            "manifest_sha256": manifest.get("manifest_sha256"),
        })
        graph_edges.append({
            "source": manifest_node,
            "target": candidate_node,
            "relation": "documents_inputs_for",
        })
    return {
        "schema": "chronos-evidence-graph/1.0",
        "candidate_id": candidate_id,
        "nodes": graph_nodes,
        "edges": graph_edges,
        "claim": {
            "verdict": analysis.get("verdict"),
            "leading_model": analysis.get("leading_model"),
            "abstention_reasons": analysis.get("abstention_reasons", []),
            "status": "unresolved" if analysis.get("verdict") == "unknown" else "model_selected_not_confirmed",
        },
        "graph_sha256": _seal({"nodes": graph_nodes, "edges": graph_edges}),
        "limitations": [
            "Hashes bind the exported records; they do not prove source authenticity or scientific truth.",
            "The graph records the supplied analysis and measurements. It does not independently validate calibration.",
            "A selected model is not a confirmed astronomical discovery.",
        ],
    }
