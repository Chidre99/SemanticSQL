"""Inspect retrieval for a single question.

Usage:
    python scripts/inspect_retrieval.py --database pagila "How many films are rated PG-13?"
    python scripts/inspect_retrieval.py --database chinook "Top 10 best-selling tracks by revenue"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.retriever import retrieve  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database", required=True)
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("question", nargs="+")
    args = ap.parse_args()
    q = " ".join(args.question)

    chunks = retrieve(q, args.database, k=args.k)
    print(f"\n=== retrieval for: {q!r} ({args.database}) ===\n")
    for i, c in enumerate(chunks, 1):
        print(f"--- [{i}] {c.doc_type:8s}  table={c.table:24s}  score={c.score:.3f} ---")
        print(c.text)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
