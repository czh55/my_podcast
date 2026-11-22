# 红豆牛奶不加糖 · 播客 → 成片 → GitHub Pages

「红豆牛奶不加糖」是一档关于**变化**的原创播客：AI 的变化、年龄的变化、身份的变化。节目名只是一个轻松的名字，主题始终是「变化」。目的只有一个——**减少焦虑**。原「才岁」系列（才30、才40、才50）并入「年龄的变化」。

`docs/` 为 GitHub Pages 根目录。品牌素材在 `docs/assets/`（logo、favicon、分享图、共享样式 `site.css`），节目简介、主持人、订阅链接在 `docs/site.json`——平台链接上线后填入 `url` 即可。

## 产品规则

| 维度 | 约定 |
|------|------|
| 变化类型 | `ai` AI 的变化 · `age` 年龄的变化 · `identity` 身份的变化 |
| 节奏 | 约每月 1 期，全站统一编号 |
| 内容主轴 | 一线亲历者的真实场景 + 可执行的小动作，不做趋势预测和说教 |
| 录制方法 | 答题卡 + 打断规则 + 复盘三问，见 `docs/WORKFLOW.md` |

## 目录

```
my_podcast/
├── README.md
├── edits/                     # 剪辑决策表（每期一个 JSON）
├── scripts/
│   ├── transcribe.py          # faster-whisper 转写（词级时间戳）
│   ├── edit_episode.py        # 按决策表剪辑、降噪、响度标准化、写章节
│   └── build_episode_data.py  # 生成网页章节与转写数据
└── docs/                      ← GitHub Pages
    ├── index.html             # 首页：变化类型 + 构思准则 + 篇目
    ├── series.json            # 变化类型
    ├── episodes.json          # 篇目索引
    ├── principles.json        # 构思准则（含录制方法）
    ├── WORKFLOW.md            # 出题 → 答题卡 → 录制 → 剪辑 → 复盘
    ├── audio/                 # 成片 mp3
    ├── outlines/              # 录前大纲
    └── episodes/              # 成片页 / 大纲页（data/ 为章节与转写）
```

## 本地预览

```bash
python3 scripts/serve.py 8765
# 打开 http://127.0.0.1:8765/
```

用 `scripts/serve.py` 而不是 `python3 -m http.server`：后者不支持 HTTP Range，音频无法按章节跳转。成片页的章节和转写通过 `fetch` 加载，直接双击 HTML 只能播放音频。

## 当前进度

- **EP01 · AI 的变化**：已剪辑（62:04），成片页 `docs/episodes/bian-ep01-ai.html`
- **怀孕**（身份的变化）：大纲阶段，`docs/episodes/cai30-ep01-pregnancy.html`
