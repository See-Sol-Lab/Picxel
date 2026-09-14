"""The ComfyUI bridge nodes, exercised with plain lists (no torch/numpy on the test machine)."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comfyui import picxel_nodes as nodes


def frame(w, h, rgb):
    return [[list(rgb)] * w for _ in range(h)]


class ComfyBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(nodes, "JOB_FILE", self.root / "job.json")
        patcher.start(); self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tensor_round_trip_with_mask(self):
        img = nodes.image_to_pil(frame(3, 2, (1.0, 0.0, 0.5)), [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
        self.assertEqual(img.size, (3, 2)); self.assertEqual(img.getpixel((0, 0)), (255, 0, 128, 255))
        self.assertEqual(img.getpixel((2, 0))[3], 0)                      # mask 1 -> transparent
        rgb, mask = nodes.pil_to_image(img)
        self.assertEqual(len(rgb), 2); self.assertEqual(len(rgb[0]), 3)
        self.assertAlmostEqual(rgb[0][0][0], 1.0); self.assertEqual(mask[0][2], 1.0); self.assertEqual(mask[0][0], 0.0)

    def test_mask_with_transposed_dimensions_is_not_silently_reshaped(self):
        with self.assertRaisesRegex(ValueError, "MASK"):
            nodes.image_to_pil(frame(3, 2, (1, 0, 0)), [[0, 1], [1, 0], [0, 0]])

    def test_export_writes_pngs_and_the_panel_job(self):
        folder = self.root / "in"
        job = nodes.export_frames([frame(4, 4, (0.2, 0.4, 0.6)), frame(4, 4, (0.9, 0.1, 0.1))], folder, "hero", [128, 32, 999])
        self.assertEqual(job["files"], ["hero-01.png", "hero-02.png"]); self.assertEqual(job["mode"], "batch")
        self.assertEqual(job["sizes"], [32, 128]); self.assertEqual(job["export"], str(folder / "picxel-out"))
        self.assertEqual(json.loads(nodes.JOB_FILE.read_text(encoding="utf-8"))["import"], str(folder))
        self.assertEqual(json.loads((folder / "picxel-out" / nodes.STATUS_NAME).read_text())["state"], "waiting")
        self.assertEqual(Image.open(folder / "hero-01.png").getpixel((0, 0)), (51, 102, 153, 255))
        single = nodes.export_frames([frame(2, 2, (0, 0, 0))], folder, "a b/c", [])
        self.assertEqual((single["files"], single["mode"], single["sizes"]), (["a-b-c.png"], "single", [64]))

    def test_export_refuses_a_running_panel_job_and_oversized_batches(self):
        folder = self.root / "in"
        nodes.export_frames([frame(2, 2, (0, 0, 0))], folder, "x", [64])
        (folder / "picxel-out" / nodes.STATUS_NAME).write_text(json.dumps({"state": "running"}))
        with self.assertRaisesRegex(ValueError, "还有任务在进行"):
            nodes.export_frames([frame(2, 2, (0, 0, 0))], folder, "y", [64])
        (folder / "picxel-out" / nodes.STATUS_NAME).write_text(json.dumps({"state": "done"}))
        with self.assertRaisesRegex(ValueError, "最多"):
            nodes.export_frames([frame(2, 2, (0, 0, 0))] * (nodes.BATCH_LIMIT + 1), folder, "y", [64])
        with self.assertRaises(ValueError):
            nodes.export_frames([], folder, "y", [64])

    def test_load_prefers_finished_folder_and_reports_missing(self):
        folder = self.root / "in"
        out = folder / "picxel-out"; (out / nodes.FINISHED_DIR).mkdir(parents=True)
        Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(out / "hero-64.png")
        Image.new("RGBA", (64, 64), (0, 255, 0, 0)).save(out / nodes.FINISHED_DIR / "hero-64.png")
        Image.new("RGBA", (256, 256)).save(out / nodes.FINISHED_DIR / "hero-64@4x.png")
        paths = nodes.finished_pngs(folder, 64)
        self.assertEqual([p.name for p in paths], ["hero-64.png"]); self.assertEqual(paths[0].parent.name, nodes.FINISHED_DIR)
        images, masks, names = nodes.PicxelLoad().run(str(folder), "64")
        self.assertEqual(names, "hero-64.png"); self.assertEqual(nodes._rows(images[0])[0][0], [0.0, 1.0, 0.0]); self.assertEqual(nodes._rows(masks[0])[0][0], 1.0)
        self.assertEqual(nodes.finished_pngs(folder, 32), [])
        with self.assertRaisesRegex(ValueError, "没有 32"):
            nodes.PicxelLoad().run(str(folder), "32")

    def test_node_contract(self):
        for cls in nodes.NODE_CLASS_MAPPINGS.values():
            self.assertTrue(callable(getattr(cls, cls.FUNCTION))); self.assertIn("required", cls.INPUT_TYPES())
        self.assertEqual(set(nodes.NODE_DISPLAY_NAME_MAPPINGS), set(nodes.NODE_CLASS_MAPPINGS))


if __name__ == "__main__":
    unittest.main()
