"""Small deterministic game props; run from any directory, then inspect the previews."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from px import Grid
from picxel import build_sheet, load, render

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "out/items-32plus"
OUT.mkdir(parents=True, exist_ok=True)
PALETTE = {"A": "#222034", "B": "#663931", "C": "#8f563b", "D": "#d9a066",
           "E": "#eec39a", "F": "#ac3232", "G": "#d95763", "H": "#cbdbfc",
           "I": "#ffffff", "J": "#5b6ee1", "K": "#306082", "L": "#fbf236"}


def save(g, name):
    path = OUT / f"{name}.pxg"
    g.write(path, name, "item", PALETTE)
    render(load(path), OUT)


# Native 32px bottle: one-pixel contour and deliberate glass glints.
g = Grid(32)
g.disc(16, 20, 10, 9, "A")
g.disc(16, 20, 9, 8, "K")
g.rect(12, 6, 19, 14, "A")
g.rect(13, 7, 18, 14, "H")
g.rect(11, 4, 20, 8, "A")
g.rect(12, 5, 19, 7, "C")
g.line(12, 5, 17, 5, "E")
g.rect(9, 18, 22, 23, "F")
g.rect(11, 24, 20, 26, "F")
g.line(9, 18, 22, 18, "G")
g.line(10, 14, 10, 17, "I")
g.line(11, 13, 12, 12, "I")
g.line(11, 20, 11, 22, "G")
save(g, "potion-red-32")

# Chest at 32px: lid, lower body and fittings are broad connected regions.
g = Grid(32)
g.rect(5, 13, 26, 25, "A")
g.disc(16, 13, 11, 7, "A")
g.disc(16, 13, 9, 5, "C")
g.rect(7, 12, 24, 16, "C")
g.rect(8, 10, 23, 12, "D")
g.rect(10, 8, 21, 9, "D")
g.line(11, 8, 19, 8, "E")
g.rect(7, 18, 24, 23, "B")
g.rect(7, 18, 24, 19, "C")
g.rect(6, 12, 8, 24, "D")
g.rect(23, 12, 25, 24, "D")
g.line(6, 13, 6, 23, "E")
g.line(25, 13, 25, 24, "C")
g.line(9, 16, 22, 16, "A")
g.rect(14, 15, 17, 20, "A")
g.rect(15, 16, 16, 19, "D")
g.put("L", (15, 16))
g.put("A", (16, 18))
save(g, "chest-32")

# Diagonal blade uses consistent stair steps, with a broad guard and handle.
g = Grid(32)
g.tri(10, 18, 25, 4, 24, 11, "A")
g.tri(10, 18, 24, 11, 15, 22, "A")
g.tri(12, 18, 24, 6, 22, 12, "H")
g.tri(12, 18, 22, 12, 15, 20, "J")
g.line(13, 17, 23, 7, "I")
g.line(7, 26, 13, 20, "A")
g.line(6, 25, 12, 19, "A")
g.line(8, 27, 14, 21, "A")
g.line(7, 25, 12, 20, "C")
g.line(8, 26, 13, 21, "B")
g.line(8, 18, 17, 24, "A")
g.line(8, 17, 18, 24, "A")
g.line(9, 18, 17, 23, "D")
g.put("L", (9, 18), (10, 19))
g.rect(5, 25, 8, 28, "A")
g.put("D", (6, 26), (7, 26), (6, 27))
save(g, "sword-32")
build_sheet(OUT, OUT / "dist", 3)
