"""Palette fidelity regressions; these assert color behavior, not quantizer internals."""
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import picxel as px


class PaletteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "source.png"

    def palette(self, image, count=16, anchor=None):
        image.save(self.path)
        return px.extract_palette(self.path, count, anchor)

    def test_small_feature_survives_full_resolution_color_collection(self):
        image = Image.new("RGBA", (1024, 1024), "#333333")
        image.putpixel((0, 0), (255, 0, 0, 255))
        self.assertEqual(set(self.palette(image, 4)), {"#333333", "#ff0000"})

    def test_exact_low_color_art_keeps_close_intentional_shades(self):
        image = Image.new("RGB", (32, 32), "#101010")
        image.putpixel((12, 12), (17, 17, 17))
        self.assertEqual(set(self.palette(image, 2)), {"#101010", "#111111"})

    def test_lightness_endpoints_do_not_use_rgb_channel_sum(self):
        image = Image.new("RGB", (90, 30))
        draw = ImageDraw.Draw(image)
        for x, color in enumerate(("#ff0000", "#00ff00", "#0000ff")):
            draw.rectangle((30*x, 0, 30*x+29, 29), fill=color)
        self.assertEqual(set(self.palette(image, 2)), {"#0000ff", "#00ff00"})

    def test_sparse_transparent_edge_fringe_does_not_take_a_palette_slot(self):
        image = Image.new("RGBA", (128, 128))
        draw = ImageDraw.Draw(image)
        for i, color in enumerate(("#202020", "#505050", "#909090", "#eeeeee")):
            draw.rectangle((16+24*i, 16, 39+24*i, 111), fill=color)
        for y in (40, 41, 42):
            image.putpixel((16, y), (255, 0, 255, 255))
        self.assertNotIn("#ff00ff", self.palette(image, 4, {"size": 32}))

    def test_fine_region_preserves_a_small_accent(self):
        image = Image.new("RGB", (200, 200))
        draw = ImageDraw.Draw(image)
        for x in range(200):
            gray = 20 + x
            draw.line((x, 0, x, 199), fill=(gray, gray, gray))
        draw.rectangle((80, 80, 85, 85), fill="#ff0000")
        anchor = {"size": 64, "regions": [{"box": [.4, .4, .43, .43], "detail": "fine"}]}
        self.assertIn("#ff0000", self.palette(image, 4, anchor))

    def test_auto_colors_are_actual_source_rgb_values(self):
        image = Image.new("RGB", (128, 32))
        for y in range(32):
            for x in range(128):
                image.putpixel((x, y), (x*2, 30+y, 80))
        source = {"#%02x%02x%02x" % image.getpixel((x, y)) for x in range(128) for y in range(32)}
        colors = self.palette(image, 8)
        self.assertTrue(set(colors).issubset(source))
        self.assertLessEqual(len(colors), 8)
        self.assertEqual(colors, px.extract_palette(self.path, 8))

    def test_invisible_rgb_never_changes_the_palette(self):
        image = Image.new("RGBA", (64, 64), (255, 0, 255, 0))
        ImageDraw.Draw(image).rectangle((16, 16, 47, 47), fill="#ac3232")
        image.putpixel((20, 20), (0, 0, 255, 127))
        expected = self.palette(image, 4)
        self.assertEqual(expected, ["#ac3232"])
        image.putpixel((0, 0), (0, 255, 0, 0))
        self.assertEqual(expected, self.palette(image, 4))

    def test_pinned_colors_are_exact_unique_and_ordered(self):
        image = Image.new("RGB", (64, 64), "#eeeeee")
        self.assertEqual(self.palette(image, 2, {"palette": ["#101010", "#101010", "#111111"]}),
                         ["#101010", "#111111"])

    def test_later_region_budget_overrides_an_earlier_region(self):
        image = Image.new("RGB", (64, 64))
        for x in range(64):
            ImageDraw.Draw(image).line((x, 0, x, 63), fill=(x*4, 60, 100))
        coarse = {"box": [0, 0, 1, 1], "detail": "coarse"}
        fine = {"box": [0, 0, .5, .5], "detail": "fine"}
        expected = self.palette(image, 4, {"regions": [coarse]})
        self.assertEqual(expected, self.palette(image, 4, {"regions": [fine, coarse]}))

    def test_custom_import_uses_source_colors_too(self):
        image = Image.new("RGBA", (32, 32))
        draw = ImageDraw.Draw(image)
        for x in range(2, 30):
            draw.line((x, 2, x, 29), fill=(x*8, 30, 80, 255))
        image.save(self.path)
        source = {"#%02x%02x%02x" % (x*8, 30, 80) for x in range(2, 30)}
        sheet = px.import_png(self.path, 32, None, "item", "custom", colors=4)
        self.assertTrue(set(sheet.colors.values()).issubset(source))
        self.assertFalse(px.check(sheet)[0])


if __name__ == "__main__":
    unittest.main()
