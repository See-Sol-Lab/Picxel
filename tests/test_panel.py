"""The panel's job/status files and result scan -- no server, no dialogs."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import panel


class PanelFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.src, self.dst = root / "in", root / "out"
        self.src.mkdir()
        for name in ("a.png", "b.jpg", "notes.txt"):
            (self.src / name).write_bytes(b"x")
        self.job_file = root / "job.json"
        patcher = mock.patch.object(panel, "JOB_FILE", self.job_file)
        patcher.start(); self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_folder_import_lists_images_only_and_writes_waiting_status(self):
        job = panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "batch", "sizes": [64, 32]})
        self.assertEqual(job["files"], ["a.png", "b.jpg"])
        self.assertEqual(json.loads(self.job_file.read_text(encoding="utf-8"))["sizes"], [64, 32])
        self.assertEqual(panel.load_status(self.dst)["state"], "waiting")

    def test_single_mode_keeps_one_file_and_drops_batch_only_flags(self):
        job = panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "single",
                              "files": ["b.jpg", "a.png"], "style_check": True, "parallel": True})
        self.assertEqual(job["files"], ["b.jpg"])
        self.assertFalse(job["style_check"]); self.assertFalse(job["parallel"])

    def test_batch_limit_and_bad_input_are_refused(self):
        too_many = [f"{i}.png" for i in range(panel.BATCH_LIMIT + 1)]
        with self.assertRaises(ValueError):
            panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "batch", "files": too_many})
        with self.assertRaises(ValueError):
            panel.save_job({"import": str(self.src / "missing"), "export": str(self.dst), "mode": "batch"})
        self.assertFalse(self.job_file.exists())

    def test_status_transitions_and_result_scan(self):
        job = panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "batch", "sizes": [64]})
        panel.set_status(self.dst, "running")
        self.assertIsNotNone(panel.load_status(self.dst)["started"])
        Image.new("RGBA", (256, 256)).save(self.dst / "a-64@4x.png")     # only asset a finished
        scan = panel.scan_results(job)
        self.assertEqual((scan["done"], scan["total"]), (1, 2))
        self.assertIn("64", scan["results"]["a"]["sizes"]); self.assertEqual(scan["results"]["b"]["sizes"], {})
        self.assertEqual(scan["results"]["b"]["missing"], "AI 还没画到这张")     # no batch report yet
        status = panel.set_status(self.dst, "interrupted", "quota")
        self.assertEqual(status["state"], "interrupted")
        self.assertIsNotNone(status["finished"])
        self.assertEqual(panel.load_status(self.dst)["note"], "quota")
        self.assertIsNotNone(panel.state_payload()["elapsed"])
        with self.assertRaises(ValueError):
            panel.set_status(self.dst, "flying")

    def test_missing_reason_comes_from_the_batch_report(self):
        job = panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "batch", "sizes": [64]})
        (self.dst / panel.REPORT_NAME).write_text(json.dumps({"jobs": [
            {"name": "a", "status": "base-ready", "problems": ["64: (warn) 5 isolated pixels"],
             "face_review": [{"sheet": "a-64.pxg", "status": "needs-face-review"}]},
            {"name": "b", "status": "check-failed", "problems": ["64: too many colors"]}]}), encoding="utf-8")
        Image.new("RGBA", (256, 256)).save(self.dst / "a-64@4x.png")
        Image.new("RGBA", (64, 64)).save(self.dst / "a-64.png")
        r = panel.scan_results(job)["results"]
        self.assertEqual(r["a"]["sizes"]["64"]["png"], "/file?root=export&path=a-64.png")   # native PNG for crisp zoom
        self.assertEqual(r["a"]["warnings"], ["64: 5 isolated pixels"]); self.assertEqual(r["a"]["faces"], ["a-64.pxg"])
        self.assertEqual(r["b"]["missing"], "底稿没过校验：64: too many colors")

    def test_clear_job_and_missing_export_folder(self):
        panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "batch"})
        import shutil; shutil.rmtree(self.dst)
        self.assertTrue(panel.state_payload()["export_missing"])
        panel.clear_job()
        self.assertIsNone(panel.load_job()); self.assertIsNone(panel.state_payload()["job"])
        panel.clear_job()                                                       # idempotent

    def test_style_choice_is_written_only_for_outliers(self):
        job = panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "batch", "style_check": True})
        stems = ["a", "b"]
        self.assertEqual(panel.style_questions(self.src, stems), [])           # no review file yet
        review = {"profile": "x", "references": ["a"], "assets": {
            "a": {"file": "a.png", "match": True, "reason": "fits", "choice": None},
            "b": {"file": "b.jpg", "match": False, "reason": "pastel", "choice": None}}}
        (self.src / panel.STYLE_NAME).write_text(json.dumps(review), encoding="utf-8")
        self.assertEqual(panel.style_questions(self.src, stems), [{"name": "b", "reason": "pastel", "choice": None}])
        self.assertEqual(panel.state_payload()["style"][0]["name"], "b")
        panel.set_style_choice(self.src, "b", "unify")
        self.assertEqual(json.loads((self.src / panel.STYLE_NAME).read_text(encoding="utf-8"))["assets"]["b"]["choice"], "unify")
        for name, choice in (("a", "unify"), ("b", "maybe"), ("zzz", "unify")):
            with self.assertRaises(ValueError):
                panel.set_style_choice(self.src, name, choice)


if __name__ == "__main__":
    unittest.main()
