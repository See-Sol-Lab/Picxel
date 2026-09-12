"""Picxel panel -- a local page for the human: pick where the images come from and where the
assets go, watch one spinner while the assistant works in chat, then see the results as cards.

The panel never drives the assistant. It writes one job file the assistant reads
(`picxel job show`), and reads back the status file the assistant updates
(`picxel job start|done|stop`) plus whatever PNGs land in the export folder.
Standard library only: http.server for the page, tkinter for the native folder dialogs."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")          # notes may be Chinese; a cp936 console must not crash the command

SIZES = (32, 64, 128)
BATCH_LIMIT = 20
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
JOB_FILE = Path.home() / ".picxel" / "current-job.json"
STATUS_NAME = "picxel.status.json"
IDLE_SECONDS = 240          # no new file in the export folder for this long while "running" -> looks interrupted
PANEL_HTML = Path(__file__).with_name("panel.html")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- job + status files

def load_job() -> dict | None:
    if not JOB_FILE.exists():
        return None
    return json.loads(JOB_FILE.read_text(encoding="utf-8"))


def save_job(job: dict) -> dict:
    """Validate the panel's choices and write the job file the assistant will read."""
    problems = []
    src, dst = Path(job.get("import") or ""), Path(job.get("export") or "")
    if not src.is_dir():
        problems.append("import folder does not exist")
    if not str(dst):
        problems.append("export folder is empty")
    mode = job.get("mode")
    if mode not in ("single", "batch"):
        problems.append("mode must be single or batch")
    files = [f for f in job.get("files", []) if isinstance(f, str)]
    if src.is_dir() and not files:
        files = sorted(p.name for p in src.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if mode == "single":
        files = files[:1]
    if not files:
        problems.append("no images selected")
    if len(files) > BATCH_LIMIT:
        problems.append(f"a batch is at most {BATCH_LIMIT} images")
    sizes = [int(s) for s in job.get("sizes", [64]) if int(s) in SIZES] or [64]
    if problems:
        raise ValueError("; ".join(problems))
    clean = {
        "import": str(src), "export": str(dst), "mode": mode, "files": files, "sizes": sizes,
        "style_check": bool(job.get("style_check")) and mode == "batch",
        "parallel": bool(job.get("parallel")) and mode == "batch",
        "created": now(),
    }
    JOB_FILE.parent.mkdir(parents=True, exist_ok=True)
    JOB_FILE.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    dst.mkdir(parents=True, exist_ok=True)
    (dst / STATUS_NAME).write_text(json.dumps({"state": "waiting", "updated": now(), "note": ""}, indent=2) + "\n", encoding="utf-8")
    return clean


def status_path(export: Path) -> Path:
    return export / STATUS_NAME


def load_status(export: Path) -> dict:
    p = status_path(export)
    if not p.exists():
        return {"state": "waiting", "updated": None, "note": ""}
    return json.loads(p.read_text(encoding="utf-8"))


def set_status(export: Path, state: str, note: str = "") -> dict:
    if state not in ("waiting", "running", "done", "interrupted"):
        raise ValueError("state must be waiting, running, done or interrupted")
    export.mkdir(parents=True, exist_ok=True)
    current = load_status(export)
    status = {"state": state, "updated": now(), "note": note,
              "started": current.get("started") if state != "running" else now()}
    status_path(export).write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return status


def scan_results(job: dict) -> dict:
    """What actually exists in the export folder, grouped by asset name, plus the newest file time."""
    export = Path(job["export"])
    stems = [Path(f).stem for f in job["files"]]
    results, newest = {}, 0.0
    if export.is_dir():
        for p in export.iterdir():
            if p.suffix.lower() == ".png":
                newest = max(newest, p.stat().st_mtime)
        for stem in stems:
            sizes = {}
            for size in job["sizes"]:
                preview = export / f"{stem}-{size}@4x.png"
                if preview.exists():
                    sizes[str(size)] = f"/file?root=export&path={preview.name}"
            results[stem] = sizes
    return {"results": results, "newest": newest,
            "done": sum(1 for s in stems if results.get(s)), "total": len(stems)}


def state_payload() -> dict:
    job = load_job()
    if job is None:
        return {"job": None, "status": {"state": "waiting"}, "results": {}, "done": 0, "total": 0}
    status = load_status(Path(job["export"]))
    scan = scan_results(job)
    idle = None
    if status.get("state") == "running":
        last = scan["newest"]
        if not last and status.get("started"):
            last = datetime.fromisoformat(status["started"]).timestamp()
        idle = max(0, datetime.now().timestamp() - last) if last else 0
        if idle > IDLE_SECONDS:
            status = dict(status, looks_stalled=True)
    originals = {Path(f).stem: f"/file?root=import&path={f}" for f in job["files"]}
    return {"job": job, "status": status, "originals": originals, "idle": idle, **scan}


# ---------------------------------------------------------------- native dialogs / opening folders

def pick(kind: str) -> list[str]:
    """Open the OS file/folder dialog through tkinter and return the chosen paths ([] if cancelled)."""
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError:
        raise RuntimeError("tkinter is not available; type the path instead")
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        if kind == "dir":
            chosen = filedialog.askdirectory(title="选择文件夹")
            return [chosen] if chosen else []
        if kind == "file":
            chosen = filedialog.askopenfilename(title="选择一张图片", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
            return [chosen] if chosen else []
        chosen = filedialog.askopenfilenames(title=f"选择图片（最多 {BATCH_LIMIT} 张）", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        return list(chosen)
    finally:
        root.destroy()


def open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))                        # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


# ---------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):                         # keep the console quiet
        pass

    def _json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            body = PANEL_HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/api/state":
            self._json(state_payload())
        elif url.path == "/file":
            q = parse_qs(url.query)
            job = load_job()
            root = q.get("root", [""])[0]
            if job is None or root not in ("import", "export"):
                self.send_error(404); return
            base = Path(job[root]).resolve()
            target = (base / q.get("path", [""])[0]).resolve()
            if base not in target.parents or not target.is_file():
                self.send_error(404); return            # only files inside the two chosen folders
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png" if target.suffix == ".png" else "image/jpeg" if target.suffix in (".jpg", ".jpeg") else "image/webp")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

    def do_POST(self):
        url = urlparse(self.path)
        try:
            if url.path == "/api/pick":
                self._json({"paths": pick(self._body().get("kind", "dir"))})
            elif url.path == "/api/job":
                self._json({"job": save_job(self._body())})
            elif url.path == "/api/stop":
                job = load_job()
                if job is None:
                    raise ValueError("no job")
                self._json({"status": set_status(Path(job["export"]), "interrupted", "面板上手动结束等待")})
            elif url.path == "/api/open":
                job = load_job()
                if job is None:
                    raise ValueError("no job")
                open_folder(Path(job["export"]))
                self._json({"ok": True})
            else:
                self.send_error(404)
        except Exception as exc:                        # surfaced in the page, not in a traceback
            self._json({"error": str(exc)}, 400)


def serve(port: int, open_browser: bool) -> int:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Picxel panel: {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


# ---------------------------------------------------------------- `picxel job ...` for the assistant

def job_command(action: str, note: str) -> int:
    job = load_job()
    if action == "show":
        if job is None:
            print("no panel job; ask the user to set import/export in the panel, or take paths from chat")
            return 1
        print(json.dumps(job, indent=2, ensure_ascii=False))
        print(f"status: {load_status(Path(job['export']))['state']}")
        return 0
    if job is None:
        print("no panel job to update")
        return 1
    state = {"start": "running", "done": "done", "stop": "interrupted"}[action]
    status = set_status(Path(job["export"]), state, note)
    print(f"job {state}: {job['export']}" + (f" -- {note}" if note else ""))
    return 0
