# 子报告结构

每个检查模块都必须输出 JSON 子报告。

子报告结构：

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

浏览器实测模块应在 `metrics` 中汇总轻量性能观测：

```json
{
  "checked_pages": 0,
  "avg_open_time_ms": 0,
  "max_open_time_ms": 0,
  "slow_pages": 0,
  "avg_ttfb_ms": 0,
  "max_ttfb_ms": 0
}
```

`browser-inspection.visited_pages[]` 应包含 `performance` 字段：

```json
{
  "label": "entry-before-login",
  "url": "https://example.com/",
  "performance": {
    "open_time_ms": 0,
    "ttfb_ms": 0,
    "dom_content_loaded_ms": 0,
    "load_event_ms": 0,
    "transfer_size_bytes": 0,
    "encoded_body_size_bytes": 0,
    "resource_count": 0
  }
}
```

性能字段允许为 `null`，表示当前浏览器或目标页面未提供该时序。`open_time_ms` 是从导航开始到 `networkidle` 的单次墙钟耗时；它是巡检快照，不是压测结果。

问题项结构：

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

要求：

- `business_impact` 必须使用管理员能理解的语言。
- `technical_evidence` 可以包含技术细节，但不得包含敏感信息。
- `evidence_files` 可以引用截图、日志片段或其他证据文件。
