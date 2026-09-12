# Picxel

> 名字占位。

让 Claude Code / Codex 这类编程助手按固定规格**逐格填色**批量产出像素游戏素材。AI 写一份文本图纸，脚本渲染、校验、打包；不用生图模型猜像素，不离开编程助手，不另起服务。

- 三个尺寸档位：16 / 32 / 64。别的不支持。
- 每张最多 16 色，从 DB32 主色板里选。
- 图纸是纯文本 `.pxg`：头部声明色号，下面每行一个像素行。
- 导出：原尺寸 PNG、4 倍预览、整目录精灵表 PNG + JSON、一个自包含的 HTML 总览页。
- 导入：把现成的 PNG 读成图纸，AI 接着改。

规格见 [SPEC.md](SPEC.md)；AI 的操作规矩见 [SKILL.md](SKILL.md)。

## 装成 skill

```bash
git clone <this repo> ~/.claude/skills/picxel     # Claude Code
# Codex：放进它的 skills 目录，同一份 SKILL.md
```

只需要 Python 3 和 Pillow（`pip install pillow`）。

## 用

```bash
python scripts/picxel.py check  examples/grass-01.pxg
python scripts/picxel.py render examples/grass-01.pxg -o out
python scripts/picxel.py import ref.png --size 32 --kind sprite
python scripts/picxel.py sheet  examples -o examples/dist      # 开 examples/dist/index.html
```

`examples/` 里三张是第一版试画：32×32 草地（四边可拼）、32×32 正面小人、16×16 红药水。
