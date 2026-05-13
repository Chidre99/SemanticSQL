"""Metrics.

Each metric takes (predicted_dict, ground_truth_dict, predicted_result_rows,
ground_truth_result_rows) and returns 0/1 — easy to aggregate.

We aggregate at the end with simple means: per-condition, per-difficulty,
per-DB.
"""
from __future__ import annotations

import hashlib
from typing import Any, Iterable


# ---- per-row helpers ------------------------------------------------------


def parsed(pred: dict[str, Any]) -> int:
    v = pred.get("validation")
    if v is None:
        return 0
    return int(v["parse"]["ok"])


def policy_pass(pred: dict[str, Any]) -> int:
    v = pred.get("validation")
    if v is None:
        return 0
    return int(v["parse"]["ok"] and v["policy"]["ok"])


def identifier_valid(pred: dict[str, Any]) -> int:
    """1 if every referenced identifier exists in the live schema."""
    v = pred.get("validation")
    if v is None or not v["parse"]["ok"]:
        return 0
    return int(v["identifiers"]["ok"])


def hallucinated(pred: dict[str, Any]) -> int:
    """1 if there's at least one identifier the LLM made up."""
    return 1 - identifier_valid(pred)


def executes(pred: dict[str, Any]) -> int:
    v = pred.get("validation")
    if v is None:
        return 0
    # The orchestrator does a dry-run; the baseline runs validate() without retry.
    # In both cases, dryrun.ok && error is None signals it would execute.
    return int(v["parse"]["ok"] and v["policy"]["ok"] and v["identifiers"]["ok"] and v["dryrun"]["ok"])


# ---- result-set match -----------------------------------------------------


def _hash_rows(rows: Iterable[Any], ordered: bool) -> str:
    """Stable hash of a result set.

    For ORDER BY queries we preserve row order; otherwise we sort the rows
    so two equivalent result sets hash the same.
    """
    norm = [tuple(map(_stringify, r)) for r in rows]
    if not ordered:
        norm.sort()
    h = hashlib.sha256()
    for r in norm:
        h.update("|".join(r).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _stringify(v: Any) -> str:
    """Coerce to a comparable string. Decimal/datetime/None all canonicalize."""
    if v is None:
        return "<NULL>"
    if isinstance(v, float):
        # avoid 1.0 vs 1 mismatches between groundtruth and prediction
        if v.is_integer():
            return str(int(v))
        return f"{v:.6f}".rstrip("0").rstrip(".")
    if isinstance(v, (int,)):
        return str(v)
    return str(v).strip()


def result_match(
    pred_rows: list[list[Any]] | list[dict[str, Any]] | None,
    gt_rows: list[list[Any]] | list[dict[str, Any]] | None,
    ordered: bool,
) -> int:
    if pred_rows is None or gt_rows is None:
        return 0
    # Normalize to list-of-tuples (drop column names — same query may use
    # different aliases in pred vs gt; the values are what matter).
    pred = _as_rows(pred_rows)
    gt = _as_rows(gt_rows)
    return int(_hash_rows(pred, ordered) == _hash_rows(gt, ordered))


def _as_rows(rows: list[Any]) -> list[list[Any]]:
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return [list(r.values()) for r in rows]
    return [list(r) for r in rows]


# ---- top-level summary ----------------------------------------------------


def summarise(records: list[dict[str, Any]]) -> dict[str, float]:
    """Compute aggregate metrics across all eval rows for one condition."""
    if not records:
        return {}

    def mean(key: str) -> float:
        vals = [r[key] for r in records if key in r]
        return sum(vals) / len(vals) if vals else 0.0

    return {
        "n":                   len(records),
        "parse_rate":          mean("parsed"),
        "policy_pass_rate":    mean("policy_pass"),
        "identifier_valid_rate": mean("identifier_valid"),
        "hallucination_rate":  mean("hallucinated"),
        "execution_rate":      mean("executes"),
        "result_match_rate":   mean("result_match"),
    }
