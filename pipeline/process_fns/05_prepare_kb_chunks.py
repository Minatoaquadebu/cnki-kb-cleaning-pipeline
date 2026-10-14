def prepare_kb_chunks(df):
    """Table→MD, metadata, number fidelity, light header/footer & encoding cleanup."""
    import hashlib
    import re
    import unicodedata
    from pathlib import Path

    PIPELINE_VERSION = "kb-clean-2.0.0"
    PARSER_ID = "mineru+kbc"

    if df is None or getattr(df, "empty", True):
        return df
    out = df.copy()

    # Numbers with optional thousand separators / spaces; allow trailing decimals.
    num_re = re.compile(r"(?<![\w.])\d{1,3}(?:[\s,]\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?")
    table_re = re.compile(r"<table\b.*?</table>", re.I | re.S)
    cell_re = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.I | re.S)
    row_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
    tag_re = re.compile(r"<[^>]+>")
    doi_re = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
    year_in_name_re = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
    date_in_name_re = re.compile(r"(19|20)\d{2}-\d{2}-\d{2}")
    header_footer_re = re.compile(
        r"^(?:"
        r"第?\s*\d+\s*页"
        r"|\d+\s*/\s*\d+"
        r"|page\s*\d+(?:\s*of\s*\d+)?"
        r"|-\s*\d+\s*-"
        r")$",
        re.I,
    )
    # Common CNKI / PDF running headers (short lines repeated).
    running_header_re = re.compile(
        r"^(中国知网|知网|CNKI|万方|维普|超星|"
        r"下载|打印|收藏|分享|"
        r"DOI[:：].*)$",
        re.I,
    )
    mojibake_map = {
        "â€œ": "“",
        "â€": "”",
        "â€˜": "‘",
        "â€™": "’",
        "â€”": "—",
        "â€“": "–",
        "Â·": "·",
        "Â": "",
        "Ã—": "×",
        "ï¼š": "：",
        "ï¼Œ": "，",
        "ã€": "、",
    }

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

    def fix_encoding(text):
        t = str(text or "")
        for bad, good in mojibake_map.items():
            if bad in t:
                t = t.replace(bad, good)
        t = unicodedata.normalize("NFKC", t)
        # Heal numbers broken across newlines: "1\n000" / "12.\n5"
        t = re.sub(r"(\d)\s*\n\s*(\d)", r"\1\2", t)
        t = re.sub(r"(\d)\.\s*\n\s*(\d)", r"\1.\2", t)
        return t

    def strip_headers_footers(text):
        lines = str(text or "").splitlines()
        kept = []
        for line in lines:
            s = line.strip()
            if not s:
                kept.append(line)
                continue
            if header_footer_re.match(s):
                continue
            if running_header_re.match(s) and len(s) < 40:
                continue
            # Lone page number
            if re.fullmatch(r"\d{1,4}", s) and len(kept) > 0:
                continue
            kept.append(line)
        return "\n".join(kept)

    def normalize_number_token(tok):
        s = str(tok).replace(",", "").replace(" ", "").replace("\u3000", "")
        if not s:
            return ""
        try:
            if "." in s:
                v = float(s)
                # Collapse 1.20 / 1.2
                if v == int(v) and abs(v) < 1e15:
                    return str(int(v))
                return ("%f" % v).rstrip("0").rstrip(".")
            return str(int(s))
        except Exception:
            return s

    def number_set(text):
        return {normalize_number_token(m.group(0)) for m in num_re.finditer(str(text or "")) if normalize_number_token(m.group(0))}

    def extract_from_text(text):
        t = str(text or "")
        author = journal = volume = issue = doi = abstract = keywords = ""
        doi_m = doi_re.search(t)
        if doi_m:
            doi = doi_m.group(0).rstrip(".")
        # First ~1200 chars often carry front-matter cues
        head = t[:1200]
        for pat, key in (
            (r"(?:作者|作者姓名|Author[s]?)\s*[:：]\s*([^\n]{2,80})", "author"),
            (r"(?:期刊|刊物|Journal)\s*[:：]\s*([^\n]{2,80})", "journal"),
            (r"(?:卷)\s*[:：]?\s*(\d+)", "volume"),
            (r"(?:期)\s*[:：]?\s*(\d+)", "issue"),
            (r"(?:摘要|Abstract)\s*[:：]?\s*([^\n]{10,400})", "abstract"),
            (r"(?:关键词|Key\s*words?)\s*[:：]\s*([^\n]{2,200})", "keywords"),
        ):
            m = re.search(pat, head, re.I)
            if not m:
                continue
            val = m.group(1).strip()
            if key == "author":
                author = val
            elif key == "journal":
                journal = val
            elif key == "volume":
                volume = val
            elif key == "issue":
                issue = val
            elif key == "abstract":
                abstract = val
            elif key == "keywords":
                keywords = val
        return author, journal, volume, issue, doi, abstract, keywords

    def meta(source, kind):
        path = str(source or "")
        name = Path(path).stem
        low = path.lower()
        kind_l = str(kind or "").lower().strip()

        if ("官微" in path) or ("官网" in path) or ("wechat" in low):
            doc_type = "wechat"
        elif "cnki" in low or kind_l == "cnki":
            doc_type = "cnki"
        elif kind_l in ("pdf", "markdown", "md", "html", "docx", "txt"):
            # Never infer cnki from kind==pdf alone
            doc_type = kind_l if kind_l != "md" else "markdown"
        elif kind_l:
            doc_type = kind_l
        else:
            doc_type = "unknown"

        # Year/date only from filename stem (not full path — avoids path folder years)
        date_m = date_in_name_re.search(name)
        date = date_m.group(0) if date_m else ""
        if date:
            year = date[:4]
        else:
            year_m = year_in_name_re.search(name)
            year = year_m.group(1) if year_m else ""

        title = name
        if date:
            title = name.split(date, 1)[-1].lstrip("_- ")
        # Strip leading year_
        title = re.sub(r"^(?:19|20)\d{2}[_:\-\s]+", "", title).strip() or name

        # Author-ish prefix: "张三_题目" / "Zhang_Title"
        author_guess = ""
        am = re.match(r"^([\u4e00-\u9fff]{2,4}|[A-Za-z][A-Za-z.\- ]{1,40})[_-]", title)
        if am and len(title) > len(am.group(0)) + 4:
            author_guess = am.group(1).strip()
            title = title[len(am.group(0)):].strip() or title

        return doc_type, year, date, title, author_guess

    cleaned_src = out["cleaned_chunk"] if "cleaned_chunk" in out.columns else [""] * len(out)
    raw_src = out["raw_chunk"] if "raw_chunk" in out.columns else [""] * len(out)
    kinds = out["kind"] if "kind" in out.columns else [""] * len(out)
    sources = out["source"] if "source" in out.columns else [""] * len(out)

    kb_text, fidelity, invented, invented_n = [], [], [], []
    fidelity_severe = []
    kb_ids = []
    doc_types, years, dates, titles = [], [], [], []
    authors, journals, volumes, issues, dois, abstracts, keywords_l = [], [], [], [], [], [], []
    pipe_vers, parsers = [], []

    for cleaned, raw, source, kind in zip(cleaned_src, raw_src, sources, kinds):
        text = html_tables_to_md(cleaned)
        text = fix_encoding(text)
        text = strip_headers_footers(text)
        kb_text.append(text)

        raw_fixed = fix_encoding(raw)
        raw_nums = number_set(raw_fixed)
        new_nums = sorted(number_set(text) - raw_nums)
        invented.append(",".join(new_nums))
        invented_n.append(len(new_nums))
        # Soft gate: format-only diffs already removed by normalize.
        # Severe = many genuinely new numbers (likely hallucination).
        severe = len(new_nums) > 3
        fidelity_severe.append(severe)
        fidelity.append(not severe)

        doc_type, year, date, title, author_guess = meta(source, kind)
        a, j, v, iss, doi, ab, kw = extract_from_text(text)
        if not a and author_guess:
            a = author_guess
        doc_types.append(doc_type)
        years.append(year)
        dates.append(date)
        titles.append(title)
        authors.append(a)
        journals.append(j)
        volumes.append(v)
        issues.append(iss)
        dois.append(doi)
        abstracts.append(ab)
        keywords_l.append(kw)
        pipe_vers.append(PIPELINE_VERSION)
        parsers.append(PARSER_ID)
        digest = hashlib.sha1((str(source) + "\n" + text).encode("utf-8", "ignore")).hexdigest()[:16]
        kb_ids.append(digest)

    out["cleaned_chunk"] = kb_text
    out["kb_text"] = kb_text
    out["fidelity_ok"] = fidelity
    out["fidelity_severe"] = fidelity_severe
    out["invented_numbers"] = invented
    out["invented_number_count"] = invented_n
    out["doc_type"] = doc_types
    out["year"] = years
    out["doc_date"] = dates
    out["title"] = titles
    out["author"] = authors
    out["journal"] = journals
    out["volume"] = volumes
    out["issue"] = issues
    out["doi"] = dois
    out["abstract"] = abstracts
    out["keywords"] = keywords_l
    out["kb_id"] = kb_ids
    out["pipeline_version"] = pipe_vers
    out["parser"] = parsers
    return out
