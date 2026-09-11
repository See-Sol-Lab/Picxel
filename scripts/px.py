"""Tiny pixel-op helpers for authoring .pxg sheets: every call is a decision about specific pixels."""
import math


class Grid:
    def __init__(self, n):
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

    def outline(self, c):
        """Every opaque pixel that touches transparency (4-way) or the sheet edge becomes c."""
        n = self.n
        sil = [[self.g[y][x] != "." for x in range(n)] for y in range(n)]
        for y in range(n):
            for x in range(n):
                if not sil[y][x]:
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

    def rows(self):
        return ["".join(r) for r in self.g]

    def write(self, path, name, kind, colors, palette="db32"):
        used = {c for r in self.g for c in r if c != "."}
        head = [f"name: {name}", f"size: {self.n}", f"kind: {kind}", f"palette: {palette}"] + [f"{k}: {v}" for k, v in colors.items() if k in used]
        open(path, "w", encoding="utf-8", newline="\n").write("\n".join(head) + "\n---\n" + "\n".join(self.rows()) + "\n")
