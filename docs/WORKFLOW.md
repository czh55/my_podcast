# 才岁播客工作流

主题给定后，按下列步骤产出可迭代大纲，并挂到 GitHub Pages 系列墙。

```
Task Progress:
- [ ] 1. 确认系列（才30/才40…）与期数槽位
- [ ] 2. 调研：年龄段语境 + 社会议题 + 必要事实锚点
- [ ] 3. 写 Markdown 大纲（docs/outlines/{slug}.md）
- [ ] 4. 生成可读 HTML（docs/episodes/{slug}.html）
- [ ] 5. 更新 docs/episodes.json（status、summary、outputs）
- [ ] 6. 本地预览 docs/
- [ ] 7. 用户迭代大纲
- [ ] 8. 成片后补录音链接 / 转录 / 总结页（可选）
- [ ] 9. 提交并推送 main（Pages 才更新）
```

## 大纲质量标准

1. **先定边界**：写清「不是什么 / 是什么」，避免做成百科或种草。
2. **社会主线 + 事实底线**：医学/法律数字只作锚点，主线是结构与经验。
3. **可录音**：有冷开场、分段时码、收束行动/决策地图。
4. **可迭代**：文末必须有开放问题，方便用户改立场、拆集、换标题。
5. **免责声明**：涉及健康/法律时标明不构成专业建议。

## 索引字段（episodes.json）

| 字段 | 说明 |
|------|------|
| `id` / `slug` | 稳定标识，如 `cai30-ep01-pregnancy` |
| `series` | `cai30` / `cai40` / … |
| `episode` | 1–12 |
| `status` | `slot` \| `outline` \| `draft` \| `published` |
| `planned_month` | `YYYY-MM` |
| `outputs.outline` | 相对 `docs/` 的 HTML 路径 |
| `outputs.outline_md` | Markdown 源路径 |

## 系列字段（series.json）

`id`, `title`, `age_span`, `decade_label`, `status`(`active`/`planned`), `planned_episodes`, `interval`, `theme`, `cover_accent`

## 与 bilibili-workshop 的对应关系

| bilibili-workshop | 本仓库 |
|-------------------|--------|
| `docs/index.json` 视频条目 | `docs/episodes.json` 播客篇目 |
| `*-图文实录.html` / `*-理性分析.svg` | `episodes/*.html` 大纲/成片页（后续可再加 SVG） |
| 平台转录流水线 | 主题调研 → 大纲迭代 →（可选）录音后转录 |
| GitHub Pages `docs/` | 相同 |
