---
name: picxel
description: Create and refine pixel-art game assets in Claude Code or Codex: references or descriptions to palette-indexed 32/64/128 PNGs, editable grids and spritesheets, using current-session drawing or image tools without requiring an API key.
---

# Picxel

The assistant makes visual decisions; Python enforces the grid and exports. Requires Python 3.10+ and Pillow. Run from this directory or use absolute script paths.

## Contract

- Output only requested sizes: 32, 64 or 128. Use 64 when unspecified; 32 for compact props, 128 for detailed subjects. Import larger sizes from a detailed source, not an enlarged small sprite.
- `.pxg`: symbols A–P, `.` transparent, at most 16 colors. Items/sprites need transparent corners; tiles repeat. Use coherent material ramps and preserve identifying features.
- `base-ready` is format success, not visual approval. Keep failures and pending choices visible.

## Workflow

1. **Inspect once, annotate.** Look at originals together; write one `<name>.anchor.json` per asset using [anchor.md](references/anchor.md). Record only useful keep/drop/region information. For visible faces, assess complexity and original gaze per [faces.md](references/faces.md); plain objects skip that path.
2. **Batch style** (only when the user asks, or the panel checkbox is on: `batch --style-check`). With two or more images, follow [batch-style.md](references/batch-style.md). Complete the generated `batch.style.json` visually; compatible assets need no question. Ask only about substantial outliers and honor the user's original/unify choice. `--only` still uses this full-batch context.
3. **Prepare concepts.** `batch refs -o work --provider codex --sizes 64` prints the next actions. Read only the needed prompt files. Generate/inspect the first baseline, then use approved concepts as style references where instructed. One concept per asset serves all requested sizes. Save the exact reported filename (`name.png` or `name.unified.png`) to `concepts/`. Inspect composition before import; regenerate only a failed asset.
4. **Finish locally.** `batch refs -o work --provider codex --concept-dir concepts --sizes 64`. Existing concepts skip mosaic work. Use `--concept-background 'key:#ff00ff'` for an intentionally chosen magenta key; real alpha is preferable. A painted checkerboard is not transparency.
5. **Review and edit selectively.** Inspect native/enlarged previews, using a batch overview first and detail crops for uncertain assets. Apply [checklist.md](references/checklist.md). For edits, `show` gives a short palette summary; `show --box ...` prints just the necessary window. Use `Grid.load()`, shape operations and `write()`; do not rewrite or read a whole 128-row grid for a few pixels. Group related changes in one build script, render, inspect. Passing results need no invented fixes.
6. **Eyes/mouth only when needed.** For complex faces, follow the face prompt and [faces.md](references/faces.md). Inspect the high-resolution original gaze before a local patch. Preserve eyebrows, nose, hair and eye contours; gaze outranks contrast. Clear faces stay unchanged. Do not smooth/outline after eye repair.
7. **Deliver.** `sheet work -o work/dist` creates PNG/JSON and an HTML overview. Deliver selected final assets and a concise keep-feature review. Read the full JSON report only when the console summary lacks a needed detail.

## Efficient operations

Use `python scripts/picxel.py` before these commands:

```text
batch refs -o work --provider none --sizes 64
batch refs -o work --provider codex --concept-dir concepts --sizes 128,64
```

For targeted rework and inspection:

```bash
python scripts/picxel.py batch refs -o redo --provider codex --concept-dir concepts --only hero potion --sizes 64
python scripts/picxel.py show work/hero-64.pxg
python scripts/picxel.py show work/hero-64.pxg --box 25,12,39,20
python scripts/picxel.py face work/hero-64.pxg --anchor refs/hero.anchor.json --patch work/hero.face.json
python scripts/picxel.py sheet work -o work/dist
```

`--only` processes named assets, preserves unrelated outputs, and writes a report for that invocation. Use a separate redo folder when retaining reviewed results; do not rerun the whole batch just to package it. `show --full` is available only when the entire grid is actually needed. After major edits to a larger sprite, `derive big-128.pxg --sizes 64,32` can create smaller starting points, but inspect their eyes/handles independently.

For simple assets without references, draw directly with `scripts/px.py`: `Grid(n)`, `rect`, `disc`, `tri`, `line`, `put`, `outline`, `write`. Shapes cost fewer decisions than ASCII rows. Draw outline before important small features or protect them with `keep`. Palette format: [palettes.md](references/palettes.md); grid format: [SPEC.md](SPEC.md).

`codex/claude/api` are concept-source labels, not subprocess/API clients. Use actual current-session capabilities; without an image tool, draw with code. `none` is local mosaic drafting and cannot perform a requested style redraw. No silent paid fallback. Queue is the default; subagents require explicit user request. No animation/editor/panel work is included here.
