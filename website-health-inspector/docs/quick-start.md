# 快速开始

本文档帮助你从一个 URL、一个管理员账号或一份 Excel 清单开始，跑出可交付的正式巡检报告。

## 前置条件

- Python 3.10 或更高版本。
- 能访问目标网站的网络环境。
- 如需深度浏览，准备管理员账号和密码。
- 如需 AI 导读图，优先使用当前 Codex 会话内置 `image_gen`；若不可用，必须先让用户选择提供自己的图片接口 API Key、使用 HTML 图文导览或启用内置生图后重试。

进入 Skill 根目录：

```powershell
Set-Location "D:\Code\vibe实验室\网络安全智能体\网站健康状况检测\website-health-inspector"
```

## 模式一：临时 URL 快速巡检

适合只知道一个公开 URL，需要快速检查页面可访问性、内容完整性和基础浏览器表现的场景。

```powershell
python scripts/run_health_inspection.py --url https://example.com/admin --out runs/adhoc
```

这个模式不能证明登录后页面健康，也不能覆盖主机、数据库、DNS、TLS 深度校验、性能压测或微服务内部状态。报告中应把这些范围写成巡检边界。

## 模式二：URL + 管理员账号深度巡检

适合验证登录入口、登录后页面、受保护页面跳转和截图证据链。流程默认只读，不点击删除、审批、重启或提交业务数据等危险动作。

推荐通过环境变量传递密码：

```powershell
Read-Host "Admin password" -MaskInput | ForEach-Object { [Environment]::SetEnvironmentVariable("WEBSITE_HEALTH_ADMIN_PASSWORD", $_, "Process") }
python scripts/run_health_inspection.py --url https://example.com/admin --username admin --password-env WEBSITE_HEALTH_ADMIN_PASSWORD --out runs/deep
```

也可以在运行环境中提前设置 `WEBSITE_HEALTH_ADMIN_PASSWORD`，避免命令历史中出现明文密码。

## 模式三：Excel 资源清单巡检

适合管理员维护系统、站点、主机和服务清单，需要批量巡检的场景。

先生成或准备 Excel 清单：

```powershell
python scripts/create_inventory_template.py --out assets/inventory-template.xlsx
```

导入 Excel 并执行巡检：

```powershell
python scripts/import_inventory_excel.py --excel path\to\inventory.xlsx --out runs/inventory-run
python scripts/inspect_sites.py --inventory runs/inventory-run/inventory.normalized.json --out runs/inventory-run
```

## 常用开关

跳过页面发现：

```powershell
python scripts/run_health_inspection.py --url https://example.com/admin --out runs/adhoc --no-discovery
```

用户明确选择复用已有 AI 导读图，不重新调用图片接口：

```powershell
python scripts/run_health_inspection.py --url https://example.com/admin --out runs/adhoc --guide-mode reuse-existing
```

用户明确不提供 API Key 时，使用 HTML 图文导览：

```powershell
python scripts/run_health_inspection.py --url https://example.com/admin --out runs/adhoc --guide-mode html-guide
```

指定检查模块：

```powershell
python scripts/run_health_inspection.py --url https://example.com/admin --out runs/adhoc --checks discovery,content,deep-browser,host
```

跳过质量审计只建议用于调试：

```powershell
python scripts/run_health_inspection.py --url https://example.com/admin --out runs/debug --no-quality-audit
```

跳过 PDF 生成只建议用于调试；使用后交付清单不会标记为完整可交付：

```powershell
python scripts/run_health_inspection.py --url https://example.com/admin --out runs/debug --no-pdf
```

## 输出文件

一次正式巡检结束后，运行目录通常包含：

- `inventory.normalized.json`：标准化资源清单。
- `content-report.json`：内容完整性检查子报告。
- `browser-inspection-report.json`：深度浏览子报告，只有配置或触发浏览器检查时生成。
- `host-report.json`：主机与服务检查子报告，只有配置主机或服务时生成。
- `final-report.json`：合并后的结构化总报告。
- `final-report.html`：正式 HTML 报告。
- `final-report.pdf`：由正式 HTML 打印渲染生成的 PDF 报告。
- `final-report.md`：Markdown 报告。
- `quality-audit.md` 和 `quality-audit.json`：质量审计结果。
- `delivery-manifest.md` 和 `delivery-manifest.json`：交付清单。
- `ai-report-guide-status.json`：AI 导读图生成、复用、等待用户选择或 HTML 图文导览状态。

最终优先交付整个 `delivery/` 文件夹，其中包含 `delivery/final-report.html` 和 `delivery/final-report.pdf`；再按需附带 `final-report.json`、`final-report.md` 和 `quality-audit.md`。

## 手动拆分执行

当需要定位某个阶段的问题时，可以拆分运行：

```powershell
python scripts/build_adhoc_inventory.py --url https://example.com/admin --out runs/adhoc
python scripts/discover_site_pages.py --inventory runs/adhoc/inventory.normalized.json --out runs/adhoc --merge
python scripts/check_content.py --inventory runs/adhoc/inventory.normalized.json --out runs/adhoc
python scripts/check_deep_browser.py --inventory runs/adhoc/inventory.normalized.json --out runs/adhoc
python scripts/check_host_services.py --inventory runs/adhoc/inventory.normalized.json --out runs/adhoc
python scripts/merge_reports.py --in runs/adhoc --out runs/adhoc/final-report.json
python scripts/render_report.py --report runs/adhoc/final-report.json --out runs/adhoc --guide-mode html-guide
python scripts/audit_report_quality.py --run-dir runs/adhoc --iteration 1 --out runs/adhoc/quality-audit.md
```

拆分执行时也必须以 `final-report.html` 作为唯一正式 HTML 入口，并确认 `final-report.pdf` 已生成。
