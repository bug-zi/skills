# Excel 资源清单字段规范

管理员通过 `.xlsx` 工作簿维护巡检对象。工作簿中的 Sheet 名称建议保持固定，脚本会按这些名称读取。

## Sheet 结构

### 系统清单

必填字段：`system_id`、`system_name`、`priority`、`owner`、`environment`、`enabled`、`remark`。

- `system_id`：系统唯一标识，其他 Sheet 通过它关联。
- `system_name`：报告中展示的系统名称。
- `priority`：系统重要性，支持 `critical`、`high`、`medium`、`low`。
- `owner`：责任人或责任组。
- `environment`：环境，例如 `prod`、`staging`、`test`。
- `enabled`：是否启用，支持 `yes`、`no`。

### 网站页面

必填字段：`system_id`、`page_id`、`page_name`、`url`、`expected_status`、`timeout_ms`、`enabled`。

每一行表示一个需要巡检的网站页面。启用行会进入网站可访问性与内容审查流程。

### 内容检查规则

必填字段：`system_id`、`page_id`、`required_text`、`forbidden_text`、`min_length`、`rule_enabled`。

- `required_text`：页面必须出现的文本，多个值用分号分隔。
- `forbidden_text`：页面不能出现的异常文本，多个值用分号分隔。
- `min_length`：页面正文最小长度，低于该值视为内容可能不完整。

### 管理员功能流程

必填字段：`flow_id`、`system_id`、`flow_name`、`step_order`、`action`、`target`、`value`、`expect`、`enabled`。

支持动作：`goto`、`click`、`fill`、`wait_for`、`expect_text`、`expect_url_contains`、`expect_selector`。

流程用于模拟管理员只读操作路径，例如登录、进入后台首页、打开用户管理页、查看审计日志等。

### 主机清单

必填字段：`host_id`、`system_id`、`host_name`、`ip`、`port`、`auth_ref`、`enabled`。

`auth_ref` 是凭证引用，不是明文密码。真实凭证应放在环境变量、平台密钥管理系统或堡垒机中。

### 微服务清单

必填字段：`service_id`、`system_id`、`host_id`、`service_name`、`check_type`、`check_target`、`expected`、`enabled`。

第一版支持的 `check_type`：

- `http`：检查健康接口状态码。
- `port`：检查 TCP 端口是否可达。
- `systemd`：预留远程 systemd 服务状态检查。

### 凭证引用

必填字段：`auth_ref`、`auth_type`、`env_keys`、`remark`。

Excel 中只记录凭证引用和环境变量名称，不记录真实密码、Token、私钥内容。

### 全局配置

必填字段：`key`、`value`。

推荐配置项：

- `default_timeout_ms`
- `max_parallel`
- `report_language`
- `allow_mutation`
- `screenshot_on_failure`
- `crawler_enabled`
- `crawler_max_depth`
- `crawler_max_pages`

## 校验规则

导入时应阻止以下问题：

- 缺少必要 Sheet。
- 缺少必要字段。
- `system_id`、`page_id`、`host_id` 引用不存在。
- URL、端口、状态码、超时时间非法。
- 管理员功能流程包含危险动作，且 `allow_mutation=false`。
- Excel 中出现疑似明文密码、Token、私钥等敏感内容。

