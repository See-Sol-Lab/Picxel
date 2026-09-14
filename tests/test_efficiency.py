"""Optimization regressions: identical pixels and less unnecessary work/output."""
import contextlib
from collections import Counter
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import picxel as px
from px import Grid


class EfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.anchor = {"subject": "gem", "size": 32, "kind": "item", "keep": ["red gem"]}

    def asset(self, name):
        (self.root / f"{name}.anchor.json").write_text(json.dumps(self.anchor), encoding="utf-8")
        image = Image.new("RGBA", (64, 64), "white")
        ImageDraw.Draw(image).rectangle((12, 12, 51, 51), fill="red")
        image.save(self.root / f"{name}.png")

    def test_histogram_voting_matches_row_major_pixel_votes(self):
        rng = random.Random(2718)
        palette = [(0, 0, 0), (255, 0, 0), (0, 0, 255), (255, 255, 255)]
        image = Image.new("RGBA", (96, 96))
        for y in range(96):
            for x in range(96):
                image.putpixel((x, y), (*rng.choice(palette), rng.choice((0, 127, 128, 200, 255))))
        source = self.root / "vote.png"
        image.save(source)
        actual = px.import_png(source, 32, "vote", "tile", "custom").image()
        for y in range(32):
            for x in range(32):
                votes = Counter()
                for dy in range(3):
                    for dx in range(3):
                        color = image.getpixel((3*x+dx, 3*y+dy))
                        votes[None if color[3] < 128 else color[:3]] += 1
                transparent = votes.pop(None, 0)
                expected = (0, 0, 0, 0) if transparent >= 4.5 else (*votes.most_common(1)[0][0], 255)
                self.assertEqual(actual.getpixel((x, y)), expected)

    def test_ellipse_bounds_keep_original_geometry(self):
        for cx, cy, rx, ry in ((15, 18, 3, 5), (7.5, 8.25, 2.5, 4.5), (-1, 10, 6, 3), (127, 126, 4, 5)):
            grid = Grid(128)
            grid.disc(cx, cy, rx, ry, "A")
            expected = {(x, y) for y in range(128) for x in range(128)
                        if ((x+.5-cx)/rx)**2 + ((y+.5-cy)/ry)**2 <= 1}
            actual = {(x, y) for y, row in enumerate(grid.rows()) for x, c in enumerate(row) if c == "A"}
            self.assertEqual(actual, expected)

    def test_existing_concept_skips_mosaic(self):
        self.asset("gem")
        concepts = self.root / "concepts"
        concepts.mkdir()
        with Image.open(self.root / "gem.png") as image:
            image.save(concepts / "gem.png")
        out = self.root / "out"
        with patch.object(px, "mosaic", side_effect=AssertionError("unnecessary mosaic")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(px.batch(self.root, out, "codex", [32], concepts), 0)
        self.assertFalse((out / "gem.pre.png").exists())
        self.assertTrue((out / "gem-32.png").exists())

    def test_preparation_keeps_mosaic_and_prints_next_action(self):
        self.asset("gem")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(px.batch(self.root, self.root / "out", "codex", [32]), 2)
        self.assertTrue((self.root / "out/gem.pre.png").exists())
        self.assertIn("prompt=gem.prompt.txt", output.getvalue())
        self.assertIn("save=gem.png", output.getvalue())

    def test_only_keeps_batch_context_and_preserves_other_outputs(self):
        for name in ("a", "b"):
            self.asset(name)
        images = {name: self.root / f"{name}.png" for name in ("a", "b")}
        px.batch_style(self.root, images)
        review_path = self.root / "batch.style.json"
        data = json.loads(review_path.read_text())
        data.update(profile="Flat fantasy style", references=["a"])
        for item in data["assets"].values():
            item.update(match=True, reason="Compatible style", choice=None)
        review_path.write_text(json.dumps(data), encoding="utf-8")
        out = self.root / "out"
        out.mkdir()
        other = out / "a-32.pxg"
        other.write_text("a manually refined result", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(px.batch(self.root, out, "none", [32], only=["b"]), 0)
        report = json.loads((out / "batch-report.json").read_text())
        self.assertEqual(report["selected"], ["b"])
        self.assertEqual([j["name"] for j in report["jobs"]], ["b"])
        self.assertEqual(report["jobs"][0]["style_references"], ["a"])
        self.assertEqual(other.read_text(), "a manually refined result")

    def test_unknown_selection_fails_before_processing(self):
        self.asset("gem")
        with self.assertRaisesRegex(ValueError, "--only"):
            px.batch(self.root, self.root / "out", "none", [32], only=["missing"])
        self.assertFalse((self.root / "out").exists())

    def test_show_defaults_to_brief_and_full_is_explicit(self):
        sheet = px.Sheet("tile", 128, "tile", "custom", {"A": "#000000"}, ["A"*128]*128)
        source = self.root / "tile.pxg"
        source.write_text(sheet.dump(), encoding="utf-8")
        brief, full = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(brief):
            self.assertEqual(px.main(["show", str(source)]), 0)
        with contextlib.redirect_stdout(full):
            self.assertEqual(px.main(["show", str(source), "--full"]), 0)
        self.assertIn("palette:", brief.getvalue())
        self.assertNotIn("A"*128, brief.getvalue())
        self.assertIn("A"*128, full.getvalue())
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            px.main(["show", str(source), "--box=-1,0,4,4"])

    def test_shorter_prompt_keeps_artistic_constraints(self):
        anchor = dict(self.anchor, drop=["strands"], colors=["ruby red"])
        text = px.concept_prompt(anchor)
        for required in ("gem", "Target 32x32", "red gem", "strands", "ruby red", "top-left light",
                         "one pixel grid", "2-3 shades/material", "antialiasing", "pose and proportions"):
            self.assertIn(required, text)

    def test_explicit_background_is_consistent_with_generation_prompt(self):
        prompt = px.concept_prompt(self.anchor, background="key:#00ff00")
        self.assertIn("flat #00ff00 background", prompt)
        self.assertIn("background only", prompt)
        self.assertNotIn("true transparency", prompt)
        tile = px.concept_prompt(dict(self.anchor, kind="tile"), background="key:#00ff00")
        self.assertIn("Opaque square tile", tile)
        self.assertNotIn("#00ff00", tile)

    def test_batch_overview_and_refresh_use_only_selected_assets(self):
        self.asset("gem")
        concepts = self.root / "concepts"
        concepts.mkdir()
        with Image.open(self.root / "gem.png") as image:
            image.save(concepts / "gem.png")
        out = self.root / "out"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(px.batch(self.root, out, "codex", [32, 128, 64], concepts, only=["gem"]), 0)
        report = json.loads((out / "batch-report.json").read_text())
        self.assertEqual(report["previews"], ["review-1.png"])
        with Image.open(out / "review-1.png") as overview:
            self.assertEqual(overview.size, (1088, 448))
        # Refresh consumes the rendered results, not the original source or model.
        (self.root / "gem.png").unlink()
        Image.new("RGBA", (128, 128), "blue").save(out / "gem-128.png")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(px.main(["review", str(out)]), 0)
        with Image.open(out / "review-1.png") as overview:
            self.assertEqual(overview.getpixel((280 + 128, 32 + 128)), (0, 0, 255))
            self.assertEqual(overview.getpixel((280 + 128, 316 + 64)), (0, 0, 255))

    def test_overview_pages_and_failures(self):
        jobs = []
        out = self.root
        for i in range(5):
            name = f"gem{i}"
            Image.new("RGBA", (32, 32), "red").save(out / f"{name}.concept.png")
            Image.new("RGBA", (32, 32), "red").save(out / f"{name}-32.png")
            jobs.append({"name": name, "status": "base-ready", "sheets": [f"{name}-32.pxg"]})
        jobs.append({"name": "failed", "status": "failed", "sheets": []})
        self.assertEqual(px.review_overview(jobs, out), ["review-1.png", "review-2.png"])
        with Image.open(out / "review-2.png") as overview:
            self.assertEqual(overview.size, (544, 448))
        self.assertEqual(px.review_overview(jobs[-1:], out), [])

    def test_shared_decoded_concept_preserves_native_colors_and_input(self):
        image = Image.new("RGBA", (128, 128))
        image.paste((16, 16, 16, 255), (20, 20, 108, 108))
        image.putpixel((60, 60), (17, 17, 17, 255))
        original = image.tobytes()
        palette = ["#101010", "#111111"]
        for size in (32, 64, 128):
            sheet = px._import_image(image, size, "gem", "item", "custom", palette)
            self.assertEqual(image.tobytes(), original)
            self.assertFalse(px.check(sheet)[0])
            if size == 128:
                self.assertEqual(sheet.image().tobytes(), original)


if __name__ == "__main__":
    unittest.main()
