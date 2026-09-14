# Picxel

基于GPT生图模型的像素画生成算法，让模型理解原图、重新画出神似的素材。
该项目并非只是处理一个图片，让图片看起来像是像素画但不能用。而是真正想要满足从海量现实图片中，绘制新素材的独立游戏开发者的需求。
因为思路不同，所以不算重复造轮子。

模型负责看图、概括形状和修画；本地 Python 负责色板、像素网格、校验和批量打包。默认路径不需要 API key，但必须由codex启动。

- 32×32 / 64×64 / 128×128，单张最多 16 色，透明 PNG。
- 32 适合简洁物品，64 适合常规素材，128 用于更丰富的轮廓与细节。16×16 已退出生成和校验规格；历史对比图片保留作记录。
- 可编辑 `.pxg` 文本网格、原尺寸 PNG、4× 预览、精灵表 PNG + JSON、自包含 HTML 总览。
- 简单物品可以用绘图指令直接画；复杂参考图由当前助手可用的生图工具先出效果图，再变成严格网格。
- 素材逐张生成，画风是否适用由用户查看成品判断，不自动鉴定或统一画风。
- 人物、动物可附加面部检查：清晰的面部保留；复杂面部在像素化后只检查并按需修画眼睛和嘴巴，原图视线方向、眼仁与眼白位置优先；眉毛、鼻子和其他区域保持原样。普通物品跳过。详见 [面部规程](references/faces.md)。
- 自动底稿仍需看图验收，不能保证任意照片一键变成可交付像素画。

## 安装

需要 Python 3.10+ 与 Pillow：`python -m pip install pillow`。

```bash
git clone https://github.com/See-Sol-Lab/Picxel.git ~/.claude/skills/picxel
# Codex 用户将同一目录放到自己的 skills 目录，读取 SKILL.md。
```

## 使用

在安装目录运行。参考图配一份同名 `<name>.anchor.json`，格式见 [锚定单](references/anchor.md)。

```bash
# 完全本地的自动底稿
python scripts/picxel.py batch examples/ref -o examples/out/local-32plus --sizes 128,64,32

# 助手生图路线：准备提示词，再由当前助手生成 concepts/<name>.png
python scripts/picxel.py batch examples/ref -o examples/out/assisted --provider codex --sizes 64
# needs-concept 表示等待助手生成效果图。
python scripts/picxel.py batch examples/ref -o examples/out/assisted --provider codex --concept-dir concepts --sizes 64

# 助手看图、修画、验收后打包
python scripts/picxel.py sheet examples/out/assisted -o examples/out/assisted/dist
python -m unittest discover -s tests -v
```

`provider` 是效果图来源：`none` 用马赛克底稿；`codex` / `claude` / `api` 读取助手准备的 PNG。它们不在 Python 内启动另一份助手或付费 API。原生生图是否可用、额度如何，取决于当前宿主；只有编程能力时也能走绘图指令路线。

效果图优先使用真实透明通道。模型使用主体中不存在的纯色底时，可指定 `--concept-background 'key:#ff00ff'`：除去底外，会在已去除区域旁的一源像素范围内清理高饱和、同色相的残色。此规则仅用于显式技术底色，保留较暗轮廓及内部近似色；主体边缘若也使用该底色，应换底色或使用真实透明图。

批量报告区分 `needs-concept`、`base-ready`、`check-failed`、`failed`；自动底稿视觉验收为 `pending`。退出码：0 全部底稿就绪，1 存在失败，2 等待效果图。

## 人类面板

```bash
python scripts/picxel.py panel        # 打开 http://127.0.0.1:8770
```

在面板选择图片、导出位置、单张 / 批量（最多 20 张）和尺寸，然后在对话里让 AI 开始。侧栏的提示框和「新任务」紧接在尺寸选择之后。素材逐张生成，画风由用户自行判断。

批量生成时显示转圈与计时；助手需要澄清时显示问题并等待对话回复。结果按「效果图 → 128 → 64 → 32」排列为等大的正方形卡片，点卡片进入对比层，支持 1 / 2 / 4 / 8 倍、左右键切换素材与 Esc 关闭。缺失尺寸、底稿失败和面部待修状态如实展示；校验里的"孤立像素"一类提示是给助手看的，留在 `batch-report.json`，不上面板。结束后显示耗时及完成时刻，中断则展示已有结果。

面板不启动助手，只保存 `~/.picxel/current-job.json`、读取状态和产物。「新任务」清空设置，已有成品保留。导出目录不存在时直接提示；文件选择使用系统对话框。窄窗口自动上下排列。

生成中锁定当前设置。重新选图后，之前的成品保留在磁盘，但不计入新任务的完成数量；原尺寸 PNG 和放大预览都写完才算一个尺寸就绪。全部请求尺寸就绪后，该素材才计为完成。

任务结束时自动把去底效果图和已完成尺寸的原尺寸 PNG 整理到 `picxel-out/成品图/`。该文件夹只放交付图片；图纸、提示词和 4 倍工作预览继续保留在工作目录。一切都在本机，面板不提供下载；「打开成品图」直接打开这个图片文件夹。原始参考图通过「查看原图」链接查看。

批量选图可一次多选，也可用「继续添加图片」分次追加，同一图片自动去重，最多 20 张。当前一批使用同一个素材文件夹；选到其他目录或超过上限时会提示并保留已选列表。单张模式重新选图仍替换原来的图片。

单张模式提供制作台：等待时显示原图与阶段提示，效果图就绪后并排展示，像素成品就绪时播放约 5 秒的色块显现演示。可「直接看成品」或「重播绘制演示」；修画后的 PNG 会按文件更新时间刷新。演示使用已有成品像素，不代表模型内部落笔顺序，也不增加模型调用或延迟导出。系统开启减少动态效果时直接显示成品。批量模式继续使用转圈和计时。

## ComfyUI 接口

`comfyui/` 是一个独立的 ComfyUI 自定义节点包，只做进出口：「Picxel 导出」把图里流过的 IMAGE 存成透明底 PNG 并写面板同格式的任务文件，用户切到面板让 AI 开始；「Picxel 载入」把画好的 `<名>-<尺寸>.png` 读回 IMAGE + MASK。不 import Picxel、不跑算法。装法和用法见 [comfyui/README.md](comfyui/README.md)。

## 更快地处理与返工

每张效果图的解码结果和色板在各尺寸间复用。`batch` 自动生成 `review-*.png`，每页最多四个素材，按效果图、尺寸降序展示，并同时保留放大图和原尺寸图。助手可一次查看整批结果，问题区域再放大；修画后运行 `review work` 刷新总览即可，无需重新跑 `batch`。面板任务验收后直接 `job done` 导出成品，精灵表和 HTML 按需打包。

已有效果图时跳过马赛克重建。`batch --only hero potion` 只处理指定素材；其他输出保持原样，报告的 `selected` 标明本次处理范围。建议返工输出到单独目录，再选择最终稿打包。

`show file.pxg` 默认输出尺寸和色板摘要；局部编辑用 `--box x0,y0,x1,y1`，确实要查看完整网格才加 `--full`。助手按需读取提示文件、先看整体预览再放大问题区域，同一素材的效果图用于所有请求尺寸，通过验收的素材无需反复修改。

完整规程见 [SKILL.md](SKILL.md)，格式见 [SPEC.md](SPEC.md)。`examples/ref/` 提供演示参考图。

维护者运行 `python -m unittest discover -s tests -v` 检查 Python 流程；选图交互逻辑另用 Node.js 运行 `node --test tests/test_panel_selection.cjs`。
