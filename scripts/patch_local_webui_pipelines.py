#!/usr/bin/env python3
"""Patch local DataFlow-WebUI pipeline_registry.json with hardened process_fns."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "scripts"))
from sync_process_fns import inject, load_fn_source, patch_tokenizer_and_filters  # noqa: E402

FN_MAP = [
    ("03_stitch_broken_tables.py", "stitch_broken_tables"),
    ("05_prepare_kb_chunks.py", "prepare_kb_chunks"),
    ("09_keep_body_chunks.py", "keep_body_chunks"),
    ("10_export_kb_corpus.py", "export_kb_corpus"),
]

DEFAULT_IDS = [
    "bab85d76-6abd-428e-acc2-9d987fa1785e",
    "5858ed12-2567-46b8-8601-94a1c4e25973",
    "cdedf66e-bff2-4d27-a7b2-a7db7bca58e1",
]

# Known local export targets (from historical runs)
KNOWN_EXPORTS = {
    "bab85d76-6abd-428e-acc2-9d987fa1785e": r"D:\DataFlow-WebUI-main\backend\data\kb_corpus\cnki_wechat_trial4.jsonl",
    "5858ed12-2567-46b8-8601-94a1c4e25973": r"D:\DataFlow-WebUI-main\backend\data\kb_corpus\cnki_papers_full.jsonl",
    "cdedf66e-bff2-4d27-a7b2-a7db7bca58e1": r"D:\DataFlow-WebUI-main\backend\data\kb_corpus\github_pack_test.jsonl",
}


def find_export_path(config: dict, pipeline_id: str, task_registry: Optional[Path]) -> Optional[str]:
    if pipeline_id in KNOWN_EXPORTS:
        return KNOWN_EXPORTS[pipeline_id]
    blob = json.dumps(config, ensure_ascii=False)
    for m in re.finditer(r'Path\(r?"([^"]+\.jsonl)"\)', blob.replace("\\\\", "\\")):
        p = m.group(1)
        if "{{" not in p:
            return p
    if task_registry and task_registry.exists():
        text = task_registry.read_text(encoding="utf-8")
        # Prefer path near this pipeline id
        idx = text.find(pipeline_id)
        window = text[idx : idx + 200000] if idx >= 0 else text
        for m in re.finditer(
            r'def export_kb_corpus\(df\):.*?Path\(r?"([^"]+\.jsonl)"\)',
            window,
            flags=re.S,
        ):
            p = m.group(1).replace("\\\\", "\\")
            if "{{" not in p:
                return p
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--task-registry", default=None)
    parser.add_argument("--ids", nargs="*", default=DEFAULT_IDS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    registry_path = Path(args.registry)
    task_path = Path(args.task_registry) if args.task_registry else registry_path.parent / "task_registry.json"
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    pipelines: Dict[str, Any] = data.get("pipelines") or data
    fn_dir = PACK / "pipeline" / "process_fns"
    base_sources = {
        def_name: load_fn_source(fn_dir / fname, def_name)
        for fname, def_name in FN_MAP
    }

    for pid in args.ids:
        pl = pipelines.get(pid)
        if not pl:
            print(f"missing {pid}")
            continue
        cfg = pl.get("config")
        if not isinstance(cfg, dict):
            print(f"no config on {pid}")
            continue
        export_path = find_export_path(cfg, pid, task_path)
        sources = dict(base_sources)
        if export_path:
            sources["export_kb_corpus"] = sources["export_kb_corpus"].replace(
                "{{KB_EXPORT_PATH}}", export_path
            )
            print(f"  export_path={export_path}")
        else:
            print(f"  WARN: kept placeholder for {pid[:8]}")

        counter = [0]
        pl["config"] = inject(cfg, sources, counter)
        patch_tokenizer_and_filters({"config": pl["config"]})
        print(f"{pid[:8]}… injected {counter[0]} fns → {pl.get('name')}")

    if args.dry_run:
        print("dry-run: not writing")
        return
    registry_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {registry_path}")


if __name__ == "__main__":
    main()
