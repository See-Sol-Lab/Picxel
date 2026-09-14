"""The panel's job/status files and result scan -- no server, no dialogs."""
from pathlib import Path
import json
import io
import os
import zipfile
import sys
import tempfile
import unittest
import subprocess
import threading
import http.client
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import panel


class PanelFiles(unittest.TestCase):
    def test_reused_directory_never_exports_old_or_incomplete_results(self):
        settings = {"import": str(self.src), "export": str(self.dst), "mode": "batch", "files": ["a.png"], "sizes": [32, 64]}
        job = panel.save_job(settings)
        for name in ("a.concept.png", "a-64.png", "a-64@4x.png"):
            Image.new("RGBA", (64, 64)).save(self.dst / name)
            os.utime(self.dst / name, (1, 1))
        (self.dst / panel.REPORT_NAME).write_text(json.dumps({"jobs": [{"name": "a", "problems": ["previous error"]}]}))
        os.utime(self.dst / panel.REPORT_NAME, (1, 1))
        scan = panel.scan_results(job)
        self.assertEqual(scan["done"], 0)
        self.assertEqual(scan["results"]["a"]["errors"], [])
        self.assertEqual(panel.deliverable_images(job), [])
        # A new native PNG with a previous render's marker is not complete.
        Image.new("RGBA", (64, 64)).save(self.dst / "a-64.png")
        self.assertEqual(panel.scan_results(job)["results"]["a"]["sizes"], {})
        Image.new("RGBA", (256, 256)).save(self.dst / "a-64@4x.png")
        self.assertEqual(panel.scan_results(job)["done"], 0)  # still missing 32
        self.assertEqual([name for _, name in panel.deliverable_images(job)], ["a-64.png"])

    def test_running_settings_are_locked_and_invalid_paths_are_rejected(self):
        settings = {"import": str(self.src), "export": str(self.dst), "mode": "single", "files": ["a.png"]}
        for update in ({"export": ""}, {"files": ["../a.png"]}, {"files": ["notes.txt"]}, {"files": ["missing.png"]}):
            with self.assertRaises(ValueError):
                panel.save_job(dict(settings, **update))
        saved = panel.save_job(settings)
        panel.set_status(self.dst, "running")
        with self.assertRaisesRegex(ValueError, "当前任务"):
            panel.save_job(dict(settings, files=["b.jpg"]))
        self.assertEqual(panel.load_job(), saved)
        self.assertEqual(panel.load_status(self.dst)["state"], "running")
        started = panel.load_status(self.dst)["started"]
        self.assertEqual(panel.set_status(self.dst, "running")["started"], started)

    def test_http_origin_and_file_boundaries(self):
        filename = "fruit & cream #1.png"
        Image.new("RGB", (4, 4), "red").save(self.src / filename)
        panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "single", "files": [filename]})
        server = ThreadingHTTPServer(("127.0.0.1", 0), panel.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        def request(method, url, body=None, headers=None):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request(method, url, body, headers or {})
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()
        try:
            status, data = request("GET", "/api/state")
            self.assertEqual(status, 200)
            url = json.loads(data)["originals"][Path(filename).stem]
            self.assertEqual(url, "/file?" + urlencode({"root": "import", "path": filename}))
            self.assertEqual(request("GET", url), (200, (self.src / filename).read_bytes()))
            self.assertEqual(request("GET", "/file?root=import&path=notes.txt")[0], 404)
            self.assertEqual(request("GET", "/api/state", headers={"Host": "untrusted.example"})[0], 403)
            self.assertEqual(request("POST", "/api/clear", "{}", {"Content-Type": "application/json", "Origin": "https://untrusted.example"})[0], 403)
            self.assertEqual(request("POST", "/api/clear", "{}", {"Content-Type": "text/plain"})[0], 400)
            self.assertEqual(request("POST", "/api/clear", "[]", {"Content-Type": "application/json"})[0], 400)
            self.assertIsNotNone(panel.load_job())
            origin = f"http://127.0.0.1:{server.server_port}"
            self.assertEqual(request("POST", "/api/clear", "{}", {"Content-Type": "application/json", "Origin": origin})[0], 200)
            self.assertIsNone(panel.load_job())
        finally:
            server.shutdown(); server.server_close(); worker.join()

    def test_result_timestamps_change_after_refinement(self):
        job = panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "single", "files": ["a.png"], "sizes": [64]})
        for name, size in (("a.concept.png", 128), ("a-64.png", 64), ("a-64@4x.png", 256)):
            Image.new("RGBA", (size, size), "red").save(self.dst / name)
        before = panel.scan_results(job)["results"]["a"]
        self.assertEqual(before["concept_updated"], (self.dst / "a.concept.png").stat().st_mtime)
        changed = before["sizes"]["64"]["updated"] + 10
        os.utime(self.dst / "a-64.png", (changed, changed))
        self.assertEqual(panel.scan_results(job)["results"]["a"]["sizes"], {})
        os.utime(self.dst / "a-64@4x.png", (changed, changed))
        after = panel.scan_results(job)["results"]["a"]
        self.assertEqual(after["sizes"]["64"]["updated"], changed)
        self.assertEqual(after["concept_updated"], before["concept_updated"])

    def test_finished_folder_contains_only_concepts_and_completed_native_images(self):
        job = panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "single", "files": ["a.png"], "sizes": [32, 128]})
        Image.new("RGBA", (200, 200), (0, 255, 0, 128)).save(self.dst / "a.concept.png")
        Image.new("RGBA", (128, 128)).save(self.dst / "a-128.png")
        Image.new("RGBA", (512, 512)).save(self.dst / "a-128@4x.png")
        Image.new("RGBA", (32, 32)).save(self.dst / "a-32.png")  # not complete yet
        Image.new("RGBA", (64, 64)).save(self.dst / "a.pre.png")
        (self.dst / "a.pal").write_text("#000000")
        (self.dst / "a.prompt.txt").write_text("work instructions")
        folder = panel.export_images(job)
        self.assertEqual(folder.name, "成品图")
        self.assertEqual({p.name for p in folder.iterdir()}, {"a-效果图.png", "a-128.png"})
        self.assertEqual((folder / "a-效果图.png").read_bytes(), (self.dst / "a.concept.png").read_bytes())
        self.assertTrue((self.dst / "a.prompt.txt").exists())
        self.assertTrue((self.dst / "a.pre.png").exists())
        with zipfile.ZipFile(io.BytesIO(panel.download_images(job))) as archive:
            self.assertEqual(archive.namelist(), ["a-效果图.png", "a-128.png"])
            self.assertEqual(archive.read("a-效果图.png"), (self.dst / "a.concept.png").read_bytes())

    def test_done_automatically_collects_deliverables(self):
        panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "single", "files": ["a.png"], "sizes": [64]})
        Image.new("RGBA", (64, 64)).save(self.dst / "a-64.png")
        Image.new("RGBA", (256, 256)).save(self.dst / "a-64@4x.png")
        panel.set_status(self.dst, "done")
        self.assertEqual(panel.load_status(self.dst)["state"], "done")
        self.assertTrue((self.dst / panel.FINISHED_DIR / "a-64.png").exists())

    def test_concept_is_exposed_separately_from_original(self):
        job = panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "single", "files": ["a.png"], "sizes": [64]})
        self.assertIsNone(panel.scan_results(job)["results"]["a"]["concept"])
        Image.new("RGBA", (200, 200)).save(self.dst / "a.concept.png")
        self.assertEqual(panel.scan_results(job)["results"]["a"]["concept"], "/file?root=export&path=a.concept.png")

    def test_picker_worker_uses_main_thread_subprocess_and_unicode_paths(self):
        response = subprocess.CompletedProcess([], 0, '["C:/素材/瓶子.png"]', '')
        results = []
        with mock.patch.object(panel.subprocess, "run", return_value=response) as run:
            worker = threading.Thread(target=lambda: results.append(panel.pick("files")))
            worker.start()
            worker.join()
        self.assertEqual(results, [["C:/素材/瓶子.png"]])
        self.assertEqual(run.call_args.args[0][-2:], ["--pick", "files"])
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")

    def test_picker_cancel_and_error_are_reported(self):
        with mock.patch.object(panel.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, '[]', '')):
            self.assertEqual(panel.pick("dir"), [])
        with mock.patch.object(panel.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, '', 'dialog unavailable')):
            with self.assertRaisesRegex(RuntimeError, "dialog unavailable"):
                panel.pick("file")
        with self.assertRaises(ValueError):
            panel.pick("invalid")

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
        self.assertNotIn("style_check", job); self.assertNotIn("parallel", job)

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
        Image.new("RGBA", (64, 64)).save(self.dst / "a-64.png")
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
        Image.new("RGBA", (64, 64)).save(self.dst / "a-64.png")
        Image.new("RGBA", (256, 256)).save(self.dst / "a-64@4x.png")
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

    def test_new_job_reusing_old_outputs_resets_idle_clock(self):
        settings = {"import": str(self.src), "export": str(self.dst), "mode": "single", "files": ["a.png"], "sizes": [128]}
        current = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)
        with mock.patch.object(panel, "datetime", wraps=datetime) as clock:
            clock.now.return_value = current - timedelta(minutes=45)
            panel.save_job(settings)
            panel.set_status(self.dst, "running")
            old = self.dst / "previous.png"
            old.write_bytes(b"keep previous output")
            stamp = clock.now.return_value.timestamp()
            os.utime(old, (stamp, stamp))
            panel.clear_job()
            self.assertIsNone(panel.state_payload()["job"])
            clock.now.return_value = current
            panel.save_job(settings)
            waiting = panel.state_payload()
            self.assertIsNone(waiting["elapsed"])
            self.assertIsNone(waiting["idle"])
            self.assertNotIn("started", waiting["status"])
            panel.set_status(self.dst, "running")
            state = panel.state_payload()
            self.assertEqual(state["idle"], 0)
            self.assertEqual(state["elapsed"], 0)
            self.assertFalse(state["status"].get("looks_stalled", False))
            self.assertEqual(old.read_bytes(), b"keep previous output")

    def test_idle_warning_still_tracks_real_inactivity_and_new_output(self):
        current = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)
        with mock.patch.object(panel, "datetime", wraps=datetime) as clock:
            clock.now.return_value = current
            panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "batch", "sizes": [64]})
            panel.set_status(self.dst, "running")
            clock.now.return_value = current + timedelta(seconds=panel.IDLE_SECONDS + 1)
            self.assertTrue(panel.state_payload()["status"]["looks_stalled"])
            fresh = self.dst / "a.concept.png"
            fresh.write_bytes(b"new output")
            stamp = clock.now.return_value.timestamp() - 10
            os.utime(fresh, (stamp, stamp))
            state = panel.state_payload()
            self.assertEqual(state["idle"], 10)
            self.assertEqual(state["elapsed"], panel.IDLE_SECONDS + 1)
            self.assertFalse(state["status"].get("looks_stalled", False))

    def test_asking_and_resume_keep_the_original_timer(self):
        panel.save_job({"import": str(self.src), "export": str(self.dst), "mode": "batch"})
        panel.set_status(self.dst, "running")
        started = panel.set_status(self.dst, "asking", "Please clarify the object")["started"]
        self.assertEqual(panel.state_payload()["status"]["state"], "asking")
        self.assertEqual(panel.set_status(self.dst, "running")["started"], started)


if __name__ == "__main__":
    unittest.main()
