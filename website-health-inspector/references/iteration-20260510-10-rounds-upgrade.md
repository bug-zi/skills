# 2026-05-10 十轮升级迭代记录

本轮升级基于一次真实 URL + 管理员凭证深度巡检暴露的问题，对 `website-health-inspector` 做 10 个可测试、可复用的小迭代。目标是提高页面覆盖、降低 SPA 误报、避免登录态误判，并把敏感信息防泄露前移到公共写入层。

## 10 轮迭代

1. 公共 JSON 脱敏：`health_common.write_json()` 在写入结构化报告前递归脱敏密码、Token、API Key、Cookie、Authorization 等字段。
2. 显式 secret 脱敏：新增 `scrub_sensitive_text()` / `scrub_sensitive_data()`，支持把本轮用户提供的明文密码加入脱敏名单，同时保留 `password_env` 这类安全引用。
3. 浏览器采集脱敏：`check_deep_browser.clean_text()`、console、request failure 等浏览器证据文本统一走脱敏逻辑。
4. 渲染后页面判定：新增 `rendered_route_utils.py`，识别 `in_app_404`、`http_404`、`server_error`、`empty_render`、`rendered_ok` 等页面状态，避免只看 HTTP 200。
5. 参数化路由边界：新增 `route_requires_parameters()`，将 `/courses/:id`、`/projects/{projectId}` 等归为覆盖边界，而不是误判为真实坏页。
6. JS bundle 路由发现：`discover_site_pages.py` 可从同源脚本中提取 SPA 静态路由，并记录参数化路由。
7. 深度浏览入口扩展：`check_deep_browser.py` 增加公共页脚、证书、数据集、工作台、系统设置、项目中心、用户管理等种子入口，并把自动浏览上限从 10 提升到 25。
8. 登录成功信号增强：浏览器模块新增 `login_status_from_signals()`，把成功的登录/认证接口 2xx 与页面导航/身份信号结合，降低“登录成功但识别未知”的误判。
9. 根因归类结构化：`merge_reports.py` 与 `render_report.py` 支持 `category` / `cluster_key` / `finding_type` 元数据，英文标题或结构化发现也能稳定归到 `front-route-404`、`parameterized-route-boundary` 等根因。
10. 质量审计加严：`audit_report_quality.py` 扫描 HTML、Markdown、根 JSON、交付 JSON/Markdown/HTML 的疑似 secret，并新增 `login_status_consistent`，防止“浏览器模块已登录成功但报告仍提示登录未确认”的矛盾。

## 新增回归测试

新增 `tests/test_20260510_upgrade_iterations.py`，覆盖：

- 明文密码、Bearer token、OpenAI key 脱敏且不污染原始对象。
- 浏览器文本采集脱敏。
- 渲染后 404 与参数化路由识别。
- 深度浏览种子入口覆盖公共页脚和后台常用入口。
- 登录 2xx 信号参与成功判定。
- 质量审计识别登录态矛盾与交付 JSON secret。
- 根因评分对参数化路由边界不扣分。
- JS bundle 的 SPA 路由发现。

## 验证结果

已执行：

```bash
python -m pytest tests\test_20260510_upgrade_iterations.py -q
python -m pytest -q
python -m compileall scripts tests
```

结果：

- 新增回归测试：8 passed
- 全量测试：17 passed
- 脚本与测试编译：通过

## 使用影响

- 生成报告时，结构化 JSON 默认更安全；报告中不应再出现用户提供的管理员密码或常见 secret。
- 对 SPA 网站，静态 HTTP 内容过短仍会保留为低可信边界提示，最终判断更依赖浏览器渲染证据。
- 深度浏览会默认覆盖更多公开与管理入口，但仍保持只读，跳过 logout/delete/remove/payment 等危险路径。
- 参数化详情页不会因缺少业务 ID 被当作主要故障扣分。
- 质量审计失败时应优先修复 `no_secret_like_text` 和 `login_status_consistent`。
