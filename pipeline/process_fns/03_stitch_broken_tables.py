def stitch_broken_tables(df):
    import pandas as pd
    if df is None or getattr(df, "empty", True) or "raw_chunk" not in df.columns:
        return df
    def broken(text):
        t = str(text or "")
        low = t.lower()
        s = t.lstrip().lower()
        if low.count("<table") > low.count("</table"):
            return True
        return s.startswith(("td>", "/td>", "tr>", "/tr>", "</td", "</tr", "th>", "/th>"))
    out = []
    buf = None
    for rec in df.to_dict(orient="records"):
        text = str(rec.get("raw_chunk") or "")
        if buf is None:
            buf = rec
            continue
        prev = str(buf.get("raw_chunk") or "")
        same = buf.get("source") == rec.get("source")
        if same and (broken(prev) or broken(text)) and (len(prev) + len(text) < 12000):
            merged = dict(buf)
            merged["raw_chunk"] = prev + "\n" + text
            buf = merged
        else:
            out.append(buf)
            buf = rec
    if buf is not None:
        out.append(buf)
    return pd.DataFrame(out)
