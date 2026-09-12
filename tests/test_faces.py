"""Conditional facial repair and local, palette-safe pixel edits."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import picxel as px


class FaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        rows = [list("." * 32) for _ in range(32)]
        for y in range(4, 28):
            rows[y][4:28] = "B" * 24
        self.sheet = px.Sheet("portrait", 32, "sprite", "custom", {"A": "#000000", "B": "#d9a066", "C": "#ffffff"},
                              ["".join(row) for row in rows], self.root / "portrait.pxg")
        self.face = {"box": [.2, .1, .8, .6], "complex": True, "expression": "calm half-lidded eyes",
                     "gaze": "downward, pupils on image-left with sclera visible on image-right",
                     "reason": "bangs and shadow merge into the eye line"}
        self.anchor = {"size": 32, "kind": "sprite", "keep": ["expression"], "faces": [self.face]}
        self.plan = {"source": "portrait", "size": 32, "patches": [
            {"face": 0, "feature": "eye", "box": [10, 10, 15, 11], "rows": ["AABBAA", "ACBBAC"],
             "eyes": [{"box": [10, 10, 11, 11], "light": "C", "dark": "A"},
                      {"box": [14, 10, 15, 11], "light": "C", "dark": "A"}]}]}

    def test_objects_and_clear_faces_cannot_receive_a_patch(self):
        for faces in ([], [dict(self.face, complex=False)]):
            with self.assertRaisesRegex(ValueError, "complex face"):
                px.face_patch(self.sheet, dict(self.anchor, faces=faces), self.plan)

    def test_patch_preserves_every_pixel_outside_face_box_and_source(self):
        before = self.sheet.dump()
        result = px.face_patch(self.sheet, self.anchor, self.plan)
        for y in range(32):
            for x in range(32):
                if not (10 <= x <= 15 and 10 <= y <= 11):
                    self.assertEqual(result.rows[y][x], self.sheet.rows[y][x])
        self.assertEqual(self.sheet.dump(), before)
        self.assertEqual(result.image().getchannel("A").tobytes(), self.sheet.image().getchannel("A").tobytes())
        self.assertEqual(result.colors, self.sheet.colors)
        self.assertFalse(px.check(result)[0])

    def test_open_eye_requires_light_dark_and_sufficient_contrast(self):
        plan = copy.deepcopy(self.plan)
        plan["patches"][0]["rows"][1] = "AABBAA"
        with self.assertRaisesRegex(ValueError, "open eye"):
            px.face_patch(self.sheet, self.anchor, plan)
        self.sheet.colors["C"] = "#151515"
        with self.assertRaisesRegex(ValueError, "open eye"):
            px.face_patch(self.sheet, self.anchor, self.plan)

    def test_closed_or_occluded_eyes_do_not_require_sclera(self):
        plan = copy.deepcopy(self.plan)
        plan["patches"][0]["rows"] = ["BBBBBB", "AABBAA"]
        plan["patches"][0]["eyes"] = []
        result = px.face_patch(self.sheet, self.anchor, plan)
        self.assertEqual(result.rows[11][10:16], "AABBAA")

    def test_invalid_patches_fail_without_mutating_source(self):
        for change in ({"box": [-1, 10, 4, 11]}, {"rows": ["ZZZZZZ", "ZZZZZZ"]},
                       {"rows": ["......", "......"]}, {"rows": ["A"]}):
            plan = copy.deepcopy(self.plan)
            plan["patches"][0].update(change)
            before = self.sheet.dump()
            with self.assertRaises(ValueError):
                px.face_patch(self.sheet, self.anchor, plan)
            self.assertEqual(self.sheet.dump(), before)
        with self.assertRaisesRegex(ValueError, "source/size"):
            px.face_patch(self.sheet, self.anchor, dict(self.plan, size=64))

    def test_extra_light_color_does_not_recolor_existing_materials(self):
        plan = copy.deepcopy(self.plan)
        plan["colors"] = {"P": "#fff3dc"}
        plan["patches"][0]["rows"] = ["AABBAA", "APBBAP"]
        for eye in plan["patches"][0]["eyes"]:
            eye["light"] = "P"
        result = px.face_patch(self.sheet, self.anchor, plan)
        self.assertEqual(result.colors["B"], self.sheet.colors["B"])
        self.assertEqual(result.colors["P"], "#fff3dc")
        with self.assertRaisesRegex(ValueError, "redefine"):
            px.face_patch(self.sheet, self.anchor, dict(plan, colors={"B": "#ffffff"}))

    def test_face_annotations_are_validated(self):
        path = self.root / "face.anchor.json"
        for faces in ("human", [{"complex": "yes"}], [dict(self.face, box=[0, 0, 2, 1])]):
            path.write_text(json.dumps(dict(self.anchor, faces=faces)), encoding="utf-8")
            with self.assertRaises(ValueError):
                px.load_anchor(path)

    def test_brows_nose_and_general_face_edits_are_rejected(self):
        for feature in (None, "brow", "nose", "face"):
            plan = copy.deepcopy(self.plan)
            plan["patches"][0]["feature"] = feature
            with self.assertRaisesRegex(ValueError, "eye or mouth"):
                px.face_patch(self.sheet, self.anchor, plan)

    def test_eye_patch_cannot_change_the_surrounding_face(self):
        plan = copy.deepcopy(self.plan)
        plan["patches"][0]["rows"][0] = "AAABAA"
        with self.assertRaisesRegex(ValueError, "outside the declared eye"):
            px.face_patch(self.sheet, self.anchor, plan)

    def test_mouth_patch_leaves_eyes_untouched(self):
        plan = {"source": self.sheet.name, "size": 32, "patches": [
            {"face": 0, "feature": "mouth", "box": [12, 20, 14, 20], "rows": ["BAB"]}]}
        result = px.face_patch(self.sheet, self.anchor, plan)
        self.assertEqual(result.rows[:20], self.sheet.rows[:20])
        self.assertEqual(result.rows[20][12:15], "BAB")

    def test_complex_face_requires_original_gaze_assessment(self):
        anchor = copy.deepcopy(self.anchor)
        del anchor["faces"][0]["gaze"]
        with self.assertRaisesRegex(ValueError, "original gaze"):
            px.face_patch(self.sheet, anchor, self.plan)

    def test_prompt_preserves_expression_species_and_intentional_occlusion(self):
        prompt = px.face_prompt(self.anchor, 64)
        self.assertIn(self.face["expression"], prompt)
        self.assertIn(self.face["gaze"], prompt)
        self.assertIn("Do not add or redraw eyebrows", prompt)
        self.assertIn("takes priority over increasing contrast", prompt)
        self.assertIn("species-appropriate", prompt)
        self.assertIn("already readable, preserve", prompt)
        self.assertIn("source boxes are not pixel-sheet coordinates", prompt)
        self.assertIn("No complex visible face", px.face_prompt({}, 64))

    def test_batch_only_attaches_face_review_when_needed(self):
        image = Image.new("RGBA", (64, 64))
        ImageDraw.Draw(image).rectangle((12, 12, 51, 51), fill="#d9a066")
        image.save(self.root / "portrait.png")
        apath = self.root / "portrait.anchor.json"
        for label, faces, status in (("object", [], None), ("clear", [dict(self.face, complex=False)], "preserve"),
                                     ("complex", [self.face], "needs-face-review")):
            apath.write_text(json.dumps(dict(self.anchor, faces=faces)), encoding="utf-8")
            out = self.root / label
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(px.batch(self.root, out, "none", [32]), 0)
            job = json.loads((out / "batch-report.json").read_text())["jobs"][0]
            if status is None:
                self.assertNotIn("face_review", job)
            else:
                self.assertEqual(job["face_review"][0]["status"], status)
            self.assertEqual(bool(list(out.glob("*.face-prompt.txt"))), label == "complex")
        self.assertEqual((self.root / "clear/portrait-32.png").read_bytes(), (self.root / "object/portrait-32.png").read_bytes())

    def test_face_command_writes_a_sibling_and_preserves_original(self):
        self.sheet.path.write_text(self.sheet.dump(), encoding="utf-8")
        source = self.sheet.path.read_bytes()
        apath, ppath = self.root / "anchor.json", self.root / "patch.json"
        apath.write_text(json.dumps(self.anchor), encoding="utf-8")
        ppath.write_text(json.dumps(self.plan), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(px.main(["face", str(self.sheet.path), "--anchor", str(apath), "--patch", str(ppath)]), 0)
        self.assertEqual(self.sheet.path.read_bytes(), source)
        self.assertTrue((self.root / "portrait-face.png").exists())


if __name__ == "__main__":
    unittest.main()
