# The anchor sheet — what to keep before anything is drawn

Before touching a reference, look at it and write `anchor.json` next to it. The anchor is the contract for every later step: the mosaic uses `regions`, the concept prompt uses `keep`/`drop`, the palette weights by `regions`, and the final check asks whether each `keep` item is still visible.

```json
{
  "subject": "woman with long black curly hair, arms crossed, pistol in right hand",
  "kind": "sprite",
  "size": 64,
  "keep": [
    "long black curly hair silhouette",
    "arms crossed, hands visible",
    "red halter dress with gold sheen",
    "black pistol in the right hand",
    "red lips; eyes as two dark points"
  ],
  "drop": [
    "hair strand texture",
    "dress pattern",
    "skin gradients",
    "earrings",
    "eye makeup and nose"
  ],
  "regions": [
    {"name": "hair",  "box": [0.05, 0.02, 0.95, 0.95], "detail": "coarse"},
    {"name": "face",  "box": [0.35, 0.15, 0.62, 0.42], "detail": "fine"},
    {"name": "dress", "box": [0.25, 0.42, 0.75, 1.00], "detail": "medium"},
    {"name": "gun",   "box": [0.55, 0.55, 1.00, 0.85], "detail": "fine"}
  ],
  "colors": ["black hair", "pale skin", "red dress", "gold sheen", "red lips"]
}
```

- `keep`: 3–6 things, ordered by importance. At 32 prioritize the first few; at 64 preserve the main features; at 128 use the extra pixels for shape and feature clarity. Review each size instead of assuming all details survive. Write them as what a viewer must recognise, not as drawing instructions.
- `drop`: what the reference has that the sprite must not try to carry. Everything high-frequency goes here: fur, strands, fabric weave, gradients, tiny jewellery.
- `regions`: boxes in fractions of the image (`x0, y0, x1, y1`). `detail` is the budget for that area: `fine` stays untouched in the mosaic pass, `medium` is blocked at 1/32 of the image width, `coarse` at 1/16. Later regions override earlier ones where they overlap, so list the big soft areas first and the small sharp ones last.
- `colors`: named in words; the palette step turns them into hex from the concept image.
- Optional `faces`: only for visible human/animal faces. Each entry has an original-frame `box`, boolean `complex`, an `expression` to retain and a concrete `reason`; complex faces also require a `gaze` observation from the high-resolution original. Clear faces keep the normal workflow; complex faces are checked again after pixelization and repaired only when needed. See [faces.md](faces.md). These source boxes are not assumed to be final-grid edit coordinates.
- Optional `palette`: explicit lowercase hex colors to reserve, e.g. `["#222034", "#ffffff", "#d95763"]`. It must fit the requested color count. Supply the complete shared palette to lock colors across related assets. Words in `colors` guide the assistant; they do not reserve numeric colors by themselves.

Rules of thumb: hair, manes, foliage, cloth folds → `coarse`. Faces, hands, held objects → `fine`. Bodies and clothing → `medium`. A simple item may need only a few anchors. The budget describes what matters, not a promise that an importer will understand anatomy.

Mosaic color blocks align to the full image and retain the source alpha silhouette. Region boxes still refer to the original frame. After a concept changes pose, crop or proportions, look at it and update the boxes before palette weighting. The final review uses the original semantic `keep` list.
