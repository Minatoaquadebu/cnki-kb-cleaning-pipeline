#!/usr/bin/env python3
"""Inject pipeline/process_fns/*.py into cleaning_*.json (single source of truth).

Edit process_fns/, then run this before materialize / publish / import.
Also patches tokenizer (bert-base-chinese) and soft fidelity filter.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


TARGETS: List[Tuple[str, List[Tuple[str, str]]]] = [
    (
        "pipeline/cleaning_only.json",
        [
            ("03_stitch_broken_tables.py", "stitch_broken_tables"),
            ("05_prepare_kb_chunks.py", "prepare_kb_chunks"),
            ("09_keep_body_chunks.py", "keep_body_chunks"),
            ("10_export_kb_corpus.py", "export_kb_corpus"),
        ],
    ),
    (
        "pipeline/cleaning_plus_qa.json",
        [
            ("03_stitch_broken_tables.py", "stitch_broken_tables"),
            ("05_prepare_kb_chunks.py", "prepare_kb_chunks"),
            ("09_keep_body_chunks.py", "keep_body_chunks"),
            ("10_export_kb_corpus.py", "export_kb_corpus"),
        ],
    ),
]


def load_fn_source(path: Path, def_name: str) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"(?m)^def {re.escape(def_name)}\(", text)
    if not m:
        raise SystemExit(f"def {def_name} not found in {path}")
    return text[m.start():].rstrip() + "\n"


def find_nodes(data: dict) -> List[dict]:
    for key in ("ops", "operators", "nodes", "steps"):
        val = data.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict) and "name" in val[0]:
            return val
    cfg = data.get("config")
    if isinstance(cfg, dict):
        return find_nodes(cfg)
    raise SystemExit("Could not find operator list in pipeline JSON")


def bump_version(data: dict) -> None:
    data["version"] = "2.0.0"
    desc = str(data.get("description") or "")
    if "kb-clean-2.0" not in desc:
        data["description"] = (
            desc.rstrip(".")
            + ". Hardening: zh tokenizer, soft fidelity, SimHash dedupe, "
            "incremental export, richer metadata (kb-clean-2.0)."
        )


def inject(obj: Any, sources: Dict[str, str], counter: List[int]) -> Any:
    if isinstance(obj, list):
        return [inject(x, sources, counter) for x in obj]
    if isinstance(obj, dict):
        if obj.get("name") == "process_fn":
            val = obj.get("value")
            if isinstance(val, list) and val and isinstance(val[0], str):
                src = val[0]
                for def_name, body in sources.items():
                    if src.lstrip().startswith(f"def {def_name}("):
                        counter[0] += 1
                        return {**obj, "value": [body]}
        return {k: inject(v, sources, counter) for k, v in obj.items()}
    return obj


def patch_tokenizer_and_filters(data: dict) -> None:
    nodes = find_nodes(data)
    for node in nodes:
        if node.get("name") == "KBCChunkGenerator":
            init = (node.get("params") or {}).get("init") or []
            for p in init:
                if p.get("name") == "tokenizer_name":
                    p["value"] = "bert-base-chinese"
                # Keep chunk_size / overlap numeric values; they are token counts
                # for the Chinese tokenizer (not English bert-base-uncased).
            node["comment"] = (
                "Chunk with bert-base-chinese (token budget = chunk_size, recursive)."
            )
        if node.get("name") == "GeneralFilter":
            init = (node.get("params") or {}).get("init") or []
            for p in init:
                if p.get("name") == "filter_rules" and isinstance(p.get("value"), list):
                    new_rules = []
                    for rule in p["value"]:
                        if isinstance(rule, str) and "fidelity_ok" in rule:
                            new_rules.append(
                                'lambda df: (~df["fidelity_severe"].fillna(False)) '
                                'if "fidelity_severe" in df.columns '
                                'else df["fidelity_ok"].fillna(True)'
                            )
                        else:
                            new_rules.append(rule)
                    p["value"] = new_rules


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", default=None)
    args = parser.parse_args()
    pack_root = Path(args.pack_root or Path(__file__).resolve().parents[1])
    fn_dir = pack_root / "pipeline" / "process_fns"

    for rel, mapping in TARGETS:
        path = pack_root / rel
        if not path.exists():
            print(f"skip missing {path}")
            continue
        sources = {
            def_name: load_fn_source(fn_dir / fname, def_name)
            for fname, def_name in mapping
        }
        data = json.loads(path.read_text(encoding="utf-8"))
        counter = [0]
        data = inject(data, sources, counter)
        patch_tokenizer_and_filters(data)
        bump_version(data)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"{path.name}: injected {counter[0]} process_fn(s)")


if __name__ == "__main__":
    main()
