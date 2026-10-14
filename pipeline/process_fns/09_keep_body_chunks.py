def keep_body_chunks(df):
    """Drop bibliography / formula-noise chunks; keep body text."""
    import re

    if df is None or getattr(df, "empty", True) or "cleaned_chunk" not in df.columns:
        return df

    # Leading bibliography headings (CN / EN / spaced variants)
    refs_head_re = re.compile(
        r"^\s*(?:"
        r"参\s*考\s*文\s*献"
        r"|引\s*用\s*文\s*献"
        r"|参考书目"
        r"|References?"
        r"|Bibliograph(?:y|ies)"
        r"|Works\s+Cited"
        r"|Literature\s+Cited"
        r")\s*[:：]?\s*$",
        re.I | re.M,
    )
    refs_inline_re = re.compile(
        r"^\s*(?:"
        r"参\s*考\s*文\s*献"
        r"|References?"
        r"|Bibliograph(?:y|ies)"
        r")\s*[:：]",
        re.I,
    )

    def is_refs_chunk(t):
        head = t[:200]
        if refs_head_re.search(head):
            return True
        first = t.lstrip().splitlines()[0] if t.lstrip() else ""
        if refs_inline_re.match(first):
            return True
        # Dense citation list without a heading
        cites = len(re.findall(r"\[\d+\]", t))
        if cites >= 4 and len(t) < 700:
            return True
        # Numbered ref lines: "1. Author..." density
        num_lines = sum(1 for line in t.splitlines() if re.match(r"^\s*\[\d+\]|\s*\d+\.\s+\S", line))
        if num_lines >= 5 and cites >= 2 and len(t) < 1200:
            return True
        return False

    def is_formula_noise(t):
        # Pure formula dumps / author superscript lists — drop, don't try to recover
        if t.count("$^{") >= 6 and len(t) < 450:
            return True
        if t.count("$") >= 12 and len(re.findall(r"[\u4e00-\u9fff]", t)) < 20 and len(t) < 500:
            return True
        if re.match(r"^[\s,A-Za-z\-\.]+\$\{\^", t) and len(t) < 350:
            return True
        return False

    def keep(text):
        t = str(text or "").strip()
        if len(t) < 80:
            return False
        if is_refs_chunk(t):
            return False
        if is_formula_noise(t):
            return False
        return True

    mask = df["cleaned_chunk"].map(keep)
    return df.loc[mask].reset_index(drop=True)
