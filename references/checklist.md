# Look, then fix — the critique checklist

Run this against the `@4x` preview after every pass. Fix what fails, re-render, look again. Two passes minimum; do not deliver a sheet you have not looked at.

## Reads at a glance
- [ ] At 4× it is obvious what the thing is without the name. If you have to squint, the silhouette is wrong — fix the silhouette before touching colors.
- [ ] The silhouette is one solid shape (or a deliberate few). No thin one-pixel arms, stalks, or handles unless the size is 64.
- [ ] Nothing important sits on the outermost row/column of a `sprite` or `item` (it will touch the neighbor when placed in a scene).

## Pixels
- [ ] No orphan pixels: a single pixel whose four neighbors are all other colors is noise unless it is a deliberate highlight (eye glint, sparkle).
- [ ] No "jaggies": diagonal edges step by consistent amounts (1-1-1 or 2-2-2), not 1-3-1.
- [ ] No doubled outline: outline is one pixel thick everywhere.
- [ ] Curves use the pixel-art circle pattern (long flat runs at top/bottom/sides, short steps at the diagonals), not a staircase of equal steps.

## Colors
- [ ] Each material has a ramp of 2–4 steps from one palette family, not random palette picks.
- [ ] Light comes from one direction (default: top-left). Highlights up-left, shadows down-right, everywhere.
- [ ] The darkest color is the outline color and nothing else uses it as fill, except deliberate deep shadow.
- [ ] Count colors: a tile 4–8, an item 4–8, a character 8–16. More than that is usually mud.
- [ ] No pillow shading (light ring around the edge, dark center) — that is the classic beginner tell.

## Tiles only
- [ ] Place the tile next to itself mentally (or check the seam warning): no visible line at the seam, no obvious repeating "feature" that will grid the whole map.
- [ ] Detail is scattered, not centered — a centered blob repeats as a polka-dot field.

## Characters only
- [ ] Features that must read (ears, eyes, horns, hands) are drawn **last**, on top of hair/mane/tufts — the lion's ears vanished under mane tufts until they were moved after them.
- [ ] Head is large relative to body at 16/32 (2:3 to 1:1 head-to-body); at 64 proportions can approach 1:3.
- [ ] Eyes are 1–2 pixels and dark; a mouth is optional and often better omitted at 16/32.
- [ ] Feet sit on the bottom row or one above it, so the character stands on the tile below it.
- [ ] Left and right halves are near-mirrors for a front view (small asymmetry is fine, big asymmetry reads as a bug).

## Before delivering
- [ ] `check` passes with zero errors; every warning either fixed or explained in one line.
- [ ] Name is descriptive and stable (`grass-01`, `hero-idle-front`, `potion-red`), because the sheet JSON keys on it.
