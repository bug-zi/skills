# 2026-05-10 AI 导读图失败兜底升级

## 目标

- AI 图片生成失败时不再只显示缺图提示。
- 首页自动生成一份 HTML/CSS 图文导览，作为正式报告首屏兜底。
- 明确用户可选择配置 `.env` 生成 AI 导读图，或不配置并跳过生图。

## 变更

- 新增 `ai-report-guide-status.json`，记录 `generated`、`missing_api_key`、`failed`、`skipped`。
- `render_guide_cover` 在没有 AI 图片时渲染 `html-guide-visual`。
- 质量审计接受“AI 图片或 HTML 导览兜底”二选一。
- 文档明确 `.env` 可选项和 `--skip-ai-guide-image` 行为。

## 交付口径

AI 图片是增强项，不是正式报告可交付的硬前置。没有成功生图时，HTML 图文导览必须完整、可读、可交付。
