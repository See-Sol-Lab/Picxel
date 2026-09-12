"""Chibi lion cub from the reference: big round mane, round face, small round ears, huge eyes, tiny nose, open smile."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from px import Grid

COLORS = {
    "A": "#663931",  # outline / nose (dark brown — kawaii, not black)
    "B": "#222034",  # pupils
    "C": "#d9a066",  # mane (golden tan, as in the reference)
    "D": "#8f563b",  # mane shadow
    "E": "#eec39a",  # face fur
    "G": "#ffffff",  # eye white / highlight
    "H": "#8a6f30",  # iris
    "I": "#d95763",  # tongue / blush
    "J": "#df7126",  # mane warm accent (tuft tips)
    "K": "#d77bba",  # inner ear (pink)
}
OUT = str(Path(__file__).resolve().parent / "lion-%d.pxg")


def lion64():
    g = Grid(64); c = 32
    # ---- silhouette: mane disc, ears, chest tuft
    g.disc(c, 30, 27, 26, "C")                       # mane
    for (ex, ey) in ((12, 12), (52, 12)):            # ears (round) sitting on the mane rim
        g.disc(ex, ey, 7, 7, "C")
    g.disc(c, 58, 14, 9, "E")                        # chest fur below the mane
    # mane tufts (triangles poking out of the disc rim)
    tufts = [(c, 0, 25, 9, 39, 9), (20, 2, 13, 12, 26, 11), (44, 2, 38, 11, 51, 12), (8, 8, 9, 18, 18, 14), (56, 8, 46, 14, 55, 18),
             (1, 24, 7, 17, 9, 30), (63, 24, 55, 17, 57, 30), (2, 40, 7, 33, 11, 44), (62, 40, 53, 33, 57, 44),
             (8, 54, 10, 45, 18, 51), (56, 54, 46, 51, 54, 45), (20, 60, 17, 52, 26, 56), (44, 60, 38, 56, 47, 52)]
    for t in tufts:
        g.tri(*t, "C")
    # ---- flat colour: face
    g.disc(c, 34, 19, 17, "E")                       # face
    # ---- shade: mane darker at the bottom/right, lighter at top-left
    g.disc(c, 30, 27, 26, "C")
    for y in range(64):
        for x in range(64):
            if g.g[y][x] == "C":
                dx, dy = (x + 0.5 - c) / 27, (y + 0.5 - 30) / 26
                r = (dx * dx + dy * dy) ** 0.5
                if r > 0.86 and (dx + dy) > 0.25:      # lower-right rim
                    g.g[y][x] = "D"
                elif r < 0.6 and dx < -0.15 and dy < -0.1:  # upper-left glow
                    g.g[y][x] = "J"
    g.disc(c, 34, 19, 17, "E")                       # redraw face over shading
    # dark mane band hugging the face (the reference has a darker inner mane ring)
    for y in range(64):
        for x in range(64):
            if g.g[y][x] in ("C", "J"):
                dx, dy = (x + 0.5 - c) / 19, (y + 0.5 - 34) / 17
                if dx * dx + dy * dy <= 1.28:
                    g.g[y][x] = "D"
    # face stays flat-lit (kawaii): the dark mane ring does the separating
    for (ex, ey) in ((12, 13), (52, 13)):            # ears on top of everything: rim, fur, pink inner
        g.disc(ex, ey, 7.5, 7.5, "A")
        g.disc(ex, ey, 6.5, 6.5, "C")
        g.disc(ex, ey + 0.5, 4, 4, "K")
    # ---- face features
    for (ex, ey) in ((23, 33), (41, 33)):            # kawaii eyes: dark ring, big iris, pupil, two highlights, thin white at the bottom
        g.disc(ex, ey, 5.5, 6, "A")
        g.disc(ex, ey, 4.5, 5, "H")
        g.disc(ex, ey + 1.5, 3, 3, "B")
        g.rect(ex - 2, ey + 3, ex + 2, ey + 3, "G")
        g.rect(ex - 3, ey - 3, ex - 1, ey - 1, "G")
        g.put("G", (ex + 2, ey + 1))
    g.tri(30, 41, 34, 41, 32, 44, "A")               # nose
    g.put("A", (31, 41), (32, 41), (33, 41), (31, 42), (32, 42), (33, 42), (32, 43))
    g.rect(28, 45, 36, 45, "A")                      # mouth line
    g.rect(29, 46, 35, 48, "A")                      # open mouth (dark)
    g.rect(30, 47, 34, 49, "I")                      # tongue
    g.put("A", (30, 49), (34, 49))
    g.put("G", (28, 46), (28, 47), (36, 46), (36, 47))   # two tiny fangs
    g.put("I", (18, 40), (19, 40), (18, 41), (19, 41), (45, 40), (46, 40), (45, 41), (46, 41))  # blush
    # ---- outline
    g.outline("A")
    g.write(OUT % 64, "lion-64", "sprite", COLORS)


def lion32():
    g = Grid(32); c = 16
    g.disc(c, 15, 13.5, 13, "C")                     # mane
    for (ex, ey) in ((6, 6), (26, 6)):
        g.disc(ex, ey, 3.5, 3.5, "C")
    g.disc(c, 29, 7, 4.5, "E")                       # chest
    for t in ((c, 0, 12, 5, 20, 5), (9, 1, 6, 7, 13, 6), (23, 1, 19, 6, 26, 7), (0, 13, 4, 9, 5, 16), (32, 13, 27, 9, 28, 16),
              (1, 22, 4, 17, 7, 25), (31, 22, 25, 25, 28, 17), (6, 29, 8, 23, 12, 27), (26, 29, 20, 27, 24, 23)):
        g.tri(*t, "C")
    for y in range(32):
        for x in range(32):
            if g.g[y][x] == "C":
                dx, dy = (x + 0.5 - c) / 13.5, (y + 0.5 - 15) / 13
                r = (dx * dx + dy * dy) ** 0.5
                if r > 0.84 and (dx + dy) > 0.25:
                    g.g[y][x] = "D"
    g.disc(c, 17, 9.5, 8.5, "D")                     # dark inner ring
    g.disc(c, 17, 9, 8, "E")                         # face
    for (ex, ey) in ((6, 6), (26, 6)):               # ears on top: rim, fur, pink inner
        g.disc(ex, ey, 4, 4, "A")
        g.disc(ex, ey, 3, 3, "C")
        g.disc(ex, ey + 0.5, 1.6, 1.6, "K")
    for (ex, ey) in ((12, 16), (20, 16)):            # eyes 3 wide x 4 tall: iris, pupil, one highlight
        g.rect(ex - 1, ey - 1, ex + 1, ey + 2, "B")
        g.rect(ex - 1, ey - 1, ex + 1, ey, "H")
        g.put("G", (ex - 1, ey - 1), (ex + 1, ey + 1))
    g.put("A", (15, 20), (16, 20), (17, 20), (16, 21))   # nose
    g.rect(14, 23, 18, 23, "A")                      # mouth
    g.rect(15, 24, 17, 24, "I")                      # tongue
    g.put("A", (14, 24), (18, 24))
    g.put("I", (8, 20), (9, 20), (23, 20), (24, 20))  # blush
    g.outline("A")
    g.write(OUT % 32, "lion-32", "sprite", COLORS)


lion64(); lion32()
print("written")
