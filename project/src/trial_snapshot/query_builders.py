"""Reusable SQLAlchemy query builders for Step 0 on EPO TIP.

This module is expected to run inside TIP, where ``epo.tipdata.patstat`` is
available. It keeps database work in SQL and returns query objects instead of
downloading large PATSTAT tables into notebook memory.
"""

from __future__ import annotations

from sqlalchemy import and_, case, func, literal, or_, select

from epo.tipdata.patstat.database.models import (
    TLS201_APPLN,
    TLS202_APPLN_TITLE,
    TLS203_APPLN_ABSTR,
    TLS209_APPLN_IPC,
    TLS224_APPLN_CPC,
)

from .sector_config import SectorConfig


def symbol_prefix_condition(symbol_column, codes: tuple[str, ...]):
    """Match PATSTAT classification symbols after removing padding blanks."""

    symbol = func.replace(symbol_column, " ", "")
    return or_(*(symbol.like(code.replace(" ", "") + "%") for code in codes))


def keyword_condition(terms: tuple[str, ...]):
    """Match any term in a title or abstract, case-insensitively."""

    title = func.lower(TLS202_APPLN_TITLE.appln_title)
    abstract = func.lower(TLS203_APPLN_ABSTR.appln_abstract)
    return or_(*(column.like(f"%{term.lower()}%") for term in terms for column in (title, abstract)))


class SectorQueryBuilder:
    """Construct the four auditable blocks of the Smart Glasses query."""

    def __init__(self, db, config: SectorConfig):
        self.db = db
        self.config = config

    def _base_filter(self):
        """Apply PATSTAT hygiene and the family-level candidate year window."""

        return and_(
            # PATSTAT reserves very high application IDs for dummy records.
            TLS201_APPLN.appln_id > 0,
            TLS201_APPLN.appln_id < 900000000,
            TLS201_APPLN.docdb_family_id > 0,
            TLS201_APPLN.ipr_type == self.config.ipr_type,
            TLS201_APPLN.earliest_filing_year
            >= self.config.candidate_earliest_filing_year_min,
            TLS201_APPLN.earliest_filing_year
            <= self.config.candidate_earliest_filing_year_max,
        )

    def _cpc_family_ids(self, codes: tuple[str, ...]):
        """Return DOCDB families with a matching CPC on any valid member."""

        return (
            self.db.query(TLS201_APPLN.docdb_family_id.label("docdb_family_id"))
            .select_from(TLS201_APPLN)
            .join(
                TLS224_APPLN_CPC,
                TLS201_APPLN.appln_id == TLS224_APPLN_CPC.appln_id,
            )
            .filter(
                self._base_filter(),
                symbol_prefix_condition(TLS224_APPLN_CPC.cpc_class_symbol, codes),
            )
            .distinct()
            .subquery()
        )

    def _ipc_family_ids(self, codes: tuple[str, ...]):
        """Return DOCDB families with a matching IPC on any valid member."""

        return (
            self.db.query(TLS201_APPLN.docdb_family_id.label("docdb_family_id"))
            .select_from(TLS201_APPLN)
            .join(
                TLS209_APPLN_IPC,
                TLS201_APPLN.appln_id == TLS209_APPLN_IPC.appln_id,
            )
            .filter(
                self._base_filter(),
                symbol_prefix_condition(TLS209_APPLN_IPC.ipc_class_symbol, codes),
            )
            .distinct()
            .subquery()
        )

    def _keyword_family_ids(self, terms: tuple[str, ...]):
        """Return families whose title/abstract match on any valid member."""

        return (
            self.db.query(TLS201_APPLN.docdb_family_id.label("docdb_family_id"))
            .select_from(TLS201_APPLN)
            .outerjoin(
                TLS202_APPLN_TITLE,
                TLS201_APPLN.appln_id == TLS202_APPLN_TITLE.appln_id,
            )
            .outerjoin(
                TLS203_APPLN_ABSTR,
                TLS201_APPLN.appln_id == TLS203_APPLN_ABSTR.appln_id,
            )
            .filter(self._base_filter(), keyword_condition(terms))
            .distinct()
            .subquery()
        )

    def _family_intersection(
        self,
        *columns,
        required_sets,
        exclude_contact_only: bool = False,
    ):
        """Select valid applications from families present in every set.

        Each required set is calculated independently, so a classification may
        occur on one family member while the English evidence occurs on another.
        This is important for international families whose priority filing has
        no English title or abstract.
        """

        query = self.db.query(*columns).select_from(TLS201_APPLN).filter(
            self._base_filter()
        )
        for family_set in required_sets:
            query = query.filter(
                TLS201_APPLN.docdb_family_id.in_(
                    select(family_set.c.docdb_family_id)
                )
            )

        if exclude_contact_only:
            excluded = self._keyword_family_ids(self.config.exclude_terms)
            positive_eyewear = self._keyword_family_ids(
                self.config.eyewear_context_terms + self.config.specific_keywords
            )
            # Exclude contact-lens-only families, but retain mixed families that
            # also contain explicit spectacles/eyewear evidence.
            query = query.filter(
                or_(
                    ~TLS201_APPLN.docdb_family_id.in_(
                        select(excluded.c.docdb_family_id)
                    ),
                    TLS201_APPLN.docdb_family_id.in_(
                        select(positive_eyewear.c.docdb_family_id)
                    ),
                )
            )
        return query

    def core_cpc(self, *columns):
        return self._family_intersection(
            *columns,
            required_sets=(self._cpc_family_ids(self.config.core_cpc_codes),),
            exclude_contact_only=True,
        )

    def core_ipc(self, *columns):
        return self._family_intersection(
            *columns,
            required_sets=(
                self._ipc_family_ids(self.config.core_ipc_codes),
                self._keyword_family_ids(self.config.eyewear_context_terms),
            ),
        )

    def specific_keywords(self, *columns):
        return self._family_intersection(
            *columns,
            required_sets=(
                self._keyword_family_ids(self.config.specific_keywords),
            ),
        )

    def component_cpc_with_context(self, *columns):
        """Require a component code plus eyewear and smart-technology context."""

        return self._family_intersection(
            *columns,
            required_sets=(
                self._cpc_family_ids(self.config.component_cpc_codes),
                self._keyword_family_ids(self.config.eyewear_context_terms),
                self._keyword_family_ids(self.config.technology_context_terms),
            ),
        )

    def family_blocks(self):
        """Return the four query blocks at DOCDB-family level."""

        family_id = TLS201_APPLN.docdb_family_id.label("docdb_family_id")
        return {
            "core_cpc": self.core_cpc(family_id).distinct(),
            "core_ipc": self.core_ipc(family_id).distinct(),
            "specific_keywords": self.specific_keywords(family_id).distinct(),
            "component_cpc_and_context": self.component_cpc_with_context(family_id).distinct(),
        }

    def application_ids(self):
        """Return valid applications belonging to any selected DOCDB family."""

        application_id = TLS201_APPLN.appln_id.label("appln_id")
        return (
            self.core_cpc(application_id)
            .union(
                self.core_ipc(application_id),
                self.specific_keywords(application_id),
                self.component_cpc_with_context(application_id),
            )
            .subquery()
        )

    def family_membership(self):
        """Return one row per family with membership flags for all query blocks.

        The four sets are combined with ``UNION ALL`` and aggregated inside
        PATSTAT. This supports overlap analysis without downloading the full
        family list into notebook memory.
        """

        family_id = TLS201_APPLN.docdb_family_id.label("docdb_family_id")
        tagged_queries = (
            self.core_cpc(family_id, literal("core_cpc").label("query_block")).distinct(),
            self.core_ipc(family_id, literal("core_ipc").label("query_block")).distinct(),
            self.specific_keywords(
                family_id,
                literal("specific_keywords").label("query_block"),
            ).distinct(),
            self.component_cpc_with_context(
                family_id,
                literal("component_cpc_and_context").label("query_block"),
            ).distinct(),
        )
        hits = tagged_queries[0].union_all(*tagged_queries[1:]).subquery()

        return (
            self.db.query(
                hits.c.docdb_family_id,
                func.max(
                    case((hits.c.query_block == "core_cpc", 1), else_=0)
                ).label("in_core_cpc"),
                func.max(
                    case((hits.c.query_block == "core_ipc", 1), else_=0)
                ).label("in_core_ipc"),
                func.max(
                    case((hits.c.query_block == "specific_keywords", 1), else_=0)
                ).label("in_specific_keywords"),
                func.max(
                    case(
                        (hits.c.query_block == "component_cpc_and_context", 1),
                        else_=0,
                    )
                ).label("in_component_context"),
            )
            .select_from(hits)
            .group_by(hits.c.docdb_family_id)
            .subquery()
        )
