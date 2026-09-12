---
name: picxel
description: Produce game-ready pixel-art assets (tiles, items, character sprites) by writing a text grid of palette symbols that a script renders and checks. Use when the user asks for pixel art, sprites, tiles, tilesets, game assets, 16x16 / 32x32 / 64x64 art, or to convert an image into pixel art. Never use an image-generation model for the pixels themselves.
---

# Picxel

You are the pixel artist. You write a `.pxg` sheet — a header of palette symbols plus one line of characters per row — and `scripts/picxel.py` renders it to PNG, checks it, and packs a directory of sheets into a spritesheet with a preview page. Every pixel is a character you chose.

## Fixed rules (v0.1)

- Sizes: **16, 32, or 64** only. Tiles and items default to 32; a hero or boss at 64; icons and tiny props at 16. Nothing else.
- Palette: at most **16 colors** per sheet, chosen from `references/palettes.md` (DB32). `palette: custom` only when importing a user's PNG.
- Symbols: `A`–`P` for colors, `.` for transparent. One character per pixel, exactly `size` rows of `size` characters.
- `kind: tile` must have no transparent pixels and must repeat cleanly; `kind: item` and `kind: sprite` must have transparent corners.
- You never ask an image model to draw the sprite. A reference image (the user's, or one they generated elsewhere) is for looking at, not for pasting.

## Sheet format

```
name: grass-01
size: 32
kind: tile
palette: db32
A: #4b692f
B: #6abe30
C: #99e550
---
AAAAAAAABAAAAAAAAAAAAAAAAAAABAAA
... 32 rows in total ...
```

Names are stable identifiers (`grass-01`, `hero-idle-front`, `potion-red`); the spritesheet JSON keys on them.

## How to draw (do not skip steps)

1. **Decide** size and kind from the request. Write the header with the ramps you will use (see the ramp list in `references/palettes.md`; 2–4 steps per material, light from the top-left).
2. **Silhouette first.** Fill the grid with one color and `.` only. Render (`render`) and look at the `@4x.png`. If the shape does not read as the thing at 4×, fix the shape now — colors will not save a bad silhouette.
3. **Flat color.** Replace the silhouette with 2–4 base colors, one per material. Render, look.
4. **Shade.** Add one lighter and one darker step per material along its ramp; highlights up-left, shadows down-right. Render, look.
5. **Outline and clean.** Trace the outer edge in the darkest color, one pixel thick; remove isolated pixels; fix jagged diagonals. Render, run `check`, look.
6. **Critique** against `references/checklist.md` and fix. Two look-fix rounds minimum. Deliver only a sheet that passes `check` with no errors.

**Use `scripts/px.py` to author.** Writing 64 rows by hand invites off-by-one errors; instead write a small build script (`examples/lion.build.py` is the model) that places shapes with `Grid.disc / tri / rect / put`, shades by rules, calls `outline()` last and `write()`s the `.pxg`. Every call is still your decision about specific pixels; the script just keeps the rows aligned and makes the next pass a one-line edit. Draw the features that must read (ears, eyes, hands) *after* hair, manes and tufts, or they get buried.

Working at 64: draw the silhouette at 32 first, scale the idea up mentally, then fill 64 in four 32×32 quadrants (top-left, top-right, bottom-left, bottom-right) so each quadrant is a full row set you can reason about.

Tiles: keep detail scattered and small; anything centered becomes a polka-dot field when repeated. The `check` seam warning compares the left/right and top/bottom edges — soften edge rows/columns until it is quiet.

## From a reference image (the main path for batches)

Drawing from imagination misses what the reference shows (pose, tilt, proportion). When the user gives an image, do not start on a blank canvas:

1. **Anchor.** Look at the image and write `<name>.anchor.json` (format: `references/anchor.md`): 3–6 things to keep, what to drop, regions with a detail budget (`coarse` / `medium` / `fine`), size, kind. This is free — you are the vision model.
2. **Mosaic.** `mosaic ref.png --anchor ref.anchor.json` strips the background (corner flood fill) and blocks each region at its budget: hair and cloth go coarse, faces and held objects stay fine.
3. **Concept** (optional). `concept ref.pre.png --anchor … --provider none` uses the mosaic as the concept. Providers `codex` / `claude` / `api` are reserved for a flat redraw with an image model and are not implemented yet; `--prompt-only` prints the prompt they must use.
4. **Palette.** `palette ref.concept.png --colors 12 -o ref.pal` — colors come from the image, so hue never drifts.
5. **Base sheet.** `import ref.concept.png --size 32 --kind sprite --palette ref.pal` — pose and silhouette land on the grid at zero cost.
6. **Refine, ≤ 20 steps.** `smooth` first, then edit with `scripts/px.py`: `Grid.load()` the sheet, `erase()` what the downsample smeared, `replace()` a muddy color with its ramp neighbor, redraw the two or three `keep` features that got lost (eyes as dots, the held object's silhouette), `outline()`, `write()`. Render and look once in the middle and once at the end.
7. **Verify.** Look at the `@4x.png` next to the anchor: is every `keep` item still recognisable? Answer yes/no per item in your report; a `no` on the first two items means redo, not deliver.

Two rules learned the hard way:
- **Erasing exposes what was behind.** `erase()` on a region shared with hair/body leaves a transparent notch — repaint the background layer before calling it done.
- **Refine once, at the largest size.** Fix the 64 sheet, then majority-vote downsample it to 32 and 16 (2x2 / 4x4 cells); only tiny touch-ups (a lost held object, a two-pixel eye) happen at the small sizes. Never run the full refine three times.

## Batches

Two modes; the user chooses:
- **queue** — one asset at a time through steps 1–7, cheapest in tokens, no interaction until the sheet is built.
- **parallel** — split the manifest across subagents, one asset each, same steps; fast, several times the tokens.
Batch runs never edit interactively; assets that fail verification go to a redo list, which the user reopens one at a time in single mode. Steps 1–4 for the whole manifest first, then 5–7.

The deterministic half is one command. Put each reference image next to its `<name>.anchor.json` in one directory (you write the anchors first — that is step 1 for the whole batch), then:

```bash
python scripts/picxel.py batch refs/ --sizes 32          # -> refs/base/: pre, concept, .pal, base .pxg + renders, batch-report.json
```

One bad job never sinks the batch — it lands in the report as `failed`. After `batch`, only steps 6–7 (refine + verify) remain per sheet; that is where queue vs parallel applies.

## Commands

```bash
python scripts/picxel.py check  assets/grass-01.pxg
python scripts/picxel.py render assets/grass-01.pxg -o out        # out/grass-01.png + out/grass-01@4x.png
python scripts/picxel.py import ref.png --size 32 --kind sprite   # ref.png -> ref.pxg, colors snapped to DB32
python scripts/picxel.py sheet  assets -o assets/dist             # sheet.png + sheet.json + index.html + png/
python scripts/picxel.py mosaic ref.png --anchor ref.anchor.json  # -> ref.pre.png (background stripped, regions blocked)
python scripts/picxel.py concept ref.pre.png --anchor ref.anchor.json --provider none   # -> ref.concept.png
python scripts/picxel.py palette ref.concept.png --colors 12 -o ref.pal
python scripts/picxel.py smooth assets/hero.pxg --passes 2 --keep B  # merge specks; keep symbol B (eyes) untouched
python scripts/picxel.py batch refs/ --sizes 64,32                # whole directory of <name>.anchor.json + image -> base sheets
```

Read the `@4x.png` after every render — that is your eyes. Open `dist/index.html` for the user: it is self-contained (zoom, checkerboard, kind filter, download links), no server needed.

## Batches without references

A list like "4 grass variants, 2 dirt, a fence in 3 pieces, 20 items" goes through the from-scratch steps, one `.pxg` per asset in one directory, then `sheet` once at the end. Report kept warnings in one line each; redo only what the user marks.

## Importing

`import` turns a square PNG (any integer multiple of the size) into a sheet by majority color per cell, snapped to DB32. Use it to bring in the user's existing art, then edit the `.pxg` like any other sheet: recolor a material by changing one header line, add a variant by copying the file and editing rows.

## What this skill does not do

No animation, frame alignment, or anchors — that is the game engine's job. No non-square sizes. No editor UI. If asked for these, say so and deliver the static assets.
