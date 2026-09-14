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
2. **Prepare concepts.** `batch refs -o work --provider codex --sizes 64` prints the next actions. Read needed prompts together. One concept per asset serves all requested sizes. Save the exact reported filename (`name.png`) to `concepts/`. Review concepts together with their pixel outputs in step 4. The user judges style suitability; do not classify outliers or require style choices. Regenerate only an asset with an observed composition/identity failure.
3. **Finish locally once.** After the requested concepts are ready, run `batch refs -o work --provider codex --concept-dir concepts --sizes 64` once for the batch. It shares each decoded concept and palette across sizes and creates `review-*.png`. Existing concepts skip mosaic work. For an intentionally chosen magenta key, pass `--concept-background 'key:#ff00ff'` in BOTH preparation and finishing so the generated prompt and removal agree; real alpha is preferable. A painted checkerboard is not transparency.
4. **Review and edit selectively.** Open the reported `review-*.png`: each page shows up to four concepts with requested sizes enlarged and native. Apply [checklist.md](references/checklist.md), then crop only uncertain details. No custom overview script is needed. For edits, `show` gives a short palette summary; `show --box ...` prints just the necessary window. Use `Grid.load()`, shape operations and `write()`; do not read/rewrite a whole 128-row grid for a few pixels. Group related fixes in one script and render; `review work` refreshes the overview without rerunning generation or pixel conversion. Passing assets need no edits or repeated inspection.
5. **Eyes/mouth only when needed.** For complex faces, follow the face prompt and [faces.md](references/faces.md). Inspect the high-resolution original gaze before a local patch. Preserve eyebrows, nose, hair and eye contours; gaze outranks contrast. Clear faces stay unchanged. Do not smooth/outline after eye repair.
6. **Deliver immediately after acceptance.** For a panel job, `job done` exports the image-only deliverables; give a concise result. Create an atlas/HTML with `sheet work -o work/dist` only when requested. Do not rerun batch, build duplicate packaging, or write a lengthy review log just to finish. Read the full JSON report only when the console summary lacks a needed detail.

## The panel (when the user mentions it)

`python scripts/picxel.py panel` opens a local page where the human picks the import folder (or a few images), the export folder, single vs batch (at most 20), sizes, with no optional checkboxes. Assets are generated sequentially. There is no generate button: the page tells the user to talk to you. The page never drives you; it only writes a job file and watches the export folder.

Single mode shows the source, available concept and pixel output, with an optional 5-second reveal/replay of delivered pixels. This is a presentation animation, not the model's internal stroke history. Save normal outputs as usual; do not add model calls, split drawing into artificial steps, or delay `job done` for the animation. Batch mode keeps the spinner.

1. `job show` prints the job (import, export, files, sizes). Take paths and options from it instead of asking again.
2. `job start` right before the first batch/refine step; the page shows one spinner with elapsed time.
3. Work as usual, writing every final `<name>-<size>.png` / `@4x.png` into the export folder (`batch ... -o <export>`; refined sheets rendered there too). Generate one asset at a time.
4. `job ask --note "what you need"` whenever you stop to wait for the user (a question in chat): the page drops the spinner and says it is waiting for them; `job start` again when you resume (the clock keeps running from the original start).
5. `job done` at the end (automatically copies clean concepts and completed native PNGs into the image-only `成品图/` subfolder), or `job stop --note "why"` when you must stop early (quota, a failed asset you will not retry). Never leave it running: the page then shows cards for what exists and says "interrupted", which is what the user wants to see. The page also reads `batch-report.json` in the export folder to explain missing sizes and show check warnings, so keep `batch -o <export>` pointed there.

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
python scripts/picxel.py review work
python scripts/picxel.py face work/hero-64.pxg --anchor refs/hero.anchor.json --patch work/hero.face.json
python scripts/picxel.py sheet work -o work/dist
```

`--only` processes named assets, preserves unrelated outputs, and writes a report for that invocation. Use a separate redo folder when retaining reviewed results; do not rerun the whole batch just to package it. `show --full` is available only when the entire grid is actually needed; `show --box` numbers its columns from the box's own x0, not from 0, so read edit coordinates off that ruler. After major edits to a larger sprite, `derive big-128.pxg --sizes 64,32` can create smaller starting points, but inspect their eyes/handles independently. `derive` writes only the `.pxg`: render the derived sheets yourself (`render(load(path), out_dir)`) or the panel and the delivery folder never see them.

For photographs, the concept model redraws the isolated subject using the original for identity and pose. Request transparency or a deliberate absent-from-subject key upfront; do not carry sky/grass/room into the concept and then repaint every size to remove it. The local `none` provider can only draft a photo; it cannot replace this semantic redraw.

For simple assets without references, draw directly with `scripts/px.py`: `Grid(n)`, `rect`, `disc`, `tri`, `line`, `put`, `outline`, `write`. Shapes cost fewer decisions than ASCII rows. Draw outline before important small features or protect them with `keep`. Palette format: [palettes.md](references/palettes.md); grid format: [SPEC.md](SPEC.md).

`codex/claude/api` are concept-source labels, not subprocess/API clients. Use actual current-session capabilities; without an image tool, draw with code. `none` is local mosaic drafting and cannot perform a requested style redraw. No silent paid fallback. The panel workflow processes assets sequentially. No animation/editor/panel work is included here.
