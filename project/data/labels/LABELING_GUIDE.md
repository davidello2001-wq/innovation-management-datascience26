# Labelling guide · Smart glasses (client: Amplifon)

One rule and one file format for everyone who labels, human or AI, on every branch. The format is the one of the team validation worksheets (`trial_branch`, `src/validate_query.py`), so the same labelled files feed the precision script there and the classifier here.

Read the **title and abstract** of each family and fill these columns:

| Column | Values |
|---|---|
| `relevance_label` | **1** smart glasses (our sector) · **0** not in the sector · **?** cannot decide from title and abstract |
| `exclusion_reason` | only when the label is 0: one code of the list below |
| `technology_segment` | optional, when the label is 1, with the names used in the team worksheets: `display_AR_optics`, `audio_hearing`, `sensing_accessibility`, `interaction_tracking`, `hardware_power`, `smart_glasses_application` |
| `reviewer` | your initials (an AI labeller writes `AI`) |
| `review_notes` | in **English**, one short reason when the case is not obvious |

## 1 · Smart glasses

A device worn like **glasses** (or a see-through head-mounted display) with **electronics**, or something made clearly for such a device.

- AR / MR glasses and **see-through** head-mounted displays (optical or video see-through), including monocular head-worn displays
- glasses with a camera, sensors, a display, speakers, microphones, bone conduction, hearing-aid functions
- **audio and hearing glasses**, hearing aids built into spectacle frames, audio modules that clip onto glasses
- clip-on modules that turn ordinary glasses into smart glasses
- components **clearly** made for near-eye AR displays or smart glasses (waveguides, combiners, projectors, frames with batteries), when the abstract says so
- software, methods and systems whose device is **explicitly** AR glasses, smart glasses or a see-through HMD
- charging cases and accessories made for smart glasses

## 0 · Not in the sector: say why

| `exclusion_reason` | When |
|---|---|
| `adjacent_hmd_vr` | **adjacent market**, kept apart and shown as a comparison: closed / immersive VR headsets and their lenses, straps, housings; software and methods for VR, or for a head-mounted display whose type is **not stated**; helmet-mounted displays |
| `vehicle_hud` | head-up displays for cars, vehicles or aircraft (windshield, cockpit, dashboard) |
| `viewing_3d` | 3D viewing glasses for TV, monitors or cinema (shutter or polarised glasses) |
| `conventional_eyewear` | eyewear without electronics: frames, hinges, temples, nose pads, sunglasses, ophthalmic lenses |
| `contact_lens` | contact lenses, including smart contact lenses |
| `eyewear_retail` | virtual try-on of frames, selling or fitting glasses, measuring faces for glasses |
| `unrelated` | "smart glass" windows, doors, building glass; anything else |

**Between 1 and `adjacent_hmd_vr`:** 1 only if the abstract says glasses / eyewear / see-through / AR. A head-mounted display whose type is **not stated** is 0 with `adjacent_hmd_vr`, not `?`: these families are a large part of the candidates and the classifier needs examples of them; `?` is kept for abstracts that say too little to tell what the device is at all. Earlier rows that were left empty or given 1 by default with the note "HMD type not stated" are read with this rule (`src/labels.py`).

A free-text reason written before these codes existed is still understood: a reason that mentions VR, a headset, a helmet or an HMD is read as the adjacent market.

The adjacent market is deliberately **not** a third label: the precision of a query only needs 1 / 0, and the reason tells the classifier and the deck which of the rejected families are the neighbouring HMD / VR market.

## Examples from our samples

| Title (abridged) | Label | Reason / why |
|---|---|---|
| New TWS intelligent glasses with wireless charging function | 1 | glasses with electronics |
| Glasses with hearing aids | 1 | hearing glasses |
| Danger source early warning system based on AR head-mounted display | 1 | AR HMD software |
| Waveguide with exit pupil expander for AR glasses | 1 | component made for AR glasses |
| Folding type virtual reality helmet | 0 | `adjacent_hmd_vr` |
| Menu navigation in a head-mounted display (VR content) | 0 | `adjacent_hmd_vr` |
| Modular augmented reality military helmet display | 0 | `adjacent_hmd_vr` |
| Dynamically calibrated head-up display (windshield) | 0 | `vehicle_hud` |
| Liquid crystal shutter glasses for stereo image | 0 | `viewing_3d` |
| Monture de lunettes (spectacle frame hinge) | 0 | `conventional_eyewear` |
| Crime prevention door using smart glass | 0 | `unrelated` |

## Files

- Labelled worksheets go in `project/data/labels/` (CSV, any name, with a `docdb_family_id` column). They are small and are the evidence of the validation: commit them.
- Worksheets not labelled yet stay out of that folder (e.g. `project/data/unlabeled/`): a family listed in `data/labels/` is not sampled again.
- Older files with the first format of this branch (`label` 1 / 2 / 0, `labeler`, `note`; 2 = adjacent market) are still read: `src/labels.py` converts both formats to the same table. If two files disagree on a family, it is flagged as a conflict and left out until someone decides.
