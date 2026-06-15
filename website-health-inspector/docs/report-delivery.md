# 报告与交付

## 交付就绪状态

- `delivery-manifest.json` 中的 `package_complete` 表示预期 HTML/PDF/Markdown/JSON 和 delivery 文件夹已经存在。
- `ready_to_deliver` 还要求 `quality-audit.md/json` 存在，并且质量门禁状态不是 `fail`。
- `audit_report_quality.py` 会在写出审计文件后刷新 manifest；如果它返回 1，需要先修复报告或运行环境再交付。
- PDF 是正式 HTML 打印产物。Chrome/Edge 缺失时，`render_report.py` 会写入 `pdf-generation-error.txt`，不会生成占位 PDF。

巡检的核心交付物是管理人员可读、可复核、可转工单的正式报告，而不是脚本日志或临时 HTML。

## 正式交付物

运行目录中优先交付：

- `final-report.html`：正式 HTML 报告，第一入口。
- `final-report.pdf`：正式 PDF 报告，由 HTML 打印渲染生成，便于归档和转发。
- `final-report.json`：结构化总报告，可供后续自动化读取。
- `final-report.md`：Markdown 摘要，便于复制到沟通工具。
- `quality-audit.md`：人工可读质量审计报告。

辅助交付物：

- `quality-audit.json`：机读质量门禁结果。
- `delivery-manifest.md`：正式入口、摘要、质量审计和归档状态清单。
- `delivery-manifest.json`：机读交付清单。
- 截图证据：如 `entry-before-login.png`、`after-login.png`、`page-*.png`。

不要把 `final-*-health-report.html` 作为最终报告交付。它只能视为草稿或历史临时产物。正式渲染器会把根目录残留的非正式 HTML 移入 `_archived-nonfinal-html`。

## HTML/PDF 报告结构

正式 HTML 是视觉源文件；PDF 是 HTML 的打印版本。正式 HTML 和 PDF 应包含：

1. AI 导读图或 HTML 图文导览封面。
2. 实时数据栏。
3. 阅读导航。
4. 管理结论。
5. 健康总览。
6. 不健康索引或重点问题索引。
7. 风险域分布。
8. 优先事项和建议动作。
9. 系统健康矩阵。
10. 折叠式证据章节。
11. 截图和技术证据附录。
12. 可复制交付摘要。
13. 复测时间线。

关键模板标记：

- `guide-cover`
- `report-nav`
- `fold-section`
- `ai-report-guide.png` 或 `html-guide-visual`

阅读导航应支持当前章节高亮，通过 `aria-current` 和高亮样式标记当前阅读位置。

## 写作原则

报告读者是平台管理员、运维管理员、安全管理员和管理负责人。写作顺序应是：

1. 整体判断。
2. 影响系统。
3. 需要优先处理的事项。
4. 关键证据。
5. 技术详情和附录。

优先写业务影响，再写技术证据。不要让第一句变成 selector、HTTP header、堆栈或命令输出。

推荐判断句：

```text
当前判断：公开首页可访问；管理员登录链路未通过自动化确认；受保护业务入口可用性待复核；未发现已确认的生产级故障。
```

人工登录已验证正常时：

```text
当前判断：公开首页可访问；人工登录验证正常；自动化巡检未捕获稳定登录态信号，属于巡检代理识别能力边界，不构成网站登录故障。受保护入口需在人工已确认登录态下复测。
```

## 质量审计

正式报告生成后运行：

```powershell
python scripts/audit_report_quality.py --run-dir runs/adhoc --iteration 1 --out runs/adhoc/quality-audit.md
```

审计重点包括：

- 是否使用正式模板，而不是临时手写 HTML。
- 是否存在折叠章节。
- 是否存在重复段落、重复结论或机械化建议。
- 导航锚点是否有效。
- 阅读导航是否具备当前章节高亮能力。
- `ai-report-guide.png` 是否只引用一次；没有 AI 图时是否存在 `html-guide-visual` HTML 图文导览。
- 是否提供可复制交付摘要。
- 浏览器实测是否覆盖登录链路、截图和受保护页面证据。
- 是否存在乱码占位符、时区后缀或旧封面残留。
- 是否出现疑似 API Key、Token、Cookie、Secret。
- 运行目录是否存在容易误打开的非正式 `final-*-health-report.html`。
- 是否生成 `delivery-manifest.json` 和 `delivery-manifest.md`。
- 是否生成非空 `final-report.pdf` 和 `delivery/final-report.pdf`。

质量门禁失败时，先修正报告或模板，再重新渲染和审计。

## 交付检查清单

交付前确认：

- `final-report.html` 可以打开，且第一屏能回答整体是否健康、严重问题、影响系统和下一步动作。
- `final-report.pdf` 非空，可作为 HTML 的打印归档版本打开或转发。
- `final-report.json` 与 HTML 中的核心状态和数量一致。
- `final-report.md` 没有丢失关键结论。
- `quality-audit.md` 没有高风险失败项。
- `delivery-manifest.md` 指向的正式入口包含 `final-report.html` 和 `final-report.pdf`。
- 运行目录根部没有非正式 `final-*-health-report.html`。
- 报告没有暴露敏感信息。
- 自动化能力边界、人工复核项和已确认故障被清楚区分。

## 常见问题

报告样式像临时页面：

1. 确认打开的是 `final-report.html`。
2. 重新运行 `render_report.py`。
3. 运行质量审计检查模板标记。

PDF 缺失或为空：

1. 确认没有使用 `--no-pdf` 调试参数。
2. 重新运行 `render_report.py`，由 Playwright Chromium 从 HTML 打印生成 PDF。
3. 再运行质量审计确认 `delivery/final-report.pdf` 已进入交付包。

导读图数据和正文不同：

1. 以 `final-report.json`、HTML 实时数据栏和正文为准。
2. 需要刷新图片时，优先使用当前 Codex 会话内置 `image_gen`；若不可用且仍要求 AI 导读图，需要用户提供自己的图片接口 API Key。
3. 不提供 API Key 时，使用 `--guide-mode html-guide` 交付 HTML 图文导览版本。

登录未确认被误写成登录故障：

1. 检查是否已有人工登录复测证据。
2. 如果人工登录正常，将问题归类为自动化/MCP 操控能力边界。
3. 在报告中补充受保护入口的下一步复测条件。
