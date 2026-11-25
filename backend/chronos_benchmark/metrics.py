"""Transparent accounting for benchmark decisions and abstentions."""
from __future__ import annotations
from typing import Any, Mapping, Sequence

def summarize_decisions(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("at least one labelled decision is required")
    labels = sorted({str(r["truth"]) for r in rows} | {str(r["prediction"]) for r in rows if r.get("prediction") not in (None, "unknown")})
    decided = [r for r in rows if r.get("prediction") not in (None, "unknown")]
    correct = sum(str(r["truth"]) == str(r["prediction"]) for r in decided)
    confusion = {truth: {pred: 0 for pred in labels} for truth in labels}
    for row in rows:
        pred = str(row.get("prediction") if row.get("prediction") not in (None, "unknown") else "unknown")
        truth = str(row["truth"])
        confusion.setdefault(truth, {})
        confusion[truth][pred] = confusion[truth].get(pred, 0) + 1
    return {
        "n_total": len(rows),
        "n_decided": len(decided),
        "coverage": len(decided) / len(rows),
        "accuracy_when_decided": correct / len(decided) if decided else None,
        "end_to_end_correct_fraction": correct / len(rows),
        "abstentions": len(rows) - len(decided),
        "confusion_including_abstentions": confusion,
        "warning": "Report coverage and accuracy together. Do not compare accuracy alone when systems abstain at different rates.",
    }
