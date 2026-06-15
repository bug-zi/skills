# 总报告结构

`final-report.json` 用于整合所有模块结果。

结构示例：

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
  "score_review": {},
  "artifacts": {}
}
```

总报告职责：

- 合并所有子报告。
- 去重相同或关联问题。
- 使用同一套有效扣分模型重新计算整体状态和健康评分。
- 生成管理摘要。
- 为 HTML、Markdown 和摘要图提供统一数据。
- 渲染前记录评分合理性复核结果；低分人工批准时，`score_review` 应包含批准状态和说明。

总报告应优先服务管理阅读，原始技术证据放在详情或附录中。

配套评分审计产物：

- `overall_status` 必须与 `score` 和有效扣分簇一致；`100 分但 warning` 属于 `status_score_mismatch`。
- `score-audit.json`：包含 `status`、`blocking_reasons`、`duplicate_suspicions`、`recomputed_score`、`reported_status`、`expected_status`、`status_reasons` 和阈值。
- `score-audit.md`：面向人工复核，解释低分、状态/评分不一致、疑似重复扣分组和下一步归并建议。
