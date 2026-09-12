"""A visual refinement of the supplied lion/woman concepts, not a universal filter.

Run after batch --provider codex --concept-dir ... --sizes 64,32; these
subject-specific 64/32 examples consolidate
each material's ramp. New subjects need their own visual decisions.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from picxel import load, render, smooth_sheet, build_sheet
from px import Grid

src, out = map(Path, sys.argv[1:3])
out.mkdir(parents=True, exist_ok=True)
RAMPS = {
    "lion": {"#733119": "#5e2712", "#df8a3d": "#cd762f", "#bc6629": "#8d4a26"},
    "woman": {"#282728": "#181618", "#d5976f": "#ca8860", "#eaa475": "#f1b990",
              "#be6f49": "#ca8860", "#f8caa3": "#f1b990", "#ca3424": "#ae221b"},
}
for subject, replacements in RAMPS.items():
    for size in (64, 32):
        sheet = load(src / f"{subject}-{size}.pxg")
        # Consolidate equivalent symbols too, so cluster checks see actual colors.
        target = {sym: replacements.get(color, color) for sym, color in sheet.colors.items()}
        symbols = {}
        for sym, color in target.items():
            symbols.setdefault(color, sym)
        sheet.rows = ["".join("." if sym == "." else symbols[target[sym]] for sym in row) for row in sheet.rows]
        sheet.colors = {sym: color for color, sym in symbols.items()}
        smooth_sheet(sheet, 1, "")
        # Restore features named in the anchors after palette/cluster cleanup.
        grid = Grid(size)
        grid.g = [list(row) for row in sheet.rows]
        if subject == "woman" and size in (64, 32):
            sheet.colors["P"] = "#d9a066"
            points = ((29, 31), (30, 32), (31, 33), (32, 32), (33, 31)) if size == 64 else ((14, 15), (15, 16), (16, 15))
            grid.put("P", *points)
        if subject == "lion" and size == 64:
            grid.put("A", (29, 38), (30, 38), (31, 38), (32, 38), (33, 38), (29, 39), (33, 39))
            grid.put("L", (30, 38), (30, 39))
        sheet.rows = grid.rows()
        used = {sym for row in sheet.rows for sym in row}
        sheet.colors = {sym: color for sym, color in sheet.colors.items() if sym in used}
        sheet.palette = "custom"
        sheet.path = out / f"{subject}-{size}.pxg"
        sheet.path.write_text(sheet.dump(), encoding="utf-8")
        render(sheet, out)
build_sheet(out, out / "dist", 3)
