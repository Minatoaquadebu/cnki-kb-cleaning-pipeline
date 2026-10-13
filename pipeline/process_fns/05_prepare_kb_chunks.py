def prepare_kb_chunks(df):
    import hashlib
    import re
    from pathlib import Path
    if df is None or getattr(df, "empty", True):
        return df
    out = df.copy()
    num_re = re.compile(r"\d+(?:\.\d+)?")
    table_re = re.compile(r"<table\b.*?</table>", re.I | re.S)
    cell_re = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.I | re.S)
    row_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
    tag_re = re.compile(r"<[^>]+>")

    def table_to_md(table_html):
        grid = []
        for row in row_re.findall(table_html):
            cells = [tag_re.sub("", c).replace("\n", " ").strip() for c in cell_re.findall(row)]
            if cells:
                grid.append(cells)
        if not grid:
            return tag_re.sub("", table_html).strip()
        width = max(len(r) for r in grid)
        for row in grid:
            while len(row) < width:
                row.append("")
        lines = [
            "| " + " | ".join(grid[0]) + " |",
            "| " + " | ".join(["---"] * width) + " |",
        ]
        for row in grid[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def html_tables_to_md(text):
        t = str(text or "")
        if "<table" not in t.lower():
            return t
        return table_re.sub(lambda m: "\n" + table_to_md(m.group(0)) + "\n", t)

    def meta(source, kind):
        path = str(source or "")
        name = Path(path).stem
        low = path.lower()
        if ("官微" in path) or ("官网" in path) or ("wechat" in low):
            doc_type = "wechat"
        elif ("cnki" in low) or str(kind or "").lower() == "pdf":
            doc_type = "cnki"
        else:
            doc_type = str(kind or "unknown")
        date_m = re.search(r"(19|20)\d{2}-\d{2}-\d{2}", name)
        year_m = re.search(r"(19|20)\d{2}", path)
        date = date_m.group(0) if date_m else ""
        year = date[:4] if date else (year_m.group(0) if year_m else "")
        title = name
        if date:
            title = name.split(date, 1)[-1].lstrip("_- ")
        return doc_type, year, date, title

    cleaned_src = out["cleaned_chunk"] if "cleaned_chunk" in out.columns else ""
    raw_src = out["raw_chunk"] if "raw_chunk" in out.columns else ""
    kb_text = []
    fidelity = []
    invented = []
    kb_ids = []
    doc_types = []
    years = []
    dates = []
    titles = []
    kinds = out["kind"] if "kind" in out.columns else [""] * len(out)
    sources = out["source"] if "source" in out.columns else [""] * len(out)
    for i, (cleaned, raw, source, kind) in enumerate(zip(cleaned_src, raw_src, sources, kinds)):
        text = html_tables_to_md(cleaned)
        kb_text.append(text)
        raw_nums = set(num_re.findall(str(raw or "")))
        new_nums = sorted(set(num_re.findall(text)) - raw_nums)
        invented.append(",".join(new_nums))
        fidelity.append(len(new_nums) == 0)
        doc_type, year, date, title = meta(source, kind)
        doc_types.append(doc_type)
        years.append(year)
        dates.append(date)
        titles.append(title)
        digest = hashlib.sha1((str(source) + "\n" + text).encode("utf-8", "ignore")).hexdigest()[:16]
        kb_ids.append(digest)
    out["cleaned_chunk"] = kb_text
    out["kb_text"] = kb_text
    out["fidelity_ok"] = fidelity
    out["invented_numbers"] = invented
    out["doc_type"] = doc_types
    out["year"] = years
    out["doc_date"] = dates
    out["title"] = titles
    out["kb_id"] = kb_ids
    return out
