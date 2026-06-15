# 维护与扩展

本文档面向维护 Website Health Inspector 的开发者和 Agent。目标是让新增检查、模板升级和发布同步都保持可验证。

## 修改前先确认

维护前先看这些文件：

- `SKILL.md`：Agent 使用方式和硬性边界。
- `references/inspection-flow.md`：巡检总流程。
- `references/sub-report-schema.md`：模块子报告结构。
- `references/final-report-schema.md`：总报告结构。
- `references/report-writing.md`：管理报告写作规范。
- `references/report-design.md`：HTML 视觉和结构规范。

根目录 `README.md` 和 `docs/` 面向人类使用者；`references/` 面向 Agent 按需加载。不要把长篇教程塞进 `SKILL.md`。

## 新增检查模块

新增模块时遵循这个契约：

1. 只读取 `inventory.normalized.json`。
2. 不直接读取 Excel。
3. 输出结构化 JSON 子报告。
4. 模块失败时输出 `unknown` 或明确失败发现。
5. 不在子报告中写入敏感信息。
6. 在 `merge_reports.py` 中接入总报告合并。
7. 在 `render_report.py` 中确认 HTML 和 Markdown 能展示新模块证据。
8. 在 `audit_report_quality.py` 中加入必要质量检查。
9. 更新 README、docs 和 references 中对应说明。

子报告至少包含：

```json
{
  "report_type": "new-check",
  "generated_at": "ISO-8601 时间",
  "status": "healthy",
  "score": 100,
  "summary": "面向管理人员的摘要",
  "systems": [],
  "findings": [],
  "metrics": {}
}
```

## 更新报告模板

更新 `assets/report-template.html` 或 `scripts/render_report.py` 后，必须验证：

- `final-report.html` 是唯一正式 HTML 入口。
- `final-report.pdf` 由正式 HTML 打印渲染生成，并进入 `delivery/`。
- 非正式 `final-*-health-report.html` 会被归档。
- `guide-cover`、`report-nav`、`fold-section` 仍存在。
- 折叠章节默认可读且不会把正文拉得过长。
- 阅读导航当前章节高亮仍有效。
- 可复制交付摘要仍可用。
- `delivery-manifest.md` 和 `delivery-manifest.json` 仍生成。
- 质量审计会检查非空 `final-report.pdf` 和 `delivery/final-report.pdf`。
- 移动端和桌面端都能正常阅读。

## 更新写作逻辑

改动 `merge_reports.py` 或报告文案时，重点检查：

- 健康系统只做数据型摘要，不写冗长分析。
- 正文分析集中在不健康、待复核、自动化能力边界和风险项。
- 优先事项包含证据口径、业务影响、处理路径、建议动作和下一证据。
- 自动化登录态未确认不被写成网站登录失败。
- 单次巡检只称为快照结论，未做多时间点检测时不判断偶发或持续。

## 验证命令

快速 URL 验证：

```powershell
python scripts/run_health_inspection.py --url https://example.com/admin --out runs/maintenance-check --guide-mode html-guide
```

重新渲染已有报告：

```powershell
python scripts/render_report.py --report runs/maintenance-check/final-report.json --out runs/maintenance-check --guide-mode html-guide
```

质量审计：

```powershell
python scripts/audit_report_quality.py --run-dir runs/maintenance-check --iteration 1 --out runs/maintenance-check/quality-audit.md
```

预检图片生成能力：

```powershell
python scripts/check_image_generation_readiness.py --json --no-load-env
```

如果只改文档，也至少确认 Markdown 链接和命令路径没有明显错误。

## 同步到 Codex 安装目录

本工作区是源码副本。实际安装目录通常是：

```text
C:\Users\Administrator\.codex\skills\website-health-inspector
```

同步前确认目标目录：

```powershell
Get-ChildItem "C:\Users\Administrator\.codex\skills\website-health-inspector"
```

同步文档时可以复制：

```powershell
Copy-Item -LiteralPath ".\README.md" -Destination "C:\Users\Administrator\.codex\skills\website-health-inspector\README.md" -Force
Copy-Item -LiteralPath ".\docs" -Destination "C:\Users\Administrator\.codex\skills\website-health-inspector\docs" -Recurse -Force
```

如果同步 `SKILL.md`，确认目标仍是可触发入口文件，不要保留旧的禁用副本命名。

## 发布前检查

- README 中的命令能在当前目录执行。
- docs 与 `SKILL.md` 的核心边界一致。
- `agents/openai.yaml` 的展示名称、短描述和默认 prompt 没有过期。
- `.env` 没有被提交。
- `runs/` 中没有需要发布的敏感截图或报告。
- `scripts/__pycache__/` 不作为文档或源码交付重点。
- 已安装目录需要更新时，确认 README 和 docs 已同步。
