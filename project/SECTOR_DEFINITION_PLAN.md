# Sector definition plan: how we extract our patents

*Innovation Management PW · sector: **Smart glasses** · client: **Amplifon** · working draft v2, November 2026*

This note explains how we plan to build the patent dataset for our sector. Every later step (landscape, competition, present and future scores, Magic Quadrant) is computed on this dataset, so it has to be solid, reproducible and easy to defend in the technical appendix.

It follows the kick-off slides (Step 0 · data collection), the course tutorials (Tutorial 0 notebooks 01–02, Tutorial 1 notebooks 10–11), and two ideas that came up in the group: mining keywords from company patents, and organising our codes and keywords by their role in the query.

---

## 1. What the brief asks for

**Our setting (kick-off, slides 4–6).** We are consultants at an investment bank. The assigned sector is **smart glasses**; the client is **Amplifon**, an established hearing-care company looking for growth. The client asks three questions:

1. How is the sector doing overall?
2. Which **segments** are growing, and which are fading?
3. Who are the **emerging players** to buy or partner with?

**Consequence for the dataset.** The sector is *smart glasses as a whole*, not only hearing glasses. Amplifon's angle comes in through the **segments**: audio / hearing is the segment closest to the client's competences, and it should be clearly identifiable in the data, but the dataset must also cover displays, cameras, sensing and the rest, otherwise we cannot answer questions 1 and 2.

**Step 0 rules from the kick-off (slide 9).**

- *Define the query:* start from CPC codes (checked against the CPC scheme definitions), add keywords in titles and abstracts to catch what the classes miss, and **validate** by hand-labelling about **100 random families** or another justified method (e.g. the literature).
- *Clean:* unit of analysis = **DOCDB family**; time = **earliest priority year**; harmonise applicant names (PSN / HAN + our own rules); flag the last ~3 years as truncated.

**Code rules (slide 18).** Config, not hard-coding (`config/sector.yaml`); SQL in `src/01_extract.py`; notebooks for exploration only; **do not commit bulk PATSTAT extracts, commit the queries**. Data & code quality is 20% of the grade.

## 2. Why we need more than a list of CPC codes

Our current extraction (`tip_extraction.ipynb`) selects every application that has one of the codes in `key_words.ipynb`, joined with OR.

- **Some codes are too broad.** `H04R1/10` (earphones), `G06T7/70` (pose estimation), `G06F3/011` (interaction with the human body) or `H01Q1/273` (antennas on the body) select many patents that have nothing to do with eyewear.
- **Codes alone miss patents.** Some offices (especially older or national CN, JP, KR filings) are not always classified in CPC; IPC and keywords recover them.
- **Tutorial rules not yet applied:** count families, date by `earliest_filing_year`, keep `ipr_type = 'PI'`, drop dummy applications (`appln_id >= 900000000`), match keywords at family level.

## 3. The pipeline at a glance

```
[0] Sector definition + config/sector.yaml
        |
[1] Candidate pool: SQL, family level, high recall, one flag per rule
        |
[2] Expansion: new keywords and CPC/IPC codes from the data (2-3 rounds)
        |
[3] Semantic filter: Patent SBERT-adapt-ub (course model) + BM25 baseline
        |
[4] Validation: hand-labelled families -> precision / recall / F1, choose threshold
        |
[5] Final dataset + segment labels -> used by every later step
```

Codes give coverage, keywords catch what codes miss, data-driven expansion grows the lists, the language model removes false positives, and the labelled sample measures how well it all works.

## 4. Step 0 in detail: the written definition

Before touching code we write a **plain-English definition** of smart glasses (4–6 sentences). It is used in the deck as our sector definition, as the query text for the semantic model in step [3] (like `DAC_DESCRIPTION` in Tutorial 0, notebook 01, Section 6), and as the rulebook for hand-labelling in step [4].

### 4.1 Boundaries (to agree as a group)

| | Examples | In the sector? |
|---|---|---|
| **Smart glasses** | AR glasses with see-through displays; camera glasses; audio glasses (open-ear speakers, bone conduction); hearing-aid glasses; glasses with health or eye-tracking sensors | **yes** |
| **Borderline** | mixed-reality headsets with see-through optics; clip-on modules that turn normal glasses into smart glasses | **to decide** (proposal: include if worn as eyewear) |
| **Out** | fully immersive VR headsets that block the view; helmet-mounted displays; passive eyewear; standalone hearing aids or earbuds not built into eyewear | no |

### 4.2 Segments (for client question 2)

The same families are then tagged with one or more segments. These are close to the "hardware categories" of our first keyword file: they are not useful to *select* patents, but they are exactly what we need to *describe* the sector.

| Segment | What it covers | Relevance for Amplifon |
|---|---|---|
| Display & optics | near-eye displays, waveguides, projectors, lenses | context |
| **Audio & hearing** | speakers, bone conduction, microphone arrays, beamforming, hearing-aid functions | **core: closest to the client** |
| Camera & sensing | cameras, eye tracking, health / biometric sensors | adjacent (e.g. health monitoring) |
| Interaction & software | gesture, voice and gaze input, AR rendering, pose tracking | context |
| Frame, power & connectivity | hinges, temples, batteries, antennas, charging | context |

### 4.3 Where to find the material

| Source | What we take from it | Where |
|---|---|---|
| **CPC scheme definitions** (required by the kick-off) | exact wording of each code, inclusion / exclusion notes, neighbouring groups | <https://www.cooperativepatentclassification.org> → e.g. `G02B 27/01`, `G02C 11/00`, `H04R 25/00` |
| **Seed patents** | 10–20 patents of known smart-glasses products, especially audio / hearing ones: their codes and their vocabulary | Espacenet (<https://worldwide.espacenet.com>) |
| **Academic literature** | a citable definition and a search strategy to adapt (as Tutorial 0 does with the AI paper by Liu et al.) | Scopus / Google Scholar: `"smart glasses" AND patent`, `"smart eyewear"`, `"head-mounted display" AND "patent landscape"`, `"hearing glasses"` |
| **Patent landscape reports** | ready-made definitions and code lists | WIPO Patent Landscape Reports, *WIPO Technology Trends* (2021 edition on assistive technology, for the hearing segment) |
| **Industry sources** | product categories and market terminology | reports and press releases of eyewear, consumer-electronics and hearing-care companies |

**Codes to check first** (verify every title in the scheme before using it):

- `G02B 27/01`, `G02B 27/017`, `G02B 27/0172`: head-up / head-mounted displays (already in our list)
- `G02C 11/00`, `G02C 11/06`, `G02C 11/10`: non-optical adjuncts on spectacles; hearing aids; other electronic devices
- `H04R 25/…`: hearing aids, including directivity / multiple microphones (`H04R 25/40` …)
- `H04R 2460/13`: hearing devices using bone conduction
- `G06F 1/163`: wearable computers

### 4.4 Draft definition (to edit together)

> *Smart glasses* are wearable computing devices in the form of eyeglasses or other head-worn eyewear that integrate electronic components into the frame or lenses, such as see-through or near-eye displays, cameras and sensors, microphones and speakers (including bone-conduction transducers), processors, batteries and wireless connectivity. They capture information about the wearer and the surroundings and deliver visual and/or audio information to the wearer, enabling functions such as augmented-reality overlays, hands-free communication and media, navigation, health monitoring and hearing assistance. The field excludes fully immersive virtual-reality headsets that block the wearer's view, helmet-mounted displays, conventional passive eyewear, and hearing aids or earbuds that are not integrated into eyewear.

A second, shorter description for the **audio & hearing** segment is useful too: the model can then score each family both for "smart glasses" and for "hearing-related".

### 4.5 Output of Step 0

1. the definition paragraph(s);
2. the boundaries table (4.1) and the segments table (4.2);
3. the seed patents with their codes;
4. the first version of `config/sector.yaml` (section 5).

## 5. The config file: one list per role in the query

For **selection** we group codes and keywords by what they do in the query; for **description** we keep a separate segment map.

```yaml
description: "Smart glasses are wearable computing devices ..."
description_hearing: "Eyewear that captures, enhances or delivers sound ..."

years: {min: 2000, max: 2025, truncated: 3}

selection:
  core_cpc:          ["G02B27/017", "G02C11/10", "G02C11/06", ...]
  core_ipc:          ["G02B27/01", "G02C11/00", ...]
  component_cpc:     ["H04R1/10", "G06F3/011", "G06T7/70", "H01Q1/273", ...]
  component_ipc:     ["H04R1/10", ...]
  specific_keywords: ["smart glasses", "smart eyewear", "augmented reality glasses", "hearing glasses"]
  eyewear_terms:     ["spectacle", "eyeglass", "eyewear", "glasses", "temple", "frame"]
  exclude_terms:     ["swimming goggle", "welding", ...]

segments:
  display_optics:    {cpc: ["G02B27/01", "G02B6/34", ...], terms: ["waveguide", "projector", ...]}
  audio_hearing:     {cpc: ["H04R", "G02C11/06", ...],     terms: ["bone conduction", "beamforming", "hearing aid", ...]}
  camera_sensing:    {cpc: ["H04N23/57", "G06V20/20", ...], terms: ["camera", "eye tracking", ...]}
  interaction:       {cpc: ["G06F3/01", "G06T19/006", ...], terms: ["gesture", "voice command", ...]}
  frame_power:       {cpc: ["G02C5/22", "H01Q1/273", ...],  terms: ["hinge", "battery", "antenna", ...]}
```

| List | Role |
|---|---|
| `core_cpc`, `core_ipc`, `specific_keywords` | enough on their own: the family is in the sector |
| `component_cpc`, `component_ipc` | **never enough alone**: only together with `eyewear_terms`, or after the semantic filter |
| `eyewear_terms` | restricts generic component codes to eyewear |
| `exclude_terms` | removes known false positives |
| `segments` | not used for selection; tags each selected family for Step 1–2 |

Selection rule for the candidate pool:

```
Sector = core_cpc ∪ core_ipc ∪ specific_keywords
       ∪ (component codes ∩ eyewear_terms)
       − exclude_terms
```

**Why IPC as well as CPC:** for **coverage**, not for infringement. CPC is used by the EPO and USPTO; IPC by almost every office, so some CN, JP and KR filings are only classified in IPC.

YAML rather than JSON because the kick-off suggests `config/sector.yaml`; it also allows comments next to each code (its CPC title and why we chose it).

## 6. The other steps, briefly

**[1] Candidate pool (SQL).** Family level, `ipr_type = 'PI'`, no dummy applications, year window on `earliest_filing_year`, blank-stripped prefix matching (`symbol_prefix_condition` from Tutorial 0). For each family one 0/1 column per rule (`r_core_cpc`, `r_core_ipc`, `r_keyword`, `r_component_eyewear`, `r_component_only`). This gives the "contribution of each strategy" table of Tutorial 0, Section 5.6, and lets us measure each rule's precision. Families that match only a component code are **candidates** for the semantic filter, not accepted directly.

**[2] Expansion from the data.**
- *Keyword mining (the "Amplifon" idea, made more robust):* take the core families plus the patents of Amplifon **and of the main players** in each segment, compare them with background patents using **TF-IDF**, and keep the 1–3-word phrases that are clearly over-represented. Plain frequency gives generic words ("device", "signal"), and one company alone would bias the definition (and Amplifon may have few patents).
- *Code mining:* for each CPC/IPC code, its **lift** = share among core families ÷ share among all patents. High-lift codes become candidates for `core`, `component` or a segment, after reading their scheme definition.
- Re-run [1]; 2–3 rounds are usually enough. Every term added is logged with its reason (technical appendix).

**[3] Semantic filter.** Every candidate family is scored with **Patent SBERT-adapt-ub** (`graziasveva93/sbert-adapt-ub`, introduced in Tutorial 0, Section 6): cosine similarity between one English abstract per family (priority EP > WO > US) and our definition. **BM25** runs alongside as a lexical baseline. Embeddings are computed once and stored outside git (TIP has 4 CPU cores, no GPU). They can be reused later: text-based novelty is one of the suggested ingredients of the future score (Step 4). Families without an English abstract rely on codes and keywords only; we report how many there are.

**[4] Validation.** The kick-off asks for about **100 random families** hand-labelled. We do that as the headline check (precision of the final dataset), and add a second, stratified sample across rules and score bands to tune the SBERT / BM25 threshold (precision, recall, F1 as in Tutorial 1, notebook 11; we keep the threshold with the best F1). Ideally two of us label independently and we report agreement. False positives feed `exclude_terms`, false negatives feed new keywords.

**[5] Final dataset.** One row per `docdb_family_id` with the rule flags, the semantic scores, the segment tags and the config version. Every later script reads this table instead of re-writing the SQL, so the whole group works on exactly the same sector. The table lives on TIP / shared storage, **not in git** (slide 18); git holds the config and the queries that rebuild it.

## 7. Proposed repository structure (aligned with kick-off slide 18)

```
config/
  sector.yaml                codes, keywords, segments, years      [0]
src/
  01_extract.py              candidate pool + rule flags           [1]
  01b_expand_terms.py        TF-IDF + code lift                    [2]
  01c_semantic_filter.py     SBERT + BM25 scores                   [3]
  01d_validate.py            labels -> precision / recall / F1     [4]
  02_clean.py                families, applicants, dates           [5]
  03_landscape.py ...        Steps 1-2, then scores and quadrant
notebooks/                   exploration only (current project/ notebooks move here)
data/labels/                 our hand labels (small, can be committed)
outputs/                     figures/ and tables/ (bulk extracts git-ignored)
```

We develop on **TEST** and run **PROD** once for the final numbers. We also keep a short log of how we use generative AI, since the deck needs a statement on it.

## 8. What we need from each of you now

1. **Boundaries:** agree on table 4.1, in particular the borderline row.
2. **Sources:** each person finds 1–2 sources from table 4.3 (ideally one paper with a patent search strategy for smart glasses or head-mounted displays) and 3–5 seed patents on Espacenet, at least one per segment.
3. **Definition:** comments and edits on 4.4, and a draft of the short hearing-segment description.
4. **Missing files:** `project/__pycache__/` contains compiled versions of `sector_keywords` and `cpc_validation`, but the `.py` files are not in the repo. If you have them, please push them.
