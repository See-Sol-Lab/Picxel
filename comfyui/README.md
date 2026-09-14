# Picxel × ComfyUI

两个节点，只做进出口，像素画全部在 Picxel 里完成。

## 装

把这个 `comfyui` 文件夹复制（或软链）到 `ComfyUI/custom_nodes/picxel/`，重启 ComfyUI。只依赖 Pillow，ComfyUI 自带。

## 用

**Picxel 导出（交给面板）** — 右键 → Picxel。接上 IMAGE（可以是一批，最多 20 张），填一个文件夹和文件名前缀，勾要的尺寸（32 / 64 / 128）。运行后：

- 图片存成透明底 PNG 到那个文件夹（有 MASK 就当透明区域，没有就整张不透明，去背景交给 Picxel）；
- 写 `~/.picxel/current-job.json`，和面板上"选择图片"写的是同一份；
- 打开 Picxel 面板，图已经选好，去对话里让 AI 开始画。

面板上有任务还在进行时节点会拒绝，先在面板结束它。

**Picxel 载入（读回成品）** — 填同一个文件夹和尺寸，把画好的 `<名>-<尺寸>.png` 读回 IMAGE + MASK，接着在 ComfyUI 里放大、拼图、存盘。优先读 `成品图` 文件夹。

节点不 import Picxel、不跑任何算法；任务文件格式跟 `scripts/panel.py` 的 `save_job` 保持一致。

代码采用 [GPL-3.0-only](LICENSE)。Copyright © 2026 See-Sol-Lab contributors.
