"""Turn association results into a traceable source-observation graph."""
from __future__ import annotations
from typing import Any, Mapping, Sequence

def build_source_graph(candidate_id: str, association_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not candidate_id:
        raise ValueError("candidate_id is required")
    nodes = [{"id": f"candidate:{candidate_id}", "type": "candidate", "label": candidate_id}]
    edges = []
    for result in association_results:
        for match in result.get("matches", []):
            source_id = str(match.get("source_id", match.get("catalogue_index")))
            node_id = f"catalogue:{source_id}"
            if not any(n["id"] == node_id for n in nodes):
                nodes.append({"id": node_id, "type": "catalogue_source", "label": source_id})
            edges.append({
                "source": f"candidate:{candidate_id}",
                "target": node_id,
                "relation": "probabilistic_positional_association",
                "probability": float(match["association_probability"]),
                "separation_arcsec": float(match["separation_arcsec"]),
                "evidence_status": "candidate association; not confirmed identity",
            })
    return {"nodes": nodes, "edges": edges, "limitations": ["Edges preserve association uncertainty; they are not identity assertions."]}
