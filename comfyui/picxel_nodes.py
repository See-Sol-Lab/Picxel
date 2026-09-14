"""ComfyUI nodes for Picxel -- a pipe in and a pipe out, nothing else.

"Picxel 导出" saves the images flowing through a ComfyUI graph as transparent PNGs into a folder
and writes the same job file the Picxel panel writes (~/.picxel/current-job.json), so the user
switches to the panel and tells the assistant to start. "Picxel 载入" reads finished pixel-art
PNGs back into the graph. No pixel-art algorithm lives here; Picxel itself is not imported.

Job-file schema mirrors scripts/panel.py `save_job`: keep the two in step."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

SIZES = (32, 64, 128)
BATCH_LIMIT = 20
JOB_FILE = Path.home() / ".picxel" / "current-job.json"
STATUS_NAME = "picxel.status.json"
FINISHED_DIR = "成品图"
SAFE_NAME = re.compile(r"[^\w\-]+", re.UNICODE)


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="microseconds")


# ---------------------------------------------------------------- tensors <-> Pillow, without requiring torch here

def _rows(tensor):
    """A [H,W,C] or [H,W] tensor as nested Python lists (numpy when available, else tolist)."""
    if hasattr(tensor, "cpu"):
        tensor = tensor.cpu()
    if hasattr(tensor, "numpy"):
        try:
            return tensor.numpy().tolist()
        except Exception:
            pass
    return tensor.tolist() if hasattr(tensor, "tolist") else tensor


def _batch(tensor):
    """Iterate a [B,...] tensor (or a list of frames)."""
    return list(tensor) if not hasattr(tensor, "shape") else [tensor[i] for i in range(int(tensor.shape[0]))]


def image_to_pil(image, mask=None) -> Image.Image:
    """ComfyUI IMAGE frame [H,W,3] in 0..1 (+ optional MASK [H,W], 1 = masked out) -> RGBA."""
    rows = _rows(image)
    h, w = len(rows), len(rows[0])
    rgb = bytes(int(max(0.0, min(1.0, c)) * 255 + 0.5) for row in rows for px in row for c in px[:3])
    out = Image.frombytes("RGB", (w, h), rgb).convert("RGBA")
    if mask is not None:
        mrows = _rows(mask)
        if len(mrows) != h or any(len(row) != w for row in mrows):
            raise ValueError("MASK 的宽高必须与 IMAGE 一致")
        alpha = bytes(int((1.0 - max(0.0, min(1.0, v))) * 255 + 0.5) for row in mrows for v in row)
        out.putalpha(Image.frombytes("L", (w, h), alpha))
    return out


def pil_to_image(img: Image.Image):
    """RGBA -> (IMAGE frame rows [H,W,3] in 0..1, MASK rows [H,W] with 1 = transparent)."""
    rgba = img.convert("RGBA")
    raw = rgba.tobytes()
    px = [raw[i:i + 4] for i in range(0, len(raw), 4)]
    w, h = rgba.size
    frame = [[[p[0] / 255, p[1] / 255, p[2] / 255] for p in px[y * w:(y + 1) * w]] for y in range(h)]
    mask = [[1.0 - p[3] / 255 for p in px[y * w:(y + 1) * w]] for y in range(h)]
    return frame, mask


def _tensor(nested):
    try:
        import torch
        return torch.tensor(nested, dtype=torch.float32)
    except ImportError:                                    # tests without ComfyUI: plain lists
        return nested


# ---------------------------------------------------------------- job file (same shape as the panel's)

def current_job_busy() -> str | None:
    """The note the panel would give: an unfinished job must be ended before a new one is written."""
    if not JOB_FILE.exists():
        return None
    try:
        job = json.loads(JOB_FILE.read_text(encoding="utf-8"))
        status = json.loads((Path(job["export"]) / STATUS_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        return None
    if status.get("state") in ("running", "asking"):
        return f"Picxel 面板上还有任务在进行（{job['export']}），先在面板结束它再导出"
    return None


def export_frames(frames, folder: Path, name: str, sizes: list[int], masks=None) -> dict:
    """Write frames as PNGs and point the Picxel panel at them. Returns the job written."""
    frames = list(frames)
    if not frames:
        raise ValueError("没有图片可导出")
    if len(frames) > BATCH_LIMIT:
        raise ValueError(f"一批最多 {BATCH_LIMIT} 张，这里有 {len(frames)} 张")
    sizes = [s for s in SIZES if s in sizes] or [64]
    name = SAFE_NAME.sub("-", name.strip()).strip("-") or "picxel"
    busy = current_job_busy()
    if busy:
        raise ValueError(busy)
    folder = Path(folder).expanduser()
    if folder.exists() and not folder.is_dir():
        raise ValueError(f"导出位置不是文件夹：{folder}")
    folder.mkdir(parents=True, exist_ok=True)
    masks = list(masks) if masks is not None else [None] * len(frames)
    if len(masks) not in (1, len(frames)):
        raise ValueError("遮罩数量要么 1 张，要么和图片一样多")
    files = []
    for i, frame in enumerate(frames):
        fname = f"{name}.png" if len(frames) == 1 else f"{name}-{i + 1:02d}.png"
        image_to_pil(frame, masks[i if len(masks) > 1 else 0]).save(folder / fname)
        files.append(fname)
    export = folder / "picxel-out"
    job = {"import": str(folder), "export": str(export), "mode": "single" if len(files) == 1 else "batch",
           "files": files, "sizes": sizes, "created": now()}
    export.mkdir(parents=True, exist_ok=True)
    (export / STATUS_NAME).write_text(json.dumps({"state": "waiting", "updated": now(), "note": ""}, indent=2) + "\n", encoding="utf-8")
    JOB_FILE.parent.mkdir(parents=True, exist_ok=True)
    JOB_FILE.write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return job


def finished_pngs(folder: Path, size: int, name: str = "") -> list[Path]:
    """`<stem>-<size>.png` files, preferring the panel's 成品图 folder when it exists."""
    folder = Path(folder).expanduser()
    candidates = [folder / FINISHED_DIR, folder, folder / "picxel-out" / FINISHED_DIR, folder / "picxel-out"]
    for base in candidates:
        if base.is_dir():
            found = sorted(p for p in base.glob(f"*-{size}.png") if "@" not in p.name and (not name or p.name.startswith(name)))
            if found:
                return found
    return []


# ---------------------------------------------------------------- the nodes

class PicxelExport:
    """Send images to Picxel: PNGs into a folder + the panel's job file."""
    CATEGORY = "Picxel"
    FUNCTION = "run"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("导入文件夹",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "folder": ("STRING", {"default": str(Path.home() / "Desktop" / "picxel-in"), "tooltip": "PNG 存到这里；Picxel 面板的导入位置就是它，导出位置是它下面的 picxel-out"}),
                "name": ("STRING", {"default": "asset", "tooltip": "文件名前缀；多张图自动加 -01、-02"}),
                "size_32": ("BOOLEAN", {"default": False}),
                "size_64": ("BOOLEAN", {"default": True}),
                "size_128": ("BOOLEAN", {"default": False}),
            },
            "optional": {"mask": ("MASK", {"tooltip": "可选：透明区域。没有就整张不透明，去背景交给 Picxel"})},
        }

    def run(self, images, folder, name, size_32, size_64, size_128, mask=None):
        sizes = [s for s, on in ((32, size_32), (64, size_64), (128, size_128)) if on]
        job = export_frames(_batch(images), Path(folder), name, sizes, _batch(mask) if mask is not None else None)
        return {"ui": {"text": [f"已交给 Picxel：{len(job['files'])} 张 → {job['import']}；打开面板，让 AI 开始画"]},
                "result": (job["import"],)}


class PicxelLoad:
    """Read finished Picxel PNGs of one size back into the graph."""
    CATEGORY = "Picxel"
    FUNCTION = "run"
    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("images", "mask", "文件名")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "folder": ("STRING", {"default": str(Path.home() / "Desktop" / "picxel-in"), "tooltip": "导出节点用过的文件夹，或它的 picxel-out / 成品图"}),
            "size": ([str(s) for s in SIZES], {"default": "64"}),
            "name": ("STRING", {"default": "", "tooltip": "只读这个前缀开头的文件；留空读全部"}),
        }}

    @classmethod
    def IS_CHANGED(cls, folder, size, name=""):
        return ",".join(f"{p.name}:{p.stat().st_mtime}" for p in finished_pngs(Path(folder), int(size), name))

    def run(self, folder, size, name=""):
        paths = finished_pngs(Path(folder), int(size), name)
        if not paths:
            raise ValueError(f"{folder} 里没有 {size}×{size} 的成品 PNG（Picxel 画完了吗？）")
        frames, masks = zip(*(pil_to_image(Image.open(p)) for p in paths))
        return (_tensor(list(frames)), _tensor(list(masks)), ", ".join(p.name for p in paths))


NODE_CLASS_MAPPINGS = {"PicxelExport": PicxelExport, "PicxelLoad": PicxelLoad}
NODE_DISPLAY_NAME_MAPPINGS = {"PicxelExport": "Picxel 导出（交给面板）", "PicxelLoad": "Picxel 载入（读回成品）"}
