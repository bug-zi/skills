---
name: website-health-inspector
description: 面向管理平台管理员的网站健康巡检 Skill。支持 Excel 资源清单标准巡检、临时 URL 快速巡检、URL + 管理员凭证的深度浏览巡检，执行网站内容完整性审查、管理员浏览器实测、可选主机与微服务健康检查，并生成面向管理人员的 HTML、PDF、Markdown、JSON 正式报告。HTML 报告必须使用正式渲染器，PDF 必须由正式 HTML 打印渲染生成，支持 GPT 图文导览封面、折叠式交互章节、技术证据附录、评分合理性复核和质量审计报告。适用于检查网站健康状况、验证管理平台可用性、审查网页内容异常、复核登录链路和生成正式巡检交付物。
---

# 网站健康巡检助手

## 自然语言调用前置确认

- 当用户用自然语言要求“巡检网站、生成报告、跑当前 Skill、检查 URL、检查 Excel 清单、复核管理后台”等任务时，如果用户没有在同一条消息中明确指定导读图方式，必须先停下来询问用户，不得直接运行 `run_health_inspection.py`、`inspect_sites.py`、`run_multi_site_inspection.py` 或 `render_report.py`。
- 询问必须让用户在这些互斥选项中选择：`GPT/AI 导读图`、`HTML 图文导览`、`复用已有 ai-report-guide.png`、`先启用/修复内置 image_gen 后重试`。如果当前会话没有内置 `image_gen` 但检测到可用用户 API Key，也仍然要先确认是否允许使用用户 API Key 调用图片接口。
- 用户选择 `GPT/AI 导读图` 后，优先使用当前会话内置 `image_gen` 生成 `ai-report-guide.png`；若本会话没有可调用内置生图工具，则要求用户提供或确认使用自己的图片接口 API Key，并在渲染时使用 `--guide-mode ai-image`。
- 用户已选择 `GPT/AI 导读图` 且提供/确认了 API Key 时，必须确保当前 Python 环境可导入 `openai`；`render_report.py --guide-mode ai-image` 会在缺包时先尝试 `python -m pip install openai`。依赖安装失败属于运行环境缺陷，必须停止并要求修复后重试，不得直接改用 HTML 图文导览。
- 用户选择 `HTML 图文导览` 后，使用 `--guide-mode html-guide`；用户选择复用已有图后，使用 `--guide-mode reuse-existing`；用户要求启用内置生图后重试时，只提示其启用并重启/新开会话，不继续生成报告。
- 禁止把“用户没说导读图方式”解释为默认同意 HTML 图文导览、默认同意使用 `.env` 中的 API Key、默认复用旧图或默认跳过生图。没有明确选择就不能执行正式渲染。

## 运行门禁

- 正式 PDF 交付前运行 `python scripts/check_runtime_dependencies.py --pdf`；输入为 Excel 清单时加 `--excel`。
- `inspect_sites.py --strict` 会在任一检查模块失败时立即停止；不加 `--strict` 时，检查模块失败会写入 runtime-failed 子报告并继续合并，`merge` / `render` 失败仍然是致命错误。
- `merge_reports.py` 生成 `final-report.json` 后，正式渲染前必须运行 `python scripts/audit_score_reasonableness.py --report reports/run-001/final-report.json --out reports/run-001 --threshold 60`；评分低于阈值、分数重算不一致、状态与评分不一致或发现疑似重复扣分时先阻断渲染。
- `render_report.py` 必须通过 Chrome/Edge 从正式 HTML 打印生成 PDF，不得生成占位 PDF；浏览器不可用时写入 `pdf-generation-error.txt` 并返回非零，除非显式使用仅供调试的 `--no-pdf`。
- `audit_report_quality.py` 会写出 `quality-audit.md/json`、刷新 `delivery-manifest.json`，并在 `status=fail` 时返回非零。
- `delivery-manifest.json` 中 `package_complete` 表示必要产物存在；`ready_to_deliver` 还要求评分审计产物存在、评分门禁通过或已人工批准、质量审计产物存在且质量门禁未失败。

使用本 Skill 为管理平台管理员执行按需网站健康巡检。核心交付物是管理人员可读的正式巡检报告，而不是原始扫描日志或临时手写 HTML。

## 运行原则

- `inventory.normalized.json` 是各检查模块的统一执行入口。
- 所有模块必须输出结构化子报告，最终由 `merge_reports.py` 合并为 `final-report.json`。
- 当用户要求巡检多个网站时，优先使用多站点 N+1 模式：每个网站独立生成一份正式报告，再生成一份整体总报告和 `delivery-batch/index.html` 首页索引。
- 多站点整体总报告必须与单站报告形态不同：单站报告是站点诊断报告，整体总报告是批次治理与管理汇总报告；整体报告应使用 `report_kind: "multi-site-overall"` 触发专用渲染，不得复用单站浏览器证据、截图索引、模块长分析等诊断叙事。
- 正式 HTML 必须由 `render_report.py` 生成。禁止手写 `final-*-health-report.html` 作为最终报告，禁止绕过正式模板。
- `render_report.py` 会自动把运行目录根部残留的 `final-*-health-report.html` 移入 `_archived-nonfinal-html`；外层根目录保留兼容用 `final-report.html` 和 `final-report.pdf`，正式对外交付入口是 `delivery/final-report.html` 与 `delivery/final-report.pdf`。
- 对外发送报告时必须发送整个 `delivery/` 文件夹，而不是单独发送 HTML 或 PDF。`delivery/html-assets/` 保存 HTML 实际引用图片，`delivery/screenshots/` 保存完整截图证据。
- 调用本 Skill 时，优先使用 Codex 当前会话内置 `image_gen` 能力生成 `ai-report-guide.png`；如果当前会话没有可用 `image_gen`，必须先和用户确认导览图方式：提供自己的 API Key 生成 AI 图、明确选择 HTML 图文导览、或启用内置 `image_gen` 后重试。
- 用户提供的图片接口配置只能写入本地 `.env` 或当前 shell 环境变量，不得写入报告正文、日志摘要、公开文档或可交付文件；占位值、示例 key 和空值都不能视为可用配置。
- 未得到用户明确选择前，不得让脚本自行降级为 HTML 图文导览；`render_report.py` 默认 `--guide-mode auto` 在无可用 API Key 时会停止并写入 `needs_user_choice`。
- 用户提供 API Key 后使用 `--guide-mode ai-image`；用户明确不提供 API Key 或只要求先交付报告时使用 `--guide-mode html-guide`；用户明确要求复用已有图时使用 `--guide-mode reuse-existing`。
- `ai-image` 模式下必须先保证 `openai` Python 包可用；缺包时由脚本自动执行 `python -m pip install openai`，安装失败写入 `missing_dependency` 并停止，不能生成最终报告。只有依赖可用后发生图片接口调用失败，才允许写入 `failed` 并自动切换为首页 HTML 图文导览兜底；最终 HTML 报告中不得显示“配置 API Key / 跳过生图 / 调用失败”等运行过程提示。
- 不得把普通摘要图复制成 `ai-report-guide.png` 冒充 AI 导读图；没有 AI 图时应明确标注为 HTML 图文导览。
- 推荐优先使用 `run_health_inspection.py` 一键管线；它会构建清单、执行模块、合并 JSON、执行评分合理性复核、渲染正式 HTML/PDF/Markdown，并执行质量门禁。
- 正式 HTML 必须包含 AI 导读图或 HTML 图文导览封面、实时数据栏、阅读导航、管理结论、健康总览、折叠式证据章节和技术附录。
- 带浏览器实测的正式 HTML/Markdown/JSON 报告必须包含网站打开时间性能快照，至少展示平均打开时间、最慢页面、慢页面数和 TTFB；该数据是单次轻量观测，不等同于持续监控或性能压测。
- 正式模板标记至少应包含 `guide-cover`、`report-nav`、`fold-section`；质量门禁不通过时必须重新渲染。
- 报告生成模块负责去重、根因归并、证据分层和管理化表达。
- 健康评分必须采用根因封顶口径：同一根因只扣一次，重复页面、重复请求、重复日志只能增加证据数量和同类次数，不得机械重复扣分。
- 最终健康评分以 `scripts/scoring_model.py` 的根因聚类结果为准；`merge_reports.py` 和 `render_report.py` 必须使用同一套模型，评分说明中的扣分合计必须与 `final-report.json` 的 `score` 一致。
- 健康状态也必须以 `scripts/scoring_model.py` 的有效扣分口径为准：`100 分 + 无正扣分簇 = healthy`；有正扣分簇但未达到严重条件为 `warning`；存在已确认 `critical` / `confirmed-outage` 有效扣分或总分低于 60 为 `critical`；无可用报告、站点未执行、URL 无效或未生成报告才是 `unknown`。
- 自动化边界、会话边界、参数化路由边界、人工确认正常等零扣分项可以展示为复核说明或证据边界，但不得把 `overall_status`、系统矩阵状态或多站点站点状态顶成 `warning`。
- 质量审计状态只表示交付物质量，不是健康状态来源；`quality_status=failed` 可以进入优先处理原因和质量指标，但不能把健康状态从 `healthy` 改成 `warning`。
- 评分聚类必须优先使用结构化字段 `cluster_key`、`category`、`finding_type`、`confidence`；只有旧报告缺少结构化字段时，才允许用标题、URL 或技术证据文本兜底识别。
- 评分聚类必须先规范化系统标识和 endpoint：`system_id` / `system_name` 统一 slug 化；URL 要去掉 HTTP 方法、query、hash、尾部斜杠，并将数字 ID、UUID、ObjectId 和静态资源 hash 归并为同一接口族。重复接口族只增加 `_cluster_count`、证据和目标列表，不得拆成多次扣分。
- 评分合理性复核是渲染前门禁，不是报告成稿后的质量审计。`score-audit.json/md` 必须在正式 HTML/PDF 生成前产生，并随 `delivery/` 一起交付。
- `score < 60`、`final-report.json.score` 与 `scoring_model.py` 重算分数不一致、`overall_status` 与有效扣分状态不一致、或存在动态 ID/query/hash/接口族差异导致的疑似重复扣分时，必须阻断正式渲染；脚本只输出证据和归并建议，不自动改分。
- 低分经人工确认合理后才可继续渲染，必须显式传入 `--score-review-approved --score-review-note "人工确认低分合理，未发现重复扣分"`；说明会写入 `delivery-manifest` 和技术附录。
- 自动化登录态未确认、自动化会话保持边界、参数化业务路由覆盖边界不得作为网站主健康扣分项；人工登录正常时，这些只能归类为自动化/MCP 能力边界。
- SPA 文本检查、`body_length` 过短、单页应用未执行 JavaScript 等低可信提示不得因多个页面重复大幅扣分，应作为自动化识别不足或低权重复核项。
- 同一接口或同一路径的多次请求失败按根因封顶扣分；不同接口可以分别计分，但必须先按规范化 endpoint 去掉 query、hash、动态 ID 与构建 hash 后归并。`GET https://host/api/users?page=1`、`/api/users/123` 与 `/assets/chunk.abcdef12.js` 这类重复形态都必须归并到稳定接口族。
- 已确认 `critical` / `high` 风险仍按最高严重度扣分，不能因为根因归并而弱化真实生产故障；但同一已确认故障的重复日志仍不得重复扣分。
- 低可信 `high-confidence-risk`、疑似高严重度信号不得直接按高危扣分，应先按 `confidence` 降为复核权重；`manual-confirmed-normal` 或人工确认正常的 confidence 必须清零，即使标题或日志像故障。
- 评分模型必须通过 `tests/test_scoring_policy_20_iterations.py` 和 `tests/test_20260513_logic_readability_iterations.py` 的 30 类回归场景后才可宣称可用；这些场景覆盖结构化根因归并、接口 query/hash/动态 ID/hash 归一化、系统名归一、自动化边界零扣分、SPA 低权重、覆盖缺口封顶、模块运行失败、非生产环境降权、可信度修正、人工确认正常清零、TLS 到期分层、慢页族群封顶和可读性门禁。
- 覆盖缺口类 `module-coverage-gap` 单项扣 5 分，多模块重复只作轻微增扣并封顶 10 分；模块运行失败 `module-runtime-failure` 扣 8 分，不得把多个失败日志机械累计为多次故障。
- 非生产、测试、预发、沙箱等环境中的 `high-confidence-risk` 或高严重度信号要降权封顶，避免把开发环境问题等同于生产故障；生产核心路径的已确认 `critical` 故障仍按最高扣分处理。
- `review-needed` 必须结合 `confidence` 修正：已确认的中风险复核项高于普通待复核，低可信或疑似信号低于普通待复核；`manual-confirmed-normal` 必须清零，不得因标题或日志像故障而继续扣分。
- `tls-expiry` 必须按剩余天数分层：已过期按高可信风险处理，7 天内按紧急风险处理，30 天内按预警处理；`slow-page` 必须按慢页问题族群封顶，多个慢页面只增加证据数量和同类次数。
- 健康报告必须先给整体健康画像，同时展示健康情况数据和不健康情况数据；健康部分只保留数据型摘要，不写冗长分析。
- 正文分析重点必须集中在不健康、待复核、自动化能力边界、自动化识别不足和风险项上，健康系统与健康模块只作为基线证据收敛展示。
- HTML/Markdown 报告应提供不健康索引，列出分类、责任域、影响范围和下一证据；优先事项必须包含证据口径、业务影响、处理路径和建议动作。
- 正式 HTML 报告应包含可复制交付摘要、风险域分布、证据包清单和复测时间线，便于直接转工单、周报和复测任务。
- 管理报告不得使用“可能影响部分页面体验或需要后续排查”“请检查”“建议尽快排查”等空泛占位句作为最终影响或建议；缺少原始影响时，要写成“影响范围尚未确认”，并明确责任角色、复测证据、服务端日志和业务预期。
- 当评分不是 100 但没有可逐项展示的问题簇时，评分说明不得写“为什么是 100 分”或“未发现扣分项”；必须说明分数来自覆盖缺口、未运行模块或上游汇总扣分，并引导查看交付清单/技术附录。
- 报告中禁止暴露密码、Token、私钥、Cookie、真实 API Key 等敏感信息。
- 对登录状态、401、ERR_ABORTED、受保护跳转等自动化信号必须标注证据边界，不能直接等同生产故障。
- 若用户或人工复测确认管理员可以正常登录，`管理员登录状态未确认` / `自动化登录态信号未确认` 必须归类为自动化/MCP 操控能力边界，不得写成网站登录失败，也不得作为网站健康主要扣分项。
- 发生在自动化登录态未确认之后的受保护页面跳转，应先解释为巡检代理可能未保持有效会话；只有人工已确认登录态下仍异常跳转，才升级为网站权限或路由问题。
- 报告推荐表述：人工登录正常时，该项反映 AI/MCP 浏览器操控、登录态识别或会话保持能力不足，不是网站自身登录链路故障。
- 完成报告后运行质量审计；若发现缺少正式模板标记、重复段落、坏锚点或多个最终 HTML，必须修正后再回复用户。

## 首选一键命令

临时 URL 或带凭证深度巡检时，优先使用一键管线：

```bash
python scripts/run_health_inspection.py --url https://example.com/admin --out reports/run-001
```

带管理员账号密码的深度浏览巡检：

```bash
python scripts/run_health_inspection.py --url https://example.com/admin --username admin --password-env WEBSITE_HEALTH_ADMIN_PASSWORD --out reports/deep
```

如果用户直接给了密码，可在当前 shell 临时设置环境变量后运行，或使用 `--password` 传入；不要把密码写进报告、文档或命令回显。

```bash
python scripts/run_health_inspection.py --url https://example.com/admin --username admin --password-env WEBSITE_HEALTH_ADMIN_PASSWORD --out reports/deep
```

用户明确选择复用已有 GPT 导读图、不重新调用图片接口：

```bash
python scripts/run_health_inspection.py --url https://example.com/admin --out reports/run-001 --guide-mode reuse-existing
```

在没有可用 `image_gen` 能力或本地图片接口配置时，先向用户确认导览图方式：

```text
当前会话没有可用 image_gen，也没有可用图片接口 API Key。你希望如何处理导览图？
1. 提供自己的图片接口 API Key，用于生成 AI 导读图。
2. 不提供 API Key，使用正式 HTML/CSS 图文导览。
3. 先启用 Codex image_generation 后重试。
```

用户提供 API Key 后使用 `--guide-mode ai-image`；用户不提供或只要求先交付报告时使用 `--guide-mode html-guide`。兼容参数 `--skip-ai-guide-image` 仅等同于 `--guide-mode html-guide`，不再表示复用已有图。

可选预检当前 Codex 图片能力与用户 key 状态：

```bash
python scripts/check_image_generation_readiness.py --json
```

预检只能检测或提示启用 Codex feature flag；Skill 不能安装宿主内置 `image_gen` 工具。若 `image_generation=false`，可提示用户执行 `codex features enable image_generation` 并重启 Codex 或新开会话；若本会话仍没有可调用内置工具且用户坚持 AI 导读图，必须要求用户提供自己的 API Key。

## 多站点 N+1 模式：多个网站批量巡检

适用于用户提供多个网站，要求“每个网站一份报告 + 一份总体报告”的场景。该模式不绑定网站数量，输入可以是简单 URL Excel 或标准资源清单 Excel。

整体总报告内容规划：

- 标题必须从 `site_results` / `systems` 提取真实巡检对象生成，例如“某系统、某门户等 N 个站点健康巡检总体报告”，正文按批次治理逻辑组织；不得使用“多站点网站健康巡检总体报告”这类笼统占位标题。
- 必须覆盖：批次总览与管理结论、巡检覆盖与质量边界、站点健康分布、优先处置站点清单、共性风险与问题族、全量站点矩阵、治理建议与复测计划、交付索引与单站报告入口。
- 不得把整体总报告写成单站报告的放大版；不要在总体报告中展开管理员浏览器实测、单站截图索引、模块证据长分析、术语说明长篇或单站根因展开。需要证据时链接到单站 `delivery/final-report.html`。
- `build_overall_report()` 应写入 `report_kind: "multi-site-overall"`、`batch_metrics`、`site_results`、`priority_sites`、`common_issue_families`；`render_report.py` 应检测该字段走专用总体 HTML/Markdown 分支。

首选命令：

```bash
python scripts/run_multi_site_inspection.py --excel path/to/sites.xlsx --out reports/batch --max-workers 5 --guide-mode html-guide
```

简单 URL Excel 至少包含 `网站名称` 和 `URL`；可选包含 `负责人`、`优先级`、`备注`、`期望状态码`、`超时时间`。标准资源清单 Excel 会按网站页面拆分成独立单站巡检任务。

交付入口：

```text
reports/batch/delivery-batch/index.html
```

对外发送时必须发送整个 `delivery-batch/` 文件夹。该文件夹包含首页索引、整体总报告、批次摘要，以及每个网站自己的 `delivery/final-report.html` 和配套素材。整体报告正式入口是 `delivery-batch/overall/final-report.html`，只做聚合治理和跳转，不承载单站证据详情。单个站点失败不得阻断整个批次，应在首页和整体报告中标记为 `unknown` 或 `warning` 并保留错误原因。

## 标准模式：Excel 资源清单巡检

适用于管理员维护了 Excel 资源清单，需要按系统、站点、主机或服务批量巡检的场景。

```bash
python scripts/import_inventory_excel.py --excel path/to/inventory.xlsx --out reports/run-001
python scripts/inspect_sites.py --inventory reports/run-001/inventory.normalized.json --out reports/run-001
```

`inspect_sites.py` 默认会执行 discovery、content、deep-browser、host、merge、render。若拆分执行，最终仍必须运行：

```bash
python scripts/merge_reports.py --in reports/run-001 --out reports/run-001/final-report.json
python scripts/audit_score_reasonableness.py --report reports/run-001/final-report.json --out reports/run-001 --threshold 60
python scripts/render_report.py --report reports/run-001/final-report.json --out reports/run-001
python scripts/audit_report_quality.py --run-dir reports/run-001 --iteration 1 --out reports/run-001/quality-audit.md
```

若评分审计阻断但人工确认低分合理且没有重复扣分，可继续渲染：

```bash
python scripts/render_report.py --report reports/run-001/final-report.json --out reports/run-001 --score-review-approved --score-review-note "人工确认低分合理，未发现重复扣分"
```

可选：生成空白 Excel 模板。

```bash
python scripts/create_inventory_template.py --out assets/inventory-template.xlsx
```

## 临时 URL 模式：无凭证快速巡检

适用于用户临时提供一个 URL，希望快速检查公开页面可访问性、内容完整性和基础浏览器表现的场景。此模式不能证明登录后页面健康，也不能覆盖主机、数据库和微服务内部状态。

推荐命令：

```bash
python scripts/run_health_inspection.py --url https://example.com/admin --out reports/adhoc
```

拆分命令：

```bash
python scripts/build_adhoc_inventory.py --url https://example.com/admin --out reports/adhoc
python scripts/inspect_sites.py --inventory reports/adhoc/inventory.normalized.json --out reports/adhoc
python scripts/audit_report_quality.py --run-dir reports/adhoc --iteration 1 --out reports/adhoc/quality-audit.md
```

如需页面发现，可在构建清单后运行受控站点发现，再继续巡检：

```bash
python scripts/discover_site_pages.py --inventory reports/adhoc/inventory.normalized.json --out reports/adhoc --merge
```

## 带凭证深度浏览模式：URL + 管理员账号密码

适用于用户提供 URL、管理员用户名和密码，希望检查登录入口、登录后页面、受保护页面跳转、浏览器请求失败、截图证据链的场景。默认只读，不点击删除、审批、重启、提交业务数据等危险动作。

推荐命令：

```bash
python scripts/run_health_inspection.py --url https://example.com/admin --username admin --password-env WEBSITE_HEALTH_ADMIN_PASSWORD --out reports/deep
```

拆分命令：

```bash
python scripts/build_adhoc_inventory.py --url https://example.com/admin --username admin --password-env WEBSITE_HEALTH_ADMIN_PASSWORD --out reports/deep
python scripts/inspect_sites.py --inventory reports/deep/inventory.normalized.json --out reports/deep
python scripts/audit_report_quality.py --run-dir reports/deep --iteration 1 --out reports/deep/quality-audit.md
```

深度浏览结果应写入 `browser-inspection-report.json`。格式和交互流程可按需读取 `references/interactive-browser-inspection.md`。

## 报告生成与 AI 导读图

`render_report.py` 会生成 `final-report.html`、`final-report.pdf`、`final-report.md`，并保留 `final-report.json`。HTML 报告包含导览封面、实时数据栏、管理结论、健康总览、折叠式证据章节和技术附录；PDF 是 HTML 的打印版正式报告。

AI 导览图提示词必须按报告类型分流，而不是生成泛用运维海报。单网站报告导览图应面向管理平台管理员，表达“巡检范围 → 健康判定 → 影响面 → 不健康索引 → 模块证据 → 复测闭环”的诊断阅读路径，并可视化 Excel 资源清单巡检、临时 URL 快速巡检、URL + 管理员凭证深度浏览三类入口，以及内容完整性审查、管理员浏览器实测、主机与微服务健康检查、受控页面发现、根因归并、风险分层、证据包和 HTML/PDF/Markdown/JSON 正式交付。多站点整体总报告导览图必须按批次治理口径设计，标题必须从 `site_results` / `systems` 中提取真实巡检对象生成，例如“某系统、某门户等 N 个站点健康巡检总体报告导览”，不得使用“多站点网站健康巡检总体报告导览”这类笼统占位标题；内容突出 N+1 交付模式、批次总览、覆盖质量、站点健康分布、优先处置站点、共性风险与问题族、全量站点矩阵、复测治理和交付索引/单站报告入口，不得复用单站浏览器证据长分析叙事。两类提示词都必须显示 `generated_at` 对应的监测时间，格式为 `YYYY-MM-DD HH:mm`；如果源数据缺失，写“以报告生成时间为准”。两类提示词都必须要求 16:9 正式管理报告信息图风格、中文大字可读、克制色彩、证据链和复测动作清晰；禁止让图片包含 URL、API Key、密码、Token、Cookie、授权头、原始日志、代码片段、CSS selector、终端窗口、水印、Logo 或随机英文填充。HTML 封面实时数据栏和正文数据仍然优先于导览图中的文字。

报告生成前必须完成导读图方式确认：有可用 `image_gen` 时优先使用内置生图；没有 `image_gen` 时，必须让用户在“提供自己的图片接口 API Key”“使用 HTML/CSS 图文导览”“启用内置 image_gen 后重试”之间作出选择。未确认且无可用 API Key 时，默认命令会停止并写入 `needs_user_choice` 状态：

```bash
python scripts/render_report.py --report reports/run-001/final-report.json --out reports/run-001
```

用户提供 API Key 后使用：

```bash
python scripts/render_report.py --report reports/run-001/final-report.json --out reports/run-001 --guide-mode ai-image
```

用户不提供 API Key，或希望不调用图片接口，使用：

```bash
python scripts/render_report.py --report reports/run-001/final-report.json --out reports/run-001 --guide-mode html-guide
```

用户明确要求复用运行目录已有 `ai-report-guide.png` 时使用：

```bash
python scripts/render_report.py --report reports/run-001/final-report.json --out reports/run-001 --guide-mode reuse-existing
```

`reuse-existing` 只接受有效 `ai-report-guide.png`；缺失、空文件或普通摘要图冒充时会停止并要求重新确认。

仅调试时可加 `--no-pdf` 跳过 PDF 生成；正式交付不得使用该参数，且质量审计会把缺少 `final-report.pdf` / `delivery/final-report.pdf` 视为交付不完整。

执行状态会写入 `ai-report-guide-status.json`，供排查用，不作为管理报告正文内容：

- `generated`：AI 导读图生成成功，首页使用图片。
- `reused_existing`：用户明确选择复用已有有效导读图。
- `needs_user_choice`：无可用 API Key 且未得到用户明确导览方式选择，停止生成最终报告。
- `html_guide_selected`：用户明确选择不提供 API Key，首页使用 HTML 图文导览。
- `missing_api_key`：用户选择 AI 导读图，但当前没有可用用户 API Key。
- `missing_dependency`：用户选择 AI 导读图且 API Key 可用，但当前 Python 环境缺少 `openai` 包且自动安装失败；停止生成最终报告，修复依赖后重试。
- `failed`：图片接口调用失败，首页使用 HTML 图文导览。

注意：`ai-report-guide.png` 是阅读导览图，可能滞后于最新 JSON。HTML 封面实时数据栏和正文数据永远优先于图片中的旧数据；没有 AI 图时，以首页 HTML 图文导览为准。最终 HTML 不应出现 API Key 配置、`--guide-mode`、`--skip-ai-guide-image` 或图片接口失败说明，这些只属于 Skill 运行过程。

## 评分合理性复核

评分审计是健康检测完成后、正式报告渲染前的独立闸门，用来专门复核低分和疑似重复扣分。默认阈值为 60 分，可用 `--score-audit-threshold` 或审计脚本的 `--threshold` 显式覆盖。

```bash
python scripts/audit_score_reasonableness.py --report reports/run-001/final-report.json --out reports/run-001 --threshold 60
```

该命令会生成：

- `score-audit.json`：机读审计结果，包含 `status`、`blocking_reasons`、`duplicate_suspicions`、`recomputed_score`。
- `score-audit.md`：人工审阅说明，列出低分原因、疑似重复扣分组、当前扣分合计、建议单次扣分、疑似多扣分数、证据样本和建议归并字段。

处理规则：

- `status=pass` 后才允许进入正式 HTML/PDF/Markdown 渲染。
- `status=blocked` 时保留 `final-report.json`、`score-audit.json`、`score-audit.md`，不得生成或更新正式 `delivery/`。
- 阻断原因包含 `low_score_requires_review`、`score_mismatch`、`duplicate_penalty_suspected` 时，先复核 `score-audit.md` 中的归并建议，不得自动重写分数。
- 人工确认低分合理后，必须用 `--score-review-approved --score-review-note "..."` 继续渲染；没有 note 不允许通过。
- `render_report.py` 独立运行时会检查同目录 `score-audit.json`；低分、审计失败或审计缺失时拒绝正式渲染，除非显式批准并提供说明。
- 评分审计是渲染前门禁；`audit_report_quality.py` 是成稿后的质量门禁，两者都必须保留。

## 交付规则

- 回复用户时优先提供 `delivery/final-report.html` 与 `delivery/final-report.pdf`，并说明需要发送整个 `delivery/` 文件夹。
- 多站点 N+1 模式回复用户时优先提供 `delivery-batch/index.html`，并说明需要发送整个 `delivery-batch/` 文件夹。
- 多站点总体报告入口保持为 `delivery-batch/overall/final-report.html`，`delivery-batch/index.html` 继续作为批次首页索引并链接各站点 `sites/<slug>/delivery/final-report.html`。
- `delivery/` 是干净交付包：根目录包含 `final-report.html`、`final-report.pdf`、`final-report.json`、`final-report.md`、评分审计、质量审计和交付清单；HTML 图片在 `html-assets/`；完整截图证据在 `screenshots/`。
- HTML 报告使用相对路径引用图片，不再把图片内嵌为 data URI。只发送单个 HTML 文件会丢图，发送整个 `delivery/` 文件夹即可跨电脑正常打开。
- `render_report.py` 会同时生成富格式 `delivery-manifest.json` 和 `delivery-manifest.md`，用于核对正式入口、质量审计、导读图、PDF、文件摘要和归档草稿；最终回复应优先给 `delivery/final-report.html` 和 `delivery/final-report.pdf`。
- `score-audit.md` 与 `score-audit.json` 必须进入 `delivery/`；最终回复必须说明评分审计状态。低分报告还必须说明是否已人工复核，以及批准说明是否写入交付清单和技术附录。
- 最终回复必须说明状态/评分一致性结果；若出现 `status_score_mismatch`，不得交付正式报告。
- `audit_report_quality.py` 会生成 `quality-audit.md` 与 `quality-audit.json`；JSON 用于机读质量门禁，Markdown 用于人工审读。
- 如果运行目录中存在 `final-*-health-report.html`，它只能视为草稿或历史临时产物，不得作为最终报告链接。
- 正式渲染后若仍在运行目录根部发现 `final-*-health-report.html`，视为质量门禁失败；重新运行 `render_report.py` 归档草稿后再交付。
- 若用户反馈样式低质，先检查打开的是否为 `final-report.html`；再运行质量审计确认正式模板标记是否齐全。
- 正式 HTML 应至少包含这些标记：`guide-cover`、`report-nav`、`fold-section`、`ai-report-guide.png` 或 `html-guide-visual`。
- 阅读导航应支持当前章节高亮：用户滚动到对应模块时，导航项应通过 `aria-current` 和高亮样式标记当前位置。

## .env 配置

`.env` 放在 Skill 根目录，可参考 `.env.example`。不要把真实密钥写进报告、提交记录或用户可见文档。

- `OPENAI_API_KEY`：可选；仅在当前会话没有内置 `image_gen`、且用户仍要求 AI 导读图时，由用户提供自己的图片接口密钥。
- `OPENAI_BASE_URL`：可选；用户自己的 OpenAI 兼容接口地址。公开 Skill 和公开文档不得内置个人代理地址。
- `OPENAI_IMAGE_MODEL`：可选，导读图模型，默认 `gpt-image-2`。
- `OPENAI_IMAGE_SIZE`：可选，导读图尺寸，例如 `2048x1152`。
- `OPENAI_IMAGE_QUALITY`：可选，导读图质量，例如 `high`。
- `WEBSITE_HEALTH_ADMIN_PASSWORD`：可选，管理员深度浏览巡检密码环境变量。

配置存在且 `OPENAI_API_KEY` 看起来可用时，`render_report.py --guide-mode ai-image` 会先确保 `openai` Python 包可用，缺包时自动安装，然后通过 `generate_ai_report_guide_image.py` 尝试生成 `ai-report-guide.png`；空值、占位值会触发停止并要求用户提供有效配置，依赖安装失败会停止并要求修复环境，只有图片接口调用失败才会记录到 `ai-report-guide-status.json` 并渲染 HTML 图文导览兜底。

## 质量审计命令

生成报告后，运行质量审计：

```bash
python scripts/audit_report_quality.py --run-dir reports/run-001 --iteration 1 --out reports/run-001/quality-audit.md
```

质量审计重点包括：

- 是否使用正式模板，而不是临时手写 HTML。
- 折叠章节是否存在，默认阅读长度是否被压缩。
- 是否有重复段落、重复结论或机械化建议。
- 是否已经存在 `score-audit.md/json`，且评分审计已通过或低分已人工批准；质量审计只复查成稿表达，不能替代渲染前评分闸门。
- `overall_status`、系统矩阵状态和评分语义是否一致；不得出现 `100 分但告警` 或 `非 100 分但健康` 这类状态/评分冲突。
- 评分说明是否采用根因封顶口径，避免同一根因在多个页面、请求或模块中重复扣分；若 `final-report.json` 分数与评分根因表扣分合计不一致，必须回到评分审计阶段处理后重新渲染。
- 是否存在空泛占位话术，例如“可能影响部分页面体验或需要后续排查”“请检查”“建议尽快排查”“Review needed”；出现时必须改成可执行的影响范围、责任角色、证据清单和复测动作。
- 导航锚点是否失效。
- 阅读导航是否具备当前章节高亮能力。
- AI 导读图是否只引用一次；若未生成 AI 图，首页是否存在 `html-guide-visual` HTML 导览。
- 最终 HTML 是否避免出现 API Key 配置、`--guide-mode`、`--skip-ai-guide-image` 或图片接口失败等运行过程提示。
- 交付摘要是否提供复制控件，便于转入工单、周报或复测沟通。
- 浏览器实测模块是否覆盖登录链路、截图和受保护页面证据。
- 带浏览器实测时，HTML/Markdown 是否展示“性能快照/打开时间”，且 `browser-inspection.metrics` 是否包含平均打开时间、最慢页面和慢页面数。
- 报告是否存在乱码占位符、时区后缀或旧封面残留。
- 报告是否出现疑似 API Key、Token、Cookie、Secret 等敏感字符串。
- 运行目录是否存在容易误打开的非正式 `final-*-health-report.html`。
- 是否存在 `delivery-manifest.json` 和 `delivery-manifest.md`，并明确正式入口与归档草稿。
- 是否生成 `delivery/final-report.html`、`delivery/final-report.pdf`、`delivery/html-assets/` 和 `delivery/screenshots/`。
- HTML 图片是否全部引用 `./html-assets/...`，不得出现本机绝对路径或 `data:image/`。
- `delivery/` 根目录不得堆放散乱图片，截图必须进入 `screenshots/`。

## 安全规则

- 管理员浏览器流程默认只读。
- 除非 `allow_mutation` 显式为 `true`，否则阻止删除、审批、重启、提交业务数据等危险动作。
- 临时 URL 模式在缺少凭证时不能宣称覆盖登录后页面健康。
- 未配置主机凭证或服务清单时，不能宣称覆盖主机、数据库、DNS、TLS 深度校验、性能压测或微服务内部健康。
- 主机检查只使用 `auth_ref` 凭证引用，真实凭证从环境变量或平台密钥系统解析。
- 如果依赖缺失或某模块无法执行，应生成 `unknown` 或带说明的部分报告，不能悄悄忽略检查缺口。

## 参考文档

根据任务只读取必要文档：

- Excel 字段规范：`references/inventory-excel-schema.md`
- 标准资源清单结构：`references/inventory-normalized-schema.md`
- 直接 URL 模式：`references/url-adhoc-mode.md`
- 受控页面发现：`references/site-discovery.md`
- 巡检总流程：`references/inspection-flow.md`
- 网站内容审查：`references/content-review.md`
- 管理员浏览器流程：`references/browser-availability.md`
- 主机与微服务健康检查：`references/host-service-health.md`
- 子报告结构：`references/sub-report-schema.md`
- 总报告结构：`references/final-report-schema.md`
- 严重度模型：`references/severity-model.md`
- 管理报告写作：`references/report-writing.md`
- HTML 报告设计：`references/report-design.md`
- 管理摘要图：`references/executive-summary-image.md`
- 交互式浏览器深度巡检：`references/interactive-browser-inspection.md`
