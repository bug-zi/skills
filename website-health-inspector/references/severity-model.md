# 严重度与优先级模型

最终优先级不能简单照搬单个模块的局部判断，应在总报告阶段重新计算。

参考因素：

- 技术严重度。
- 系统重要性。
- 业务影响。
- 影响范围。
- 证据可信度。
- 是否为生产环境。
- 是否影响管理员核心操作路径。

默认映射：

- 关键系统的管理后台不可登录或核心服务不可用：`P1`。
- 高优先级系统出现内容缺失、页面异常或响应明显变慢：`P2`。
- 中低影响范围的问题：`P3`。
- 信息性问题或覆盖不足：`P4`。

健康评分默认从 100 分开始扣减：

- `critical`：扣 35 分。
- `high`：扣 25 分。
- `medium`：扣 12 分。
- `low`：扣 5 分。
- 模块覆盖不足：扣 5 分。

分数用于快速判断整体趋势，不应替代人工风险判断。

健康状态与评分一致性：

- 健康状态以有效扣分簇为准，而不是原始 finding 数量或子模块 `status`。
- `score == 100` 且没有正扣分簇时，状态必须是 `healthy`。
- 有正扣分簇但没有已确认严重条件时，状态为 `warning`。
- 存在 `critical` / `confirmed-outage` 有效扣分，或总分低于 60 时，状态为 `critical`。
- 无可用模块结果、站点未执行、URL 无效或未生成报告时，状态为 `unknown`。
- 自动化边界、会话边界、参数化路由边界、人工确认正常等零扣分项不得把状态顶成告警。
- 质量审计结果只进入 `quality_status` 和交付质量门禁，不改变健康状态。

根因封顶补充规则：

- 总分以 `scripts/scoring_model.py` 为唯一口径，合并阶段和渲染阶段必须共用它。
- 聚类前先规范化 `system_id` / `system_name`、URL、HTTP 方法、query、hash、尾部斜杠、数字 ID、UUID、ObjectId 和静态资源构建 hash。
- 同一根因或同一接口族只扣一次；重复页面、重复请求和重复日志只增加同类次数、证据和目标列表。
- `manual-confirmed-normal` 或人工确认正常必须清零；低可信高危信号先按复核权重处理，不能直接按高危扣分。
- 评分模型必须通过 30 类回归：`tests/test_scoring_policy_20_iterations.py` 和 `tests/test_20260513_logic_readability_iterations.py`。

评分合理性复核：

- `merge_reports.py` 生成 `final-report.json` 后，必须先运行 `scripts/audit_score_reasonableness.py`，再进入正式渲染。
- 审计会重算 `final-report.json.score`，并用严格聚类和宽松接口族相似聚类检查疑似重复扣分。
- `score < 60`、重算分数不一致、状态与评分不一致或疑似重复扣分会阻断正式 HTML/PDF 交付；审计只输出证据和归并建议，不自动改分。
- 人工确认低分合理时，用 `--score-review-approved --score-review-note "..."` 继续渲染，并把说明写入交付清单和技术附录。
