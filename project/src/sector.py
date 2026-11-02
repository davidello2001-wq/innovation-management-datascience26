"""Shared building blocks for the sector query: config loading and SQL conditions.

The conditions follow Tutorial 0 (01_patstat_basics, Section 5.2): classification
symbols are compared without blanks and matched by prefix, keywords are matched
case-insensitively in titles and abstracts.
"""

from pathlib import Path

import yaml
from sqlalchemy import case, func, literal, or_, select, union_all

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
# semantic filter, like the head-up / head-mounted display codes (r_review).
CORE_RULES = ("r_core_cpc", "r_core_ipc", "r_keyword")                       # A
REVIEW_RULES = ("r_component_cpc", "r_component_ipc",                        # B
                "r_eyewear_cpc", "r_eyewear_ipc",                            # C
                "r_review")
SECTOR_RULES = CORE_RULES + REVIEW_RULES[:-1]


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


def candidate_pool_query(db, cfg):
    """One row per candidate family: a 0/1 flag per rule, priority year and family size.

    The rules are evaluated inside the database and only the flags are downloaded.
    A family is a candidate if it matches any rule except r_excluded.
    """
    rules = rule_queries(db, cfg)
    hits = union_all(*(
        select(literal(name).label("rule"), q.subquery().c.docdb_family_id.label("docdb_family_id"))
        for name, q in rules.items()
    )).subquery("hits")

    flags = (
        db.query(
            hits.c.docdb_family_id.label("docdb_family_id"),
            *(func.max(case((hits.c.rule == name, 1), else_=0)).label(name) for name in rules),
        )
        .group_by(hits.c.docdb_family_id)
        .having(func.max(case((hits.c.rule != "r_excluded", 1), else_=0)) == 1)
        .subquery("flags")
    )
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
