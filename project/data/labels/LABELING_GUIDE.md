# Labelling guide · Smart glasses (client: Amplifon)

One rule for everyone who labels, human or AI. Read the **title and abstract** of each family and write one value in the `label` column.

| Label | Meaning | Counted as |
|---|---|---|
| **1** | **Smart glasses** | our sector |
| **2** | **Adjacent head-mounted display / VR market** | kept apart, shown as a comparison |
| **0** | **Not related** | out |
| *(empty)* | cannot decide from title and abstract: say why in `note` | left out of the metrics |

## 1 · Smart glasses

A device worn like **glasses** (or a see-through head-mounted display) with **electronics**, or something made clearly for such a device.

- AR / MR glasses and **see-through** head-mounted displays (optical or video see-through), including monocular head-worn displays
- glasses with a camera, sensors, a display, speakers, microphones, bone conduction, hearing-aid functions
- **audio and hearing glasses**, hearing aids built into spectacle frames, audio modules that clip onto glasses
- clip-on modules that turn ordinary glasses into smart glasses
- components **clearly** made for near-eye AR displays or smart glasses (waveguides, combiners, projectors, frames with batteries), when the abstract says so
- software, methods and systems whose device is **explicitly** AR glasses, smart glasses or a see-through HMD
- charging cases and accessories made for smart glasses

## 2 · Adjacent market: other head-mounted displays and VR

Head-worn display technology that is **not** smart glasses.

- **closed / immersive VR headsets** (the view of the surroundings is blocked), VR helmets, phone VR boxes, and their lenses, straps, housings
- **software, methods and systems for VR**, or for a head-mounted display whose type is **not stated** (no sign of glasses, see-through optics or AR)
- helmet-mounted displays (military, aviation, industrial helmets)

When in doubt between 1 and 2: **1 only if the abstract says glasses / eyewear / see-through / AR**; otherwise 2.

## 0 · Not related

- head-up displays for **cars, vehicles or aircraft** (windshield, cockpit, dashboard)
- **3D viewing glasses** for TV, monitors or cinema (shutter or polarised glasses)
- **conventional eyewear** without electronics: frames, hinges, temples, nose pads, sunglasses, ophthalmic lenses
- **contact lenses**, including smart contact lenses
- virtual try-on of frames, selling or fitting glasses, measuring faces for glasses
- "smart glass" windows, doors, building glass; anything else unrelated

## Columns

- `label`: 1, 2, 0 or empty (nothing else)
- `labeler`: your initials (an AI labeller writes `AI`)
- `note`: in **English**, one short reason when the case is not obvious (e.g. "VR headset", "car HUD", "AR glasses software")

## Examples from our samples

| Title (abridged) | Label | Why |
|---|---|---|
| New TWS intelligent glasses with wireless charging function | 1 | glasses with electronics |
| Glasses with hearing aids | 1 | hearing glasses |
| Danger source early warning system based on AR head-mounted display | 1 | AR HMD software |
| Waveguide with exit pupil expander for AR glasses | 1 | component made for AR glasses |
| Folding type virtual reality helmet | 2 | VR headset |
| Menu navigation in a head-mounted display (VR content) | 2 | VR / unspecified HMD software |
| Modular augmented reality military helmet display | 2 | helmet-mounted display |
| Dynamically calibrated head-up display (windshield) | 0 | car HUD |
| Liquid crystal shutter glasses for stereo image | 0 | 3D viewing glasses |
| Monture de lunettes (spectacle frame hinge) | 0 | conventional eyewear |
| Crime prevention door using smart glass | 0 | smart glass window |
