---
name: pixelgrid
description: Produce game-ready pixel-art assets (tiles, items, character sprites) by writing a text grid of palette symbols that a script renders and checks. Use when the user asks for pixel art, sprites, tiles, tilesets, game assets, 16x16 / 32x32 / 64x64 art, or to convert an image into pixel art. Never use an image-generation model for the pixels themselves.
---

# pixelgrid

You are the pixel artist. You write a `.pxg` sheet — a header of palette symbols plus one line of characters per row — and `scripts/pixelgrid.py` renders it to PNG, checks it, and packs a directory of sheets into a spritesheet with a preview page. Every pixel is a character you chose.

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

## Commands

```bash
python scripts/pixelgrid.py check  assets/grass-01.pxg
python scripts/pixelgrid.py render assets/grass-01.pxg -o out        # out/grass-01.png + out/grass-01@4x.png
python scripts/pixelgrid.py import ref.png --size 32 --kind sprite   # ref.png -> ref.pxg, colors snapped to DB32
python scripts/pixelgrid.py sheet  assets -o assets/dist             # sheet.png + sheet.json + index.html + png/
```

Read the `@4x.png` after every render — that is your eyes. Open `dist/index.html` for the user: it is self-contained (zoom, checkerboard, kind filter, download links), no server needed.

## Batches

When the user gives a list ("4 grass variants, 2 dirt, a fence in 3 pieces, 20 items"), create one `.pxg` per asset in one directory, draw them one at a time through the steps above, then `sheet` the directory once at the end. Report the assets that have warnings you chose to keep, in one line each. If the user marks some for redo, redraw only those and re-run `sheet`.

## Importing

`import` turns a square PNG (any integer multiple of the size) into a sheet by majority color per cell, snapped to DB32. Use it to bring in the user's existing art, then edit the `.pxg` like any other sheet: recolor a material by changing one header line, add a variant by copying the file and editing rows.

## What this skill does not do

No animation, frame alignment, or anchors — that is the game engine's job. No non-square sizes. No editor UI. If asked for these, say so and deliver the static assets.
