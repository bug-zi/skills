# 配置与安全

Website Health Inspector 默认按只读巡检设计。配置目标是让脚本能够访问必要资源，同时避免把凭证、Token、Cookie 或真实 API Key 写进报告和文档。

## 环境变量

`.env.example` 提供可选图片接口配置示例。只有当前 Codex 会话没有内置 `image_gen`、且用户仍要求 AI 导读图时，才需要由用户提供自己的图片接口配置：

```text
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_SIZE=2048x1152
OPENAI_IMAGE_QUALITY=high
WEBSITE_HEALTH_ADMIN_PASSWORD=
```

常用变量：

- `OPENAI_API_KEY`：可选；仅在没有内置 `image_gen` 且用户仍要求 AI 导读图时，由用户提供自己的图片接口密钥。
- `OPENAI_BASE_URL`：可选；用户自己的 OpenAI 兼容接口地址，公开文档不得内置个人代理地址。
- `OPENAI_IMAGE_MODEL`：可选，导读图模型。
- `OPENAI_IMAGE_SIZE`：可选，导读图尺寸，例如 `2048x1152`。
- `OPENAI_IMAGE_QUALITY`：可选，导读图质量，例如 `high`。
- `WEBSITE_HEALTH_ADMIN_PASSWORD`：可选，管理员深度浏览巡检密码。

`.env` 已在 `.gitignore` 中忽略，不要提交真实密钥。空值、占位值和示例 key 不能视为可用配置。

## 凭证传递

推荐使用 `--password-env`：

```powershell
Read-Host "Admin password" -MaskInput | ForEach-Object { [Environment]::SetEnvironmentVariable("WEBSITE_HEALTH_ADMIN_PASSWORD", $_, "Process") }
python scripts/run_health_inspection.py --url https://example.com/admin --username admin --password-env WEBSITE_HEALTH_ADMIN_PASSWORD --out runs/deep
```

不推荐把真实密码放进命令行、报告、Markdown 文档或截图说明。若不得不临时使用 `--password`，交付前必须确认报告和质量审计中没有泄露。

Excel 的 `auth_ref` 只能保存凭证引用，不能保存真实密码、Token、私钥或 Cookie。

## 只读原则

管理员浏览器流程默认只读。除非资源清单或全局配置中明确允许 `allow_mutation=true`，否则不得执行这些动作：

- 删除、禁用、审批、发布、重启。
- 提交会改变业务数据的表单。
- 批量导入、批量修改或权限变更。
- 触发真实通知、真实支付、真实外部调用。

巡检报告应说明“本次浏览器检查为只读路径验证”，避免读者误解为完整业务验收。

## 证据边界

自动化信号必须谨慎表述：

- `401`、`403`、`ERR_ABORTED`、受保护页面跳转，不应直接等同生产故障。
- 自动化未捕获登录态时，应写成“自动化登录态信号未确认”或“巡检代理会话保持待复核”。
- 如果人工复测确认管理员能正常登录，该项应归类为自动化/MCP 操控能力边界，不得写成网站登录失败。
- 只有人工已确认登录态下仍异常跳转，才可升级为网站权限或路由问题。

推荐表述：

```text
人工登录验证正常；自动化巡检未捕获稳定登录态信号，属于巡检代理识别或会话保持能力边界，不构成网站登录故障。
```

## 敏感信息检查

交付前确认：

- 报告中没有密码、Token、私钥、Cookie、真实 API Key。
- 截图没有暴露个人敏感信息、后台密钥或业务隐私。
- `delivery-manifest.md` 没有记录明文凭证。
- `quality-audit.md` 没有把疑似密钥原文展开。
- 运行目录中不保留容易误交付的临时 HTML。

质量审计脚本会检查常见敏感字符串，但它不能替代人工审阅。

## AI 导读图配置

报告渲染前必须先确认导读图方式。`render_report.py` 在默认 `--guide-mode auto` 下，如果没有可用 API Key，会停止并要求先询问用户，而不是自行降级为 HTML 图文导览。

用户提供 API Key 后生成 AI 导读图：

```powershell
python scripts/render_report.py --report runs/adhoc/final-report.json --out runs/adhoc --guide-mode ai-image
```

`ai-image` 模式会先检查当前 Python 环境是否可导入 `openai`，缺包时自动执行 `python -m pip install openai`。如果依赖安装失败，脚本会写入 `ai-report-guide-status.json` 的 `missing_dependency` 状态和 `ai-report-guide-dependency-error.txt`，并停止生成最终报告；这属于运行环境待修复，不能直接降级为 HTML 图文导览。只有依赖可用后，真实图片接口调用失败，才允许记录 `failed` 并使用 HTML 图文导览兜底。

用户明确不提供 API Key 时，交付 HTML 图文导览：

```powershell
python scripts/render_report.py --report runs/adhoc/final-report.json --out runs/adhoc --guide-mode html-guide
```

可先预检当前环境：

```powershell
python scripts/check_image_generation_readiness.py --json
```

预检只负责读取 `codex features list` 和本地用户配置；Skill 不能安装 Codex 宿主内置 `image_gen` 工具。若 `image_generation` 为 `false`，可提示执行 `codex features enable image_generation` 并重启 Codex 或新开会话；若仍无内置工具，必须先让用户选择提供自己的 API Key、使用 HTML 图文导览或启用内置生图后重试。

AI 导读图只是阅读辅助，可能滞后于最新 JSON。正式结论以 `final-report.json`、HTML 封面实时数据栏和正文为准。
