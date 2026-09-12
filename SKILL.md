---
name: picxel
description: Create and refine batches of pixel-art game assets in Claude Code or Codex. Convert references or descriptions into palette-indexed 32/64/128 PNGs, editable text grids and spritesheets using the current assistant's drawing or image tools, without requiring an API key.
---

# Picxel

You are the artist. Python handles grid alignment, palette reduction, validation and packing. Run commands from this skill's directory or use absolute script paths. Requires Python 3.10+ and Pillow.

## Output contract

- Square 32, 64 or 128 logical pixels. `item` / `sprite` have transparent corners; leave one pixel of breathing room. `tile` fills the canvas and repeats.
- Use 32 for compact simple assets, 64 for general assets, and 128 for detailed silhouettes or larger subjects. Generate or import from a detailed source at the intended size; enlarging a finished 64px sprite does not create 128px detail.
- `.pxg` holds one palette symbol per pixel: `A`–`P`, `.` transparent, at most 16 colors. PNG alpha is binary; previews use nearest neighbor.
- Use DB32 or a shared `.pal` for related assets. Imports may use `custom`. Aim for 4–8 colors on an item/tile, 8–16 on a portrait; 2–3 connected shade clusters per material.
- Passing `check` establishes format correctness, not artistic quality. `batch` emits **base-ready**, with visual review **pending**. Do not call unreviewed output game-ready.

## Choose the shortest drawing route

For simple props and tiles, use a small build script with `scripts/px.py`: silhouette → material blocks → broad shadows → identifying details. `Grid.rect`, `disc`, `tri`, `line`, `put` place exact pixels. Render and inspect. A potion reads from its bottle and liquid, not scattered texture. Start at the intended gameplay size.

For complex reference art, use the pipeline below. A native image tool can simplify anatomy and materials into a concept; the importer enforces the final grid. High-resolution generated pixels are not automatically a valid final sprite.

## Reference pipeline

1. **Anchor.** Look at the original; write `<name>.anchor.json` using [references/anchor.md](references/anchor.md). Record pose, silhouette and 3–6 identifying features in priority order. Identify which survive at 32, 64 and 128. Keep each reference and anchor in `refs/`.
2. **Prepare.** Run `python scripts/picxel.py batch refs -o work --provider codex --sizes 64`. This writes mosaics and prompts. Exit 2 and `needs-concept` mean the assistant must supply concepts. Inspect the mosaic beside the original: it can already lose identifying features.
3. **Produce concepts in the current session.** Inspect actual available tools. With a native image tool, supply the original, mosaic when helpful, and `work/<name>.prompt.txt`. Save selected output to `concepts/<name>.png`, one image call per asset. Request broad flat clusters, consistent outline and logical grid, matching style across the batch.
   - `codex` is a handoff label. Python never launches `codex exec` and cannot invoke a tool belonging to a running assistant.
   - For Claude Code, use an image tool if that session has one; otherwise draw a flat concept or the final grid with code. The `claude` label consumes that PNG. Distinguish drawing code from native image generation in reports.
   - `none` uses the mosaic locally. It is an inexpensive draft and cannot semantically redesign hair, hands or textures.
   - `api` accepts an externally supplied concept. Picxel has no API client, never requests a key and never silently switches to a paid call. Native tools remain subject to host-plan limits.
4. **Inspect concepts.** Verify pose and features. Check real alpha: a painted checkerboard is not transparency. Prefer alpha; if a tool supplies an opaque image, request one flat key color absent from the subject (e.g. magenta). Use `concept --background 'key:#ff00ff'` or `batch --concept-background 'key:#ff00ff'` for that intentionally chosen key: it removes enclosed holes too. Default `auto` removes edge-connected background only. Complex backgrounds need a mask/redraw; corner fill is not semantic segmentation. Generated gradients are quantized in the next step.
5. **Import.** Run `python scripts/picxel.py batch refs -o work --provider codex --concept-dir concepts --sizes 64`. Non-`none` providers consume `<name>.png`. Missing concepts remain `needs-concept`; one failure does not abort the batch. Use a fresh work directory for an independent batch.
6. **Refine.** Inspect native size AND 4×. `Grid.load()` → fix the largest silhouette/material error → restore identifying features. Use `show --box` to read the region you edit. `Grid.smooth(colors, keep="...")` merges low-contrast specks; `outline(color, keep="...")` protects specified tips/highlights. Paint outlines before final features or protect those features: an inside outline can erase a narrow handle or finger. Around 20 shape operations is a useful budget, not permission to deliver a failed image.
7. **Verify.** Apply [references/checklist.md](references/checklist.md), with a mid-pass and final visual inspection. Record yes/no per required anchor feature and unresolved defects. Failed primary features go to rework. Blocky photographic texture is still a failed style conversion.

`derive` is a starting point for smaller sizes. `--keep` protects cleanup only; it cannot restore a feature that lost the downsampling vote. Touch up eyes/handles at the final resolution. Draw a distinct small silhouette when needed instead of forcing every portrait detail into 32px.

## Batch orchestration

Prepare anchors and concepts first, then import, refine and review. Queue is the default; use subagents only when the user explicitly requests parallel agent work. Keep related assets on one palette, view, light direction and outline policy. A complete 16-color hex `palette` in the anchors locks batch colors; shorter lists reserve those colors and allow additional picks. Region boxes refer to the input frame; update them if the concept changes framing.

## Commands

```bash
python scripts/picxel.py batch refs -o work --provider none --sizes 64
python scripts/picxel.py concept work/hero.pre.png --anchor refs/hero.anchor.json --prompt-only
python scripts/picxel.py concept work/hero.pre.png --anchor refs/hero.anchor.json --provider codex --result concepts/hero.png -o work/hero.concept.png
python scripts/picxel.py palette work/hero.concept.png --anchor refs/hero.anchor.json --colors 12 -o work/hero.pal
python scripts/picxel.py import work/hero.concept.png --size 64 --palette work/hero.pal -o work/hero-64.pxg
python scripts/picxel.py show work/hero-64.pxg --box 20,25,45,50
python scripts/picxel.py smooth work/hero-64.pxg --passes 1 --keep BC
python scripts/picxel.py derive work/hero-64.pxg --sizes 32 --keep BC
# For a 128px master, derive its 64/32 variants:
python scripts/picxel.py derive work/hero-128.pxg --sizes 64,32 --keep BC
python scripts/picxel.py check work/hero-64.pxg
python scripts/picxel.py render work/hero-64.pxg -o work
python scripts/picxel.py sheet work -o work/dist
```

Deliver the self-contained `dist/index.html`, PNG/JSON and the visual review. Animation, non-square frames and an interactive editor are outside the format. See [SPEC.md](SPEC.md) for grid syntax, [references/palettes.md](references/palettes.md) for DB32 ramps and [examples/lion.build.py](examples/lion.build.py) for drawing syntax (an early experiment, not a quality target).
