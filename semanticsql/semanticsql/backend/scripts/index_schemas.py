"""CLI: rebuild ChromaDB from a metadata YAML.

Usage:
    python scripts/index_schemas.py --metadata ../databases/metadata/pagila.yaml --database pagila
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add the backend root to sys.path so `app.*` resolves when run from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.indexer import build_index  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata", required=True, type=Path)
    ap.add_argument("--database", required=False, default=None)
    args = ap.parse_args()

    n = build_index(args.metadata, database=args.database, reset=True)
    print(f"indexed {n} documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
