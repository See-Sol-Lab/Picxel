#!/usr/bin/env python3
"""pixelgrid — render, check, import and sheet `.pxg` pixel-art sheets.

    pixelgrid.py check  <file.pxg>...              validate; exit 1 on errors
    pixelgrid.py render <file.pxg>... [-o DIR]     PNG at 1x and 4x (checks first)
    pixelgrid.py palette <image.png> [--colors N] [-o ref.pal]
                                                   the N most used colors of a reference, as a palette file
    pixelgrid.py import <image.png> --size N [--kind K] [--palette db32|custom|ref.pal] [--background auto]
                                                   PNG (any size) -> .pxg: background stripped, cropped, squared, colors snapped
    pixelgrid.py sheet  <DIR> [-o OUT] [--columns N]
                                                   every .pxg in DIR -> spritesheet PNG + JSON + index.html

Only Pillow is required. Sizes are fixed at 16, 32, 64.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

SIZES = (16, 32, 64)
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


def extract_palette(image: Path, count: int) -> list[str]:
    """Median-cut the opaque pixels of an image down to `count` colors, most frequent first."""
    img = Image.open(image).convert("RGBA")
    data = img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata()
    opaque = [(r, g, b) for r, g, b, a in data if a >= 128]
    if not opaque:
        raise ValueError("image has no opaque pixels")
    tiny = Image.new("RGB", (len(opaque), 1))
    tiny.putdata(opaque)
    q = tiny.quantize(colors=count, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    counts = Counter(q.get_flattened_data() if hasattr(q, "get_flattened_data") else q.getdata())
    pal = q.getpalette()
    return ["#%02x%02x%02x" % tuple(pal[i * 3:i * 3 + 3]) for i, _ in counts.most_common()]
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
                   meta.get("kind", "sprite").lower(), meta.get("palette", "db32").lower(), colors, rows, path)

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
            warnings.append(f"symbols {''.join(syms)} all map to {value} — one material lost its contrast")
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
                warnings.append(f"tile seam looks hard (left/right {lr:.0f}, top/bottom {tb:.0f}; warn above {SEAM_WARN:.0f}) — soften the edge rows/columns")
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
        warnings.append(f"{orphans} isolated pixels (warn above {ORPHAN_WARN}) — noise, or deliberate texture?")
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
    """`none`: keep alpha as is. `auto`: the most common corner color becomes transparent (with a tolerance). `#rrggbb`: that color."""
    if mode == "none":
        return img
    px = img.load()
    w, h = img.size
    if mode == "auto":
        corners = Counter(px[x, y][:3] for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)))
        target = corners.most_common(1)[0][0]
    else:
        target = tuple(int(mode[i:i + 2], 16) for i in (1, 3, 5))
    out = img.copy()
    op = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a and ((r - target[0]) ** 2 + (g - target[1]) ** 2 + (b - target[2]) ** 2) ** 0.5 < 28:
                op[x, y] = (0, 0, 0, 0)
    return out


def _square(img: Image.Image, size: int) -> Image.Image:
    """Crop to the opaque bounding box, pad to a square, resample to an exact multiple of `size`."""
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    w, h = img.size
    side = max(w, h)
    canvas = Image.new("RGBA", (side, side))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))
    block = max(1, side // size)
    target = size * block
    return canvas.resize((target, target), Image.LANCZOS) if side != target else canvas


def import_png(src: Path, size: int, name: str | None, kind: str, palette: str, background: str = "none", colors: int = 16) -> Sheet:
    img = Image.open(src).convert("RGBA")
    img = _strip_background(img, background)
    if kind != "tile":
        margin = max(1, img.width // size)          # one cell of transparent padding all round
        framed = Image.new("RGBA", (img.width + 2 * margin, img.height + 2 * margin))
        framed.paste(img, (margin, margin))
        img = _square(framed, size)
    w, h = img.size
    if w != h:
        raise ValueError(f"source must be square, got {w}x{h}")
    if w % size:
        raise ValueError(f"source {w}px is not a multiple of {size}")
    block = w // size
    px = img.load()
    cells: list[list[tuple[int, int, int] | None]] = []
    for gy in range(size):
        row: list[tuple[int, int, int] | None] = []
        for gx in range(size):
            votes: Counter = Counter()
            for y in range(gy * block, (gy + 1) * block):
                for x in range(gx * block, (gx + 1) * block):
                    r, g, b, a = px[x, y]
                    votes[None if a < 128 else (r, g, b)] += 1
            row.append(votes.most_common(1)[0][0])
        cells.append(row)
    # collapse to <= 16 colors: snap to the master palette, or quantize the cells themselves when custom
    master = palette_colors(palette, src.parent)
    if master is not None:
        mapped = {c: _nearest(c, master) for row in cells for c in row if c is not None}
    else:
        opaque = [c for row in cells for c in row if c is not None]
        tiny = Image.new("RGB", (len(opaque), 1))
        tiny.putdata(opaque)
        q = tiny.quantize(colors=min(colors, len(SYMBOLS)), method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
        mapped = {c: "#%02x%02x%02x" % q.getpixel((i, 0)) for i, c in enumerate(opaque)}
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
            f'<figure data-kind="{s.kind}"><img src="data:image/png;base64,{_b64png(img)}" width="{s.size}" height="{s.size}" alt="{s.name}">'
            f'<figcaption><b>{s.name}</b><span>{s.size}×{s.size} · {s.kind} · {len(s.colors)} colors</span><div class="sw">{swatches}</div></figcaption></figure>')
    atlas.save(out_dir / "sheet.png")
    (out_dir / "sheet.json").write_text(json.dumps({"image": "sheet.png", "cell": cell, "frames": frames}, indent=2), encoding="utf-8")
    html = HTML.replace("{{CARDS}}", "\n".join(cards)).replace("{{COUNT}}", str(len(sheets))).replace("{{ATLAS}}", _b64png(atlas))
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"sheet: {len(sheets)} assets -> {out_dir / 'sheet.png'}, sheet.json, index.html, png/")


HTML = """<!doctype html><meta charset="utf-8"><title>pixelgrid sheet</title>
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
<header><b>pixelgrid</b><span>{{COUNT}} assets</span>
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
    ap = argparse.ArgumentParser(prog="pixelgrid", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check"); p.add_argument("files", nargs="+", type=Path)
    p = sub.add_parser("render"); p.add_argument("files", nargs="+", type=Path); p.add_argument("-o", "--out", type=Path, default=Path("out"))
    p = sub.add_parser("palette"); p.add_argument("image", type=Path); p.add_argument("--colors", type=int, default=16)
    p.add_argument("-o", "--out", type=Path, help="write a .pal file (one #rrggbb per line) instead of printing")
    p = sub.add_parser("import"); p.add_argument("image", type=Path); p.add_argument("--size", type=int, required=True, choices=SIZES)
    p.add_argument("--name"); p.add_argument("--kind", default="sprite", choices=KINDS)
    p.add_argument("--palette", default="db32", help="db32 | custom | path/to/file.pal")
    p.add_argument("--colors", type=int, default=16, help="with --palette custom: how many colors to keep (<=16)")
    p.add_argument("--background", default="none", help="none | auto (most common corner color) | #rrggbb - made transparent")
    p.add_argument("-o", "--out", type=Path, help="output .pxg (default: <name>.pxg next to the image)")
    p = sub.add_parser("sheet"); p.add_argument("dir", type=Path); p.add_argument("-o", "--out", type=Path); p.add_argument("--columns", type=int, default=8)
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
        found = extract_palette(a.image, a.colors)
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
    return 2


if __name__ == "__main__":
    sys.exit(main())
