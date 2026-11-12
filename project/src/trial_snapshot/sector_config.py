"""Load and validate the sector definition used by the PATSTAT pipeline.

The configuration is deliberately separate from query code so that every
change to the Smart Glasses perimeter is visible and reviewable in Git.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SectorConfig:
    """Validated inputs required to construct the Step 0 sector query."""

    sector_name: str
    client_name: str
    query_status: str
    candidate_earliest_filing_year_min: int
    candidate_earliest_filing_year_max: int
    trend_last_complete_year: int
    ipr_type: str
    core_cpc_codes: tuple[str, ...]
    core_ipc_codes: tuple[str, ...]
    component_cpc_codes: tuple[str, ...]
    specific_keywords: tuple[str, ...]
    eyewear_context_terms: tuple[str, ...]
    technology_context_terms: tuple[str, ...]
    exclude_terms: tuple[str, ...]


def _tuple_of_strings(data: dict[str, Any], key: str) -> tuple[str, ...]:
    """Return a non-empty, trimmed, duplicate-free tuple from a JSON list."""

    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{key} must be a non-empty list")

    cleaned = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(cleaned) != len(value):
        raise ValueError(f"{key} must contain only non-empty strings")
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"{key} contains duplicate entries")
    return cleaned


def parse_sector_config(data: dict[str, Any]) -> SectorConfig:
    """Validate an already decoded sector configuration."""

    year_min = data.get("candidate_earliest_filing_year_min")
    year_max = data.get("candidate_earliest_filing_year_max")
    last_complete_year = data.get("trend_last_complete_year")
    if not isinstance(year_min, int) or not isinstance(year_max, int):
        raise ValueError("candidate earliest filing years must be integers")
    if year_min > year_max:
        raise ValueError("candidate earliest filing year_min cannot exceed year_max")
    if not isinstance(last_complete_year, int):
        raise ValueError("trend_last_complete_year must be an integer")
    if not year_min <= last_complete_year <= year_max:
        raise ValueError("trend_last_complete_year must lie inside the candidate window")

    required_text = ("sector_name", "client_name", "query_status", "ipr_type")
    for key in required_text:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"{key} must be a non-empty string")

    return SectorConfig(
        sector_name=data["sector_name"].strip(),
        client_name=data["client_name"].strip(),
        query_status=data["query_status"].strip(),
        candidate_earliest_filing_year_min=year_min,
        candidate_earliest_filing_year_max=year_max,
        trend_last_complete_year=last_complete_year,
        ipr_type=data["ipr_type"].strip(),
        core_cpc_codes=_tuple_of_strings(data, "core_cpc_codes"),
        core_ipc_codes=_tuple_of_strings(data, "core_ipc_codes"),
        component_cpc_codes=_tuple_of_strings(data, "component_cpc_codes"),
        specific_keywords=_tuple_of_strings(data, "specific_keywords"),
        eyewear_context_terms=_tuple_of_strings(data, "eyewear_context_terms"),
        technology_context_terms=_tuple_of_strings(data, "technology_context_terms"),
        exclude_terms=_tuple_of_strings(data, "exclude_terms"),
    )


def load_sector_config(path: str | Path) -> SectorConfig:
    """Read and validate a sector configuration JSON file."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    return parse_sector_config(data)
