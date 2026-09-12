"""Tiny pixel-op helpers for authoring .pxg sheets: every call is a decision about specific pixels."""
import math


class Grid:
    def __init__(self, n):
        from picxel import SIZES
        if n not in SIZES:
            raise ValueError(f"size must be one of {SIZES}, got {n}")
        self.n = n
        self.g = [["."] * n for _ in range(n)]

    def put(self, c, *pts):
        for x, y in pts:
            if 0 <= x < self.n and 0 <= y < self.n:
                self.g[y][x] = c

    def rect(self, x0, y0, x1, y1, c):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.put(c, (x, y))

    def disc(self, cx, cy, rx, ry, c):
        """Filled ellipse centred at (cx, cy) with radii rx, ry (floats allowed)."""
        for y in range(self.n):
            for x in range(self.n):
                if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1.0:
                    self.g[y][x] = c

    def tri(self, x0, y0, x1, y1, x2, y2, c):
        pts = [(x0, y0), (x1, y1), (x2, y2)]
        def side(ax, ay, bx, by, px, py):
            return (bx - ax) * (py - ay) - (by - ay) * (px - ax)
        for y in range(self.n):
            for x in range(self.n):
                px, py = x + 0.5, y + 0.5
                d1 = side(*pts[0], *pts[1], px, py); d2 = side(*pts[1], *pts[2], px, py); d3 = side(*pts[2], *pts[0], px, py)
                if (d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0):
                    self.g[y][x] = c

    def outline(self, c, keep=()):
        """Every opaque pixel that touches transparency (4-way) or the sheet edge becomes c."""
        n = self.n
        sil = [[self.g[y][x] != "." for x in range(n)] for y in range(n)]
        for y in range(n):
            for x in range(n):
                if not sil[y][x] or self.g[y][x] in keep:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < n and 0 <= ny < n) or not sil[ny][nx]:
                        self.g[y][x] = c
                        break

    def mirror(self):
        """Copy the left half onto the right half (front views are near-symmetric)."""
        n = self.n
        for y in range(n):
            for x in range(n // 2):
                self.g[y][n - 1 - x] = self.g[y][x]

    # ---- refine tools: work on a sheet that already exists (an import, an earlier pass)
    @classmethod
    def load(cls, path):
        """Read a .pxg; returns (grid, meta, colors) so a refine pass can edit and write it back."""
        text = open(path, encoding="utf-8").read()
        head, _, body = text.partition("\n---\n")
        meta, colors = {}, {}
        for line in head.splitlines():
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if len(k) == 1 and k.isupper():
                colors[k] = v
            elif k:
                meta[k] = v
        rows = [r for r in body.splitlines() if r.strip()]
        g = cls(int(meta["size"]))
        g.g = [list(r) for r in rows]
        return g, meta, colors

    def erase(self, x0, y0, x1, y1):
        """Eraser: the rectangle becomes transparent."""
        self.rect(x0, y0, x1, y1, ".")

    def replace(self, old, new, box=None):
        """Recolor: every `old` symbol becomes `new`, optionally only inside box=(x0, y0, x1, y1)."""
        x0, y0, x1, y1 = box or (0, 0, self.n - 1, self.n - 1)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if self.g[y][x] == old:
                    self.g[y][x] = new

    def smooth(self, colors, passes=1, keep=()):
        """Use the CLI's color-aware cleanup; high-contrast detail survives."""
        from picxel import Sheet, smooth_sheet
        sheet = Sheet("draft", self.n, "sprite", "custom", colors, self.rows())
        changed = smooth_sheet(sheet, passes, keep)
        self.g = [list(row) for row in sheet.rows]
        return changed

    def line(self, x0, y0, x1, y1, c):
        """Integer Bresenham line for handles, blades and deliberate diagonals."""
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        error = dx + dy
        while True:
            self.put(c, (x0, y0))
            if (x0, y0) == (x1, y1):
                break
            doubled = 2 * error
            if doubled >= dy:
                error += dy
                x0 += sx
            if doubled <= dx:
                error += dx
                y0 += sy

    def rows(self):
        return ["".join(r) for r in self.g]

    def write(self, path, name, kind, colors, palette="db32"):
        used = {c for r in self.g for c in r if c != "."}
        head = [f"name: {name}", f"size: {self.n}", f"kind: {kind}", f"palette: {palette}"] + [f"{k}: {v}" for k, v in colors.items() if k in used]
        open(path, "w", encoding="utf-8", newline="\n").write("\n".join(head) + "\n---\n" + "\n".join(self.rows()) + "\n")
