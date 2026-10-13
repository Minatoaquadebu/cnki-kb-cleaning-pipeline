#!/usr/bin/env python3
"""Replace placeholders in a portable pipeline JSON and write a ready-to-import config."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def replace_in_obj(obj: Any, mapping: Dict[str, str]) -> Any:
    if isinstance(obj, str):
        out = obj
        for key, value in mapping.items():
            out = out.replace(key, value)
        return out
    if isinstance(obj, list):
        return [replace_in_obj(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {k: replace_in_obj(v, mapping) for k, v in obj.items()}
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        default="pipeline/cleaning_only.json",
        help="Template JSON inside this pack (cleaning_only.json or cleaning_plus_qa.json)",
    )
    parser.add_argument("--serving-id", required=True, help="WebUI Serving id")
    parser.add_argument(
        "--intermediate-dir",
        required=True,
        help="MinerU intermediate directory (created if missing)",
    )
    parser.add_argument(
        "--export-path",
        required=True,
        help="Output knowledge-base JSONL path",
    )
    parser.add_argument(
        "--out",
        default="pipeline/materialized.json",
        help="Where to write the materialized pipeline JSON",
    )
    args = parser.parse_args()

    pack_root = Path(__file__).resolve().parents[1]
    template_path = (pack_root / args.template).resolve()
    out_path = (pack_root / args.out).resolve()

    intermediate = str(Path(args.intermediate_dir).expanduser().resolve())
    export_path = str(Path(args.export_path).expanduser().resolve())
    mapping = {
        "{{LLM_SERVING_ID}}": args.serving_id,
        "{{INTERMEDIATE_DIR}}": intermediate,
        "{{KB_EXPORT_PATH}}": export_path,
    }

    data = json.loads(template_path.read_text(encoding="utf-8"))
    data = replace_in_obj(data, mapping)

    Path(intermediate).mkdir(parents=True, exist_ok=True)
    Path(export_path).parent.mkdir(parents=True, exist_ok=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    print("Next: register your dataset in WebUI, then import this config (see README).")


if __name__ == "__main__":
    main()
