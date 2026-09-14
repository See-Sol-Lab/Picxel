# Look, then fix — the critique checklist

Inspect the output at native size and enlarged. Fix failures, then inspect the changed result again. Leave passing assets alone; do not invent edits or repeat identical reviews to meet a cycle count. Do not deliver a sheet you have not looked at.

## Reads at a glance
- [ ] At native size and 4× it is obvious what the thing is without the name. Fix the silhouette before touching colors.
- [ ] The silhouette is one solid shape (or a deliberate few). No thin one-pixel arms, stalks, or handles unless deliberate and readable at the target size.
- [ ] Nothing important sits on the outermost row/column of a `sprite` or `item` (it will touch the neighbor when placed in a scene).

## Pixels
- [ ] Isolated pixels (no same-color 8-neighbor) are intentional details such as eye glints; inspect them instead of blindly deleting them. Low warning counts alone do not prove good art.
- [ ] No "jaggies": diagonal edges step by consistent amounts (1-1-1 or 2-2-2), not 1-3-1.
- [ ] No doubled outline: outline is one pixel thick everywhere.
- [ ] Curves use the pixel-art circle pattern (long flat runs at top/bottom/sides, short steps at the diagonals), not a staircase of equal steps.

## Colors
- [ ] Each material has a ramp of 2–4 steps from one palette family, not random palette picks.
- [ ] Light comes from one direction (default: top-left). Highlights up-left, shadows down-right, everywhere.
- [ ] Darkest tones serve outline, eyes and deliberate deep shadow. Large black hair masses are valid; keep their shape readable.
- [ ] Count colors: a tile 4–8, an item 4–8, a character 8–16. More than that is usually mud.
- [ ] No pillow shading (light ring around the edge, dark center) — that is the classic beginner tell.

## Tiles only
- [ ] Place the tile next to itself mentally (or check the seam warning): no visible line at the seam, no obvious repeating "feature" that will grid the whole map.
- [ ] Detail is scattered, not centered — a centered blob repeats as a polka-dot field.

## Characters only
- [ ] Features that must read (ears, eyes, horns, hands) are drawn **last**, on top of hair/mane/tufts — the lion's ears vanished under mane tufts until they were moved after them.
- [ ] Choose head/body proportions for the reference and game style. At 32 emphasize readability; 64/128 can retain more anatomical detail.
- [ ] Eye and mouth sizes follow the reference and target resolution. A chibi animal may need large eyes with distinct highlights; a small human may use two dark strokes.
- [ ] Full-body sprites have a consistent baseline while keeping export padding; portraits need no invented feet.
- [ ] Preserve intentional asymmetry, tilt and pose in the anchor. Use symmetry only when the actual view calls for it.

## Before delivering
- [ ] `check` passes with zero errors; inspect warnings, fix actual defects, and briefly group intentional details by cause instead of writing a line for every repeated warning.
- [ ] Name is descriptive and stable (`grass-01`, `hero-idle-front`, `potion-red`), because the sheet JSON keys on it.
- [ ] Check real alpha, no painted checkerboard/key-color halo, coherent flat material clusters, and consistent batch palette/light/view.
- [ ] Verify anchor features at each target size; a concise per-asset result may cover all passing sizes. Clearly separate an automatic base from a visually accepted final asset.
