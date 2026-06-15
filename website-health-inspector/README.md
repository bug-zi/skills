# Website Health Inspector

面向管理平台管理员的网站健康巡检 Skill。它把临时 URL、Excel 资源清单、管理员浏览器实测、内容完整性检查、可选主机与微服务检查，收敛成正式的 `final-report.html`、`final-report.pdf`、`final-report.json`、`final-report.md` 和质量审计报告。

这个目录就是可触发的 Skill 源码；维护文档、脚本和模板时，请以 `SKILL.md` 作为 Agent 入口说明，并确保公开分发时不包含本地 `.env`。

## 适用场景

- 管理员给出一个临时 URL，需要快速判断公开页面可访问性、内容完整性和基础浏览器表现。
- 管理员给出 URL、账号和密码，需要只读验证登录入口、登录后页面、受保护页面跳转和截图证据链。
- 管理员需要在最终报告中看到网站打开时间、平均打开耗时、最慢页面和慢页面数等轻量性能快照。
- 管理员维护 Excel 资源清单，需要批量巡检系统、站点、主机和微服务。
- 需要生成正式巡检交付物，而不是零散日志、截图或临时手写 HTML。

## 快速开始

进入 Skill 根目录：

```powershell
Set-Location "D:\Code\vibe实验室\网络安全智能体\网站健康状况检测\website-health-inspector"
```

无凭证 URL 快速巡检：

```powershell
python scripts/run_health_inspection.py --url https://example.com/admin --out runs/adhoc
```

带管理员凭证的只读深度巡检：

```powershell
Read-Host "Admin password" -MaskInput | ForEach-Object { [Environment]::SetEnvironmentVariable("WEBSITE_HEALTH_ADMIN_PASSWORD", $_, "Process") }
python scripts/run_health_inspection.py --url https://example.com/admin --username admin --password-env WEBSITE_HEALTH_ADMIN_PASSWORD --out runs/deep
```

Excel 资源清单巡检：

```powershell
python scripts/import_inventory_excel.py --excel path\to\inventory.xlsx --out runs/inventory-run
python scripts/inspect_sites.py --inventory runs/inventory-run/inventory.normalized.json --out runs/inventory-run
```

正式交付文件位于运行目录中：

- `delivery/final-report.html`：正式 HTML 报告，优先交付；请发送整个 `delivery/` 文件夹。
- `delivery/final-report.pdf`：正式 PDF 报告，由 HTML 打印渲染生成。
- `final-report.json`：结构化总报告。
- `final-report.md`：Markdown 摘要报告。
- `quality-audit.md`：质量审计结果。
- `delivery-manifest.md`：交付清单和正式入口核对。
- `ai-report-guide-status.json`：AI 导读图生成、复用、等待用户选择或 HTML 图文导览状态。

## 文档

- [快速开始](docs/quick-start.md)：三种巡检模式和常用命令。
- [配置与安全](docs/configuration-and-security.md)：环境变量、凭证处理、只读原则和敏感信息边界。
- [资源清单指南](docs/inventory-guide.md)：Excel Sheet、标准 `inventory.normalized.json` 和字段约束。
- [执行管线](docs/pipeline-architecture.md)：脚本职责、数据流和模块输出。
- [报告与交付](docs/report-delivery.md)：正式报告结构、质量门禁、交付规则和常见问题。
- [维护与扩展](docs/maintenance.md)：新增检查模块、更新模板、同步安装目录和发布前检查。

## 目录结构

```text
website-health-inspector/
  agents/                 # Codex UI 元数据
  assets/                 # Excel 模板、HTML 模板和报告素材
  docs/                   # 面向使用者和维护者的文档
  references/             # Agent 按需读取的细粒度规范
  runs/                   # 本地巡检输出目录
  scripts/                # 巡检、合并、渲染和审计脚本
  .env.example            # 用户自备图片接口、管理员密码等可选配置示例
  SKILL.md
```

## 关键约束

- `inventory.normalized.json` 是所有检查模块的统一输入。
- 每个模块必须输出结构化子报告，最终由 `merge_reports.py` 合并为 `final-report.json`。
- 正式 HTML 只能交付 `final-report.html`，PDF 只能交付 `final-report.pdf`，不要交付临时 `final-*-health-report.html`。
- AI 导读图优先使用 Codex 当前会话内置 `image_gen`；不可用时必须先让用户选择提供自己的 API Key、使用 HTML 图文导览或启用内置生图后重试。用户已选择 AI 导读图且提供 API Key 时，渲染器会先确保 `openai` Python 包可用，缺包会自动安装，安装失败则停止并要求修复环境，不直接改用 HTML 图文导览。
- 报告必须明确证据边界；自动化登录态未确认不能直接写成网站登录故障。
- 带浏览器实测的最终报告必须包含页面打开时间性能快照；该快照是单次轻量观测，不等同于持续监控或性能压测。
- 报告、日志、文档和提交记录中不得暴露密码、Token、私钥、Cookie 或真实 API Key。
- 完成报告后必须运行质量审计；质量门禁失败时先修正，再交付。

## 参考命令

生成空白 Excel 模板：

```powershell
python scripts/create_inventory_template.py --out assets/inventory-template.xlsx
```

重新渲染已有总报告，并复用已有 AI 导读图：

```powershell
python scripts/render_report.py --report runs/adhoc/final-report.json --out runs/adhoc --guide-mode reuse-existing
```

用户明确不提供 API Key 时，使用 HTML 图文导览：

```powershell
python scripts/render_report.py --report runs/adhoc/final-report.json --out runs/adhoc --guide-mode html-guide
```

调试时如需跳过 PDF，可加 `--no-pdf`；正式交付不要使用该参数。

单独运行质量审计：

```powershell
python scripts/audit_report_quality.py --run-dir runs/adhoc --iteration 1 --out runs/adhoc/quality-audit.md
```

预检当前图片生成能力：

```powershell
python scripts/check_image_generation_readiness.py --json
```

用户选择 AI 导读图并提供 API Key 后，重新渲染 GPT 图片版本：

```powershell
python scripts/render_report.py --report runs/adhoc/final-report.json --out runs/adhoc --guide-mode ai-image
```

该模式会在缺少 `openai` Python 包时自动执行 `python -m pip install openai`；如果安装失败，会写入 `ai-report-guide-status.json` 的 `missing_dependency` 状态并停止，避免把环境缺陷伪装成 HTML 图文导览交付。

## 运行门禁

- 正式单站巡检前可运行 `python scripts/check_runtime_dependencies.py --pdf`；Excel 清单巡检再加 `--excel`。
- `render_report.py` 不再生成占位 PDF。Chrome/Edge 不可用时会写入 `pdf-generation-error.txt` 并返回非零；只有调试场景才显式使用 `--no-pdf`。
- `audit_report_quality.py` 在质量门禁 `status=fail` 时返回非零，并刷新 `delivery-manifest.json`。
- `delivery-manifest.json` 中 `package_complete` 表示预期报告文件已齐；`ready_to_deliver` 还要求质量审计未失败。
