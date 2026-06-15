# 执行管线

## 运行门禁

- `check_runtime_dependencies.py --pdf` 会检查 Chrome/Edge PDF 打印能力；需要导入 Excel 时再加 `--excel`。
- `inspect_sites.py --strict` 会在第一个检查模块失败时停止；默认模式会继续执行检查模块，并写入 runtime-failed 子报告，`merge` 与 `render` 失败仍然是致命错误。
- `render_report.py` 必须从正式 HTML 打印生成 PDF，不再生成占位 PDF；浏览器失败会写入 `pdf-generation-error.txt`。
- `audit_report_quality.py` 会写出 `quality-audit.md/json`、刷新交付清单，并在质量门禁 `fail` 时返回 1。

Website Health Inspector 的核心设计是：所有输入先归一化为 `inventory.normalized.json`，各检查模块输出结构化子报告，最后合并、渲染并审计正式交付物。

## 数据流

```text
临时 URL / Excel 清单
        |
        v
inventory.normalized.json
        |
        v
页面发现 -> 内容检查 -> 浏览器深度巡检 -> 主机与服务检查
        |
        v
模块子报告 JSON
        |
        v
final-report.json
        |
        v
final-report.html / final-report.pdf / final-report.md / delivery-manifest / quality-audit
```

## 一键入口

`scripts/run_health_inspection.py` 是临时 URL 和带凭证深度巡检的首选入口。它负责：

1. 构建临时资源清单。
2. 调用 `inspect_sites.py` 执行模块。
3. 合并子报告。
4. 渲染正式报告。
5. 默认执行质量审计。

常用参数：

- `--url`：巡检入口 URL。
- `--out`：运行输出目录。
- `--name`：系统或站点展示名称。
- `--username`：管理员用户名。
- `--password-env`：管理员密码环境变量名，默认 `WEBSITE_HEALTH_ADMIN_PASSWORD`。
- `--password`：管理员密码，不推荐用于正式运行。
- `--no-discovery`：跳过页面发现。
- `--checks`：指定检查模块，默认 `discovery,content,deep-browser,host`。
- `--guide-mode`：导读图生成方式，支持 `auto`、`ai-image`、`html-guide`、`reuse-existing`；无 API Key 且未明确选择时停止并要求先询问用户。
- `--skip-ai-guide-image`：兼容参数，等同于 `--guide-mode html-guide`。
- `--no-pdf`：跳过 PDF 生成，仅建议调试时使用；正式交付清单不会标记为完整可交付。
- `--no-quality-audit`：跳过质量审计，仅建议调试时使用。

## 脚本职责

输入构建：

- `create_inventory_template.py`：生成 Excel 空白模板。
- `import_inventory_excel.py`：把 Excel 导入为 `inventory.normalized.json`。
- `build_adhoc_inventory.py`：从单个 URL 构建临时资源清单。

检查模块：

- `discover_site_pages.py`：执行受控同源页面发现，可合并回清单。
- `check_content.py`：检查页面可访问性、正文长度、必含文本和禁用文本。
- `check_deep_browser.py`：执行只读管理员浏览器深度巡检，输出截图和浏览器证据。
- `check_browser_flow.py`：执行管理员流程可用性检查。
- `check_host_services.py`：检查主机端口和微服务健康目标。

报告生成：

- `merge_reports.py`：合并各模块报告为 `final-report.json`。
- `render_report.py`：渲染正式 HTML、PDF、Markdown、导读图状态和交付清单；PDF 由 HTML 打印渲染生成；缺少 API Key 且未显式选择导览方式时要求先确认用户选择；`ai-image` 模式在有 API Key 时会先确保 `openai` Python 包可用，缺包自动安装，安装失败以 `missing_dependency` 停止而不是降级 HTML。
- `check_image_generation_readiness.py`：预检 Codex `image_generation` feature flag 和用户 API Key 状态，给出内置生图、启用 feature 或要求用户提供 key 的下一步。
- `generate_ai_report_guide_image.py`：在用户提供可用图片接口配置时生成 AI 导读图；当前会话有内置 `image_gen` 时应优先由 Codex 生成图片文件。
- `generate_summary_image.py`：生成摘要图。
- `audit_report_quality.py`：审计正式报告质量。
- `summarize_iterations.py`：汇总多轮迭代运行结果。

共享工具：

- `health_common.py`：通用数据结构、状态和辅助函数。
- `env_utils.py`：环境变量读取工具。

## 子报告契约

每个检查模块都应输出 JSON 子报告：

```json
{
  "report_type": "content-review 或 function-availability 或 host-service-health 或 site-discovery",
  "generated_at": "ISO-8601 时间",
  "status": "healthy 或 warning 或 critical 或 unknown",
  "score": 0,
  "summary": "面向管理人员的简短摘要",
  "systems": [],
  "findings": [],
  "metrics": {}
}
```

发现项应包含：

```json
{
  "id": "content-001",
  "system_id": "admin-platform",
  "system_name": "统一管理平台",
  "severity": "low 或 medium 或 high 或 critical",
  "priority": "P1 或 P2 或 P3 或 P4",
  "title": "管理后台登录失败",
  "business_impact": "管理员无法进入后台执行配置操作。",
  "technical_evidence": "HTTP 500 on /login",
  "target": "https://example.com/login",
  "recommendation": "检查认证服务和网关转发。",
  "evidence_files": []
}
```

模块无法执行时，不要静默跳过。应输出 `unknown` 或明确的失败发现，让最终报告保留覆盖缺口。

## 总报告契约

`final-report.json` 是唯一结构化总报告：

```json
{
  "generated_at": "ISO-8601 时间",
  "overall_status": "healthy 或 warning 或 critical 或 unknown",
  "score": 0,
  "executive_summary": "管理摘要",
  "summary": {
    "total_systems": 0,
    "healthy": 0,
    "warning": 0,
    "critical": 0,
    "unknown": 0
  },
  "systems": [],
  "priority_findings": [],
  "module_reports": [],
  "artifacts": {}
}
```

总报告阶段负责去重、根因归并、优先级重算、健康评分和管理摘要生成。它应优先服务管理阅读，原始技术证据放在详情或附录中。

## 优先级与评分

优先级由总报告阶段综合计算，不能简单照搬单个模块结果。

参考因素：

- 技术严重度。
- 系统重要性。
- 业务影响。
- 影响范围。
- 证据可信度。
- 是否生产环境。
- 是否影响管理员核心路径。

默认健康评分从 100 分开始扣减：

- `critical`：扣 35 分。
- `high`：扣 25 分。
- `medium`：扣 12 分。
- `low`：扣 5 分。
- 模块覆盖不足：扣 5 分。

分数用于快速判断趋势，不替代人工风险判断。
