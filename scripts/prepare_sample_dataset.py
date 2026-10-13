#!/usr/bin/env python3
"""Write a tiny demo JSONL that points at the fictional sample markdown."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="samples/input.ready.jsonl",
        help="Output dataset JSONL path (relative to pack root or absolute)",
    )
    args = parser.parse_args()

    pack_root = Path(__file__).resolve().parents[1]
    md = (pack_root / "samples" / "markdown" / "sample_paper.md").resolve()
    if not md.is_file():
        raise SystemExit(f"Missing sample markdown: {md}")

    out = Path(args.out)
    if not out.is_absolute():
        out = pack_root / out
    out.parent.mkdir(parents=True, exist_ok=True)

    row = {"source": str(md), "kind": "markdown", "text_path": str(md)}
    out.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    print("In WebUI → Data Preparation, register this JSONL as a FileStorage dataset.")


if __name__ == "__main__":
    main()
