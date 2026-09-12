# Picxel

给 Claude Code / Codex 使用的像素游戏素材工作流。助手负责看图、概括形状和修画；本地 Python 负责色板、像素网格、校验和批量打包。默认路径不需要 API key，也不启动额外服务。

- 32×32 / 64×64 / 128×128，单张最多 16 色，透明 PNG。
- 32 适合简洁物品，64 适合常规素材，128 用于更丰富的轮廓与细节。16×16 已退出生成和校验规格；历史对比图片保留作记录。
- 可编辑 `.pxg` 文本网格、原尺寸 PNG、4× 预览、精灵表 PNG + JSON、自包含 HTML 总览。
- 简单物品可以用绘图指令直接画；复杂参考图由当前助手可用的生图工具先出效果图，再变成严格网格。
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
# 退出码 2 = needs-concept，助手需要生成效果图。
python scripts/picxel.py batch examples/ref -o examples/out/assisted --provider codex --concept-dir concepts --sizes 64

# 助手看图、修画、验收后打包
python scripts/picxel.py sheet examples/out/assisted -o examples/out/assisted/dist
python -m unittest discover -s tests -v
```

`provider` 是效果图来源：`none` 用马赛克底稿；`codex` / `claude` / `api` 读取助手准备的 PNG。它们不在 Python 内启动另一份助手或付费 API。原生生图是否可用、额度如何，取决于当前宿主；只有编程能力时也能走绘图指令路线。

批量报告区分 `needs-concept`、`base-ready`、`check-failed`、`failed`；自动底稿视觉验收为 `pending`。退出码：0 全部底稿就绪，1 存在失败，2 等待效果图。

完整规程见 [SKILL.md](SKILL.md)，格式见 [SPEC.md](SPEC.md)。`examples/ref/base/` 保留早期输出，便于比较。
