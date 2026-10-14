# KB Text Cleaning Pipeline（可移植包）

把 PDF / Markdown 论文清洗成可检索的知识库 JSONL，可在 DataFlow-WebUI 中直接导入使用。

本包从院发 CNKI 清洗实践中抽离，**不含 API Key、不含本机绝对路径、不含真实论文原文**。样例文本为虚构演示数据。

**版本 2.0.0（kb-clean-2.0）**：中文 tokenizer、数字保真软闸门、SimHash 近重、增量合并导出、元数据/溯源字段；`process_fns/` 为唯一源码真相，改完后必须 `python scripts/sync_process_fns.py`。

## 管线做什么

默认使用 `pipeline/cleaning_only.json`（10 步）：

1. **FileOrURLToMarkdownConverterAPI** — PDF 经 MinerU 转 Markdown（已有 md 可跳过解析逻辑，直接给 `text_path`）
2. **KBCChunkGenerator** — `bert-base-chinese`，`chunk_size`/`chunk_overlap` 为 **token** 预算（默认 1600/240），recursive
3. **stitch_broken_tables** — 合并被切断的 HTML 表
4. **KBCTextCleaner** — LLM 清洗（中文 `KnowledgeCleanerPrompt`）
5. **prepare_kb_chunks** — 表转 MD、元数据、页眉页脚/乱码轻清理、数字保真（归一化后软判定）
6. **NgramSampleEvaluator** — 重复度评分
7. 质量指标列 — `LineDupRatio` / `NgramRepeatRatio` / `kb_ok`
8. **GeneralFilter** — 丢掉过短、破表、高重复；仅丢弃 **严重** 数字编造（`fidelity_severe`）
9. **keep_body_chunks** — 丢掉参考文献（中/英）与公式噪声块
10. **export_kb_corpus** — 精确+SimHash 去重，按 `kb_id` **增量合并** 导出，写入 `pipeline_version`/`parser`

可选：`pipeline/cleaning_plus_qa.json` 在导出后再做 Text2QA + 过滤（多消耗 LLM 调用）。

## 你需要准备

1. 已安装并可打开的 **DataFlow-WebUI**（本机 `http://127.0.0.1:8000`）
2. 在 **Serving Manager** 配好一条 `APILLMServing_request`（DeepSeek / 其他 OpenAI 兼容 / 局域网模型均可）
3. 记下该 Serving 的 **id**
4. MinerU 可用（若输入是 PDF）；若只有 Markdown，见下文「只用 Markdown」

**不要**把 API Key 写进本仓库或 issue。

## 快速开始（推荐）

假设：

- WebUI 仓库根目录为 `DATAFLOW_WEBUI`
- 本包目录为 `PACK`（即本 README 所在目录）
- Serving id 为 `YOUR_SERVING_ID`

### 1. 生成样例数据集（可先跑通）

```bash
cd PACK
python scripts/prepare_sample_dataset.py
```

会得到 `samples/input.ready.jsonl`，指向虚构样例 `samples/markdown/sample_paper.md`。

在 WebUI → **Data Preparation** 注册该 JSONL，记下 **dataset id**。

### 2. 填入路径与 Serving，生成可导入配置

在 Windows PowerShell 示例（请改成你的真实路径）：

```powershell
cd PACK
python scripts/materialize_pipeline.py `
  --template pipeline/cleaning_only.json `
  --serving-id YOUR_SERVING_ID `
  --intermediate-dir "$env:DATAFLOW_WEBUI\backend\data\kbc_user_papers" `
  --export-path "$env:DATAFLOW_WEBUI\backend\data\kb_corpus\cleaned_corpus.jsonl" `
  --out pipeline/materialized.json
```

Linux / macOS：

```bash
cd PACK
python scripts/materialize_pipeline.py \
  --template pipeline/cleaning_only.json \
  --serving-id YOUR_SERVING_ID \
  --intermediate-dir "$DATAFLOW_WEBUI/backend/data/kbc_user_papers" \
  --export-path "$DATAFLOW_WEBUI/backend/data/kb_corpus/cleaned_corpus.jsonl" \
  --out pipeline/materialized.json
```

### 3. 导入 WebUI

WebUI 已启动时：

```bash
python scripts/import_into_webui.py \
  --pipeline pipeline/materialized.json \
  --dataset-id YOUR_DATASET_ID \
  --base-url http://127.0.0.1:8000
```

然后在画布打开新管线并执行。跑完后查看 `--export-path` 指向的 JSONL。

若自动导入失败，也可在 WebUI 里新建管线，对照 `pipeline/materialized.json` 里的算子与参数手工配置；`pipeline/process_fns/` 下有各 `PandasOperator` 源码便于复制。

## 换成自己的 PDF / Markdown

输入 JSONL 每行至少：

```json
{"source": "C:/path/to/paper.pdf", "kind": "pdf"}
```

或已有 Markdown：

```json
{"source": "C:/path/to/paper.md", "kind": "markdown", "text_path": "C:/path/to/paper.md"}
```

- `kind=pdf`：走 MinerU，结果写到 `INTERMEDIATE_DIR`
- `kind=markdown`：请同时提供可读的 `text_path`（可与 `source` 相同）

一次可多行。先用 1～2 篇试跑，再上全量。

## Serving 怎么填

WebUI → **Serving Manager** → 新建 `APILLMServing_request`：

| 字段 | 示例 |
|------|------|
| `api_url` | `https://api.deepseek.com/v1/chat/completions` 或 `http://192.168.x.x:8000/v1/chat/completions` |
| `model_name` | 与服务端一致 |
| API Key | 只保存在本机 Serving，勿提交 Git |

把生成的 Serving **id** 传给 `materialize_pipeline.py --serving-id`。

## 目录说明

```
cnki-kb-cleaning-pipeline/
  README.md
  LICENSE
  requirements.txt           # 仅单测依赖（pandas/pytest）
  pipeline/
    cleaning_only.json       # 由 sync 从 process_fns 生成内联代码
    cleaning_plus_qa.json
    process_fns/             # ★ 唯一源码真相（改这里）
  tests/
    test_process_fns.py
  samples/
    markdown/sample_paper.md
    input.jsonl
  scripts/
    sync_process_fns.py      # process_fns → JSON
    materialize_pipeline.py
    import_into_webui.py
    prepare_sample_dataset.py
    patch_local_webui_pipelines.py  # 可选：同步到本机 WebUI registry
```

## 修改 process_fn 后

```bash
python scripts/sync_process_fns.py
python -m pytest tests/ -q
```

再 `materialize` / 导入。不要只改 JSON 里转义字符串。

## 单测

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
```

## 注意

- 导出为按 `kb_id` 合并；若要全新文件请换 `--export-path` 或先删旧 JSONL。
- 元数据仍以文件名 + 块内浅层字段为主；PDF 内嵌 bibliographic 解析未做完整 Crossref 级抽取。
- LLM 步骤仍受 Serving/Ray 调度约束；后处理已去掉脆弱硬删，但不是多进程并行重写。
- 历史任务的 DeepSeek 缓存命中率不会出现在本包里；那是 WebUI Serving 运行时统计。
- 请勿上传他人版权论文或密钥到公开仓库。

## 许可证

MIT（见 `LICENSE`）。DataFlow / DataFlow-WebUI 本身遵循其上游许可证。
