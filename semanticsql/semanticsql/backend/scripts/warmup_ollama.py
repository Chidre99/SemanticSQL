"""Pre-load the Ollama model so the first real query doesn't pay the cold-start cost.

Usage: python scripts/warmup_ollama.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.stream import complete  # noqa: E402


async def main() -> int:
    started = time.perf_counter()
    print("warming up the model (this can take ~10–30s on first run)...")
    try:
        out = await complete(
            [
                {"role": "system", "content": "Reply with only the word OK."},
                {"role": "user", "content": "ready?"},
            ]
        )
    except Exception as e:  # noqa: BLE001
        print(f"warmup failed: {e}")
        return 1
    elapsed = time.perf_counter() - started
    print(f"warmup ok in {elapsed:.1f}s — model said: {out.strip()[:80]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
