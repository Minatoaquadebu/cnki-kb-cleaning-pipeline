def export_kb_corpus(df):
    import re
    from pathlib import Path
    if df is None:
        return df
    out = df.copy()
    if getattr(out, "empty", True):
        out["kb_exported"] = False
        out["kb_export_path"] = ""
        return out
    if "kb_text" not in out.columns:
        out["kb_text"] = out["cleaned_chunk"] if "cleaned_chunk" in out.columns else ""
    out["_i"] = range(len(out))
    out["_h"] = out["kb_text"].fillna("").map(lambda t: re.sub(r"\s+", "", str(t).lower())[:800])
    if "doc_type" in out.columns:
        out["_rank"] = out["doc_type"].map(lambda x: 0 if str(x) == "cnki" else 1)
    else:
        out["_rank"] = 1
    blank = out["_h"].eq("")
    ranked = out.loc[~blank].sort_values(["_rank", "_i"], kind="stable")
    keep_idx = set(ranked.loc[~ranked["_h"].duplicated(keep="first")].index)
    keep_idx.update(out.loc[blank].index)
    out = out.loc[out.index.isin(keep_idx)].sort_values("_i", kind="stable")
    out = out.drop(columns=["_i", "_h", "_rank"]).reset_index(drop=True)
    path = Path(r"{{KB_EXPORT_PATH}}")
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [c for c in (
        "kb_id", "source", "kind", "doc_type", "year", "doc_date", "title",
        "text_path", "kb_text", "cleaned_chunk", "NgramScore", "LineDupRatio",
        "fidelity_ok", "invented_numbers",
    ) if c in out.columns]
    out.loc[:, cols].to_json(path, orient="records", lines=True, force_ascii=False)
    out["kb_exported"] = True
    out["kb_export_path"] = str(path)
    return out
