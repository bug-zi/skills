# 2026-05-10 导读图选择前置化升级

## 目标

- 生图能力不可用时，选择发生在调用 Skill 的过程里，而不是最终报告里。
- 用户可选择提供 API Key 生成 AI 导读图，或不提供 API Key、直接使用 HTML 图文导览。
- 最终 HTML 只呈现正式导览结果，不显示 API Key 配置、跳过生图或调用失败提示。

## 变更

- `SKILL.md` 明确要求：没有 `image_gen` 且无 `.env` 图片配置时，先向用户确认导读图方式。
- `render_report.py` 的 HTML 导览去掉运行过程提示，改为正式报告导览文案。
- `audit_report_quality.py` 新增检查：最终 HTML 不得出现 API Key 配置或 `--skip-ai-guide-image` 等运行提示。

## 口径

`ai-report-guide-status.json` 记录执行状态，供排查使用；管理报告正文只展示导览结果。
