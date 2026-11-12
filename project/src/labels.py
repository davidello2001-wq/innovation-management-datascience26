"""Labelled families: one reader for every label worksheet of the team.

Two worksheet formats exist and both are read into the same table:

* team format (trial_branch, src/validate_query.py): ``relevance_label`` 1 / 0 / ?,
  ``exclusion_reason``, ``technology_segment``, ``reviewer``, ``review_notes``;
* first format of this branch: ``label`` 1 / 2 / 0, ``labeler``, ``note``,
  where 2 was the adjacent head-mounted display / VR market.

The common target is binary, ``relevance`` (1 = smart glasses, 0 = not in the
sector). The adjacent market is not a third label: it is a family with
relevance 0 whose exclusion reason says so (``adjacent``), so the precision
script of the team format reads the same files unchanged.

Pure pandas: no PATSTAT access, can be run and tested anywhere.
"""

from pathlib import Path

import numpy as np
import pandas as pd

POSITIVE = {"1", "1.0", "yes", "y", "true", "relevant"}
NEGATIVE = {"0", "0.0", "no", "n", "false", "irrelevant", "not relevant"}
ADJACENT_LABEL = {"2", "2.0", "adjacent"}            # old format: label 2
ADJACENT_REASON = "adjacent_hmd_vr"                  # team format: the code to write in exclusion_reason
# Free-text reasons written before the code existed ("VR headset", "closed HMD"...)
ADJACENT_PATTERN = r"adjacent|virtual[- ]reality|\bvr\b|headset|helmet|\bhmd\b|head[- ]mounted"

# Team rule (LABELING_GUIDE.md): a head-mounted display whose type is not stated is not in the
# sector, it is adjacent (0). Earlier worksheets left these rows empty or gave them 1 by default,
# always with this note: they are read with the rule, whatever label was written.
UNSTATED_HMD_NOTE = r"hmd tipi belirtilmemiş|hmd type not stated|unstated hmd type"

LABEL_COLUMNS = ("relevance_label", "label")
REASON_COLUMNS = ("exclusion_reason",)
NOTE_COLUMNS = ("review_notes", "note")
REVIEWER_COLUMNS = ("reviewer", "labeler")
KEPT_COLUMNS = ("sample_stratum", "source_blocks", "technology_segment")


def _first_filled(frame, columns):
    """Row by row, the first non-empty value among the columns that exist (lower-case text)."""
    out = pd.Series("", index=frame.index, dtype=object)
    for column in columns:
        if column in frame.columns:
            value = frame[column].fillna("").astype(str).str.strip()
            out = out.where(out != "", value)
    return out


def read_table(path):
    """A label worksheet as text: CSV (comma or semicolon) or Excel."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str)
    return pd.read_csv(path, dtype=str, sep=None, engine="python", encoding="utf-8-sig")


def read_label_file(path, id_column="docdb_family_id"):
    """One row per worksheet row: input_id, relevance (1 / 0 / NaN), adjacent, where it comes from.

    ``adjacent_source`` says how the adjacent market was recognised: "label" (old
    label 2), "reason" (exclusion_reason), "notes" (guessed from the free-text
    note of a file that has no exclusion reason: less reliable) or "hmd rule"
    (a head-mounted display of unstated type, see UNSTATED_HMD_NOTE).
    """
    frame = read_table(path)
    if id_column not in frame.columns:
        raise ValueError(f"{Path(path).name} has no column '{id_column}'")

    value = _first_filled(frame, LABEL_COLUMNS).str.lower()
    reason = _first_filled(frame, REASON_COLUMNS).str.lower()
    notes = _first_filled(frame, NOTE_COLUMNS).str.lower()

    relevance = pd.Series(np.nan, index=frame.index)
    relevance[value.isin(POSITIVE)] = 1.0
    relevance[value.isin(NEGATIVE | ADJACENT_LABEL)] = 0.0

    unstated_hmd = notes.str.contains(UNSTATED_HMD_NOTE, regex=True)
    relevance[unstated_hmd] = 0.0

    by_label = value.isin(ADJACENT_LABEL)
    by_reason = reason.str.contains(ADJACENT_PATTERN, regex=True)
    by_notes = (reason == "") & notes.str.contains(ADJACENT_PATTERN, regex=True)
    source = np.select([unstated_hmd, by_label, by_reason, by_notes], ["hmd rule", "label", "reason", "notes"], "")
    source = np.where(relevance == 0, source, "")       # only a family outside the sector can be adjacent

    out = pd.DataFrame({
        "input_id": frame[id_column].fillna("").astype(str).str.strip(),
        "relevance": relevance,
        "adjacent": source != "",
        "adjacent_source": source,
        "reviewer": _first_filled(frame, REVIEWER_COLUMNS),
        "file": Path(path).name,
    })
    for column in KEPT_COLUMNS:
        out[column] = frame[column].fillna("").astype(str) if column in frame.columns else ""
    return out[out["input_id"] != ""].reset_index(drop=True)


def read_label_files(paths, id_column="docdb_family_id"):
    """All the worksheets, one under the other. Files without the id column are reported and skipped."""
    parts = []
    for path in sorted(Path(p) for p in paths):
        try:
            parts.append(read_label_file(path, id_column))
        except ValueError as error:
            print(f"skipped: {error}")
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _join(values):
    return "; ".join(sorted({v for v in values if v}))


def per_family(rows, key="docdb_family_id"):
    """One row per family.

    Rows of the same family are merged. If two reviewers disagree (1 and 0) the
    family is left without a label and flagged ``conflict``: it has to be
    looked at again, not averaged. ``category`` is "1" smart glasses, "2"
    adjacent market, "0" not related (the three values of the first format).
    """
    columns = [key, "relevance", "adjacent", "category", "conflict", "n_labels",
               "reviewers", "files", "sample_stratum", "technology_segment"]
    if rows.empty:
        return pd.DataFrame(columns=columns)

    def merge(group):
        given = group["relevance"].dropna()
        conflict = given.nunique() > 1
        relevance = given.iloc[0] if len(given) and not conflict else np.nan
        adjacent = bool(relevance == 0 and group.loc[group["relevance"] == 0, "adjacent"].any())
        category = None if np.isnan(relevance) else "1" if relevance == 1 else "2" if adjacent else "0"
        return pd.Series({
            "relevance": relevance, "adjacent": adjacent, "category": category,
            "conflict": bool(conflict), "n_labels": len(given),
            "reviewers": _join(group["reviewer"]), "files": _join(group["file"]),
            "sample_stratum": _join(group["sample_stratum"]),
            "technology_segment": _join(group["technology_segment"]),
        })

    out = rows.groupby(key, sort=True)[[c for c in rows.columns if c != key]].apply(merge).reset_index()
    return out[columns]


def label_files(labels_dir):
    """The worksheets of a folder (CSV and Excel)."""
    labels_dir = Path(labels_dir)
    if not labels_dir.is_dir():
        return []
    return sorted(p for p in labels_dir.iterdir() if p.suffix.lower() in (".csv", ".xlsx", ".xls"))


def load_labels(labels_dir):
    """Every worksheet of the folder that has a docdb_family_id column, one row per family."""
    rows = read_label_files(label_files(labels_dir))
    if rows.empty:
        return per_family(rows)
    rows["docdb_family_id"] = pd.to_numeric(rows["input_id"], errors="coerce")
    rows = rows.dropna(subset=["docdb_family_id"]).astype({"docdb_family_id": "int64"})
    return per_family(rows.drop(columns="input_id"))


def listed_family_ids(labels_dir):
    """Every family that appears in a worksheet, labelled or not (used to avoid sampling it again)."""
    rows = read_label_files(label_files(labels_dir))
    if rows.empty:
        return set()
    return set(pd.to_numeric(rows["input_id"], errors="coerce").dropna().astype("int64"))


def block_precision(frame, flags, label="relevance"):
    """Precision of each query block on labelled families.

    Same table as ``precision_diagnostics`` of the team's trial_branch, for any
    0/1 flag columns: all blocks together, each block, and the families found
    by that block alone (exclusive). Families without a 1 / 0 label are ignored.
    """
    done = frame.dropna(subset=[label])
    hits = done[list(flags)].fillna(0).astype(int)
    done = done[hits.sum(axis=1) > 0]
    hits = hits.loc[done.index]
    alone = hits.sum(axis=1) == 1

    def percent(part):
        return round(float(part[label].mean() * 100), 1) if len(part) else None

    rows = [{"scope": "all blocks", "labelled": len(done), "relevant": int(done[label].sum()),
             "precision_percent": percent(done), "exclusive_labelled": None, "exclusive_precision_percent": None}]
    for flag in flags:
        block, only = done[hits[flag] == 1], done[(hits[flag] == 1) & alone]
        rows.append({"scope": flag, "labelled": len(block), "relevant": int(block[label].sum()),
                     "precision_percent": percent(block), "exclusive_labelled": len(only),
                     "exclusive_precision_percent": percent(only)})
    return pd.DataFrame(rows)
