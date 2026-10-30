"""CPC candidate families and descriptive TF-IDF; no automatic scope decisions."""

from cpc_validation import build_query, normalize_code


PATENT_STOPWORDS = sorted({
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "for",
    "from", "has", "have", "in", "into", "is", "it", "its", "of", "on", "or",
    "that", "the", "their", "there", "these", "this", "to", "using", "was", "were",
    "which", "with", "wherein", "whereby", "said", "thereof", "comprising",
    "comprises", "according", "invention", "embodiment", "embodiments",
    "provided", "provides", "plurality", "first", "second", "third",
})


def sector_query(codes, year_min, year_max, max_families, seed):
    codes = sorted({normalize_code(c) for c in codes})
    if not codes:
        raise ValueError("CPC list is empty")
    query = build_query(codes[0], year_min, year_max, max_families, seed)
    conditions = " OR ".join(
        f"REPLACE(c.cpc_class_symbol, ' ', '') LIKE '{code}%'" for code in codes
    )
    query = query.replace(
        f"REPLACE(c.cpc_class_symbol, ' ', '') LIKE '{codes[0]}%'",
        f"({conditions})",
    )
    # One row per family, even if several selected CPC prefixes match it.
    matches = " UNION ALL ".join(
        f"SELECT DISTINCT a.docdb_family_id, '{code}' AS prefix "
        "FROM tls201_appln a JOIN tls224_appln_cpc c ON a.appln_id = c.appln_id "
        f"WHERE REPLACE(c.cpc_class_symbol, ' ', '') LIKE '{code}%' "
        "AND a.appln_id > 0 AND a.appln_id < 900000000 "
        "AND a.ipr_type = 'PI'"
        for code in codes
    )
    query = query.replace(
        "SELECT docdb_family_id, priority_year, total_eligible_families, appln_id, title, abstract\nFROM texts WHERE text_rank = 1 ORDER BY docdb_family_id",
        ", matches AS (" + matches + "), membership AS ("
        "SELECT docdb_family_id, STRING_AGG(DISTINCT prefix, ' | ' ORDER BY prefix) AS matched_prefixes "
        "FROM matches GROUP BY docdb_family_id) "
        "SELECT t.docdb_family_id, t.priority_year, t.total_eligible_families, "
        "t.appln_id, t.title, t.abstract, m.matched_prefixes "
        "FROM texts t JOIN membership m ON t.docdb_family_id = m.docdb_family_id "
        "WHERE t.text_rank = 1 ORDER BY t.docdb_family_id",
    )
    return query


def extract_keywords(frame, *, min_df=2, max_df=1.0, top_n=30):
    import pandas as pd
    from sklearn.feature_extraction.text import TfidfVectorizer

    if frame["docdb_family_id"].duplicated().any():
        raise ValueError("Expected one row per DOCDB family")
    documents = (frame["title"].fillna("") + " " + frame["abstract"].fillna("")).str.strip()
    readable = frame.loc[documents.ne("")].copy().reset_index(drop=True)
    columns = ["scope", "phrase", "mean_tfidf", "family_count", "readable_families",
               "family_prevalence", "supporting_family_ids"]
    if len(readable) < min_df:
        return pd.DataFrame(columns=columns), None, readable, "Too few readable families for min_df"
    vectorizer = TfidfVectorizer(
        lowercase=True, strip_accents="unicode", stop_words=PATENT_STOPWORDS,
        ngram_range=(1, 3), token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b",
        min_df=min_df, max_df=max_df, sublinear_tf=True, norm="l2",
    )
    try:
        matrix = vectorizer.fit_transform(documents.loc[documents.ne("")])
    except ValueError as error:
        if "vocabulary" in str(error) or "terms remain" in str(error):
            return pd.DataFrame(columns=columns), None, readable, str(error)
        raise
    features = vectorizer.get_feature_names_out()
    masks = {"ALL_SECTOR": [True] * len(readable)}
    for prefix in sorted({p for value in readable["matched_prefixes"] for p in value.split(" | ")}):
        masks[prefix] = readable["matched_prefixes"].map(lambda value: prefix in value.split(" | ")).to_numpy()
    rows = []
    for scope, mask in masks.items():
        subset = matrix[mask]
        means = subset.mean(axis=0).A1
        counts = (subset > 0).sum(axis=0).A1
        order = sorted((i for i in range(len(features)) if counts[i]),
                       key=lambda i: (-means[i], features[i]))[:top_n]
        selected_families = readable.loc[mask, "docdb_family_id"].to_numpy()
        for i in order:
            supporting = subset[:, i].nonzero()[0]
            rows.append(dict(scope=scope, phrase=features[i], mean_tfidf=float(means[i]),
                             family_count=int(counts[i]), readable_families=subset.shape[0],
                             family_prevalence=float(counts[i] / subset.shape[0]),
                             supporting_family_ids=" | ".join(str(x) for x in selected_families[supporting])))
    return pd.DataFrame(rows, columns=columns), vectorizer, readable, "OK"
