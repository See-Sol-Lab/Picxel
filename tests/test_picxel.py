"""Behavior regressions: silhouette, palette voting, detail, handoff and packaging."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import picxel as px
from px import Grid


class PipelineTests(unittest.TestCase):
    def test_supported_sizes_and_removed_tier(self):
        self.assertEqual(px.SIZES, (32, 64, 128))
        for n in px.SIZES:
            self.assertEqual(Grid(n).n, n)
        with self.assertRaises(ValueError):
            Grid(16)
        source = self.save(Image.new("RGBA", (128, 128), "red"))
        with self.assertRaises(ValueError):
            px.import_png(source, 16, None, "item", "custom")
        old = px.Sheet("retired", 16, "tile", "custom", {"A": "#000000"}, ["A" * 16] * 16)
        self.assertTrue(px.check(old)[0])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exc:
                px.main(["import", str(source), "--size", "16"])
            self.assertEqual(exc.exception.code, 2)
            self.assertEqual(px.main(["batch", str(self.root), "--sizes", "16"]), 2)
        anchor = self.root / "old.anchor.json"
        anchor.write_text(json.dumps(dict(self.anchor, size=16)), encoding="utf-8")
        with self.assertRaises(ValueError):
            px.load_anchor(anchor)

    def test_128_batch_render_pack_and_derive(self):
        source = self.make_job()
        concepts = self.root / "concepts"
        concepts.mkdir()
        Image.open(source).save(concepts / "gem.png")
        out = self.root / "large"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(px.batch(self.root, out, "codex", [128, 64, 32], concepts), 0)
            px.build_sheet(out, out / "dist", 3)
        self.assertIn("Target 128x128", (out / "gem.prompt.txt").read_text())
        with Image.open(out / "gem-128.png") as image:
            self.assertEqual(image.size, (128, 128))
        with Image.open(out / "gem-128@4x.png") as image:
            self.assertEqual(image.size, (512, 512))
        frames = json.loads((out / "dist/sheet.json").read_text())["frames"]
        self.assertEqual({f["w"] for f in frames.values()}, {32, 64, 128})
        big = px.load(out / "gem-128.pxg")
        for size in (64, 32):
            self.assertFalse(px.check(px.derive(big, size))[0])
        with self.assertRaises(ValueError):
            px.derive(big, 16)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.anchor = {"subject": "gem", "size": 32, "kind": "item", "keep": ["red diamond"]}

    def save(self, image, name="ref.png"):
        path = self.root / name
        image.save(path)
        return path

    def make_job(self, name="gem", kind="item"):
        anchor = dict(self.anchor, kind=kind)
        (self.root / f"{name}.anchor.json").write_text(json.dumps(anchor), encoding="utf-8")
        im = Image.new("RGBA", (128, 128), "white")
        ImageDraw.Draw(im).rectangle((12, 12, 51, 51), fill="red")
        return self.save(im, f"{name}.png")

    def run_batch(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            result = px.batch(self.root, self.root / "out", kwargs.pop("provider", "none"), [32], **kwargs)
        report = json.loads((self.root / "out/batch-report.json").read_text(encoding="utf-8"))
        return result, report

    def test_padding_survives_crop(self):
        im = Image.new("RGBA", (101, 71), "red")
        sh = px.import_png(self.save(im), 64, None, "item", "custom")
        self.assertEqual(sh.rows[0] + sh.rows[-1], "." * 128)
        self.assertTrue(all(row[0] == row[-1] == "." for row in sh.rows))
        self.assertFalse(px.check(sh)[0])

    def test_native_pixel_art_roundtrip(self):
        im = Image.new("RGBA", (32, 32))
        ImageDraw.Draw(im).rectangle((2, 3, 13, 12), fill="#ac3232")
        im.putpixel((6, 7), (255, 255, 255, 255))
        sh = px.import_png(self.save(im), 32, None, "item", "custom")
        self.assertEqual(sh.image().tobytes(), im.tobytes())

    def test_native_close_shades_do_not_merge(self):
        im = Image.new("RGBA", (32, 32))
        ImageDraw.Draw(im).rectangle((2, 2, 13, 13), fill="#101010")
        im.putpixel((6, 6), (17, 17, 17, 255))
        sh = px.import_png(self.save(im), 32, None, "item", "custom")
        self.assertEqual(sh.image().tobytes(), im.tobytes())

    def test_invalid_grid_is_not_mutated_by_smooth(self):
        path = self.root / "bad.pxg"
        original = "name: bad\nsize: 32\nkind: item\npalette: custom\nA: #000000\n---\nA\n"
        path.write_text(original, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(px.main(["smooth", str(path)]), 1)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_vote_after_palette_merges_nearby_shades(self):
        im = Image.new("RGBA", (128, 128), "white")
        for y in range(4):
            for x in range(4):
                im.putpixel((x, y), (100 + y * 4 + x, 40, 40, 255) if y < 3 else (0, 0, 0, 255))
        pal = self.root / "colors.pal"
        pal.write_text("#6e2828\n#000000\n#ffffff\n", encoding="utf-8")
        sh = px.import_png(self.save(im), 32, None, "tile", str(pal))
        self.assertEqual(sh.colors[sh.rows[0][0]], "#6e2828")

    def test_opaque_coverage_is_separate_from_color_votes(self):
        im = Image.new("RGBA", (64, 64), "white")
        im.putpixel((0, 0), (0, 0, 0, 0))
        im.putpixel((1, 0), (0, 0, 0, 0))
        im.putpixel((0, 1), (255, 0, 0, 255))
        im.putpixel((1, 1), (0, 0, 255, 255))
        sh = px.import_png(self.save(im), 32, None, "tile", "custom")
        self.assertEqual(sh.rows[0][0], ".")

    def test_auto_background_respects_existing_alpha(self):
        im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle((4, 4, 11, 11), fill="black")
        self.assertEqual(px._strip_background(im, "auto").tobytes(), im.tobytes())

    def test_background_fill_preserves_enclosed_white(self):
        im = Image.new("RGBA", (32, 32), "white")
        ImageDraw.Draw(im).rectangle((3, 3, 12, 12), fill="black")
        im.putpixel((7, 7), (255, 255, 255, 255))
        out = px._strip_background(im, "auto")
        self.assertEqual(out.getpixel((0, 0))[3], 0)
        self.assertEqual(out.getpixel((7, 7))[3], 255)

    def test_explicit_key_removes_enclosed_background_holes(self):
        im = Image.new("RGBA", (32, 32), "magenta")
        ImageDraw.Draw(im).rectangle((3, 3, 12, 12), fill="black")
        im.putpixel((7, 7), (255, 0, 255, 255))
        out = px._strip_background(im, "key:#ff00ff")
        self.assertEqual(out.getpixel((7, 7))[3], 0)
        self.assertEqual(out.getpixel((3, 3))[3], 255)

    def test_reserved_palette_cannot_exceed_budget(self):
        source = self.save(Image.new("RGB", (8, 8), "gray"))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            px.extract_palette(source, 2, dict(self.anchor, palette=["#000000", "#ffffff", "#ff0000"]))

    def test_sheet_name_cannot_escape_output_directory(self):
        sh = px.Sheet("../escape", 32, "tile", "custom", {"A": "#000000"}, ["A" * 32] * 32)
        self.assertTrue(px.check(sh)[0])

    def test_mosaic_preserves_alpha_and_fine_regions(self):
        im = Image.new("RGBA", (128, 128))
        ImageDraw.Draw(im).ellipse((9, 7, 110, 121), fill="red")
        im.putpixel((61, 61), (255, 255, 255, 255))
        anchor = dict(self.anchor, regions=[{"box": [0, 0, 1, 1], "detail": "coarse"},
                                            {"box": [.4, .4, .6, .6], "detail": "fine"}])
        out = px.mosaic(self.save(im), anchor, self.root / "pre.png")
        actual = Image.open(out)
        self.assertEqual(im.getchannel("A").tobytes(), actual.getchannel("A").tobytes())
        self.assertEqual(actual.getpixel((61, 61)), im.getpixel((61, 61)))

    def test_tile_mosaic_retains_background(self):
        im = Image.new("RGBA", (128, 128), "green")
        out = px.mosaic(self.save(im), dict(self.anchor, kind="tile"), self.root / "pre.png")
        self.assertEqual(Image.open(out).getchannel("A").getextrema(), (255, 255))

    def test_palette_reserves_both_extremes(self):
        im = Image.new("RGB", (100, 1), "gray")
        im.putpixel((0, 0), (0, 0, 0))
        im.putpixel((99, 0), (255, 255, 255))
        self.assertEqual(set(px.extract_palette(self.save(im), 2)), {"#000000", "#ffffff"})

    def test_explicit_palette_colors_are_reserved(self):
        im = Image.new("RGB", (64, 64), "gray")
        colors = px.extract_palette(self.save(im), 4, dict(self.anchor, palette=["#ff0000"]))
        self.assertIn("#ff0000", colors)
        self.assertLessEqual(len(colors), 4)

    def test_empty_image_and_color_bounds(self):
        path = self.save(Image.new("RGBA", (64, 64)))
        with self.assertRaisesRegex(ValueError, "opaque"):
            px.import_png(path, 32, None, "item", "custom")
        for count in (0, 1, 17):
            with self.assertRaisesRegex(ValueError, "colors"):
                px.extract_palette(path, count)

    def test_cleanup_keeps_glint_and_merges_only_close_speck(self):
        rows = [list("A" * 32) for _ in range(32)]
        rows[4][4], rows[10][10] = "B", "C"
        sh = px.Sheet("test", 32, "tile", "custom", {"A": "#333333", "B": "#ffffff", "C": "#383838"},
                      ["".join(row) for row in rows])
        self.assertEqual(px.smooth_sheet(sh, 1, ""), 1)
        self.assertEqual(sh.rows[4][4], "B")
        self.assertEqual(sh.rows[10][10], "A")

    def test_grid_uses_same_cleanup_and_protected_outline(self):
        g = Grid(32)
        g.rect(2, 2, 13, 13, "A")
        g.put("B", (2, 6))
        g.outline("C", keep="B")
        self.assertEqual(g.g[6][2], "B")
        g.smooth({"A": "#333333", "B": "#ffffff", "C": "#000000"})
        self.assertEqual(g.g[6][2], "B")

    def test_line_has_connected_endpoints(self):
        g = Grid(32)
        g.line(2, 3, 12, 9, "A")
        self.assertEqual(g.g[3][2], "A")
        self.assertEqual(g.g[9][12], "A")
        self.assertEqual(sum(row.count("A") for row in g.g), 11)

    def test_provider_handoff_then_resume(self):
        source = self.make_job()
        code, report = self.run_batch(provider="codex")
        self.assertEqual(code, 2)
        self.assertEqual(report["jobs"][0]["status"], "needs-concept")
        self.assertFalse(report["jobs"][0]["sheets"])
        concepts = self.root / "concepts"
        concepts.mkdir()
        Image.open(source).save(concepts / "gem.png")
        code, report = self.run_batch(provider="codex", concept_dir=concepts)
        self.assertEqual(code, 0)
        self.assertEqual(report["jobs"][0]["status"], "base-ready")
        self.assertEqual(report["jobs"][0]["review"], "pending")

    def test_single_provider_requires_result(self):
        source = self.make_job()
        with self.assertRaisesRegex(ValueError, "needs --result"):
            px.concept(source, self.anchor, "codex", self.root / "concept.png")

    def test_one_failed_job_does_not_abort_batch(self):
        self.make_job()
        (self.root / "bad.anchor.json").write_text("[]", encoding="utf-8")
        code, report = self.run_batch()
        self.assertEqual(code, 1)
        self.assertEqual([j["status"] for j in report["jobs"]], ["failed", "base-ready"])

    def test_validation_failure_returns_nonzero(self):
        self.make_job()
        concepts = self.root / "concepts"
        concepts.mkdir()
        self.save(Image.new("RGBA", (32, 32), "red"), "concepts/gem.png")
        # Existing alpha bypasses chroma key; the corner remains opaque and invalid.
        im = Image.open(concepts / "gem.png").convert("RGBA")
        im.putpixel((8, 8), (0, 0, 0, 0))
        im.save(concepts / "gem.png")
        code, report = self.run_batch(provider="codex", concept_dir=concepts)
        self.assertEqual(code, 1)
        self.assertEqual(report["jobs"][0]["status"], "check-failed")

    def test_packaging_escapes_labels_and_keeps_native_frames(self):
        self.make_job()
        self.run_batch()
        out = self.root / "out"
        with contextlib.redirect_stdout(io.StringIO()):
            px.build_sheet(out, out / "dist", 4)
        frames = json.loads((out / "dist/sheet.json").read_text())["frames"]
        self.assertEqual(frames["gem-32"]["w"], 32)
        self.assertIn("data:image/png;base64,", (out / "dist/index.html").read_text())

    def test_derive_coverage_and_bounds(self):
        rows = ["A" * 64 for _ in range(64)]
        rows[0], rows[1] = ".." + rows[0][2:], "BC" + rows[1][2:]
        sh = px.Sheet("gem-64", 64, "tile", "custom", {"A": "#333333", "B": "#ffffff", "C": "#ff0000"}, rows)
        self.assertEqual(px.derive(sh, 32).rows[0][0], ".")
        with self.assertRaises(ValueError):
            px.derive(sh, 0)


if __name__ == "__main__":
    unittest.main()
