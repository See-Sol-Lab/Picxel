"""Style decisions here are test fixtures, not an automated visual classifier."""
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


class BatchStyleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "out"
        self.review_path = self.root / "batch.style.json"
        for name in ("potion", "horse", "anime"):
            self.add_asset(name)

    def add_asset(self, name):
        anchor = {"subject": name, "size": 32, "kind": "item", "keep": [f"{name} silhouette", "identifying colors"]}
        (self.root / f"{name}.anchor.json").write_text(json.dumps(anchor), encoding="utf-8")
        self.save_image(self.root / f"{name}.png")

    def save_image(self, path, color="red"):
        image = Image.new("RGBA", (64, 64), "white")
        ImageDraw.Draw(image).rectangle((12, 12, 51, 51), fill=color)
        image.save(path)

    def run_batch(self, provider="codex", concepts=None):
        with contextlib.redirect_stdout(io.StringIO()):
            code = px.batch(self.root, self.out, provider, [32], concepts)
        report = json.loads((self.out / "batch-report.json").read_text(encoding="utf-8"))
        return code, {job["name"]: job for job in report["jobs"]}

    def review(self, choice=None, consistent=False):
        self.run_batch()
        data = json.loads(self.review_path.read_text(encoding="utf-8"))
        data["profile"] = "Grounded fantasy, restrained saturation, crisp outlines, broad material shading."
        data["references"] = ["potion", "horse"]
        for name, item in data["assets"].items():
            item["match"] = consistent or name != "anime"
            item["reason"] = "Compatible material shading and outline treatment." if item["match"] else "Pastel anime rendering and soft decorative highlights differ from the batch."
            item["choice"] = None if item["match"] else choice
        self.review_path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def test_unreviewed_batch_prepares_assistant_review_before_generation(self):
        code, jobs = self.run_batch()
        self.assertEqual(code, 2)
        self.assertEqual({j["status"] for j in jobs.values()}, {"needs-style-review"})
        self.assertFalse(list(self.out.glob("*.prompt.txt")))
        self.assertFalse(list(self.out.glob("*.pre.png")))
        draft = json.loads(self.review_path.read_text())
        self.assertTrue(all(a["match"] is None and a["choice"] is None for a in draft["assets"].values()))
        self.assertTrue(all(len(a["sha256"]) == 64 for a in draft["assets"].values()))

    def test_only_outlier_gets_user_question_and_no_prompt(self):
        self.review()
        code, jobs = self.run_batch()
        self.assertEqual(code, 2)
        self.assertEqual(jobs["anime"]["status"], "needs-style-choice")
        self.assertEqual([c["value"] for c in jobs["anime"]["choices"]], ["original", "unify"])
        self.assertIn("Pastel anime", jobs["anime"]["question"])
        self.assertFalse((self.out / "anime.prompt.txt").exists())
        self.assertNotIn("question", jobs["potion"])
        self.assertEqual(jobs["potion"]["status"], "needs-concept")

    def test_original_choice_preserves_exact_single_image_prompt(self):
        self.review("original")
        _, jobs = self.run_batch()
        anchor = px.load_anchor(self.root / "anime.anchor.json")
        self.assertEqual((self.out / "anime.prompt.txt").read_text(), px.concept_prompt(anchor))
        self.assertEqual(jobs["anime"]["concept_file"], "anime.png")
        self.assertNotIn("style_references", jobs["anime"])

    def test_unification_prompt_changes_style_not_subject(self):
        self.review("unify")
        _, jobs = self.run_batch()
        prompt = (self.out / "anime.prompt.txt").read_text()
        self.assertIn("Restyle this outlier", prompt)
        self.assertIn("Grounded fantasy", prompt)
        self.assertIn("anime silhouette", prompt)
        self.assertIn("identifying colors", prompt)
        self.assertIn("Do not copy another asset's subject", prompt)
        self.assertEqual(jobs["anime"]["style_references"], ["potion", "horse"])
        self.assertEqual(jobs["anime"]["concept_file"], "anime.unified.png")

    def test_reference_order_has_no_circular_image_dependency(self):
        self.review("unify")
        _, jobs = self.run_batch()
        self.assertEqual(jobs["potion"]["style_references"], [])
        self.assertEqual(jobs["horse"]["style_references"], ["potion"])
        self.assertIn("Establish the batch's baseline", (self.out / "potion.prompt.txt").read_text())

    def test_consistent_batch_needs_no_user_choice(self):
        self.review(consistent=True)
        code, jobs = self.run_batch(provider="none")
        self.assertEqual(code, 0)
        self.assertTrue(all(j["status"] == "base-ready" for j in jobs.values()))
        self.assertTrue(all("question" not in j for j in jobs.values()))

    def test_none_provider_cannot_fake_unification_with_original_png(self):
        self.review("unify")
        concepts = self.root / "concepts"
        concepts.mkdir()
        self.save_image(concepts / "anime.png")
        code, jobs = self.run_batch(provider="none", concepts=concepts)
        self.assertEqual(code, 2)
        self.assertEqual(jobs["anime"]["status"], "needs-concept")
        self.assertFalse((self.out / "anime-32.png").exists())
        self.save_image(concepts / "anime.unified.png", "green")
        code, jobs = self.run_batch(provider="none", concepts=concepts)
        self.assertEqual(code, 0)
        self.assertEqual(jobs["anime"]["status"], "base-ready")
        self.assertIn("#008000", px.load(self.out / "anime-32.pxg").colors.values())

    def test_choice_is_reused_for_unchanged_batch(self):
        self.review("original")
        before = self.review_path.read_bytes()
        for _ in range(2):
            _, jobs = self.run_batch()
            self.assertEqual(jobs["anime"]["style"]["mode"], "original")
            self.assertNotIn("question", jobs["anime"])
        self.assertEqual(self.review_path.read_bytes(), before)

    def test_changed_image_invalidates_assessment_without_erasing_choices(self):
        self.review("unify")
        before = self.review_path.read_bytes()
        self.save_image(self.root / "anime.png", "blue")
        code, jobs = self.run_batch()
        self.assertEqual(code, 2)
        self.assertEqual({j["status"] for j in jobs.values()}, {"needs-style-review"})
        self.assertIn("changed", jobs["anime"]["problems"][0])
        self.assertEqual(self.review_path.read_bytes(), before)

    def test_changed_membership_needs_new_review(self):
        self.review("original")
        self.add_asset("flower")
        code, jobs = self.run_batch()
        self.assertEqual(code, 2)
        self.assertTrue(all(j["status"] == "needs-style-review" for j in jobs.values()))

    def test_single_image_ignores_batch_review(self):
        self.review()
        for name in ("potion", "horse"):
            (self.root / f"{name}.anchor.json").unlink()
            (self.root / f"{name}.png").unlink()
        _, jobs = self.run_batch()
        self.assertEqual(jobs["anime"]["status"], "needs-concept")
        self.assertNotIn("style", jobs["anime"])
        self.assertEqual((self.out / "anime.prompt.txt").read_text(), px.concept_prompt(px.load_anchor(self.root / "anime.anchor.json")))

    def test_unknown_style_reference_fails_clearly(self):
        data = self.review("unify")
        data["references"] = ["missing"]
        self.review_path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "references"):
            self.run_batch()


if __name__ == "__main__":
    unittest.main()
