"""Shared building blocks for the sector query: config loading and SQL conditions.

The conditions follow Tutorial 0 (01_patstat_basics, Section 5.2): classification
symbols are compared without blanks and matched by prefix, keywords are matched
case-insensitively in titles and abstracts.
"""

from pathlib import Path

import yaml
from sqlalchemy import func, or_

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
