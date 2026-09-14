# Picxel

给 Claude Code / Codex 使用的像素游戏素材工作流。助手负责看图、概括形状和修画；本地 Python 负责色板、像素网格、校验和批量打包。默认路径不需要 API key，也不启动额外服务。

- 32×32 / 64×64 / 128×128，单张最多 16 色，透明 PNG。
- 32 适合简洁物品，64 适合常规素材，128 用于更丰富的轮廓与细节。16×16 已退出生成和校验规格；历史对比图片保留作记录。
- 可编辑 `.pxg` 文本网格、原尺寸 PNG、4× 预览、精灵表 PNG + JSON、自包含 HTML 总览。
- 简单物品可以用绘图指令直接画；复杂参考图由当前助手可用的生图工具先出效果图，再变成严格网格。
- 单张沿用原图风格。批量先由助手看图鉴定，明显异类才询问“保留原图风格 / 统一画风”；选统一后参照同批已确定的效果图画风，保留原主体与关键特征。
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
# 画风鉴定默认关闭；加 --style-check（面板上是一个勾选框）时，多图首次会生成 batch.style.json 并等待助手完成风格鉴定。
# 一致则直接继续；明显异类由用户选择保留原风格或统一。

# 助手生图路线：准备提示词，再由当前助手生成 concepts/<name>.png
python scripts/picxel.py batch examples/ref -o examples/out/assisted --provider codex --sizes 64
# 风格检查与必要的用户选择完成后，needs-concept 表示等待效果图。
python scripts/picxel.py batch examples/ref -o examples/out/assisted --provider codex --concept-dir concepts --sizes 64

# 助手看图、修画、验收后打包
python scripts/picxel.py sheet examples/out/assisted -o examples/out/assisted/dist
python -m unittest discover -s tests -v
```

`provider` 是效果图来源：`none` 用马赛克底稿；`codex` / `claude` / `api` 读取助手准备的 PNG。它们不在 Python 内启动另一份助手或付费 API。原生生图是否可用、额度如何，取决于当前宿主；只有编程能力时也能走绘图指令路线。

效果图优先使用真实透明通道。模型使用主体中不存在的纯色底时，可指定 `--concept-background 'key:#ff00ff'`：除去底外，会在已去除区域旁的一源像素范围内清理高饱和、同色相的残色。此规则仅用于显式技术底色，保留较暗轮廓及内部近似色；主体边缘若也使用该底色，应换底色或使用真实透明图。

批量报告区分 `needs-style-review`、`needs-style-choice`、`needs-concept`、`base-ready`、`check-failed`、`failed`；自动底稿视觉验收为 `pending`。退出码：0 全部底稿就绪，1 存在失败，2 等待风格鉴定、用户选择或效果图。详情见 [批量风格流程](references/batch-style.md)。

风格鉴定由当前助手的视觉能力完成，Python 负责检查单和选择分支。`batch.style.json` 保留已选决定；输入图片更换后会要求重新看图。统一后的结果使用 `<name>.unified.png`，避免误用原风格旧图。面板按钮、打开文件夹和进度动画尚不在本轮功能中。

## 人类面板

```bash
python scripts/picxel.py panel        # 打开 http://127.0.0.1:8770
```

给不想看命令行的人：选图片（单张选一张，批量多选）、导出位置、单张 / 批量（最多 20 张）、尺寸，批量还有两个勾选框——画风鉴定（导入前 AI 先看一遍画风，差得远的问你要不要统一）和子智能体并行（快、贵、不够精确，默认逐张画）。面板上没有生图按钮：位置选好后，去对话里让 AI 开始。AI 画的时候面板只转一个圈并计时；AI 停下来等你决定（比如选画风）时不转圈，改成"AI 在等你决定"并把问题摆出来；画完一排排显示原图和各尺寸成品，"生成成功 N / M，可打开成品图查看"。中途断了（用量、网络）就如实显示已完成的几张和"生成中断"。结束后显示用时和结束时刻；没画出来的尺寸会说明为什么（AI 没画到、底稿没过校验、等你选画风……），每张下面折叠着 `batch-report.json` 里的校验提示，面部待修的打标。结果按「效果图 → 128 → 64 → 32」排列为等大的正方形卡片，点任意一张进对比层，仍按此顺序展示，1 / 2 / 4 / 8 倍切换，左右键换素材，Esc 关。勾了画风鉴定时，AI 判定为离群的图会在面板上方列出理由和"保留原图风格 / 统一画风"两个按钮，点一下就写进 `batch.style.json`（也可以在对话里答）。「新任务」清空当前设置；导出文件夹被删了会直接说。面板从不驱动 AI，只写一份任务文件（`~/.picxel/current-job.json`）、读导出文件夹里的状态、报告和成品；按钮弹的是系统自带的文件对话框。窄窗口自动上下排；固定深色。

任务结束时自动把去底效果图和已完成尺寸的原尺寸 PNG 整理到 `picxel-out/成品图/`。该文件夹只放交付图片；图纸、提示词和 4 倍工作预览继续保留在工作目录。面板可逐张下载，也可「下载全部图片」获得只含本次图片的 ZIP；「打开成品图」直接打开这个图片文件夹。原始参考图通过「查看原图」链接查看。

单张模式提供制作台：等待时显示原图与阶段提示，效果图就绪后并排展示，像素成品就绪时播放约 5 秒的色块显现演示。可「直接看成品」或「重播绘制演示」，下载随成品就绪开放；修画后的 PNG 会按文件更新时间刷新。演示使用已有成品像素，不代表模型内部落笔顺序，也不增加模型调用或延迟导出。系统开启减少动态效果时直接显示成品。批量模式继续使用转圈和计时。

## 更快地处理与返工

每张效果图的解码结果和色板在各尺寸间复用。`batch` 自动生成 `review-*.png`，每页最多四个素材，按效果图、尺寸降序展示，并同时保留放大图和原尺寸图。助手可一次查看整批结果，问题区域再放大；修画后运行 `review work` 刷新总览即可，无需重新跑 `batch`。面板任务验收后直接 `job done` 导出成品，精灵表和 HTML 按需打包。

已有效果图时跳过马赛克重建。`batch --only hero potion` 只处理指定素材，并继续使用整批风格检查单；其他输出保持原样，报告的 `selected` 标明本次处理范围。建议返工输出到单独目录，再选择最终稿打包。

`show file.pxg` 默认输出尺寸和色板摘要；局部编辑用 `--box x0,y0,x1,y1`，确实要查看完整网格才加 `--full`。助手按需读取提示文件、先看整体预览再放大问题区域，同一素材的效果图用于所有请求尺寸，通过验收的素材无需反复修改。

完整规程见 [SKILL.md](SKILL.md)，格式见 [SPEC.md](SPEC.md)。`examples/ref/base/` 保留早期输出，便于比较。
