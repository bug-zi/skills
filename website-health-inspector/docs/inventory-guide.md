# 资源清单指南

巡检系统的稳定入口是 `inventory.normalized.json`。Excel、临时 URL 和页面发现结果都应先转换或合并到这个结构中，再交给检查模块执行。

## 输入路径

临时 URL：

```powershell
python scripts/build_adhoc_inventory.py --url https://example.com/admin --out runs/adhoc
```

Excel：

```powershell
python scripts/import_inventory_excel.py --excel path\to\inventory.xlsx --out runs/inventory-run
```

受控页面发现并合并：

```powershell
python scripts/discover_site_pages.py --inventory runs/adhoc/inventory.normalized.json --out runs/adhoc --merge
```

## Excel Sheet

Excel 工作簿建议使用固定 Sheet 名称和字段。

`系统清单`：

- `system_id`：系统唯一标识。
- `system_name`：报告展示名称。
- `priority`：`critical`、`high`、`medium`、`low`。
- `owner`：责任人或责任组。
- `environment`：`prod`、`staging`、`test` 等。
- `enabled`：`yes` 或 `no`。
- `remark`：备注。

`网站页面`：

- `system_id`：关联的系统。
- `page_id`：页面唯一标识。
- `page_name`：页面名称。
- `url`：检查 URL。
- `expected_status`：期望 HTTP 状态码。
- `timeout_ms`：超时时间。
- `enabled`：是否启用。

`内容检查规则`：

- `system_id`、`page_id`：关联页面。
- `required_text`：必须出现的文本，多个值用分号分隔。
- `forbidden_text`：禁止出现的异常文本，多个值用分号分隔。
- `min_length`：页面正文最小长度。
- `rule_enabled`：规则是否启用。

`管理员功能流程`：

- `flow_id`、`system_id`、`flow_name`、`step_order`。
- `action`：支持 `goto`、`click`、`fill`、`wait_for`、`expect_text`、`expect_url_contains`、`expect_selector`。
- `target`、`value`、`expect`、`enabled`。

`主机清单`：

- `host_id`、`system_id`、`host_name`、`ip`、`port`、`auth_ref`、`enabled`。

`微服务清单`：

- `service_id`、`system_id`、`host_id`、`service_name`、`check_type`、`check_target`、`expected`、`enabled`。
- `check_type` 第一版支持 `http`、`port`，并预留 `systemd`。

`凭证引用`：

- `auth_ref`、`auth_type`、`env_keys`、`remark`。
- 这里只能写凭证引用和环境变量名称，不能写真实密钥。

`全局配置`：

- `default_timeout_ms`
- `max_parallel`
- `report_language`
- `allow_mutation`
- `screenshot_on_failure`
- `crawler_enabled`
- `crawler_max_depth`
- `crawler_max_pages`

## 标准 JSON 结构

`inventory.normalized.json` 顶层结构：

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

## 校验重点

导入时应阻止或明确报告以下问题：

- 缺少必要 Sheet 或字段。
- `system_id`、`page_id`、`host_id` 引用不存在。
- URL、端口、状态码、超时时间非法。
- `allow_mutation=false` 时出现危险动作。
- Excel 中出现疑似明文密码、Token、私钥等敏感内容。
- 同一个系统、页面或主机标识重复。

