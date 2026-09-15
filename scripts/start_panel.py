"""Prepare Picxel and return a ready local panel; no image generation is started."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import venv
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def running_panel(url: str) -> dict | None:
    try:
        with urlopen(url + "api/health", timeout=3) as response:
            info = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"The port is occupied by another service: {url}") from exc
    except URLError as exc:
        if isinstance(exc.reason, ConnectionRefusedError):
            return None
        raise RuntimeError(f"Cannot contact {url}: {exc.reason}") from exc
    except (ValueError, TimeoutError) as exc:
        raise RuntimeError(f"The service at {url} did not return Picxel health information") from exc
    if (not isinstance(info, dict) or info.get("app") != "Picxel" or not isinstance(info.get("root"), str)
            or Path(info.get("root", "")).resolve() != ROOT
            or not isinstance(info.get("python"), str) or not isinstance(info.get("pid"), int)):
        raise RuntimeError(f"The port belongs to another app or Picxel installation: {url}")
    return info


def prepare_python() -> str:
    if sys.version_info < (3, 10):
        raise RuntimeError("Picxel needs Python 3.10 or newer")
    if importlib.util.find_spec("PIL") is not None:
        return sys.executable
    # Install only into this checkout/skill, never into the user's global Python.
    environment = ROOT / ".venv"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(environment)
    probe = subprocess.run([str(python), "-c", "from PIL import Image"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode:
        subprocess.run([str(python), "-m", "pip", "install", "Pillow"], check=True, stdout=sys.stderr)
    return str(python)


def start_panel(port: int = 8770, open_browser: bool = True) -> dict:
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    url = f"http://127.0.0.1:{port}/"
    info = running_panel(url)
    reused = info is not None
    if not reused:
        python = prepare_python()
        logs = ROOT / "examples" / "out" / "panel"
        logs.mkdir(parents=True, exist_ok=True)
        error_log = logs / "stderr.log"
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {"start_new_session": True}
        with error_log.open("w", encoding="utf-8") as errors:
            process = subprocess.Popen(
                [python, str(ROOT / "scripts" / "picxel.py"), "panel", "--port", str(port), "--no-open"],
                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors,
                text=True, encoding="utf-8", **options)
        # The server prints this only after binding its port. No polling loop.
        with process.stdout:
            ready = process.stdout.readline()
        if not ready.startswith(f"Picxel panel: {url}"):
            process.wait()
            raise RuntimeError(f"Panel did not start. See {error_log}:\n" + error_log.read_text(encoding="utf-8")[-1500:])
        info = running_panel(url)
        if info is None:
            raise RuntimeError(f"Panel stopped during startup. See {error_log}")
    opened = webbrowser.open(url) if open_browser else False
    return {"url": url, "python": info["python"], "pid": info["pid"],
            "reused": reused, "browser_opened": opened}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--no-open", action="store_true", help="the assistant opens the returned URL in its host browser")
    args = parser.parse_args()
    try:
        print(json.dumps(start_panel(args.port, not args.no_open), ensure_ascii=True))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
