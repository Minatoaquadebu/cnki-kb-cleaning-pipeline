#!/usr/bin/env python3
"""Import a materialized pipeline JSON into a running local DataFlow-WebUI.

Requires WebUI at http://127.0.0.1:8000 (or --base-url).
Does not write API keys. You must already have a Serving registered.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path


def api(base: str, method: str, path: str, body=None):
    url = base.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pipeline",
        default="pipeline/materialized.json",
        help="Materialized pack JSON from materialize_pipeline.py",
    )
    parser.add_argument("--dataset-id", required=True, help="Dataset id already registered in WebUI")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--name", default=None, help="Override pipeline display name")
    args = parser.parse_args()

    pack_root = Path(__file__).resolve().parents[1]
    path = Path(args.pipeline)
    if not path.is_absolute():
        path = pack_root / path
    pack = json.loads(path.read_text(encoding="utf-8"))
    config = pack.get("config") or pack
    if "operators" not in config:
        raise SystemExit("Pipeline JSON missing config.operators")

    config = json.loads(json.dumps(config))  # deep copy via json
    config["file_path"] = ""
    config.setdefault("input_dataset", {})
    config["input_dataset"]["id"] = args.dataset_id

    # Validate first (endpoint expects PipelineConfig body, not a wrapper)
    try:
        val = api(args.base_url, "POST", "/api/v1/pipelines/validate", config)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Validate HTTP {e.code}: {detail}") from e

    payload = val.get("data") if isinstance(val, dict) and "data" in val else val
    if isinstance(payload, dict) and (
        payload.get("ok") is False or payload.get("valid") is False
    ):
        raise SystemExit(f"Validation failed: {json.dumps(payload, ensure_ascii=False, indent=2)}")

    body = {
        "name": args.name or pack.get("name") or "KB Text Cleaning",
        "config": config,
        "tags": pack.get("tags") or ["cleaning", "portable"],
    }
    try:
        created = api(args.base_url, "POST", "/api/v1/pipelines/", body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Create HTTP {e.code}: {detail}") from e

    print(json.dumps(created, ensure_ascii=False, indent=2))
    print("Imported. Open WebUI canvas, pick the new pipeline, bind Serving if needed, then run.")


if __name__ == "__main__":
    main()
