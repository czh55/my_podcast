# 才岁播客大纲 → 成片 → GitHub Pages

本仓库是「才岁」原创播客的工作站与公开档案墙，结构对齐 [bilibili-workshop](https://github.com/czh55/bilibili-workshow) / audio-workshop：`docs/` 为 GitHub Pages 根目录。

## 产品规则

| 维度 | 约定 |
|------|------|
| 系列命名 | 才30、才40、才50… |
| 年龄跨度 | 31–40、41–50、51–60… |
| 每系列 | **12 篇**，约 **每月 1 篇** |
| 内容主轴 | 当前年龄段 × 社会相关问题（不是百科教程） |

## 目录

```
my_podcast/
├── README.md
├── .gitignore
└── docs/                      ← GitHub Pages
    ├── index.html             # 系列墙首页
    ├── series.json            # 系列元数据
    ├── episodes.json          # 全部篇目索引
    ├── WORKFLOW.md            # 出题 → 大纲 → 发布流程
    ├── outlines/              # Markdown 大纲源稿
    └── episodes/              # 可读的大纲 / 成片页
```

## 本地预览

```bash
cd docs && python3 -m http.server 8765
# 打开 http://127.0.0.1:8765/
```

## GitHub Pages

1. 推送到 GitHub 仓库（如 `czh55/my_podcast`）
2. Settings → Pages → Source：Deploy from branch
3. Branch：`main`，Folder：`/docs`
4. 保存后访问 `https://<user>.github.io/my_podcast/`

若仓库名为 `czh55.github.io` 的子路径项目，确认资源用相对路径（本站已使用相对路径）。

## 当前进度

- 系列 **才30** 已开档（12 个槽位）
- **EP01 怀孕**：初步大纲已就绪  
  - 页：`docs/episodes/cai30-ep01-pregnancy.html`  
  - 源：`docs/outlines/cai30-ep01-pregnancy.md`
