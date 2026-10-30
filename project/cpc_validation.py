"""Deterministic text screening of CPC prefixes, not official CPC validation.

Only the standard library is required here. PATSTAT access is supplied by TIP.
"""

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


RULE_VERSION = "smart-glasses-screen-v1"
PATTERNS = {
    "direct": r"\b(?:smart (?:glasses|eyewear|spectacles)|augmented reality (?:glasses|eyewear)|audio (?:glasses|eyewear))\b",
    "eyewear": r"\b(?:eyeglasses|eyeglass|spectacles|spectacle|eyewear|glasses|near eye|head mounted|head worn)\b",
    "function": r"\b(?:display|displays|waveguide|waveguides|microphone|microphones|speaker|speakers|audio|hearing|sensor|sensors|camera|cameras|tracking|wireless|augmented reality|virtual reality|beamforming)\b",
    "audio": r"\b(?:audio|hearing|acoustic|microphone|microphones|speaker|speakers|beamforming|speech|sound)\b",
    "interaction": r"\b(?:gesture|gestures|gaze|tracking|voice|interaction|interface|interfaces|eye tracking)\b",
}


def screen_text(title, abstract):
    """Explainable labels: no text or no positive evidence stays uncertain."""
    value = " ".join(str(x) for x in (title, abstract) if x)
    value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    matches = {
        key: sorted({m.group(0) for m in re.finditer(pattern, value)})
        for key, pattern in PATTERNS.items()
    }
    if not value.strip():
        label = "NO_ENGLISH_TEXT"
    elif matches["direct"] or (matches["eyewear"] and matches["function"]):
        label = "LIKELY_RELEVANT"
    elif matches["eyewear"]:
        label = "POSSIBLY_RELEVANT"
    else:
        label = "NO_POSITIVE_EVIDENCE"
    return {"label": label, "audio_theme": bool(matches["audio"]),
            "interaction_theme": bool(matches["interaction"]),
            "matched_terms": json.dumps(matches, ensure_ascii=False)}


def normalize_code(code):
    code = code.replace(" ", "").upper()
    if not re.fullmatch(r"[A-HY]\d{2}[A-Z]\d+/\d+", code):
        raise ValueError(f"Expected a CPC group, got: {code!r}")
    return code


def build_query(code, year_min, year_max, sample_size, seed):
    code = normalize_code(code)
    for number in (year_min, year_max, sample_size, seed):
        if type(number) is not int:
            raise ValueError("Years, sample size and seed must be integers")
    if not 1900 <= year_min <= year_max <= 2100 or sample_size < 1:
        raise ValueError("Invalid years or sample size")
    # Sample families before joining text. Fetch English text from ANY PI member,
    # even when that member does not itself carry the selected CPC prefix.
    return f"""
WITH candidates AS (
    SELECT DISTINCT a.docdb_family_id
    FROM tls201_appln a
    JOIN tls224_appln_cpc c ON a.appln_id = c.appln_id
    WHERE REPLACE(c.cpc_class_symbol, ' ', '') LIKE '{code}%'
      AND a.appln_id > 0 AND a.appln_id < 900000000
      AND a.docdb_family_id > 0 AND a.ipr_type = 'PI'
), dated AS (
    SELECT a.docdb_family_id, MIN(a.earliest_filing_year) AS priority_year
    FROM tls201_appln a
    JOIN candidates c ON a.docdb_family_id = c.docdb_family_id
    WHERE a.appln_id > 0 AND a.appln_id < 900000000 AND a.ipr_type = 'PI'
      AND a.earliest_filing_year BETWEEN 1900 AND 2100
    GROUP BY a.docdb_family_id
), eligible AS (
    SELECT *, COUNT(*) OVER () AS total_eligible_families
    FROM dated WHERE priority_year BETWEEN {year_min} AND {year_max}
), sampled AS (
    SELECT * FROM eligible
    ORDER BY FARM_FINGERPRINT(CONCAT(CAST(docdb_family_id AS STRING), ':{seed}')),
             docdb_family_id
    LIMIT {sample_size}
), texts AS (
    SELECT s.*, a.appln_id,
      CASE WHEN LOWER(t.appln_title_lg) = 'en' THEN t.appln_title ELSE '' END AS title,
      CASE WHEN LOWER(b.appln_abstract_lg) = 'en' THEN b.appln_abstract ELSE '' END AS abstract,
      ROW_NUMBER() OVER (PARTITION BY s.docdb_family_id ORDER BY
        CASE WHEN LOWER(b.appln_abstract_lg) = 'en'
                   AND LENGTH(TRIM(b.appln_abstract)) > 0 THEN 0 ELSE 1 END,
        CASE WHEN LOWER(t.appln_title_lg) = 'en'
                   AND LENGTH(TRIM(t.appln_title)) > 0 THEN 0 ELSE 1 END,
        a.appln_filing_date, a.appln_id) AS text_rank
    FROM sampled s
    JOIN tls201_appln a ON a.docdb_family_id = s.docdb_family_id
    LEFT JOIN tls202_appln_title t ON t.appln_id = a.appln_id
    LEFT JOIN tls203_appln_abstr b ON b.appln_id = a.appln_id
    WHERE a.appln_id > 0 AND a.appln_id < 900000000 AND a.ipr_type = 'PI'
)
SELECT docdb_family_id, priority_year, total_eligible_families, appln_id, title, abstract
FROM texts WHERE text_rank = 1 ORDER BY docdb_family_id
""".strip()


def summarize(code, rows, all_codes, minimum_sample=20):
    readable = [r for r in rows if r["label"] != "NO_ENGLISH_TEXT"]
    positive = sum(r["label"] == "LIKELY_RELEVANT" for r in readable)
    rate = positive / len(readable) if readable else None
    coverage = len(readable) / len(rows) if rows else 0
    if not rows:
        decision = "NO_DATA_IN_SELECTED_ENVIRONMENT"
    elif len(readable) < minimum_sample or coverage < 0.8:
        decision = "INSUFFICIENT_TEXT_OR_SAMPLE"
    elif rate >= 0.7:
        decision = "KEEP_CANDIDATE"
    elif rate >= 0.3:
        decision = "REVIEW_MIXED_SCOPE"
    else:
        decision = "CONSIDER_NARROWING_WITH_TEXT"
    return {
        "cpc_prefix": code,
        "covered_by_listed_prefix": " | ".join(c for c in all_codes if c != code and code.startswith(c)),
        "total_eligible_families": rows[0]["total_eligible_families"] if rows else 0,
        "sampled_families": len(rows), "readable_families": len(readable),
        "english_text_coverage": coverage, "likely_relevant_families": positive,
        "heuristic_positive_rate": rate, "recommendation": decision,
        "audio_theme_families": sum(r["audio_theme"] for r in readable),
        "interaction_theme_families": sum(r["interaction_theme"] for r in readable),
    }


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_validation(patstat, codes, *, env, dataset_release, year_min=2000,
                   year_max=2022, sample_size=50, seed=42,
                   output_dir="outputs/cpc_validation"):
    if not dataset_release.strip():
        raise ValueError("Record the PATSTAT dataset release before running")
    codes = sorted({normalize_code(c) for c in codes})
    if not codes:
        raise ValueError("CPC list is empty")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = Path(output_dir) / stamp
    destination.mkdir(parents=True, exist_ok=False)
    config = dict(env=env, dataset_release=dataset_release, year_min=year_min,
                  year_max=year_max, sample_size=sample_size, seed=seed,
                  codes=codes, rule_version=RULE_VERSION, patterns=PATTERNS,
                  minimum_readable_sample=20, minimum_coverage=0.8,
                  keep_threshold=0.7, mixed_threshold=0.3,
                  note="Text heuristic; not measured precision/recall or official CPC validity.")
    (destination / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    # Save executable rule version as well as parameters.
    (destination / "rules_source.py").write_text(Path(__file__).read_text(), encoding="utf-8")
    summaries, evidence = [], []
    for index, code in enumerate(codes, 1):
        query = build_query(code, year_min, year_max, sample_size, seed)
        stem = code.replace("/", "_")
        (destination / f"{stem}.sql").write_text(query, encoding="utf-8")
        rows = [dict(row) for row in patstat.sql_query(query, use_legacy_sql=False)]
        raw = json.dumps(rows, ensure_ascii=False, indent=2, default=str)
        (destination / f"{stem}_raw.json").write_text(raw, encoding="utf-8")
        classified = [dict(row, **screen_text(row.get("title"), row.get("abstract"))) for row in rows]
        summary = summarize(code, classified, codes)
        summary["raw_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
        summaries.append(summary)
        evidence.extend(dict(cpc_prefix=code, **row) for row in classified)
        print(f"[{index}/{len(codes)}] {code}: {summary['recommendation']}", flush=True)
        # Checkpoint completed results so an interrupted run retains evidence.
        write_csv(destination / "cpc_summary.csv", summaries)
        write_csv(destination / "family_evidence.csv", evidence)
    return summaries, evidence, destination
