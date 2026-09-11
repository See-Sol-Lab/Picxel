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

- `keep`: 3–6 things, ordered by importance. At 16 the first two survive; at 32 the first four; at 64 all of them. Write them as what a viewer must recognise, not as drawing instructions.
- `drop`: what the reference has that the sprite must not try to carry. Everything high-frequency goes here: fur, strands, fabric weave, gradients, tiny jewellery.
- `regions`: boxes in fractions of the image (`x0, y0, x1, y1`). `detail` is the budget for that area: `fine` stays untouched in the mosaic pass, `medium` is blocked at 1/32 of the image width, `coarse` at 1/16. Later regions override earlier ones where they overlap, so list the big soft areas first and the small sharp ones last.
- `colors`: named in words; the palette step turns them into hex from the concept image.

Rules of thumb: hair, manes, foliage, cloth folds → `coarse`. Faces, hands, held objects, logos → `fine`. Bodies and clothing → `medium`. If you cannot name five things to keep, the size is too small for the subject or the subject is too busy for pixel art — say so instead of drawing.
