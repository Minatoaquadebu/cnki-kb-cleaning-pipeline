def keep_body_chunks(df):
    import re
    if df is None or getattr(df, "empty", True) or "cleaned_chunk" not in df.columns:
        return df
    def keep(text):
        t = str(text or "").strip()
        if len(t) < 80:
            return False
        cites = len(re.findall(r"\[\d+\]", t))
        if cites >= 4 and len(t) < 700:
            return False
        if t.lstrip().startswith(("参考文献",)) and cites >= 2:
            return False
        if t.count("$^{") >= 6 and len(t) < 450:
            return False
        if re.match(r"^[\s,A-Za-z\-\.]+\$\{\^", t) and len(t) < 350:
            return False
        return True
    return df.loc[df["cleaned_chunk"].map(keep)].reset_index(drop=True)
