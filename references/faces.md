# Conditional eye and mouth refinement

Only add this pass for a visible human or animal face. Objects without a face keep the ordinary pipeline. The current assistant judges source complexity and grid readability; Python is not a face/eye detector and does not infer landmarks from dark blobs.

## Annotate the source

When writing the anchor, inspect whether a face is present. Add `faces` only when relevant:

```json
"faces": [
  {
    "box": [0.36, 0.10, 0.67, 0.36],
    "complex": true,
    "expression": "calm, slightly aloof, half-lidded eyes, small red lips, slight head tilt",
    "gaze": "downward; pupils on image-left, visible sclera on image-right",
    "reason": "bangs, eyeliner and shadows may merge into the eyes at the target resolution"
  }
]
```

Boxes are fractions of the original reference frame. Use `complex: false` for clearly separated, readable features; preserve those faces through the normal process. Complexity is about likely feature confusion at the intended pixel size, not whether a photograph is high-resolution. Bangs across eyes, heavy shadows/makeup, overlapping hair and tiny facial regions can make conversion difficult. State a concrete reason, expression and original gaze to preserve. A complex face requires a nonempty `gaze` observation. Describe left/right in image coordinates and pupil placement relative to sclera; the example direction is not a default for other subjects.

## Inspect the pixel result before changing it

For a complex face, `batch` writes a size-specific `.face-prompt.txt` and a `face_review` entry with `needs-face-review`. Clear faces receive `preserve`; faceless assets receive no face step. The base image still renders normally. This is an assistant review task, not proof a redraw is necessary.

Inspect a close crop from the **high-resolution original**, not just the generated concept, then compare the grid at native size and enlarged. Preserve the original pupil position, the side on which sclera is visible, eyelid openness and gaze direction before increasing clarity. A clear eye that looks in the wrong direction is a failed repair.

1. Keep eyebrows, nose, hair, face shading and existing eye contours unchanged. This pass only repairs eyes and mouth; it does not establish or add eyebrows.
2. For an unclear open eye, add the smallest useful light/dark distinction **on the correct side**. Preserve the original pupil location and low upper eyelid when the subject looks downward. Never move a pupil up/right or mirror the sclera to satisfy a contrast check. If gaze is uncertain, keep the original pixels and report uncertainty.
3. Keep intentional closed eyes, profile visibility and deliberate occlusion. Animal eyes use species-appropriate pupils/glints; do not force human sclera or two visible eyes.
4. Repair mouth pixels only if unclear, preserving the original mouth shape and expression. A readable mouth needs no edits.

Locate the face again on the final grid: cropping, padding and concept redrawing can change its position. Never multiply the original reference box by the output size and assume it is the correct edit region. Use a small `show --box` window for the actual grid.

## Apply a local patch

Use the existing palette symbols to write only tight eye or mouth rectangles that need repair. Coordinates are inclusive. This schematic plan targets an already inspected grid:

```json
{
  "source": "hero-64",
  "size": 64,
  "patches": [
    {
      "face": 0,
      "feature": "eye",
      "box": [28, 16, 30, 16],
      "rows": ["AHP"],
      "eyes": [{"box": [28, 16, 30, 16], "light": "P", "dark": "A"}]
    }
  ]
}
```

`face` indexes the anchor's faces. `feature` must be `eye` or `mouth`; old full-face/brow patches are rejected. `rows` exactly fill the patch rectangle. Multiple non-overlapping patches are allowed. `eyes` is optional and only lists open eyes whose light/dark separation is being checked; omit it for closed/occluded eyes. The check requires both selected symbols to occur in the eye region and an Oklab lightness difference of at least 0.3. Changes in an open-eye patch must stay inside its declared eye boxes. Mouth patches cannot carry eye edits. The program cannot identify anatomy from the coordinates or certify gaze: accurate localization and original-gaze comparison remain the assistant's visual responsibility.

If the source sheet has a free symbol and its approved palette has an unused suitable light/dark color, an optional top-level `colors` map can declare it, e.g. `{"P":"#ffffff"}`. Existing colors cannot be redefined globally. The existing palette membership and 16-color cap still apply. If pixel area or palette contrast is insufficient, report that constraint or recommend a larger supported size instead of silently changing the global palette or forcing bad eyes.

```bash
python scripts/picxel.py face work/hero-64.pxg --anchor refs/hero.anchor.json --prompt-only
python scripts/picxel.py face work/hero-64.pxg --anchor refs/hero.anchor.json --patch work/hero.face.json
```

The command creates `hero-64-face.pxg` plus native/4× PNGs beside the source. It preserves the source file, all pixels outside the chosen rectangles, the alpha silhouette, and existing color values. Invalid plans fail before writing. Move selected final assets into a delivery folder before packing, so the original and refinement are not accidentally delivered as duplicate variants.

Inspect the result again against the original gaze and expression; correct contrast alone is insufficient. Confirm that no eyebrows were added and that pupil/sclera placement was not reversed. Do not run blanket smoothing or outlining after this pass: intentional eye highlights and pupil pixels must survive. Repeat this judgment at each requested size; a good 128px face can be unreadable at 32px. These rules apply equally to single-image and batch work, while preserving the existing rendering style.
