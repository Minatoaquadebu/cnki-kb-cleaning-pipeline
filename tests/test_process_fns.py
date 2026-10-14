"""Unit tests for process_fns (no WebUI / LLM required)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

PACK = Path(__file__).resolve().parents[1]
FN_DIR = PACK / "pipeline" / "process_fns"


def load_fn(filename: str, name: str):
    path = FN_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return getattr(mod, name)


@pytest.fixture(scope="module")
def prepare():
    return load_fn("05_prepare_kb_chunks.py", "prepare_kb_chunks")


@pytest.fixture(scope="module")
def keep_body():
    return load_fn("09_keep_body_chunks.py", "keep_body_chunks")


@pytest.fixture(scope="module")
def export_kb(tmp_path_factory):
    # Rewrite placeholder export path by exec with patched source
    src = (FN_DIR / "10_export_kb_corpus.py").read_text(encoding="utf-8")
    export_path = tmp_path_factory.mktemp("kb") / "out.jsonl"
    src = src.replace("{{KB_EXPORT_PATH}}", str(export_path).replace("\\", "\\\\"))
    ns: dict = {}
    exec(compile(src, "export_kb_corpus.py", "exec"), ns, ns)
    fn = ns["export_kb_corpus"]
    fn._export_path = export_path  # type: ignore[attr-defined]
    return fn


def test_meta_pdf_not_auto_cnki(prepare):
    df = pd.DataFrame(
        [
            {
                "source": r"D:\papers\research\my_paper.pdf",
                "kind": "pdf",
                "raw_chunk": "产值达到1000万元。",
                "cleaned_chunk": "产值达到1000万元。",
            }
        ]
    )
    out = prepare(df)
    assert out.iloc[0]["doc_type"] == "pdf"
    assert bool(out.iloc[0]["fidelity_ok"]) is True


def test_year_from_stem_not_path(prepare):
    df = pd.DataFrame(
        [
            {
                "source": r"D:\archive_2019\papers\2024-03-01_碳捕集技术.pdf",
                "kind": "cnki",
                "raw_chunk": "正文内容足够长" * 5,
                "cleaned_chunk": "正文内容足够长" * 5,
            }
        ]
    )
    out = prepare(df)
    assert out.iloc[0]["year"] == "2024"
    assert out.iloc[0]["doc_date"] == "2024-03-01"
    assert out.iloc[0]["doc_type"] == "cnki"


def test_fidelity_number_format_not_invented(prepare):
    df = pd.DataFrame(
        [
            {
                "source": "a.md",
                "kind": "markdown",
                "raw_chunk": "压力为 1 000 kPa，约为 1.20 MPa。",
                "cleaned_chunk": "压力为1000 kPa，约为1.2 MPa。",
            }
        ]
    )
    out = prepare(df)
    assert bool(out.iloc[0]["fidelity_ok"]) is True
    assert int(out.iloc[0]["invented_number_count"]) == 0


def test_fidelity_severe_many_new_numbers(prepare):
    df = pd.DataFrame(
        [
            {
                "source": "a.md",
                "kind": "markdown",
                "raw_chunk": "实验完成。",
                "cleaned_chunk": "实验得到 11、22、33、44、55 五个结果。",
            }
        ]
    )
    out = prepare(df)
    assert bool(out.iloc[0]["fidelity_severe"]) is True
    assert bool(out.iloc[0]["fidelity_ok"]) is False


def test_keep_references_en(keep_body):
    df = pd.DataFrame(
        {
            "cleaned_chunk": [
                    "这是正文段落，包含足够多的汉字用于通过长度检查。" * 5,
                "References\n[1] Smith 2019\n[2] Jones 2020\n[3] Lee 2021\n[4] Chen 2022",
                "参 考 文 献\n[1] 张三\n[2] 李四\n[3] 王五\n[4] 赵六",
            ]
        }
    )
    out = keep_body(df)
    assert len(out) == 1
    assert "正文" in out.iloc[0]["cleaned_chunk"]


def test_export_exact_and_near_dedupe(export_kb):
    text_a = "碳捕集与封存技术是降低工业排放的重要路径。" * 20
    text_b = text_a  # exact
    text_c = text_a[:-3] + "路径。"  # near
    df = pd.DataFrame(
        [
            {"kb_text": text_a, "doc_type": "cnki", "source": "a.pdf", "kb_id": "1"},
            {"kb_text": text_b, "doc_type": "pdf", "source": "b.pdf", "kb_id": "2"},
            {"kb_text": text_c, "doc_type": "pdf", "source": "c.pdf", "kb_id": "3"},
            {"kb_text": "完全不同的另一段知识库内容用于保留。" * 15, "doc_type": "pdf", "source": "d.pdf", "kb_id": "4"},
        ]
    )
    out = export_kb(df)
    path = export_kb._export_path
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) >= 2
    assert bool(out.iloc[0]["kb_exported"]) is True
    assert "pipeline_version" in lines[0]
