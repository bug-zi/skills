# agnes-ai-generation-skill 研究说明

## 使用条件

这个 skill 适合在明确要使用 Agnes AI / Sapiens AI 的生成 API 时启用，尤其是用户提到 Agnes、Agnes Image、Agnes Video、Agnes 2.0 Flash、`apihub.agnes-ai.com`，或明确要求“用 Agnes”完成文本、图片、图片编辑、视频、图片转视频、关键帧视频、API 测试等任务。

可用前置条件：

- 已安装到当前 agent 的 skills 目录，并能被客户端加载。
- 本机可运行 Python 3，脚本入口为 `scripts/agnes_api.py`。
- 网络环境能访问 `https://apihub.agnes-ai.com`。
- 已有 Agnes API Key，并通过环境变量提供：`AGNES_API_KEY`、`AGNES_API_TOKEN` 或 `APIHUB_AGNES_API_KEY`。
- 图片转图片、图片转视频、多图视频、关键帧视频需要可被 Agnes API 访问的图片 URL。
- 视频生成需要接受异步任务模式：先创建任务，再轮询或用 task id 查询结果。
- 视频参数必须满足脚本校验：`num_frames <= 441` 且满足 `8n + 1`，`frame_rate` 范围为 `1-60`，宽高为正整数。

不适合或应暂停使用的情况：

- 用户没有明确要用 Agnes，且系统已有更合适的内置图片或视频生成工具。
- 没有 API Key，或用户不愿把 key 配置到当前可信环境。
- 网络无法访问 Agnes API 网关。
- 输入图片只有本地文件路径但没有可公网访问 URL，且用户未要求上传或转换。
- 用户不能接受视频生成的等待时间、费用或第三方服务处理内容。
- 严格要求工具调用一定返回 `tool_calls`；该 skill 只确认 Agnes 接收 OpenAI 兼容工具调用请求，实际返回不稳定。
- 多图视频和关键帧视频需要高可靠交付时，应先单独 smoke test，因为最新说明里未完整重测所有端到端完成 URL。

## 1. 这个 skill 是什么，提供什么功能？

这是一个 Agnes AI 生成 API 封装 skill。它让支持 Agent Skills 的客户端通过 `https://apihub.agnes-ai.com` 调用 Agnes 文本、图像和视频模型。

主要功能：

- 文本生成：`agnes-2.0-flash`
- 流式文本输出
- OpenAI 兼容工具调用请求结构
- 文生图：`agnes-image-2.1-flash`
- 图生图 / 图片编辑：`agnes-image-2.1-flash`
- 高信息密度图片生成
- 文生视频：`agnes-video-v2.0`
- 图生视频：`agnes-video-v2.0`
- 多图视频生成
- 关键帧动画
- 视频任务创建、轮询和结果查询
- 非英文图片/视频提示词自动翻译成英文提示词

## 2. 结构、注入方式和流程

文件结构：

```text
SKILL.md
README.md
README_EN.md
LICENSE
agents/openai.yaml
references/api.md
scripts/agnes_api.py
```

`SKILL.md` 是注入给 agent 的主要说明，定义触发范围、模型选择、API key 要求、工作流和注意事项。`references/api.md` 是 API 端点和参数速查。`scripts/agnes_api.py` 是实际执行请求的 Python CLI。`agents/openai.yaml` 提供显示名、短描述和默认提示。

典型流程：

1. 用户明确要求使用 Agnes 或提出 Agnes 适配的生成任务。
2. agent 读取 `SKILL.md`，需要参数细节时读取 `references/api.md`。
3. agent 检查 API key 环境变量。
4. 图片和视频任务若含非英文提示词，脚本默认先调用文本模型翻译为英文。
5. 文本和图片任务同步返回结果；视频任务先创建异步任务，再轮询或查询 task id。
6. 脚本输出整理后的 JSON，并保留 Agnes 原始响应在 `raw` 字段中。

## 3. 优点

- 覆盖文本、图片、视频三类 Agnes API。
- 提供可直接运行的 Python CLI，agent 不需要临时拼 curl。
- 默认保护 API key，不应打印 key。
- 对图片尺寸、视频帧数、帧率、宽高做了基础校验。
- 针对中文用户友好，图片和视频提示词可自动翻译为英文。
- 视频异步流程封装清楚，支持创建、轮询、查询。
- smoke test 支持逐项验证，默认不会直接创建视频任务。

## 4. 弱点和限制

- 强依赖 Agnes 外部服务、API key、网络和账户状态。
- 视频生成可能耗时、失败或产生费用。
- 多图视频和关键帧视频虽然脚本支持，但最新说明里未完整端到端重测所有完成 URL。
- 工具调用请求兼容 OpenAI 结构，但 Agnes 不一定稳定返回 `tool_calls`。
- 图片和视频输入依赖 URL；本地图片路径不能直接作为 API 输入。
- 自动翻译可能让复杂中文视觉提示产生细微语义漂移。
- 这不是生产级 SDK，没有完整的队列、限流、成本控制、缓存或审计机制。

## 5. 适合和不适合的人群

适合：

- 已有 Agnes API Key，并想在 Codex、Claude Code、OpenClaw、Cursor、Windsurf 等 agent 中调用 Agnes 的用户。
- 需要快速做文生图、图生图、文生视频、图生视频实验的创作者或开发者。
- 希望用统一命令测试 Agnes 文本、图片、视频 API 的开发者。

不适合：

- 没有 Agnes API Key 或不想把 key 放入 agent 执行环境的用户。
- 只想使用本地模型或内置生成工具的用户。
- 对生成结果稳定性、成本审计、数据合规有生产级要求的团队。
- 需要直接处理本地私有图片、但不愿上传或提供可访问 URL 的用户。

## 6. 实际场景和主要解决的痛点

适用场景：

- 用 Agnes 生成产品图、插画、封面、视觉素材。
- 将已有图片改成指定风格或场景。
- 把图片动画化为短视频。
- 生成关键帧转场或多图过渡视频。
- 验证 Agnes API Key、模型端点和响应格式是否可用。
- 在多个 agent 客户端中复用同一套 Agnes 调用方式。

主要解决的痛点是：agent 想调用 Agnes API 时，不必临时查文档、拼请求、处理异步视频任务和解析响应。

## 7. prompt 污染、效率和安全风险

Prompt 污染风险：中低。`SKILL.md` 不算大，触发描述比较集中，但其中也包含“generate text/images/videos”等较宽泛措辞；如果环境中已有其他图像或视频 skill，最好在请求中明确“使用 Agnes”来避免误触发或工具选择摇摆。

效率风险：中低。脚本封装能减少 agent 临场摸索；但真实视频任务会等待较久，轮询会占用执行时间。

安全风险：中等。风险主要来自 API key、外部网络请求和用户内容发往第三方服务。API key 应只放在环境变量中，不应写入仓库、日志、截图或公开聊天。涉及隐私、商业机密或受监管数据时，不建议直接使用第三方生成 API。

