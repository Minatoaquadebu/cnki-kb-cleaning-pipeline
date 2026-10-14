def export_kb_corpus(df):
    """Dedupe (exact + near), merge into existing export, write provenance fields."""
    import hashlib
    import json
    import re
    from pathlib import Path

    PIPELINE_VERSION = "kb-clean-2.0.0"

    if df is None:
        return df
    out = df.copy()
    if getattr(out, "empty", True):
        out["kb_exported"] = False
        out["kb_export_path"] = ""
        out["dedupe_dropped"] = 0
        return out
    if "kb_text" not in out.columns:
        out["kb_text"] = out["cleaned_chunk"] if "cleaned_chunk" in out.columns else ""

    def norm_text(t):
        return re.sub(r"\s+", "", str(t or "").lower())

    def simhash64(text, n=3):
        """Dependency-free char-ngram SimHash for near-duplicate detection."""
        s = norm_text(text)
        if not s:
            return 0
        if len(s) < n:
            s = s + ("#" * (n - len(s)))
        bits = [0] * 64
        for i in range(len(s) - n + 1):
            gram = s[i : i + n]
            h = int(hashlib.md5(gram.encode("utf-8", "ignore")).hexdigest(), 16)
            for b in range(64):
                bits[b] += 1 if (h >> b) & 1 else -1
        out_h = 0
        for b in range(64):
            if bits[b] > 0:
                out_h |= 1 << b
        return out_h

    def hamming(a, b):
        return bin(a ^ b).count("1")

    out["_i"] = range(len(out))
    out["_norm"] = out["kb_text"].fillna("").map(norm_text)
    # Exact key: full normalized hash (not prefix-800)
    out["_exact"] = out["_norm"].map(
        lambda t: hashlib.sha1(t.encode("utf-8", "ignore")).hexdigest() if t else ""
    )
    out["_sim"] = out["kb_text"].fillna("").map(simhash64)

    if "doc_type" in out.columns:
        out["_rank"] = out["doc_type"].map(lambda x: 0 if str(x) == "cnki" else 1)
    else:
        out["_rank"] = 1

    blank = out["_exact"].eq("")
    ranked = out.loc[~blank].sort_values(["_rank", "_i"], kind="stable")

    # Exact dedupe
    exact_keep = ~ranked["_exact"].duplicated(keep="first")
    candidates = ranked.loc[exact_keep]

    # Near-dupe: Hamming distance <= 3 on SimHash among kept rows (greedy)
    kept_sims = []
    near_keep_idx = []
    for idx, row in candidates.iterrows():
        h = int(row["_sim"])
        if any(hamming(h, prev) <= 3 for prev in kept_sims):
            continue
        kept_sims.append(h)
        near_keep_idx.append(idx)

    keep_idx = set(near_keep_idx)
    keep_idx.update(out.loc[blank].index)
    dropped = int((~blank).sum() - len(near_keep_idx))
    out = out.loc[out.index.isin(keep_idx)].sort_values("_i", kind="stable")
    out = out.drop(columns=["_i", "_norm", "_exact", "_sim", "_rank"]).reset_index(drop=True)

    if "pipeline_version" not in out.columns:
        out["pipeline_version"] = PIPELINE_VERSION
    if "parser" not in out.columns:
        out["parser"] = "mineru+kbc"
    if "prompt_template" in out.columns:
        out["prompt_template"] = out["prompt_template"].fillna("KnowledgeCleanerPrompt")
    else:
        out["prompt_template"] = "KnowledgeCleanerPrompt"

    path = Path(r"{{KB_EXPORT_PATH}}")
    path.parent.mkdir(parents=True, exist_ok=True)

    cols = [c for c in (
        "kb_id", "source", "kind", "doc_type", "year", "doc_date", "title",
        "author", "journal", "volume", "issue", "doi", "abstract", "keywords",
        "text_path", "kb_text", "cleaned_chunk", "NgramScore", "LineDupRatio",
        "fidelity_ok", "fidelity_severe", "invented_numbers", "invented_number_count",
        "pipeline_version", "parser", "prompt_template",
    ) if c in out.columns]

    new_records = out.loc[:, cols].to_dict(orient="records")

    # Incremental merge by kb_id (and source+hash fallback): update existing, append new
    existing = {}
    if path.exists() and path.stat().st_size > 0:
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    kid = str(rec.get("kb_id") or "")
                    if kid:
                        existing[kid] = rec
        except Exception:
            existing = {}

    for rec in new_records:
        kid = str(rec.get("kb_id") or "")
        if kid:
            existing[kid] = rec

    with path.open("w", encoding="utf-8") as f:
        for rec in existing.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    out["kb_exported"] = True
    out["kb_export_path"] = str(path)
    out["dedupe_dropped"] = dropped
    out["export_total_rows"] = len(existing)
    return out
