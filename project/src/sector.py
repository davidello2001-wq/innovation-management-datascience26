"""Shared building blocks for the sector query: config loading and SQL conditions.

The conditions follow Tutorial 0 (01_patstat_basics, Section 5.2): classification
symbols are compared without blanks and matched by prefix, keywords are matched
case-insensitively in titles and abstracts.
"""

from pathlib import Path

import yaml
from sqlalchemy import and_, case, func, literal, literal_column, or_, select, union_all

from epo.tipdata.patstat.database.models import (
    TLS201_APPLN,
    TLS202_APPLN_TITLE,
    TLS203_APPLN_ABSTR,
    TLS209_APPLN_IPC,
    TLS224_APPLN_CPC,
)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sector.yaml"
DUMMY_APPLN_ID = 900000000   # appln_id above this value are dummy applications (Tutorial 1, 3.1)


def load_config(path=CONFIG_PATH):
    """The sector definition as a dictionary."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def symbol_prefix_condition(symbol_column, codes):
    """OR-condition: the blank-stripped classification symbol starts with one of the codes."""
    symbol = func.replace(symbol_column, " ", "")
    return or_(*(symbol.like(code.replace(" ", "") + "%") for code in codes))


def keyword_condition(terms):
    """OR-condition: any term appears in the title or in the abstract (case-insensitive).

    The texts get a leading blank, so a term written with a leading blank
    (" ar glasses") matches only at the start of a word, also at the start of the text.
    """
    title = literal(" ") + func.lower(TLS202_APPLN_TITLE.appln_title)
    abstract = literal(" ") + func.lower(TLS203_APPLN_ABSTR.appln_abstract)
    return or_(*(col.like(f"%{t.lower()}%") for t in terms for col in (title, abstract)))


def scope_filter(cfg):
    """Conditions on TLS201 shared by every query: patents only, real applications, year window."""
    return (
        TLS201_APPLN.ipr_type == cfg["ipr_type"],
        TLS201_APPLN.appln_id < DUMMY_APPLN_ID,
        TLS201_APPLN.earliest_filing_year.between(cfg["years"]["min"], cfg["years"]["max"]),
    )


def families_by_cpc(db, cfg, codes):
    """Query of the docdb_family_ids with at least one CPC symbol under the codes."""
    return (
        db.query(TLS201_APPLN.docdb_family_id.label("docdb_family_id"))
        .join(TLS224_APPLN_CPC, TLS201_APPLN.appln_id == TLS224_APPLN_CPC.appln_id)
        .filter(*scope_filter(cfg), symbol_prefix_condition(TLS224_APPLN_CPC.cpc_class_symbol, codes))
    )


def families_by_ipc(db, cfg, codes):
    """Query of the docdb_family_ids with at least one IPC symbol under the codes."""
    return (
        db.query(TLS201_APPLN.docdb_family_id.label("docdb_family_id"))
        .join(TLS209_APPLN_IPC, TLS201_APPLN.appln_id == TLS209_APPLN_IPC.appln_id)
        .filter(*scope_filter(cfg), symbol_prefix_condition(TLS209_APPLN_IPC.ipc_class_symbol, codes))
    )


def families_by_keywords(db, cfg, terms):
    """Query of the docdb_family_ids where any application mentions one of the terms.

    Matching at family level recovers inventions whose first filing has no English
    text (Tutorial 1, Section 5).
    """
    return (
        db.query(TLS201_APPLN.docdb_family_id.label("docdb_family_id"))
        .outerjoin(TLS202_APPLN_TITLE, TLS201_APPLN.appln_id == TLS202_APPLN_TITLE.appln_id)
        .outerjoin(TLS203_APPLN_ABSTR, TLS201_APPLN.appln_id == TLS203_APPLN_ABSTR.appln_id)
        .filter(*scope_filter(cfg), keyword_condition(terms))
    )


def _within(families, other):
    """Keep only the families of `families` that are also in `other` (family-level AND)."""
    return families.filter(TLS201_APPLN.docdb_family_id.in_(other.subquery().select()))


# Rule A puts a family in the sector. Rules B and C were too noisy on PROD
# (eyeballed samples, 02_candidate_pool): alone, they send the family to the
# semantic filter, like the head-up / head-mounted display codes (r_review) and,
# from v0.5, any mention of a head-mounted display or AR in the text (r_hmd_text).
CORE_RULES = ("r_core_cpc", "r_core_ipc", "r_keyword")                       # A
CONTEXT_RULES = ("r_component_cpc", "r_component_ipc",                       # B
                 "r_eyewear_cpc", "r_eyewear_ipc")                           # C
WIDE_RULES = ("r_review", "r_hmd_text")                                      # review codes, W
REVIEW_RULES = CONTEXT_RULES + WIDE_RULES


def rule_queries(db, cfg):
    """One query of docdb_family_ids per rule; the names are the flag columns of the candidate pool."""
    sel = cfg["selection"]
    mentions_eyewear = families_by_keywords(db, cfg, sel["eyewear_terms"] + sel["specific_keywords"])
    mentions_smart = families_by_keywords(db, cfg, sel["smart_terms"])
    return {
        "r_core_cpc": families_by_cpc(db, cfg, sel["core_cpc"]),
        "r_core_ipc": families_by_ipc(db, cfg, sel["core_ipc"]),
        "r_keyword": families_by_keywords(db, cfg, sel["specific_keywords"]),
        "r_component_cpc": _within(families_by_cpc(db, cfg, sel["component_cpc"]), mentions_eyewear),
        "r_component_ipc": _within(families_by_ipc(db, cfg, sel["component_ipc"]), mentions_eyewear),
        "r_eyewear_cpc": _within(families_by_cpc(db, cfg, sel["eyewear_cpc"]), mentions_smart),
        "r_eyewear_ipc": _within(families_by_ipc(db, cfg, sel["eyewear_ipc"]), mentions_smart),
        "r_review": families_by_cpc(db, cfg, sel["review_cpc"]).union(
            families_by_ipc(db, cfg, sel["review_ipc"])),
        "r_hmd_text": families_by_keywords(db, cfg, sel["hmd_terms"]),
        "r_excluded": families_by_keywords(db, cfg, sel["exclude_terms"]),
    }


def sector_family_ids(db, cfg):
    """Query of the docdb_family_ids that are in the sector for sure (rule A)."""
    rules = rule_queries(db, cfg)
    first, *others = (rules[name] for name in CORE_RULES)
    return first.union(*others)


def configured_codes(cfg, scheme):
    """All codes of the selection lists for one scheme ("cpc" or "ipc"), blanks removed."""
    sel = cfg["selection"]
    lists = ("core", "component", "eyewear", "review")
    return [c.replace(" ", "") for name in lists for c in sel.get(f"{name}_{scheme}", [])]


def _max_flags(conditions):
    """One 0/1 column per condition: 1 if any row of the group meets it."""
    return [func.max(case((cond, 1), else_=0)).label(name) for name, cond in conditions.items()]


def candidate_pool_query(db, cfg):
    """One row per candidate family: a 0/1 flag per rule, priority year and family size.

    Same rules as rule_queries, but each table is read once (v0.5): BigQuery runs
    a subquery again every time it is referenced, so the separate rule queries
    scanned all titles and abstracts about seven times. Here one scan of the texts
    gives a flag per term list, one scan of CPC and one of IPC a flag per code
    list; the rules are then combined per family. A family is a candidate if it
    matches any rule except r_excluded.
    """
    sel = cfg["selection"]
    lists = ("core", "component", "eyewear", "review")
    text_flags = {
        "k_eyewear": keyword_condition(sel["eyewear_terms"] + sel["specific_keywords"]),
        "k_smart": keyword_condition(sel["smart_terms"]),
        "k_specific": keyword_condition(sel["specific_keywords"]),
        "k_hmd": keyword_condition(sel["hmd_terms"]),
        "k_excluded": keyword_condition(sel["exclude_terms"]),
    }
    cpc_flags = {f"c_{n}": symbol_prefix_condition(TLS224_APPLN_CPC.cpc_class_symbol, sel[f"{n}_cpc"]) for n in lists}
    ipc_flags = {f"i_{n}": symbol_prefix_condition(TLS209_APPLN_IPC.ipc_class_symbol, sel[f"{n}_ipc"]) for n in lists}
    family = TLS201_APPLN.docdb_family_id.label("docdb_family_id")

    texts = (select(family, *_max_flags(text_flags))
             .select_from(TLS201_APPLN)
             .outerjoin(TLS202_APPLN_TITLE, TLS201_APPLN.appln_id == TLS202_APPLN_TITLE.appln_id)
             .outerjoin(TLS203_APPLN_ABSTR, TLS201_APPLN.appln_id == TLS203_APPLN_ABSTR.appln_id)
             .where(*scope_filter(cfg), or_(*text_flags.values()))
             .group_by(TLS201_APPLN.docdb_family_id))
    cpc = (select(family, *_max_flags(cpc_flags))
           .select_from(TLS201_APPLN)
           .join(TLS224_APPLN_CPC, TLS201_APPLN.appln_id == TLS224_APPLN_CPC.appln_id)
           .where(*scope_filter(cfg), or_(*cpc_flags.values()))
           .group_by(TLS201_APPLN.docdb_family_id))
    ipc = (select(family, *_max_flags(ipc_flags))
           .select_from(TLS201_APPLN)
           .join(TLS209_APPLN_IPC, TLS201_APPLN.appln_id == TLS209_APPLN_IPC.appln_id)
           .where(*scope_filter(cfg), or_(*ipc_flags.values()))
           .group_by(TLS201_APPLN.docdb_family_id))

    # Stack the three scans (missing flags = 0) and keep the maximum per family
    names = [*text_flags, *cpc_flags, *ipc_flags]

    def padded(query, own):
        sq = query.subquery()
        return select(sq.c.docdb_family_id,
                      *(sq.c[n] if n in own else literal_column("0").label(n) for n in names))

    stacked = union_all(padded(texts, text_flags), padded(cpc, cpc_flags), padded(ipc, ipc_flags)).subquery("stacked")
    f = (select(stacked.c.docdb_family_id, *(func.max(stacked.c[n]).label(n) for n in names))
         .group_by(stacked.c.docdb_family_id)
         .subquery("f")).c

    # The rules of rule_queries, from the flags (same names and order)
    rules = {
        "r_core_cpc": f.c_core == 1,
        "r_core_ipc": f.i_core == 1,
        "r_keyword": f.k_specific == 1,
        "r_component_cpc": and_(f.c_component == 1, f.k_eyewear == 1),
        "r_component_ipc": and_(f.i_component == 1, f.k_eyewear == 1),
        "r_eyewear_cpc": and_(f.c_eyewear == 1, f.k_smart == 1),
        "r_eyewear_ipc": and_(f.i_eyewear == 1, f.k_smart == 1),
        "r_review": or_(f.c_review == 1, f.i_review == 1),
        "r_hmd_text": f.k_hmd == 1,
        "r_excluded": f.k_excluded == 1,
    }
    flags = (select(f.docdb_family_id, *(case((cond, 1), else_=0).label(n) for n, cond in rules.items()))
             .where(or_(*(cond for n, cond in rules.items() if n != "r_excluded")))
             .subquery("flags"))

    # Family year = earliest priority year among its applications. It can be older
    # than the year of the matched application, so the window is applied again here.
    family_year = func.min(TLS201_APPLN.earliest_filing_year)
    return (
        db.query(
            *flags.c,
            family_year.label("year"),
            func.max(TLS201_APPLN.docdb_family_size).label("family_size"),
        )
        .join(TLS201_APPLN, TLS201_APPLN.docdb_family_id == flags.c.docdb_family_id)
        .filter(TLS201_APPLN.ipr_type == cfg["ipr_type"], TLS201_APPLN.appln_id < DUMMY_APPLN_ID)
        .group_by(*flags.c)
        .having(family_year.between(cfg["years"]["min"], cfg["years"]["max"]))
    )


def families_from_ids(db, patstat, id_type, values, chunk=1000):
    """Map external identifiers to docdb_family_id. Returns a DataFrame (input_id, docdb_family_id).

    id_type: "docdb_family_id", "appln_id", "publication_number" (e.g. "EP3123456A1",
    "US 10,123,456 B2") or "application_number" (office + number, e.g. "EP15123456").
    Numbers are matched as office + number without the kind code and without leading zeros.
    """
    import re as _re
    import pandas as _pd
    from epo.tipdata.patstat.database.models import TLS211_PAT_PUBLN

    values = [str(v).strip() for v in values if str(v).strip() and str(v).strip().lower() != "nan"]
    if id_type == "docdb_family_id":
        return _pd.DataFrame({"input_id": values, "docdb_family_id": [int(float(v)) for v in values]})

    if id_type == "appln_id":
        wanted = _pd.DataFrame({"input_id": values, "appln_id": [int(float(v)) for v in values]})
        ids = wanted["appln_id"].unique().tolist()
        parts = [patstat.df(db.query(TLS201_APPLN.appln_id, TLS201_APPLN.docdb_family_id)
                            .filter(TLS201_APPLN.appln_id.in_(ids[i:i + chunk])))
                 for i in range(0, len(ids), chunk)]
        found = _pd.concat(parts, ignore_index=True) if parts else _pd.DataFrame()
        if found.empty:
            return _pd.DataFrame(columns=["input_id", "docdb_family_id"])
        return wanted.merge(found, on="appln_id")[["input_id", "docdb_family_id"]]

    # office + number: "EP 3 123 456 A1" -> ("EP", "3123456")
    parsed = []
    for v in values:
        m = _re.match(r"^([A-Za-z]{2})\W*([0-9][0-9 ,./-]*)", v)
        if m:
            parsed.append((v, m.group(1).upper(), _re.sub(r"\D", "", m.group(2)).lstrip("0")))
    if not parsed:
        return _pd.DataFrame(columns=["input_id", "docdb_family_id"])
    wanted = _pd.DataFrame(parsed, columns=["input_id", "auth", "nr"])

    if id_type == "publication_number":
        auth_col, nr_col, key = TLS211_PAT_PUBLN.publn_auth, TLS211_PAT_PUBLN.publn_nr, TLS211_PAT_PUBLN.appln_id
        base = db.query(auth_col.label("auth"), nr_col.label("nr"), TLS201_APPLN.docdb_family_id).join(
            TLS201_APPLN, TLS201_APPLN.appln_id == key)
    elif id_type == "application_number":
        auth_col, nr_col = TLS201_APPLN.appln_auth, TLS201_APPLN.appln_nr
        base = db.query(auth_col.label("auth"), nr_col.label("nr"), TLS201_APPLN.docdb_family_id)
    else:
        raise ValueError(f"unknown id_type: {id_type}")

    # filter on offices and numbers separately (BigQuery has no tuple IN), then keep the exact pairs
    nrs = wanted["nr"].unique().tolist()
    parts = [patstat.df(base.filter(auth_col.in_(wanted["auth"].unique().tolist()), nr_col.in_(nrs[i:i + chunk])))
             for i in range(0, len(nrs), chunk)]
    found = _pd.concat(parts, ignore_index=True) if parts else _pd.DataFrame()
    if found.empty:
        return _pd.DataFrame(columns=["input_id", "docdb_family_id"])
    found["nr"] = found["nr"].astype(str).str.lstrip("0")
    return wanted.merge(found, on=["auth", "nr"])[["input_id", "docdb_family_id"]].drop_duplicates()


OFFICE_PRIORITY = ("EP", "WO", "US")   # preferred source of the English abstract of a family


def family_english_texts(db, family_ids):
    """One row per family: the English abstract (and the title of the same application).

    Among the applications of the family with an English abstract, take the first
    office in OFFICE_PRIORITY, then any other office; ties broken by appln_id.
    The language code is compared case-insensitively ("EN" and "en" both occur).
    """
    office_rank = case(*((TLS201_APPLN.appln_auth == o, i) for i, o in enumerate(OFFICE_PRIORITY)),
                       else_=len(OFFICE_PRIORITY))
    rank = func.row_number().over(
        partition_by=TLS201_APPLN.docdb_family_id,
        order_by=(office_rank, TLS201_APPLN.appln_id),
    ).label("rank")
    ranked = (
        db.query(
            TLS201_APPLN.docdb_family_id,
            TLS201_APPLN.appln_id,
            TLS201_APPLN.appln_auth,
            TLS202_APPLN_TITLE.appln_title,
            TLS203_APPLN_ABSTR.appln_abstract,
            rank,
        )
        .join(TLS203_APPLN_ABSTR, TLS201_APPLN.appln_id == TLS203_APPLN_ABSTR.appln_id)
        .outerjoin(TLS202_APPLN_TITLE, TLS201_APPLN.appln_id == TLS202_APPLN_TITLE.appln_id)
        .filter(
            TLS201_APPLN.docdb_family_id.in_([int(i) for i in family_ids]),
            func.lower(func.trim(TLS203_APPLN_ABSTR.appln_abstract_lg)) == "en",
        )
        .subquery()
    )
    return db.query(
        ranked.c.docdb_family_id, ranked.c.appln_id, ranked.c.appln_auth,
        ranked.c.appln_title, ranked.c.appln_abstract,
    ).filter(ranked.c.rank == 1)


def family_titles(db, family_ids):
    """All titles (with their language) of the applications of the families, for eyeballing samples."""
    return (
        db.query(TLS201_APPLN.docdb_family_id, TLS202_APPLN_TITLE.appln_title_lg, TLS202_APPLN_TITLE.appln_title)
        .join(TLS202_APPLN_TITLE, TLS201_APPLN.appln_id == TLS202_APPLN_TITLE.appln_id)
        .filter(TLS201_APPLN.docdb_family_id.in_([int(i) for i in family_ids]))
    )
