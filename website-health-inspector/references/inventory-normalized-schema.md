# 标准资源清单结构

所有检查模块只读取 `inventory.normalized.json`，不要直接读取 Excel。

顶层结构：

```json
{
  "generated_at": "ISO-8601 时间",
  "source": {
    "type": "excel 或 adhoc-url",
    "path": "来源路径或 URL"
  },
  "systems": [],
  "global": {}
}
```

系统对象：

```json
{
  "id": "admin-platform",
  "name": "统一管理平台",
  "priority": "critical",
  "owner": "运维组",
  "environment": "prod",
  "websites": [],
  "admin_flows": [],
  "hosts": [],
  "services": []
}
```

网站页面对象：

```json
{
  "page_id": "login",
  "name": "登录页",
  "url": "https://example.com/login",
  "expected_status": 200,
  "timeout_ms": 5000,
  "content_checks": {
    "required_text": ["登录"],
    "forbidden_text": ["404", "500", "系统维护"],
    "min_length": 500
  }
}
```

全局配置示例：

```json
{
  "allow_mutation": false,
  "screenshot_on_failure": true,
  "max_parallel": 5,
  "crawler": {
    "enabled": true,
    "max_depth": 1,
    "max_pages": 20
  }
}
```

该文件是巡检系统的稳定执行入口。Excel、临时 URL、页面发现结果都应先转换或合并到该结构中。

