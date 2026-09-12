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
        self.assertIn("64", scan["results"]["a"]); self.assertEqual(scan["results"]["b"], {})
        status = panel.set_status(self.dst, "interrupted", "quota")
        self.assertEqual(status["state"], "interrupted")
        self.assertEqual(panel.load_status(self.dst)["note"], "quota")
        with self.assertRaises(ValueError):
            panel.set_status(self.dst, "flying")


if __name__ == "__main__":
    unittest.main()
