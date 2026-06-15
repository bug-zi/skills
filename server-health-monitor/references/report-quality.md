# 报告质量门

每次正式服务器健康检查都必须生成干净的 `delivery/` 文件夹。

必需交付文件：

- `delivery/final-report.html`
- `delivery/final-report.pdf`
- `delivery/final-report.md`
- `delivery/final-report.json`
- `delivery/guide-image-status.json`
- `delivery/quality-audit.json`
- `delivery/quality-audit.md`
- `delivery/delivery-manifest.json`
- `delivery/delivery-manifest.md`

当一次巡检包含多台服务器时，还必须生成 N+1 交付包：

- `delivery-batch/index.html`
- `delivery-batch/batch-summary.json`
- `delivery-batch/overall/final-report.html`
- `delivery-batch/overall/final-report.pdf`
- `delivery-batch/servers/index.html`
- `delivery-batch/servers/<slug>/delivery/final-report.html`
- `delivery-batch/servers/<slug>/delivery/final-report.pdf`

`delivery-batch/index.html` 是批次首页入口；`overall/` 是整体总报告；`delivery-batch/servers/index.html` 是单服务器报告索引入口；`servers/<slug>/delivery/` 是单服务器完整报告包。不得让用户直接打开 `delivery-batch/servers/` 原生文件夹目录作为交付入口。

中文要求：

- HTML、PDF、Markdown、质量审计、交付清单、导航、表头、管理结论和证据说明都必须使用中文表达。
- 不得在正式报告中出现 `Management Summary`、`Findings`、`Technical Evidence`、`Server Matrix` 等英文标题。
- 不得出现连续问号、Unicode replacement character、常见 mojibake 片段或明显乱码。

导览图要求：

- 报告表头必须包含 GPT 导览图或中文 HTML/CSS 导览图，导览区域不得留空。
- 生成导览图必须优先由 Codex/助手自主使用 GPT 生图能力，不得先默认使用 HTML/CSS。
- 当报告覆盖类型为 `doops-self-collected` 时，导览图提示词必须明确这是 zheyin doops 节点自身运行状态监测，突出 CPU、内存、磁盘、负载、主要进程、关键服务、doops 心跳和 workspace 采集链路；不得暗示已经覆盖 Excel 清单内其他普通业务服务器。
- 若自主 GPT 生图失败，再询问用户是否提供自己的 API Key；用户提供后，使用 OpenAI Image API 和 `gpt-image-2` 生成 `delivery/html-assets/guide-image.png`。
- 默认 `auto` 模式在没有 AI 导览图、没有可用图像生成密钥、且用户没有明确选择 HTML/CSS 时，必须中止，不得静默降级为 HTML/CSS。
- 用户不提供 API Key 或明确不使用 AI 导览图时，必须先询问并取得用户确认；确认后、旧参数 `--skip-guide-image` 或生成失败时，必须写入 `guide-image-status.json`，并在正式 HTML 中渲染 `html-guide-visual`。
- 正式报告正文不得展示密钥变量名、真实密钥、失败堆栈、代理地址、接口配置细节、跳过 GPT 或缺少 API Key 的运行提示。

HTML 要求：

- 必须由 runner 生成，不得把手写 HTML 当作最终报告。
- 必须包含 `guide-cover`、`report-nav`、`fold-section` 标记。
- 总报告和单机报告必须共享统一的 compact/AI cover 视觉体系：AI 图模式必须包含 `ai-cover`、`ai-guide-stage` 和 `compact-report`，HTML/CSS 备用导览图模式必须包含 `fallback-cover-grid` 和 `compact-report`。
- 总报告 HTML 正文必须使用精简结构，只保留 `compact-summary`、`compact-core-metrics`、`compact-key-services`、`compact-matrix`、`compact-findings`、`compact-evidence` 和 `matrix-card-list`。
- N+1 批次必须生成 `delivery-batch/servers/index.html`，页面必须包含 `server-report-index`、状态卡片、单机报告 HTML/PDF 链接，并从 `delivery-batch/index.html` 提供“打开单机报告索引”入口。
- JSON 必须包含 20 项高级报告模块结构化数据：`decision_summary`、`risk_heatmap`、`owner_brief`、`sla_timeline`、`evidence_ladder`、`data_quality`、`remediation_roadmap`、`change_watchlist`、`service_health`、`capacity_summary`、`asset_segments`、`business_impact`、`control_checklist`、`work_order_actions`、`appendix_index`、`readability_score`、`report_narrative`、`review_questions`、`scope_statement`、`next_report_plan`。
- HTML 不得为了满足“20 项”而展示全零、空数组、无明细、观察型伪工单等低信号模块；高级洞察只保留在 JSON 交付数据里，不进入总报告正文。
- 桌面端服务器矩阵应保留表格密度，移动端必须提供 `matrix-card-list` 卡片视图，避免窄屏横向挤压。
- 打印样式必须保留管理简报、风险队列、处置行动和技术证据的可读性，关键卡片不得被分页强行切断。
- 必须展示检查覆盖边界，特别是没有主机凭证或只做网络探测时。
- 不得暴露密码、Token、Cookie、私钥或 API Key。

PDF 要求：

- 必须与 HTML/Markdown 使用同一份报告数据。
- 必须能正确显示中文。当前 runner 使用 `reportlab` 和本机中文字体生成 PDF。

写作规则：

- 先给管理结论、状态计数和覆盖范围。
- `doops-self-collected` 报告必须在管理结论、doops 通道、技术证据和导览图中说明“采集对象是 zheyin doops 节点自身”，并写明无需 SSH/WinRM/SNMP，不代表其他普通服务器主机指标。
- 必须生成结构化 `summary.report_insights`，至少包含 `executive_brief`、`risk_queue`、`evidence_confidence`、`coverage_gaps`、`metric_insights`、`action_board`、`reading_map`、`quality_score` 和 `advanced`。
- `summary.report_insights.advanced` 必须包含 21 项高级洞察键：`decision_summary`、`risk_heatmap`、`owner_brief`、`sla_timeline`、`evidence_ladder`、`data_quality`、`remediation_roadmap`、`change_watchlist`、`service_health`、`process_health`、`capacity_summary`、`asset_segments`、`business_impact`、`control_checklist`、`work_order_actions`、`appendix_index`、`readability_score`、`report_narrative`、`review_questions`、`scope_statement`、`next_report_plan`。
- Markdown 必须与 HTML 同口径精简，只包含管理结论、清单分层摘要、核心指标、关键服务、doops 通道、服务器矩阵、问题与建议、趋势与证据边界等必要章节。
- 管理摘要必须说明网络探测、主机指标、主要进程、服务状态覆盖情况，严重/预警/需复核数量，P1/P2/P3 优先级数量，以及趋势状态。
- 当启用认证安全巡检时，HTML、Markdown 和 JSON 必须增加“认证安全”模块：覆盖服务器数、认证日志可读取数量、疑似密码爆破服务器数、弱口令风险服务器数、防护配置缺口服务器数、证据未覆盖服务器数。未启用时不得把认证安全写成已覆盖。
- 认证安全详情只能展示失败/成功登录统计、来源数量、脱敏账号标签、命中规则、防护配置状态和处置建议；不得展示明文密码、hash、完整原始日志、token、私钥或完整认证头。
- AI 导览图提示词在认证安全启用时必须包含“认证安全、爆破迹象、防护配置、密码强度风险”元素，但必须明确不出现密码内容、hash、账号明细或原始日志。
- 分析重点放在严重、预警、未知和证据边界事项。
- 问题项必须包含证据、业务影响、处置建议、优先级、建议处理时限和端口来源；业务影响未提供时必须明确写“业务影响未在清单中提供，需由业务侧确认”。
- 推断或旧版清单中的 SSH/RDP 等管理端口不可达不得直接作为严重业务故障；应标记为预警/需复核，除非清单显式声明其为业务依赖。
- 服务器矩阵必须展示服务器、地址、业务角色、状态、优先级、建议处理时限和证据边界；不得展示负责人、业务部门、系统等级这类长期缺失字段。
- 有上一期 `final-report.json` 时必须展示新增、恢复、持续问题和状态变化；没有上一期时必须展示“本次为基线巡检，暂无趋势对比”。
- 健康服务器只作为基线证据展示，不写冗长正向分析。
- 明确说明离线模式和网络层检查不能替代主机级持续监控。

质量审计要求：

- `quality-audit.json` 必须同时提供稳定键值 `checks` 和人类可读 `check_items`。
- `checks.layout_upgrade_markers` 必须为 `pass`，否则不得交付正式报告。
- `checks.advanced_upgrade_markers` 必须为 `pass`，确认 JSON 20 项高级模块结构化数据完整。
- `checks.advanced_visible_signal` 必须为 `pass`，确认 HTML 已隐藏低信号模块并只展示有信息增量的高级模块。
- `checks.sensitive_data_scan` 必须识别真实密钥、明文密码值、私钥块、Authorization/Bearer 值和 doops gateway token；不得因为 `password_strength`、`password_login_enabled` 这类结构化安全字段名误报。
