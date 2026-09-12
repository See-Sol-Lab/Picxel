#!/usr/bin/env python3
"""Picxel -- render, check, import and sheet `.pxg` pixel-art sheets.

    picxel.py check  <file.pxg>...              validate; exit 1 on errors
    picxel.py render <file.pxg>... [-o DIR]     PNG at 1x and 4x (checks first)
    picxel.py palette <image.png> [--colors N] [-o ref.pal]
                                                   the N most used colors of a reference, as a palette file
    picxel.py import <image.png> --size N [--kind K] [--palette db32|custom|ref.pal] [--background auto]
                                                   PNG (any size) -> .pxg: background stripped, cropped, squared, colors snapped
    picxel.py sheet  <DIR> [-o OUT] [--columns N]
                                                   every .pxg in DIR -> spritesheet PNG + JSON + index.html
    picxel.py mosaic <ref.png> --anchor anchor.json  apply the anchor's detail budget per region -> ref.pre.png
    picxel.py concept <ref.pre.png> --anchor anchor.json [--provider codex --result concept.png]
                                                   consume an assistant-produced concept, or use the mosaic with none
    picxel.py derive <big.pxg> --sizes 64,32          refine once at 128, majority-vote downsample the rest
    picxel.py show   <file.pxg> [--box x0,y0,x1,y1 | --full]   compact summary, explicit crop or full grid
    picxel.py face   <file.pxg> --anchor ref.anchor.json --patch face.json
                                                   optional, local facial repair; --prompt-only prepares visual review
    picxel.py smooth <file.pxg>... [--passes N] [--keep SYMS]   merge specks in place
    picxel.py batch  <DIR> [-o OUT] [--provider P] [--sizes 64,32] [--only NAME ...]
                                                   every <name>.anchor.json + image in DIR -> base sheets + batch-report.json

Only Pillow is required. Sizes are fixed at 32, 64, 128.
"""
from __future__ import annotations

import argparse
import re
import base64
import io
import json
import sys
import math
import hashlib
from html import escape
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SIZES = (32, 64, 128)
KINDS = ("tile", "item", "sprite")
SYMBOLS = "ABCDEFGHIJKLMNOP"
TRANSPARENT = "."
PREVIEW_SCALE = 4
DB32 = [
    "#000000", "#222034", "#45283c", "#663931", "#8f563b", "#df7126", "#d9a066", "#eec39a",
    "#fbf236", "#99e550", "#6abe30", "#37946e", "#4b692f", "#524b24", "#323c39", "#3f3f74",
    "#306082", "#5b6ee1", "#639bff", "#5fcde4", "#cbdbfc", "#ffffff", "#9badb7", "#847e87",
    "#696a6a", "#595652", "#76428a", "#ac3232", "#d95763", "#d77bba", "#8f974a", "#8a6f30",
]
PALETTES = {"db32": DB32}


def palette_colors(name: str, base: Path | None) -> list[str] | None:
    """Colors for a `palette:` value: a built-in name, or a .pal file (one #rrggbb per line). None = custom."""
    if name in PALETTES:
        return PALETTES[name]
    if name == "custom":
        return None
    path = Path(name)
    if not path.exists() and not path.is_absolute() and base is not None:
        path = base / path                          # sheets name their .pal relative to themselves
    if path.suffix == ".pal" and path.exists():
        return [line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines() if line.strip().startswith("#")]
    raise ValueError(f"unknown palette {name!r} (built-ins: {sorted(PALETTES)}, or a .pal file, or custom)")


PALETTE_WEIGHT = {"fine": 8, "medium": 2, "coarse": 1}
PALETTE_MIN_DIST = 0.02  # Oklab distance; explicit colors and small exact palettes stay intact.


def _oklab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """sRGB to perceptual lightness/a/b. Ottosson's public-domain Oklab matrices:
    https://bottosson.github.io/posts/oklab/
    """
    r, g, b = (v / 255 for v in rgb)
    r, g, b = (v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in (r, g, b))
    l = (0.4122214708*r + 0.5363325363*g + 0.0514459929*b) ** (1/3)
    m = (0.2119034982*r + 0.6806995451*g + 0.1073969566*b) ** (1/3)
    s = (0.0883024619*r + 0.2817188376*g + 0.6299787005*b) ** (1/3)
    return (0.2104542553*l + 0.7936177850*m - 0.0040720468*s,
            1.9779984951*l - 2.4285922050*m + 0.4505937099*s,
            0.0259040371*l + 0.7827717662*m - 0.8086757660*s)


def _palette_from_image(img: Image.Image, count: int, anchor: dict | None = None) -> list[str]:
    """Select actual source colors using coverage, regional importance and perceptual error."""
    if not 2 <= count <= 16:
        raise ValueError("colors must be between 2 and 16")
    anchor = anchor or {}
    reserved = list(dict.fromkeys(anchor.get("palette", [])))
    if any(not isinstance(c, str) or not _hex_ok(c) for c in reserved):
        raise ValueError("anchor palette must contain lowercase #rrggbb colors")
    if len(reserved) > count:
        raise ValueError("anchor palette exceeds requested color count")
    picked = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in reserved]
    w, h = img.size
    # Full-resolution histograms avoid dropping a small feature at thumbnail grid phases.
    # Edges contribute less evidence than solid interiors; fully transparent RGB never votes.
    alpha = img.getchannel("A").point(lambda a: a if a >= 128 else 0)
    confidence = alpha.filter(ImageFilter.MinFilter(3)).point(lambda a: 255 if a >= 128 else 32)
    alpha = ImageChops.multiply(alpha, confidence)
    regions = Image.new("L", img.size, 1)
    draw = ImageDraw.Draw(regions)
    for region in anchor.get("regions", []):
        x0, y0, x1, y1 = (round(v * dim) for v, dim in zip(region["box"], (w, h, w, h)))
        if x1 > x0 and y1 > y0:
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=PALETTE_WEIGHT[region["detail"]])
    hist: Counter = Counter()
    weighted = img.copy()
    for weight in sorted(value for _, value in regions.getcolors()):
        mask = regions.point(lambda v: 255 if v == weight else 0)
        weighted.putalpha(ImageChops.multiply(alpha, mask))
        for pixels, (r, g, b, a) in weighted.getcolors(w * h):
            if a:
                hist[(r, g, b)] += pixels * a * weight / 255
    if not hist:
        raise ValueError("image has no opaque pixels")
    ordered = sorted(hist, key=lambda c: (-hist[c], c))
    remaining = [c for c in ordered if c not in picked]
    if len(picked) + len(remaining) <= count:
        return ["#%02x%02x%02x" % c for c in picked + remaining]
    # Group variations perceptually too: an 8-level RGB bin is far too coarse
    # near black. Representatives remain actual source colors, not averages.
    labs = {c: _oklab(c) for c in hist}
    labs.update((c, _oklab(c)) for c in picked)

    def candidates(population):
        bins = {}
        for color in sorted(population, key=lambda c: (-population[c], c)):
            key = tuple(round(v / PALETTE_MIN_DIST) for v in labs[color])
            if key not in bins:
                bins[key] = [0.0, color]
            bins[key][0] += population[color]
        return {color: mass for mass, color in bins.values()}

    weights = candidates(hist)
    target = anchor.get("size", SIZES[-1])
    # Less than a quarter target pixel of weighted support is unreliable noise.
    support = min(max(weights.values()), sum(hist.values()) / (4 * target * target))
    weights = {c: mass for c, mass in weights.items() if mass >= support}

    def distance(a, b):
        return sum((x - y) ** 2 for x, y in zip(labs[a], labs[b]))

    ends = sorted(weights, key=lambda c: (labs[c][0], c))
    for color in (ends[0], ends[-1]):
        if len(picked) < count and color not in picked:
            if not picked or min(distance(color, p) for p in picked) >= PALETTE_MIN_DIST ** 2:
                picked.append(color)
    # A designated fine region gets a chance to keep its dominant perceptual
    # color before large materials spend the remaining slots. Later coarse
    # regions already removed their overlap from this mask.
    fine_alpha = ImageChops.multiply(alpha, regions.point(lambda v: 255 if v == PALETTE_WEIGHT["fine"] else 0))
    weighted.putalpha(fine_alpha)
    for region in anchor.get("regions", []):
        if region["detail"] != "fine" or len(picked) >= count:
            continue
        box = tuple(round(v * dim) for v, dim in zip(region["box"], (w, h, w, h)))
        patch = weighted.crop(box)
        local: Counter = Counter()
        if patch.width and patch.height:
            for pixels, (r, g, b, a) in patch.getcolors(patch.width * patch.height):
                if a:
                    local[(r, g, b)] += pixels * a
        if local:
            options = candidates(local)
            color = max(options, key=lambda c: (options[c], c))
            if min(distance(color, p) for p in picked) >= PALETTE_MIN_DIST ** 2:
                picked.append(color)
    errors = {c: min(distance(c, p) for p in picked) for c in weights}
    while len(picked) < count:
        eligible = [c for c in weights if errors[c] >= PALETTE_MIN_DIST ** 2]
        if not eligible:
            break
        color = max(eligible, key=lambda c: (weights[c] * errors[c], weights[c], c))
        picked.append(color)
        errors = {c: min(error, distance(c, color)) for c, error in errors.items()}
    return ["#%02x%02x%02x" % c for c in picked]


def extract_palette(image: Path, count: int, anchor: dict | None = None) -> list[str]:
    """Read a concept and select up to count precise colors, with optional anchor priorities."""
    with Image.open(image) as img:
        return _palette_from_image(img.convert("RGBA"), count, anchor)
SEAM_WARN = 40.0      # mean RGB distance across a tile edge
ORPHAN_WARN = 3       # pixels with no same-color neighbor (8-way) per sheet


# ---------------------------------------------------------------- model

class Sheet:
    def __init__(self, name: str, size: int, kind: str, palette: str, colors: dict[str, str], rows: list[str], path: Path | None = None):
        self.name, self.size, self.kind, self.palette, self.colors, self.rows, self.path = name, size, kind, palette, colors, rows, path

    @classmethod
    def parse(cls, text: str, path: Path | None = None) -> "Sheet":
        head, sep, body = text.partition("\n---\n")
        if not sep:
            raise ValueError("missing `---` line between header and rows")
        meta: dict[str, str] = {}
        colors: dict[str, str] = {}
        for line in head.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if len(key) == 1 and key in SYMBOLS:
                colors[key] = value.lower()
            else:
                meta[key.lower()] = value
        rows = [r.rstrip("\r") for r in body.splitlines() if r.strip() != ""]
        return cls(meta.get("name", path.stem if path else "untitled"), int(meta.get("size", "0") or 0),
                   meta.get("kind", "sprite").lower(), meta.get("palette", "db32"), colors, rows, path)

    def dump(self) -> str:
        head = [f"name: {self.name}", f"size: {self.size}", f"kind: {self.kind}", f"palette: {self.palette}"]
        head += [f"{k}: {v}" for k, v in self.colors.items()]
        return "\n".join(head) + "\n---\n" + "\n".join(self.rows) + "\n"

    def rgba(self, symbol: str) -> tuple[int, int, int, int]:
        if symbol == TRANSPARENT:
            return (0, 0, 0, 0)
        h = self.colors[symbol].lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)

    def image(self) -> Image.Image:
        img = Image.new("RGBA", (self.size, self.size))
        px = img.load()
        for y, row in enumerate(self.rows):
            for x, sym in enumerate(row):
                px[x, y] = self.rgba(sym)
        return img


# ---------------------------------------------------------------- check

def _hex_ok(value: str) -> bool:
    return len(value) == 7 and value[0] == "#" and all(c in "0123456789abcdef" for c in value[1:])


def _dist(a: str, b: str) -> float:
    ra, ga, ba = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    rb, gb, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    return ((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2) ** 0.5


def check(sheet: Sheet) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors block rendering."""
    errors: list[str] = []
    warnings: list[str] = []
    if not re.fullmatch(r"[\w.-]+", sheet.name) or sheet.name in (".", ".."):
        errors.append("name must be a filename-safe identifier (letters, digits, underscore, dot, hyphen)")
    if sheet.size not in SIZES:
        errors.append(f"size must be one of {SIZES}, got {sheet.size}")
    if sheet.kind not in KINDS:
        errors.append(f"kind must be one of {KINDS}, got {sheet.kind!r}")
    try:
        master = palette_colors(sheet.palette, sheet.path.parent if sheet.path else None)
    except ValueError as exc:
        errors.append(str(exc))
        master = None
    if not sheet.colors:
        errors.append("no colors declared (A: #rrggbb ...)")
    if len(sheet.colors) > len(SYMBOLS):
        errors.append(f"more than {len(SYMBOLS)} colors declared")
    for sym, value in sheet.colors.items():
        if not _hex_ok(value):
            errors.append(f"color {sym} is not #rrggbb: {value!r}")
        elif master is not None and value not in master:
            errors.append(f"color {sym} = {value} is not in the {sheet.palette} palette")
    if errors:
        return errors, warnings

    n = sheet.size
    if len(sheet.rows) != n:
        errors.append(f"expected {n} rows, got {len(sheet.rows)}")
    for i, row in enumerate(sheet.rows, 1):
        if len(row) != n:
            errors.append(f"row {i}: expected {n} characters, got {len(row)}")
        bad = sorted({c for c in row if c != TRANSPARENT and c not in sheet.colors})
        if bad:
            errors.append(f"row {i}: undeclared symbols {''.join(bad)}")
    if errors:
        return errors, warnings

    used = {c for row in sheet.rows for c in row if c != TRANSPARENT}
    by_hex: dict[str, list[str]] = {}
    for sym, value in sheet.colors.items():
        by_hex.setdefault(value, []).append(sym)
    for value, syms in by_hex.items():
        if len(syms) > 1:
            warnings.append(f"symbols {''.join(syms)} all map to {value} -- one material lost its contrast")
    unused = sorted(set(sheet.colors) - used)
    if unused:
        warnings.append(f"declared but unused colors: {''.join(unused)}")
    if sheet.kind in ("sprite", "item"):
        corners = [sheet.rows[0][0], sheet.rows[0][-1], sheet.rows[-1][0], sheet.rows[-1][-1]]
        if any(c != TRANSPARENT for c in corners):
            errors.append(f"{sheet.kind}: all four corners must be transparent")
        if not used:
            errors.append("sheet is entirely transparent")
    if sheet.kind == "tile":
        if any(TRANSPARENT in row for row in sheet.rows):
            warnings.append("tile has transparent pixels (fine for overlay tiles, wrong for ground)")
        else:
            lr = sum(_dist(sheet.colors[r[0]], sheet.colors[r[-1]]) for r in sheet.rows) / n
            tb = sum(_dist(sheet.colors[a], sheet.colors[b]) for a, b in zip(sheet.rows[0], sheet.rows[-1])) / n
            if lr > SEAM_WARN or tb > SEAM_WARN:
                warnings.append(f"tile seam looks hard (left/right {lr:.0f}, top/bottom {tb:.0f}; warn above {SEAM_WARN:.0f}) -- soften the edge rows/columns")
    orphans = 0
    for y in range(n):
        for x in range(n):
            c = sheet.rows[y][x]
            if c == TRANSPARENT:
                continue
            # 8-neighborhood: a diagonal outline step is connected, a lone speck in a field is not
            same = any(sheet.rows[y + dy][x + dx] == c for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                       if (dx or dy) and 0 <= x + dx < n and 0 <= y + dy < n)
            if not same:
                orphans += 1
    if orphans > ORPHAN_WARN:
        warnings.append(f"{orphans} isolated pixels (warn above {ORPHAN_WARN}) -- noise, or deliberate texture?")
    return errors, warnings


def load(path: Path) -> Sheet:
    return Sheet.parse(path.read_text(encoding="utf-8"), path)


def report(sheet: Sheet, errors: list[str], warnings: list[str]) -> None:
    label = sheet.path.name if sheet.path else sheet.name
    for e in errors:
        print(f"{label}: error: {e}")
    for w in warnings:
        print(f"{label}: warning: {w}")
    if not errors:
        print(f"{label}: ok ({sheet.size}x{sheet.size} {sheet.kind}, {len(sheet.colors)} colors{', ' + str(len(warnings)) + ' warning(s)' if warnings else ''})")


# ---------------------------------------------------------------- render

def render(sheet: Sheet, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    img = sheet.image()
    native = out_dir / f"{sheet.name}.png"
    preview = out_dir / f"{sheet.name}@{PREVIEW_SCALE}x.png"
    img.save(native)
    img.resize((sheet.size * PREVIEW_SCALE,) * 2, Image.NEAREST).save(preview)
    return native, preview


# ---------------------------------------------------------------- import

def _nearest(rgb: tuple[int, int, int], palette: list[str]) -> str:
    probe = "#%02x%02x%02x" % rgb
    return min(palette, key=lambda p: _dist(p, probe))


def _strip_background(img: Image.Image, mode: str) -> Image.Image:
    """`none`: keep alpha as is. `auto`: flood-fill from the corners -- only background *connected to the edge* goes
    transparent, so a face the same tone as the backdrop survives. `#rrggbb`: same, seeded with that color."""
    if mode == "none":
        return img
    if mode.startswith("key:"):
        color = mode[4:].lower()
        if not _hex_ok(color):
            raise ValueError("key background must be key:#rrggbb")
        # An explicitly chosen key color is absent from the subject. Remove it
        # even inside closed hair loops or handles, unlike edge-only auto fill.
        diff = ImageChops.difference(img.convert("RGB"), Image.new("RGB", img.size, color))
        r, g, b = diff.split()
        mask = ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda v: 0 if v <= 30 else 255)
        out = img.copy()
        out.putalpha(ImageChops.multiply(img.getchannel("A"), mask))
        return out
    # Existing alpha is authoritative. RGB under transparent pixels is arbitrary.
    if mode == "auto" and img.getchannel("A").getextrema()[0] < 255:
        return img
    px = img.load()
    w, h = img.size
    if mode == "auto":
        corners = Counter(px[x, y][:3] for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)))
        target = corners.most_common(1)[0][0]
    else:
        if not _hex_ok(mode.lower()):
            raise ValueError("background must be none, auto, or #rrggbb")
        target = tuple(int(mode[i:i + 2], 16) for i in (1, 3, 5))
    tol2 = 30 * 30
    def is_bg(x: int, y: int) -> bool:
        r, g, b, a = px[x, y]
        return a > 0 and (r - target[0]) ** 2 + (g - target[1]) ** 2 + (b - target[2]) ** 2 <= tol2
    seen = bytearray(w * h)
    stack = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    out = img.copy()
    op = out.load()
    while stack:
        x, y = stack.pop()
        i = y * w + x
        if seen[i] or not is_bg(x, y):
            continue
        seen[i] = 1
        op[x, y] = (0, 0, 0, 0)
        if x > 0: stack.append((x - 1, y))
        if x < w - 1: stack.append((x + 1, y))
        if y > 0: stack.append((x, y - 1))
        if y < h - 1: stack.append((x, y + 1))
    return out


def _square(img: Image.Image, size: int) -> Image.Image:
    """Fit the subject inside a one-output-pixel margin without smoothing edges."""
    bbox = img.getchannel("A").point(lambda a: 255 if a >= 128 else 0).getbbox()
    if not bbox:
        raise ValueError("image has no opaque pixels")
    img = img.crop(bbox)
    w, h = img.size
    block = max(1, math.ceil(max(w, h) / (size - 2)))
    side = size * block
    canvas = Image.new("RGBA", (side, side))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))
    return canvas


def import_png(src: Path, size: int, name: str | None, kind: str, palette: str, background: str = "none", colors: int = 16) -> Sheet:
    if size not in SIZES or kind not in KINDS:
        raise ValueError("unsupported size or kind")
    if not 2 <= colors <= 16:
        raise ValueError("colors must be between 2 and 16")
    img = Image.open(src).convert("RGBA")
    img = _strip_background(img, background)
    # Native pixel art is already aligned. Preserve it byte-for-byte in geometry.
    if kind != "tile" and img.size != (size, size):
        img = _square(img, size)
    w, h = img.size
    if w != h:
        raise ValueError(f"source must be square, got {w}x{h}")
    if w < size or w % size:
        img = img.resize((size * max(1, w // size),) * 2, Image.Resampling.BOX)
        w, h = img.size
    master = palette_colors(palette, src.parent)
    if master is None:
        master = _palette_from_image(img, colors)
    if not master or len(master) > 256 or any(not _hex_ok(c) for c in master):
        raise ValueError("palette must contain valid #rrggbb colors")
    # Quantize BEFORE voting: a hundred close skin tones must beat one exact
    # repeated background or outline tone. RGB majority on a painting is invalid.
    pal_image = Image.new("P", (1, 1))
    rgb_palette = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in master]
    pal_image.putpalette([v for c in rgb_palette for v in c] + list(rgb_palette[-1]) * (256 - len(master)))
    rgb = img.convert("RGB")
    unique = img.getcolors(maxcolors=256)
    # Pillow's palette lookup uses a coarse cache. Already-indexed colors must
    # not merge merely because two deliberately close shades share a cache cell.
    indexed = unique and all(c[3] < 128 or c[:3] in rgb_palette for _, c in unique)
    quantized = rgb if indexed else rgb.quantize(palette=pal_image, dither=Image.Dither.NONE).convert("RGB")
    quantized.putalpha(img.getchannel("A"))
    img = quantized
    block = w // size
    px = img.load()
    cells: list[list[tuple[int, int, int] | None]] = []
    for gy in range(size):
        row: list[tuple[int, int, int] | None] = []
        for gx in range(size):
            if block == 1:
                r, g, b, a = px[gx, gy]
                row.append(None if a < 128 else (r, g, b))
                continue
            patch = img.crop((gx * block, gy * block, (gx + 1) * block, (gy + 1) * block))
            votes: Counter = Counter()
            for amount, (r, g, b, a) in patch.getcolors(block * block):
                votes[None if a < 128 else (r, g, b)] += amount
            transparent = votes.pop(None, 0)
            if transparent >= block * block / 2:
                row.append(None)
                continue
            maximum = max(votes.values())
            winners = {color for color, amount in votes.items() if amount == maximum}
            if len(winners) == 1:
                row.append(next(iter(winners)))
            else:
                # Preserve the original row-major tiebreak; histogram order is not pixel order.
                row.append(next(px[x, y][:3] for y in range(gy * block, (gy + 1) * block)
                                for x in range(gx * block, (gx + 1) * block)
                                if px[x, y][3] >= 128 and px[x, y][:3] in winners))
        cells.append(row)
    # Encode palette colors as symbols, keeping the output within 16 colors.
    mapped = {c: "#%02x%02x%02x" % c for row in cells for c in row if c is not None}
    if not mapped:
        raise ValueError("image has no opaque pixels at the target size")
    ordered = list(dict.fromkeys(mapped[c] for row in cells for c in row if c is not None))
    if len(ordered) > len(SYMBOLS):
        # palette snap can still exceed 16 distinct colors; keep the 16 most frequent, remap the rest
        freq = Counter(mapped[c] for row in cells for c in row if c is not None)
        keep = [c for c, _ in freq.most_common(len(SYMBOLS))]
        remap = {c: (c if c in keep else _nearest(tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)), keep)) for c in ordered}
        mapped = {k: remap[v] for k, v in mapped.items()}
        ordered = keep
    symbol_of = {hexv: SYMBOLS[i] for i, hexv in enumerate(ordered)}
    rows = ["".join(TRANSPARENT if c is None else symbol_of[mapped[c]] for c in row) for row in cells]
    colors = {symbol_of[h]: h for h in ordered}
    return Sheet(name or src.stem, size, kind, palette, colors, rows)


# ---------------------------------------------------------------- reference pipeline

DETAIL_DIVISOR = {"fine": None, "medium": 32, "coarse": 16}   # block = image width / divisor


def load_anchor(path: Path) -> dict:
    """Validate anchor.json (see references/anchor.md) and return it."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("anchor.json must be an object")
    problems = []
    if not isinstance(data.get("keep"), list) or not 1 <= len(data["keep"]) <= 8:
        problems.append("keep must list 1-8 things")
    if data.get("size") not in SIZES:
        problems.append(f"size must be one of {SIZES}")
    if data.get("kind") not in KINDS:
        problems.append(f"kind must be one of {KINDS}")
    if isinstance(data.get("keep"), list) and not all(isinstance(v, str) and v.strip() for v in data["keep"]):
        problems.append("keep entries must be nonempty strings")
    for field in ("drop", "colors"):
        if not isinstance(data.get(field, []), list) or any(not isinstance(v, str) for v in data.get(field, [])):
            problems.append(f"{field} must list strings")
    palette = data.get("palette", [])
    if not isinstance(palette, list) or len(palette) > 16 or any(not isinstance(c, str) or not _hex_ok(c) for c in palette):
        problems.append("palette must list at most 16 lowercase #rrggbb colors")
    regions = data.get("regions", [])
    if not isinstance(regions, list):
        problems.append("regions must be a list")
        regions = []
    for i, region in enumerate(regions):
        if not isinstance(region, dict):
            problems.append(f"regions[{i}] must be an object")
            continue
        box = region.get("box")
        if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in box) and box[0] < box[2] and box[1] < box[3]):
            problems.append(f"regions[{i}].box must be [x0, y0, x1, y1] in 0..1 with x0<x1, y0<y1")
        if region.get("detail") not in DETAIL_DIVISOR:
            problems.append(f"regions[{i}].detail must be one of {sorted(DETAIL_DIVISOR)}")
    faces = data.get("faces", [])
    if not isinstance(faces, list):
        problems.append("faces must be a list")
        faces = []
    for i, face in enumerate(faces):
        if not isinstance(face, dict):
            problems.append(f"faces[{i}] must be an object")
            continue
        box = face.get("box")
        if not (isinstance(box, list) and len(box) == 4 and
                all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in box) and box[0] < box[2] and box[1] < box[3]):
            problems.append(f"faces[{i}].box must bound the source face in 0..1")
        if type(face.get("complex")) is not bool:
            problems.append(f"faces[{i}].complex must be true or false")
        for field in ("expression", "reason"):
            if not isinstance(face.get(field), str) or not face[field].strip():
                problems.append(f"faces[{i}].{field} must be nonempty text")
        if face.get("complex") is True and (not isinstance(face.get("gaze"), str) or not face["gaze"].strip()):
            problems.append(f"faces[{i}].gaze must describe the original gaze before eye repair")
    if problems:
        raise ValueError("anchor.json: " + "; ".join(problems))
    return data


def mosaic(image: Path, anchor: dict, out: Path, background: str = "auto") -> Path:
    """Apply the anchor's detail budget: block-average each region at its divisor; `fine` regions stay untouched.
    Regions apply in order, later ones override earlier ones where they overlap. The background is stripped first
    (before any blurring moves its color), so everything downstream sees real transparency."""
    img = _strip_background(Image.open(image).convert("RGBA"), "none" if anchor["kind"] == "tile" else background)
    w, h = img.size
    result = img.copy()
    for region in anchor.get("regions", []):
        divisor = DETAIL_DIVISOR[region["detail"]]
        x0, y0, x1, y1 = (int(round(region["box"][0] * w)), int(round(region["box"][1] * h)),
                          int(round(region["box"][2] * w)), int(round(region["box"][3] * h)))
        if divisor is None:
            result.paste(img.crop((x0, y0, x1, y1)), (x0, y0))      # restore full detail from the source
            continue
        # One canvas-aligned grid, rather than a differently phased grid per box.
        # Only color is simplified; the original alpha silhouette stays intact.
        small = img.resize((divisor, max(1, round(h * divisor / w))), Image.Resampling.BOX)
        blocked = small.resize(img.size, Image.Resampling.NEAREST)
        result.paste(blocked.crop((x0, y0, x1, y1)), (x0, y0))
    result.putalpha(img.getchannel("A"))
    out.parent.mkdir(parents=True, exist_ok=True)
    result.save(out)
    return out


def concept(pre: Path, anchor: dict, provider: str, out: Path, result: Path | None = None, background: str = "auto") -> Path:
    """Import an assistant-produced concept; Python never launches an agent or pays for an API."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if provider != "none" and result is None:
        raise ValueError(f"{provider} needs --result IMAGE from the current assistant's image tool or drawing tools; "
                         "use --prompt-only to prepare it. No CLI or API is launched automatically.")
    img = Image.open(result if result is not None else pre).convert("RGBA")
    if anchor["kind"] != "tile":
        img = _strip_background(img, background)
    if not img.getchannel("A").point(lambda a: 255 if a >= 128 else 0).getbbox():
        raise ValueError("concept image has no opaque pixels")
    img.save(out)
    return out


def concept_prompt(anchor: dict, style: dict | None = None, mode: str = "original") -> str:
    framing = ("Opaque square tile, matching opposite edges, no border or centered emblem."
               if anchor["kind"] == "tile" else
               "Single isolated subject on true transparency, entire silhouette visible with a small empty margin.")
    prompt = (f"Game pixel art: {anchor.get('subject', '')}. Target {anchor['size']}x{anchor['size']} logical pixels. "
            "Resolution-appropriate details; connected flat clusters, 2-3 shades/material, one pixel grid, "
            "top-left light, crisp stepped edges. No gradients, antialiasing, texture noise, dithering, decorations, text or watermark. "
            "Preserve source pose and proportions. "
            f"{framing} Keep: {'; '.join(anchor['keep'])}. Omit: {'; '.join(anchor.get('drop', []))}. "
            f"Palette: {', '.join(anchor.get('palette', anchor.get('colors', [])))}; at most 12-16 colors. "
            "Use the original for identity; restore identifying features lost in the mosaic.")
    if style is None or mode == "original":
        return prompt
    instruction = ("Restyle this outlier to match the batch rendering style. The source supplies subject content, "
                   "not the rendering style. " if mode == "unify" else
                   "Keep this compatible asset consistent with the shared batch rendering style. ")
    references = (f"Style reference assets: {', '.join(style['references'])}. "
                  "Use their approved concept images as style references, keeping the original image as the content reference. "
                  if style["references"] else "Establish the batch's baseline concept using the shared style and this source. ")
    return (prompt + "\n\n" + instruction + f"Shared style: {style['profile']} "
            + references +
            "Match outline treatment, shading, material rendering, texture density and palette treatment. "
            "Preserve the source identity, pose, silhouette and all required keep features, including identifying colors. "
            "Do not copy another asset's subject, costume, anatomy or background. Style consistency does not mean identical hues.")


def smooth_sheet(sheet: Sheet, passes: int, keep: str) -> int:
    """Deterministic speck cleanup on a sheet (same rule as check's isolated-pixel warning)."""
    n = sheet.size
    grid = [list(r) for r in sheet.rows]
    changed = 0
    for _ in range(passes):
        snap = [row[:] for row in grid]
        for y in range(n):
            for x in range(n):
                c = snap[y][x]
                if c == TRANSPARENT or c in keep:
                    continue
                around = [snap[y + dy][x + dx] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                          if (dx or dy) and 0 <= x + dx < n and 0 <= y + dy < n]
                if c in around:
                    continue
                opaque = [m for m in around if m != TRANSPARENT]
                if opaque:
                    target = Counter(opaque).most_common(1)[0][0]
                    # A high-contrast singleton can be an eye, glint or weapon tip.
                    if _dist(sheet.colors[c], sheet.colors[target]) <= 48:
                        grid[y][x] = target
                        changed += 1
    sheet.rows = ["".join(r) for r in grid]
    return changed


def face_prompt(anchor: dict, size: int) -> str:
    faces = [(i, face) for i, face in enumerate(anchor.get("faces", [])) if face["complex"]]
    if not faces:
        return "No complex visible face annotated; preserve the existing pixels."
    notes = " ".join(f"Face {i}: {f['expression']}. Original gaze: {f['gaze']}. Risk: {f['reason']}. Source box: {f['box']}." for i, f in faces)
    return (f"Inspect the {size}x{size} pixel sheet beside the original reference. {notes} "
            "If eyes and mouth are already readable, preserve them. Otherwise repair only the eyes or mouth. "
            "First inspect the high-resolution ORIGINAL, not just the generated concept: record pupil position, "
            "which side shows sclera, eyelid openness, and whether the gaze is down, up or sideways. "
            "Preserving this gaze takes priority over increasing contrast. Never mirror pupil/sclera placement "
            "or shift pupils upward merely to make them clearer. If gaze is uncertain, preserve the original pixels. "
            "Preserve existing eyebrows, nose, hair, face shading and eye contours. Do not add or redraw eyebrows. "
            "Give visible open eyes a small amount of light sclera on the correct side "
            "and dark pupils when appropriate; for animal eyes use species-appropriate pupils and catchlights. "
            "Preserve intentional closed eyes, profile views, occlusion and expression; never force two wide-open human eyes. "
            "Clarify mouth pixels only when needed, preserving the original mouth shape and expression. "
            "Keep head tilt, identity and batch style. "
            "Locate the face again on this final grid: source boxes are not pixel-sheet coordinates. "
            "Use existing palette colors; a free symbol may expose an unused approved light/dark color. "
            "Write a face patch with source, size, optional colors, patches [{face, feature, box, rows, eyes}]. "
            "feature must be eye or mouth. Use tight, separately inspected eye/mouth boxes, never a full-face patch. "
            "Boxes are inclusive pixel coordinates; eyes optionally list {box, light, dark} for open-eye contrast checks. "
            "Inspect at native size and 4x after applying; do not smooth or outline over the repaired details. "
            "If the face is too small or lacks usable light/dark colors, report the limitation instead of inventing detail.")


def face_patch(sheet: Sheet, anchor: dict, plan: dict) -> Sheet:
    """Apply assistant-authored facial pixels; no face detector or generic eye template."""
    errors, _ = check(sheet)
    if errors:
        raise ValueError("invalid source sheet: " + "; ".join(errors))
    if not isinstance(plan, dict) or plan.get("source") != sheet.name or plan.get("size") != sheet.size:
        raise ValueError("face patch source/size does not match the sheet")
    patches = plan.get("patches")
    if not isinstance(patches, list) or not patches:
        raise ValueError("face patch needs a nonempty patches list")
    grid = [list(row) for row in sheet.rows]
    additions = plan.get("colors", {})
    if not isinstance(additions, dict) or any(k not in SYMBOLS or len(k) != 1 or not isinstance(v, str) or not _hex_ok(v)
                                            for k, v in additions.items()):
        raise ValueError("face colors must use A-P and lowercase #rrggbb")
    if any(k in sheet.colors and sheet.colors[k] != v for k, v in additions.items()):
        raise ValueError("face patch cannot redefine existing colors outside the face")
    colors = dict(sheet.colors, **additions)
    faces = anchor.get("faces", [])
    touched = set()

    def pixel_box(box):
        if not (isinstance(box, list) and len(box) == 4 and all(type(v) is int for v in box) and
                0 <= box[0] <= box[2] < sheet.size and 0 <= box[1] <= box[3] < sheet.size):
            raise ValueError("face patch box must be inclusive pixel coordinates inside the sheet")
        return box

    for patch in patches:
        if not isinstance(patch, dict):
            raise ValueError("each face patch must be an object")
        if patch.get("feature") not in ("eye", "mouth"):
            raise ValueError("face patch feature must be eye or mouth; brows, nose and whole-face edits are excluded")
        face = patch.get("face")
        if type(face) is not int or not 0 <= face < len(faces) or not faces[face]["complex"]:
            raise ValueError("face patch must target an annotated complex face; objects and clear faces are preserved")
        if not isinstance(faces[face].get("gaze"), str) or not faces[face]["gaze"].strip():
            raise ValueError("face patch requires an assessment of the original gaze")
        x0, y0, x1, y1 = pixel_box(patch.get("box"))
        rows = patch.get("rows")
        if not isinstance(rows, list) or len(rows) != y1 - y0 + 1 or any(not isinstance(r, str) or len(r) != x1 - x0 + 1 for r in rows):
            raise ValueError("face patch rows must exactly fill its box")
        for dy, row in enumerate(rows):
            for dx, symbol in enumerate(row):
                x, y = x0 + dx, y0 + dy
                if (x, y) in touched:
                    raise ValueError("face patches must not overlap")
                touched.add((x, y))
                if symbol != TRANSPARENT and symbol not in colors:
                    raise ValueError("face patch must use the existing palette symbols")
                if (symbol == TRANSPARENT) != (sheet.rows[y][x] == TRANSPARENT):
                    raise ValueError("face patch must preserve the source alpha silhouette")
                grid[y][x] = symbol
        eyes = patch.get("eyes", [])
        if not isinstance(eyes, list) or any(not isinstance(eye, dict) for eye in eyes):
            raise ValueError("eyes must list open-eye check objects")
        if patch["feature"] == "mouth" and eyes:
            raise ValueError("mouth patches cannot include eye edits")
        eye_pixels = set()
        for eye in eyes:
            ex0, ey0, ex1, ey1 = pixel_box(eye.get("box"))
            if not (x0 <= ex0 <= ex1 <= x1 and y0 <= ey0 <= ey1 <= y1):
                raise ValueError("eye check must stay inside its face patch")
            eye_pixels.update((x, y) for y in range(ey0, ey1 + 1) for x in range(ex0, ex1 + 1))
            light, dark = eye.get("light"), eye.get("dark")
            if light not in colors or dark not in colors:
                raise ValueError("eye check needs existing light/dark palette symbols")
            lightness = [_oklab(tuple(int(colors[c][i:i+2], 16) for i in (1, 3, 5)))[0] for c in (light, dark)]
            visible = {grid[y][x] for y in range(ey0, ey1 + 1) for x in range(ex0, ex1 + 1)}
            if lightness[0] - lightness[1] < 0.3 or light not in visible or dark not in visible:
                raise ValueError("open eye needs visible, distinct light and dark pixels")
        if eyes and any(grid[y][x] != sheet.rows[y][x] and (x, y) not in eye_pixels
                        for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)):
            raise ValueError("eye patch changes pixels outside the declared eye regions")
    name = sheet.name + "-face"
    result = Sheet(name, sheet.size, sheet.kind, sheet.palette, colors, ["".join(r) for r in grid],
                   sheet.path.with_name(name + ".pxg") if sheet.path else None)
    errors, _ = check(result)
    if errors:
        raise ValueError("invalid face result: " + "; ".join(errors))
    return result


REF_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def batch_style(src_dir: Path, images: dict[str, Path]) -> tuple[dict | None, str]:
    """The assistant judges style; this file binds its review/choices to the actual images."""
    if len(images) < 2:
        return None, ""
    path = src_dir / "batch.style.json"
    inputs = {name: {"file": image.name, "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
              for name, image in images.items()}
    if not path.exists():
        draft = {"profile": "", "references": [], "assets": {
            name: dict(source, match=None, reason="", choice=None) for name, source in inputs.items()}}
        path.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return None, "Visually review the batch and complete batch.style.json; Python does not classify art style."
    review = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(review, dict) or not isinstance(review.get("assets"), dict):
        raise ValueError("batch.style.json must contain an assets object")
    if set(review["assets"]) != set(inputs):
        return None, "Batch membership changed; visually review the new batch and update batch.style.json."
    for name, source in inputs.items():
        item = review["assets"][name]
        if not isinstance(item, dict):
            raise ValueError(f"batch.style.json: {name} must be an object")
        if any(item.get(k) != v for k, v in source.items()):
            return None, f"Reference image {name} changed; review it before updating its file/sha256 in batch.style.json."
        if item.get("match") is None:
            return None, f"Style review for {name} is incomplete in batch.style.json."
        if type(item["match"]) is not bool:
            raise ValueError(f"batch.style.json: {name}.match must be true, false or null")
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError(f"batch.style.json: {name}.reason must explain the visual assessment")
        if item.get("choice") not in (None, "original", "unify"):
            raise ValueError(f"batch.style.json: {name}.choice must be null, original or unify")
        if item["match"] and item.get("choice") is not None:
            raise ValueError(f"batch.style.json: compatible asset {name} needs no user choice")
    profile, references = review.get("profile"), review.get("references")
    if not isinstance(profile, str) or not isinstance(references, list):
        raise ValueError("batch.style.json: profile must be text and references must be asset names")
    if any(not isinstance(name, str) or name not in inputs for name in references):
        raise ValueError("batch.style.json: references must name assets in this batch")
    if any(not review["assets"][name]["match"] for name in references):
        raise ValueError("batch.style.json: style references must be compatible baseline assets")
    if any(item["match"] or item.get("choice") == "unify" for item in review["assets"].values()):
        if not profile.strip() or not references:
            return None, "Choose a baseline style and reference assets before generating a unified batch."
    return review, ""


def batch(src_dir: Path, out_dir: Path, provider: str, sizes: list[int] | None, concept_dir: Path | None = None,
          concept_background: str = "auto", only: list[str] | None = None, style_check: bool = True) -> int:
    """One directory = one batch. Every <name>.anchor.json + sibling image becomes a base sheet
    (mosaic -> concept -> palette -> import -> smooth -> check -> render). The model-side
    erase-and-paint pass happens afterwards, per sheet, in queue or parallel mode -- never here."""
    anchors = sorted(src_dir.glob("*.anchor.json"))
    if not anchors:
        print(f"no *.anchor.json in {src_dir}")
        return 1
    available = {p.name[:-len(".anchor.json")] for p in anchors}
    if only is not None and (not only or set(only) - available):
        raise ValueError("--only must name existing assets: " + ", ".join(sorted(available)))
    out_dir.mkdir(parents=True, exist_ok=True)
    images = {}
    for apath in anchors:
        stem = apath.name[:-len(".anchor.json")]
        image = next((apath.with_name(stem + ext) for ext in REF_SUFFIXES if apath.with_name(stem + ext).exists()), None)
        if image is not None:
            images[stem] = image
    # Style review is opt-in (CLI --style-check / the panel checkbox); by default each asset is drawn as it is.
    style, style_problem = batch_style(src_dir, images) if style_check else (None, "")
    jobs, failed = [], 0
    for apath in anchors:
        stem = apath.name[:-len(".anchor.json")]
        if only is not None and stem not in only:
            continue
        job = {"name": stem, "anchor": apath.name, "status": "base-ready", "sheets": [], "problems": [],
               "review": "pending"}
        jobs.append(job)
        try:
            anchor = load_anchor(apath)
            if sizes:
                anchor = dict(anchor, size=max(sizes))
            image = images.get(stem)
            if image is None:
                raise FileNotFoundError(f"no reference image {stem}.png/.jpg next to the anchor")
            if style_problem:
                job["status"] = "needs-style-review"
                job["problems"].append(style_problem)
                continue
            mode = "original"
            if style is not None:
                assessment = style["assets"][stem]
                mode = "matched" if assessment["match"] else assessment["choice"]
                job["style"] = {"mode": mode, "reason": assessment["reason"]}
                if mode is None:
                    job["status"] = "needs-style-choice"
                    job["question"] = f"{stem} 与这批素材的画风差异较大：{assessment['reason']}。保留原图风格，还是统一到这批画风？"
                    job["choices"] = [{"value": "original", "label": "保留原图风格"},
                                      {"value": "unify", "label": "统一画风"}]
                    job["problems"].append("Await the user's choice in batch.style.json; do not generate this asset yet.")
                    continue
                if mode != "original":
                    references = style["references"]
                    # Establish the first baseline before referring to it; avoid
                    # asking two not-yet-generated baseline concepts to reference each other.
                    job["style_references"] = references[:references.index(stem)] if stem in references else references
            pre = out_dir / f"{stem}.pre.png"
            prompt = out_dir / f"{stem}.prompt.txt"
            prompt_style = dict(style, references=job.get("style_references", [])) if style is not None else None
            prompt.write_text(concept_prompt(anchor, prompt_style, mode), encoding="utf-8")
            job["prompt"] = prompt.name
            concept_name = f"{stem}.unified.png" if mode == "unify" else f"{stem}.png"
            job["concept_file"] = concept_name
            needs_concept = provider != "none" or mode == "unify"
            result = concept_dir / concept_name if concept_dir and needs_concept else None
            have_concept = result is not None and result.exists()
            if not needs_concept or not have_concept:
                mosaic(image, anchor, pre)
            if needs_concept and not have_concept:
                job["status"] = "needs-concept"
                job["problems"].append(f"Generate {concept_name} in a concept directory, then rerun with --concept-dir DIR")
                continue
            con = concept(pre, anchor, provider, out_dir / f"{stem}.concept.png", result, concept_background)
            pal_path = out_dir / f"{stem}.pal"
            pal_path.write_text("\n".join(extract_palette(con, len(SYMBOLS), anchor)) + "\n", encoding="utf-8")
            for size in sizes or [anchor["size"]]:
                sheet = import_png(con, size, f"{stem}-{size}", anchor["kind"], pal_path.name, background="none")
                sheet.path = out_dir / f"{stem}-{size}.pxg"      # check resolves the .pal relative to the sheet
                # Fine regions already have a sampling budget; never blindly erase
                # all isolated pixels before the assistant has inspected features.
                smooth_sheet(sheet, 1, "")
                used = {c for row in sheet.rows for c in row}
                sheet.colors = {c: v for c, v in sheet.colors.items() if c in used}
                errors, warnings = check(sheet)
                spath = sheet.path
                spath.write_text(sheet.dump(), encoding="utf-8")
                if errors:
                    job["status"] = "check-failed"
                    job["problems"] += [f"{size}: {e}" for e in errors]
                else:
                    render(sheet, out_dir)
                    if anchor.get("faces"):
                        complex_face = any(face["complex"] for face in anchor["faces"])
                        review = {"sheet": spath.name, "status": "needs-face-review" if complex_face else "preserve"}
                        if complex_face:
                            fp = out_dir / f"{sheet.name}.face-prompt.txt"
                            fp.write_text(face_prompt(anchor, size), encoding="utf-8")
                            review["prompt"] = fp.name
                        job.setdefault("face_review", []).append(review)
                job["problems"] += [f"{size}: (warn) {w}" for w in warnings]
                job["sheets"].append(spath.name)
            if job["status"] == "check-failed":
                failed += 1
        except Exception as exc:                                    # one bad job must not sink the batch
            job["status"] = "failed"
            job["problems"].append(str(exc))
            failed += 1
    report_path = out_dir / "batch-report.json"
    payload = {"provider": provider, "jobs": jobs}
    if only is not None:
        payload["selected"] = sorted(set(only))
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    todo = [j for j in jobs if j["status"] == "base-ready"]
    print(f"batch{' subset' if only is not None else ''}: {len(jobs)} jobs, {len(todo)} base sheets ready, {failed} failed -> {report_path}")
    if style_problem:
        print(style_problem)
    for j in jobs:
        mark = {"base-ready": "+", "needs-style-review": "?", "needs-style-choice": "?",
                "needs-concept": "?", "check-failed": "!", "failed": "x"}[j["status"]]
        if j["status"] == "needs-concept":
            detail = f"prompt={j['prompt']}; save={j['concept_file']}"
            if j.get("style_references"):
                detail += "; style refs=" + ",".join(j["style_references"])
        elif j["status"] == "needs-style-review":
            detail = "needs-style-review"
        else:
            detail = ", ".join(j["sheets"]) or j["problems"][0]
        print(f"  {mark} {j['name']}: {detail}")
        if "question" in j:
            print(f"    {j['question']}")
        for face in j.get("face_review", []):
            if face["status"] == "needs-face-review":
                print(f"    face review: {face['sheet']} -> {face['prompt']}")
    if todo:
        print("next: refine each base sheet against its anchor (erase + paint, <= 20 steps) -- queue or parallel per SKILL.md")
    return 1 if failed else (2 if any(j["status"].startswith("needs-") for j in jobs) else 0)


def derive(sheet: Sheet, size: int) -> Sheet:
    """Majority-vote downsample a refined sheet to a smaller supported size. Refine once at the
    largest size, derive the rest; a mostly-transparent cell stays transparent."""
    if size not in SIZES:
        raise ValueError(f"size must be one of {SIZES}")
    factor, rem = divmod(sheet.size, size)
    if rem or factor < 2:
        raise ValueError(f"cannot derive {size} from {sheet.size}")
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            votes = Counter(sheet.rows[y * factor + dy][x * factor + dx]
                            for dy in range(factor) for dx in range(factor))
            transparent = votes.pop(TRANSPARENT, 0)
            top = TRANSPARENT if transparent >= factor * factor / 2 else votes.most_common(1)[0][0]
            row.append(top)
        rows.append("".join(row))
    used = {c for r in rows for c in r if c != TRANSPARENT}
    name = re.sub(r"-\d+$", "", sheet.name) + f"-{size}"
    return Sheet(name, size, sheet.kind, sheet.palette,
                 {k: v for k, v in sheet.colors.items() if k in used}, rows,
                 sheet.path.with_name(f"{name}.pxg") if sheet.path else None)


# ---------------------------------------------------------------- sheet

def _b64png(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build_sheet(src_dir: Path, out_dir: Path, columns: int) -> None:
    files = sorted(src_dir.glob("*.pxg"))
    if not files:
        sys.exit(f"no .pxg files in {src_dir}")
    sheets: list[Sheet] = []
    failed = 0
    for f in files:
        s = load(f)
        errors, warnings = check(s)
        report(s, errors, warnings)
        if errors:
            failed += 1
        else:
            sheets.append(s)
    if failed:
        sys.exit(f"{failed} sheet(s) failed check; fix them before building the sheet")
    out_dir.mkdir(parents=True, exist_ok=True)
    cell = max(s.size for s in sheets)
    cols = max(1, min(columns, len(sheets)))
    rows_n = (len(sheets) + cols - 1) // cols
    atlas = Image.new("RGBA", (cols * cell, rows_n * cell))
    frames: dict[str, dict] = {}
    cards: list[str] = []
    for i, s in enumerate(sheets):
        x, y = (i % cols) * cell, (i // cols) * cell
        img = s.image()
        atlas.paste(img, (x, y))
        frames[s.name] = {"x": x, "y": y, "w": s.size, "h": s.size, "kind": s.kind, "source": s.path.name}
        render(s, out_dir / "png")
        swatches = "".join(f'<i style="background:{v}" title="{k} {v}"></i>' for k, v in s.colors.items())
        cards.append(
            f'<figure data-kind="{s.kind}"><img src="data:image/png;base64,{_b64png(img)}" width="{s.size}" height="{s.size}" alt="{escape(s.name)}">'
            f'<figcaption><b>{escape(s.name)}</b><span>{s.size}×{s.size} · {s.kind} · {len(s.colors)} colors</span><div class="sw">{swatches}</div></figcaption></figure>')
    atlas.save(out_dir / "sheet.png")
    (out_dir / "sheet.json").write_text(json.dumps({"image": "sheet.png", "cell": cell, "frames": frames}, indent=2), encoding="utf-8")
    html = HTML.replace("{{CARDS}}", "\n".join(cards)).replace("{{COUNT}}", str(len(sheets))).replace("{{ATLAS}}", _b64png(atlas))
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"sheet: {len(sheets)} assets -> {out_dir / 'sheet.png'}, sheet.json, index.html, png/")


HTML = """<!doctype html><meta charset="utf-8"><title>Picxel sheet</title>
<style>
:root{--bg:#1b1b1f;--fg:#e8e8ec;--card:#26262c}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif}
header{display:flex;gap:16px;align-items:center;padding:12px 20px;border-bottom:1px solid #333;position:sticky;top:0;background:var(--bg)}
header label{display:flex;gap:6px;align-items:center}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;padding:20px}
figure{margin:0;background:var(--card);border-radius:8px;padding:12px;display:flex;flex-direction:column;align-items:center;gap:8px}
figure img{image-rendering:pixelated;image-rendering:crisp-edges;width:calc(var(--z)*1px * var(--s));height:auto;background:var(--chk)}
figcaption{width:100%;display:flex;flex-direction:column;gap:4px}
figcaption span{opacity:.7;font-size:12px}
.sw{display:flex;flex-wrap:wrap;gap:3px}.sw i{width:14px;height:14px;border-radius:3px;display:inline-block;border:1px solid #0006}
.hidden{display:none}
#atlas{padding:0 20px 30px}#atlas img{image-rendering:pixelated;max-width:100%;background:var(--chk)}
</style>
<header><b>Picxel</b><span>{{COUNT}} assets</span>
<label>zoom <input id="z" type="range" min="1" max="12" value="6"><span id="zv">6×</span></label>
<label><input id="chk" type="checkbox" checked> checkerboard</label>
<label>show <select id="kind"><option value="">all</option><option>tile</option><option>item</option><option>sprite</option></select></label>
<a href="sheet.png" download style="color:#9cf">sheet.png</a><a href="sheet.json" download style="color:#9cf">sheet.json</a></header>
<main>{{CARDS}}</main>
<section id="atlas"><h3>sheet.png</h3><img src="data:image/png;base64,{{ATLAS}}" alt="spritesheet"></section>
<script>
const CHK="url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2216%22 height=%2216%22><rect width=%2216%22 height=%2216%22 fill=%22%23333%22/><rect width=%228%22 height=%228%22 fill=%22%23444%22/><rect x=%228%22 y=%228%22 width=%228%22 height=%228%22 fill=%22%23444%22/></svg>')";
const root=document.documentElement,z=document.getElementById('z'),zv=document.getElementById('zv'),chk=document.getElementById('chk'),kind=document.getElementById('kind');
function apply(){zv.textContent=z.value+'×';document.querySelectorAll('figure img').forEach(i=>{i.style.width=(i.getAttribute('width')*z.value)+'px'});root.style.setProperty('--chk',chk.checked?CHK:'none');document.querySelectorAll('figure').forEach(f=>f.classList.toggle('hidden',kind.value&&f.dataset.kind!==kind.value))}
z.oninput=chk.onchange=kind.onchange=apply;apply();
</script>
"""


# ---------------------------------------------------------------- cli

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="picxel", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check"); p.add_argument("files", nargs="+", type=Path)
    p = sub.add_parser("render"); p.add_argument("files", nargs="+", type=Path); p.add_argument("-o", "--out", type=Path, default=Path("out"))
    p = sub.add_parser("palette"); p.add_argument("image", type=Path); p.add_argument("--colors", type=int, default=16)
    p.add_argument("--anchor", type=Path, help="weight fine/medium regions so small critical colors survive")
    p.add_argument("-o", "--out", type=Path, help="write a .pal file (one #rrggbb per line) instead of printing")
    p = sub.add_parser("import"); p.add_argument("image", type=Path); p.add_argument("--size", type=int, required=True, choices=SIZES)
    p.add_argument("--name"); p.add_argument("--kind", default="sprite", choices=KINDS)
    p.add_argument("--palette", default="db32", help="db32 | custom | path/to/file.pal")
    p.add_argument("--colors", type=int, default=16, help="with --palette custom: how many colors to keep (<=16)")
    p.add_argument("--background", default="none", help="none | auto (most common corner color) | #rrggbb - made transparent")
    p.add_argument("-o", "--out", type=Path, help="output .pxg (default: <name>.pxg next to the image)")
    p = sub.add_parser("sheet"); p.add_argument("dir", type=Path); p.add_argument("-o", "--out", type=Path); p.add_argument("--columns", type=int, default=8)
    p = sub.add_parser("mosaic"); p.add_argument("image", type=Path); p.add_argument("--anchor", type=Path, required=True); p.add_argument("-o", "--out", type=Path)
    p.add_argument("--background", default="auto", help="none | auto | #rrggbb - stripped before blocking")
    p = sub.add_parser("concept"); p.add_argument("image", type=Path, help="the pre-processed (mosaic) reference"); p.add_argument("--anchor", type=Path, required=True)
    p.add_argument("--provider", default="none", choices=("none", "codex", "claude", "api")); p.add_argument("-o", "--out", type=Path)
    p.add_argument("--result", type=Path, help="concept PNG produced by the current assistant; required for non-none providers")
    p.add_argument("--background", default="auto", help="none | auto | #rrggbb (edge fill) | key:#rrggbb (explicit key everywhere)")
    p.add_argument("--prompt-only", action="store_true", help="print the concept prompt for the chosen provider and exit")
    p = sub.add_parser("smooth"); p.add_argument("files", nargs="+", type=Path); p.add_argument("--passes", type=int, default=2)
    p.add_argument("--keep", default="", help="symbols never merged (eyes, highlights), e.g. BG")
    p = sub.add_parser("derive"); p.add_argument("file", type=Path); p.add_argument("--sizes", required=True, help="comma list, e.g. 64,32")
    p.add_argument("--keep", default="", help="symbols the built-in speck pass must not merge (eyes, held objects)")
    p = sub.add_parser("show"); p.add_argument("file", type=Path)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--box", help="x0,y0,x1,y1 crop (inclusive)")
    group.add_argument("--full", action="store_true", help="print the full grid; default shows only metadata and palette")
    p = sub.add_parser("face"); p.add_argument("file", type=Path); p.add_argument("--anchor", type=Path, required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--prompt-only", action="store_true"); group.add_argument("--patch", type=Path)
    p = sub.add_parser("panel", help="local page for the human: pick folders, watch progress, see results"); p.add_argument("--port", type=int, default=8770)
    p.add_argument("--no-open", action="store_true", help="do not open the browser automatically")
    p = sub.add_parser("job", help="the panel's job file: show it, or mark it start/done/stop"); p.add_argument("action", choices=("show", "start", "done", "stop"))
    p.add_argument("--note", default="", help="shown on the panel, e.g. why it stopped")
    p = sub.add_parser("batch"); p.add_argument("dir", type=Path); p.add_argument("-o", "--out", type=Path)
    p.add_argument("--provider", default="none", choices=("none", "codex", "claude", "api"))
    p.add_argument("--concept-dir", type=Path, help="assistant-produced <name>.png concepts; missing results are reported as needs-concept")
    p.add_argument("--concept-background", default="auto", help="concept background: auto | none | key:#rrggbb")
    p.add_argument("--sizes", help="comma list overriding each anchor's size, e.g. 128,64,32")
    p.add_argument("--style-check", action="store_true", help="multi-image batches: review art-style consistency first (off by default)")
    p.add_argument("--only", nargs="+", help="process only these asset names; still use the full batch's style review")
    a = ap.parse_args(argv)

    if a.cmd in ("check", "render"):
        failed = 0
        for f in a.files:
            s = load(f)
            errors, warnings = check(s)
            report(s, errors, warnings)
            if errors:
                failed += 1
            elif a.cmd == "render":
                native, preview = render(s, a.out)
                print(f"  -> {native}  {preview}")
        return 1 if failed else 0
    if a.cmd == "palette":
        found = extract_palette(a.image, a.colors, load_anchor(a.anchor) if a.anchor else None)
        if a.out:
            a.out.write_text("\n".join(found) + "\n", encoding="utf-8")
            print(f"{len(found)} colors -> {a.out}")
        else:
            print("\n".join(found))
        return 0
    if a.cmd == "import":
        s = import_png(a.image, a.size, a.name, a.kind, a.palette, a.background, a.colors)
        out = a.out or a.image.with_name(f"{s.name}.pxg")
        out.write_text(s.dump(), encoding="utf-8")
        errors, warnings = check(s)
        report(s, errors, warnings)
        print(f"  -> {out}")
        return 1 if errors else 0
    if a.cmd == "sheet":
        build_sheet(a.dir, a.out or a.dir / "dist", a.columns)
        return 0
    if a.cmd == "mosaic":
        anchor = load_anchor(a.anchor)
        out = mosaic(a.image, anchor, a.out or a.image.with_name(a.image.stem + ".pre.png"), a.background)
        print(f"mosaic -> {out} ({len(anchor.get('regions', []))} regions)")
        return 0
    if a.cmd == "concept":
        anchor = load_anchor(a.anchor)
        if a.prompt_only:
            print(concept_prompt(anchor))
            return 0
        out = concept(a.image, anchor, a.provider, a.out or a.image.with_name(a.image.stem.replace(".pre", "") + ".concept.png"), a.result, a.background)
        print(f"concept ({a.provider}) -> {out}")
        return 0
    if a.cmd == "derive":
        sheet = load(a.file)
        errors, warnings = check(sheet)
        if errors:
            report(sheet, errors, warnings)
            return 1
        failed = 0
        for size in (int(v) for v in a.sizes.split(",")):
            if size not in SIZES:
                print(f"--sizes must come from {SIZES}"); return 2
            small = derive(sheet, size)
            smooth_sheet(small, 1, a.keep)                 # downsampling leaves specks; one pass is enough
            used = {c for r in small.rows for c in r if c != TRANSPARENT}
            small.colors = {k: v for k, v in small.colors.items() if k in used}
            out = a.file.with_name(f"{small.name}.pxg")
            small.path = out
            out.write_text(small.dump(), encoding="utf-8")
            errors, warnings = check(small)
            report(small, errors, warnings)
            failed += bool(errors)
        return 1 if failed else 0
    if a.cmd == "show":
        sheet = load(a.file)
        errors, warnings = check(sheet)
        if errors:
            report(sheet, errors, warnings)
            return 1
        if not a.box and not a.full:
            used = Counter(c for row in sheet.rows for c in row if c != TRANSPARENT)
            print(f"{sheet.name}: {sheet.size}x{sheet.size} {sheet.kind}, {len(used)} colors")
            print("palette: " + "  ".join(f"{c}={sheet.colors[c]} ({n})" for c, n in used.items()))
            print("Use --box x0,y0,x1,y1 for an edit window, or --full for all pixels.")
            return 0
        x0, y0, x1, y1 = (int(v) for v in a.box.split(",")) if a.box else (0, 0, sheet.size - 1, sheet.size - 1)
        if not (0 <= x0 <= x1 < sheet.size and 0 <= y0 <= y1 < sheet.size):
            raise ValueError("show box must lie inside the sheet")
        print("   " + "".join(str(x % 10) for x in range(x0, x1 + 1)))
        for y in range(y0, y1 + 1):
            print(f"{y:2} {sheet.rows[y][x0:x1 + 1]}")
        used = sorted({c for y in range(y0, y1 + 1) for c in sheet.rows[y][x0:x1 + 1] if c != TRANSPARENT})
        print("colors here: " + "  ".join(f"{c}={sheet.colors[c]}" for c in used))
        return 0
    if a.cmd == "face":
        sheet, anchor = load(a.file), load_anchor(a.anchor)
        if a.prompt_only:
            print(face_prompt(anchor, sheet.size))
            return 0
        plan = json.loads(a.patch.read_text(encoding="utf-8"))
        result = face_patch(sheet, anchor, plan)
        result.path.write_text(result.dump(), encoding="utf-8")
        render(result, result.path.parent)
        print(f"face patch -> {result.path}; visually verify expression at native size and 4x")
        return 0
    if a.cmd == "panel":
        from panel import serve
        return serve(a.port, not a.no_open)
    if a.cmd == "job":
        from panel import job_command
        return job_command(a.action, a.note)
    if a.cmd == "batch":
        sizes = [int(v) for v in a.sizes.split(",")] if a.sizes else None
        if sizes and any(v not in SIZES for v in sizes):
            print(f"--sizes must come from {SIZES}"); return 2
        return batch(a.dir, a.out or a.dir / "base", a.provider, sizes, a.concept_dir, a.concept_background, a.only, a.style_check)
    if a.cmd == "smooth":
        failed = 0
        for f in a.files:
            sh = load(f)
            errors, warnings = check(sh)
            if errors:
                report(sh, errors, warnings)
                failed += 1
                continue
            n = smooth_sheet(sh, a.passes, a.keep)
            f.write_text(sh.dump(), encoding="utf-8")
            errors, warnings = check(sh)
            report(sh, errors, warnings)
            print(f"  merged {n} specks -> {f}")
        return 1 if failed else 0
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
