"""Eval runner.

Compares baseline vs treatment across the queries.yaml set, with:
  - diskcache for LLM responses (so reruns are nearly free)
  - rich progress bar
  - one CSV per run in results/
  - a side-by-side summary table printed at the end

Usage:
    python eval/run_eval.py                       # both conditions, full set
    python eval/run_eval.py --condition treatment # one condition only
    python eval/run_eval.py --limit 10            # smoke test
    python eval/run_eval.py --no-cache            # bypass diskcache
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

import diskcache
import pandas as pd
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

# Make `app.*` importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import settings  # noqa: E402
from app.db.connections import execute, close_pools  # noqa: E402
from app.db.introspect import load_schemas  # noqa: E402

from conditions import baseline_condition, treatment_condition  # noqa: E402
import metrics as M  # noqa: E402

logging.basicConfig(level=logging.WARNING)
console = Console()

ROOT = Path(__file__).resolve().parent
CACHE = diskcache.Cache(str(ROOT / "cache"))


# ----------------------------------------------------------- helpers -------


def _cache_key(condition: str, question: str, database: str) -> str:
    raw = f"{settings.llm_model}|{condition}|{database}|{question}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _maybe_cached(condition: str, question: str, database: str, *, use_cache: bool) -> dict[str, Any]:
    key = _cache_key(condition, question, database)
    if use_cache and key in CACHE:
        return CACHE[key]

    if condition == "baseline":
        result = await baseline_condition(question, database)
    elif condition == "treatment":
        result = await treatment_condition(question, database)
    else:
        raise ValueError(condition)

    if use_cache:
        CACHE[key] = result
    return result


async def _run_ground_truth(database: str, sql: str) -> tuple[list[str], list[list[Any]]] | None:
    """Execute ground-truth SQL against the DB. Returns None on error."""
    try:
        return await execute(database, sql)
    except Exception as e:  # noqa: BLE001
        console.print(f"  [yellow]ground-truth SQL failed:[/] {e}")
        return None


async def _run_predicted(database: str, sql: str) -> tuple[list[str], list[list[Any]]] | None:
    if not sql:
        return None
    try:
        return await execute(database, sql)
    except Exception:
        return None


# ----------------------------------------------------------- main ----------


async def run(args: argparse.Namespace) -> int:
    queries_path = Path(args.queries)
    queries = yaml.safe_load(queries_path.read_text(encoding="utf-8"))
    if args.limit:
        queries = queries[: args.limit]
    console.print(f"[bold]Loaded {len(queries)} queries from {queries_path.name}[/]\n")

    # Introspect schemas so the validator works
    console.print("Loading live schemas…")
    await load_schemas()

    conditions = ["baseline", "treatment"] if args.condition == "both" else [args.condition]

    rows_out: list[dict[str, Any]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        for cond in conditions:
            task = progress.add_task(f"[cyan]{cond:9s}[/]", total=len(queries))
            for q in queries:
                rec = await _evaluate_one(cond, q, use_cache=not args.no_cache)
                rows_out.append(rec)
                progress.advance(task)

    await close_pools()

    # ---- write CSV ----
    df = pd.DataFrame(rows_out)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_csv = ROOT / "results" / f"run-{ts}.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    console.print(f"\n[green]wrote {out_csv}[/]")

    # ---- summary ----
    _print_summary(df)
    _print_failure_breakdown(df)
    return 0


async def _evaluate_one(condition: str, q: dict[str, Any], *, use_cache: bool) -> dict[str, Any]:
    database = q["database"]
    question = q["question"]

    pred = await _maybe_cached(condition, question, database, use_cache=use_cache)

    # Always re-execute predicted SQL: it's cheap and not cacheable across DB state changes.
    pred_rows: list[list[Any]] | None = None
    if pred.get("rows"):
        # treatment already executed
        pred_rows = pred["rows"]
    else:
        result = await _run_predicted(database, pred.get("sql", ""))
        if result is not None:
            _, rows = result
            pred_rows = rows

    # Ground truth — execute (or pull from a sidecar cache key).
    gt_result = await _run_ground_truth(database, q["ground_truth_sql"])
    if gt_result is None:
        gt_rows: list[list[Any]] | None = None
    else:
        _, gt_rows = gt_result

    ordered = "order by" in q["ground_truth_sql"].lower()

    rec = {
        "id":         q["id"],
        "database":   database,
        "difficulty": q.get("difficulty", "?"),
        "condition":  condition,
        "question":   question,
        "predicted_sql": pred.get("sql", ""),
        "attempts":   pred.get("attempts", 1),
        "parsed":          M.parsed(pred),
        "policy_pass":     M.policy_pass(pred),
        "identifier_valid": M.identifier_valid(pred),
        "hallucinated":    M.hallucinated(pred),
        "executes":        M.executes(pred),
        "result_match":    M.result_match(pred_rows, gt_rows, ordered),
        "predicted_row_count": len(pred_rows) if pred_rows is not None else None,
        "gt_row_count":        len(gt_rows)   if gt_rows   is not None else None,
        "error":            (pred.get("error") or "")[:200],
    }
    return rec


# ----------------------------------------------------------- reports -------


def _print_summary(df: pd.DataFrame) -> None:
    console.print("\n[bold]Overall metrics[/]\n")
    summary = (
        df.groupby("condition")
          .agg(
              n=("id", "count"),
              parse_rate=("parsed", "mean"),
              policy_pass_rate=("policy_pass", "mean"),
              identifier_valid_rate=("identifier_valid", "mean"),
              hallucination_rate=("hallucinated", "mean"),
              execution_rate=("executes", "mean"),
              result_match_rate=("result_match", "mean"),
              avg_attempts=("attempts", "mean"),
          )
          .reset_index()
    )

    t = Table(show_header=True, header_style="bold")
    t.add_column("Condition", style="cyan")
    for col in ["n", "parse", "policy", "ident_valid", "halluc", "exec", "match", "avg_attempts"]:
        t.add_column(col, justify="right")

    for _, row in summary.iterrows():
        t.add_row(
            row["condition"],
            str(int(row["n"])),
            f"{row['parse_rate']*100:.1f}%",
            f"{row['policy_pass_rate']*100:.1f}%",
            f"{row['identifier_valid_rate']*100:.1f}%",
            f"{row['hallucination_rate']*100:.1f}%",
            f"{row['execution_rate']*100:.1f}%",
            f"{row['result_match_rate']*100:.1f}%",
            f"{row['avg_attempts']:.2f}",
        )
    console.print(t)

    # Headline delta
    if {"baseline", "treatment"}.issubset(set(summary["condition"])):
        b = summary[summary["condition"] == "baseline"].iloc[0]
        t_ = summary[summary["condition"] == "treatment"].iloc[0]
        rel = (b["hallucination_rate"] - t_["hallucination_rate"]) / b["hallucination_rate"] if b["hallucination_rate"] else 0.0
        console.print(
            f"\n[bold green]Headline:[/] hallucination rate "
            f"{b['hallucination_rate']*100:.1f}% → {t_['hallucination_rate']*100:.1f}% "
            f"({rel*100:+.1f}% relative)"
        )
        rel_match = (t_["result_match_rate"] - b["result_match_rate"]) / max(b["result_match_rate"], 1e-9)
        console.print(
            f"[bold green]         [/] result-match rate "
            f"{b['result_match_rate']*100:.1f}% → {t_['result_match_rate']*100:.1f}% "
            f"({rel_match*100:+.1f}% relative)"
        )


def _print_failure_breakdown(df: pd.DataFrame) -> None:
    """Tag each failing row by primary cause for iteration."""
    console.print("\n[bold]Failure breakdown (treatment only)[/]\n")
    sub = df[(df["condition"] == "treatment") & (df["result_match"] == 0)]
    if sub.empty:
        console.print("  [green]no result-match failures[/]")
        return
    tags: list[str] = []
    for _, r in sub.iterrows():
        if not r["parsed"]:           tags.append("parse")
        elif not r["policy_pass"]:    tags.append("policy")
        elif not r["identifier_valid"]: tags.append("hallucination")
        elif not r["executes"]:       tags.append("runtime")
        else:                          tags.append("wrong_answer")
    sub = sub.assign(tag=tags)
    by_tag = sub["tag"].value_counts().to_dict()
    for tag, n in by_tag.items():
        console.print(f"  {tag:14s} {n}")


# ----------------------------------------------------------- entrypoint ----


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", default=str(ROOT / "queries.yaml"))
    ap.add_argument("--condition", choices=["baseline", "treatment", "both"], default="both")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
