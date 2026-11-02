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
    """OR-condition: any term appears in the title or in the abstract (case-insensitive)."""
    title = func.lower(TLS202_APPLN_TITLE.appln_title)
    abstract = func.lower(TLS203_APPLN_ABSTR.appln_abstract)
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


# Rules that put a family in the sector (see config/sector.yaml, rules A, B, C)
SECTOR_RULES = (
    "r_core_cpc", "r_core_ipc", "r_keyword",            # A
    "r_component_cpc", "r_component_ipc",               # B
    "r_eyewear_cpc", "r_eyewear_ipc",                   # C
)


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
    return (
        db.query(
            *flags.c,
            func.min(TLS201_APPLN.earliest_filing_year).label("year"),
            func.max(TLS201_APPLN.docdb_family_size).label("family_size"),
        )
        .join(TLS201_APPLN, TLS201_APPLN.docdb_family_id == flags.c.docdb_family_id)
        .filter(TLS201_APPLN.ipr_type == cfg["ipr_type"], TLS201_APPLN.appln_id < DUMMY_APPLN_ID)
        .group_by(*flags.c)
    )


def family_titles(db, family_ids):
    """All titles (with their language) of the applications of the families, for eyeballing samples."""
    return (
        db.query(TLS201_APPLN.docdb_family_id, TLS202_APPLN_TITLE.appln_title_lg, TLS202_APPLN_TITLE.appln_title)
        .join(TLS202_APPLN_TITLE, TLS201_APPLN.appln_id == TLS202_APPLN_TITLE.appln_id)
        .filter(TLS201_APPLN.docdb_family_id.in_([int(i) for i in family_ids]))
    )
