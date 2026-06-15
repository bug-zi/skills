# anysearch skill 研究报告

## 研究范围

本次只研究本地已安装的 `D:\Code\skills\anysearch` skill，没有安装、同步、修复、删除或改写其他技能。

已检查的本地文件：

- `SKILL.md`
- `README.md`
- `runtime.conf`
- `runtime.conf.example`
- `.env.example`
- `.gitignore`
- `scripts/anysearch_cli.py`
- `scripts/anysearch_cli.js`
- `scripts/anysearch_cli.ps1`
- `scripts/anysearch_cli.sh`
- `scripts/generate.py`
- `scripts/shared/doc_spec.md`
- `scripts/shared/constants.json`

外部核验来源：

- AnySearch 官方站点将其描述为面向 AI agent 的搜索基础设施，支持匿名访问、智能路由、结构化输出、API、MCP 和 Skill 集成。
- GitHub 仓库标题与本地 README 的定位一致：这是一个面向 AI agent 的统一实时搜索 skill。

本次没有执行真实 `search`、`list_domains`、`batch_search` 或 `extract` API 调用；只运行了离线 `doc` 命令和本地生成一致性检查。

## 1. 这个 skill 是做什么的，提供什么功能？

`anysearch` 是一个给 AI agent 使用的实时搜索 skill。它把 AnySearch 云端搜索服务封装成本地跨平台 CLI，让 agent 不需要安装 MCP server，也能通过命令行调用搜索、垂直领域搜索、批量搜索和网页内容提取。

它主要提供这些功能：

- 通用网页搜索：用自然语言查询当前信息、新闻、资料、文档、网页结果等。
- 垂直领域搜索：针对 `finance`、`academic`、`legal`、`code`、`health`、`travel`、`geo` 等领域，先用 `list_domains` 查询可用 `sub_domain` 和查询格式，再执行更结构化的搜索。
- 内容类型过滤：支持 `web`、`news`、`code`、`doc`、`academic`、`data`、`image`、`video`、`audio`。
- 时间过滤：支持 `day`、`week`、`month`、`year`。
- 批量搜索：`batch_search` 可以一次提交多个独立查询，适合并行查多个主题。
- URL 内容提取：`extract` 可以读取 HTML 页面全文并以 Markdown 输出，结果会截断到约 50,000 字符。
- 离线接口说明：`doc` 命令本地读取 `scripts/shared/doc_spec.md` 和 `constants.json`，输出 agent 可读的命令规格。
- API key 管理：支持 `--api_key`、skill 目录 `.env`、系统环境变量和匿名访问。优先级是 `--api_key` > `.env` > 环境变量 > 匿名访问。

当前本地 `runtime.conf` 指定运行时为 Python，命令为：

```text
python D:/Code/skills/anysearch/scripts/anysearch_cli.py
```

## 2. 这个 skill 的结构、文件内容、注入方式和流程是什么？

目录结构可以概括为：

```text
anysearch/
  SKILL.md
  README.md
  runtime.conf
  runtime.conf.example
  .env
  .env.example
  .gitignore
  scripts/
    anysearch_cli.py
    anysearch_cli.js
    anysearch_cli.ps1
    anysearch_cli.sh
    generate.py
    shared/
      doc_spec.md
      constants.json
```

核心文件作用：

- `SKILL.md`：agent 注入用的主提示文件，定义 skill 元信息、触发场景、命令速查、API key 规则、平台检测和错误处理策略。
- `README.md`：给人看的安装、配置和验证说明。
- `runtime.conf`：当前环境的预检测运行时配置。这个文件存在时，agent 应优先直接使用其中的命令。
- `runtime.conf.example`：运行时配置模板。
- `.env`：本地 API key 配置文件，会被 CLI 自动加载。该文件被 `.gitignore` 忽略。
- `.env.example`：API key 配置示例。
- `.gitignore`：忽略 `.env`、`runtime.conf`、`__pycache__`。
- `scripts/shared/constants.json`：统一维护可用领域、内容类型、时间过滤值和 zone。
- `scripts/shared/doc_spec.md`：统一维护 CLI 接口说明模板。
- `scripts/generate.py`：把 shared 常量和文档模板注入到四种 CLI 的 generated 区块中。
- 四个 `anysearch_cli.*` 文件：Python、Node.js、PowerShell、Bash 四套同构 CLI。

当这个 skill 被注入时，agent 会看到 `SKILL.md` 中的触发规则和命令规则。典型流程是：

1. 判断任务是否需要搜索、事实核验、网页提取、垂直领域搜索或多意图并行搜索。
2. 如果 `runtime.conf` 存在，直接读取其中的 `Command`。
3. 如果是普通搜索，调用 `<cmd> search "query"`。
4. 如果可能属于垂直领域，先调用 `<cmd> list_domains --domain <domain>`，读取返回的 `sub_domain`、`query_format`、`params_schema` 和 `zone`。
5. 按 `list_domains` 返回的格式构造垂直搜索命令。
6. 如果多个独立查询可并行，调用 `batch_search`。
7. 如果搜索摘要不够，需要阅读全文，调用 `extract`。
8. CLI 把命令参数组装为 JSON-RPC 2.0 请求，向 `https://api.anysearch.com/mcp` 发送 `tools/call`。
9. CLI 从响应的 `result.content[].text` 中提取文本并打印。

四套 CLI 的共同点：

- 都使用同一个 endpoint：`https://api.anysearch.com/mcp`。
- 都支持 `search`、`list_domains`、`extract`、`batch_search`、`doc`。
- 都会尝试加载脚本目录或 skill 根目录附近的 `.env`。
- 有 API key 时使用 `Authorization: Bearer <key>`。
- 没有 API key 时走匿名访问。

四套 CLI 的差异：

- Python 版使用 `requests`，要求 Python 3.6+ 和 `requests`。
- Node.js 版使用内置 `https`，无需外部 npm 包。
- PowerShell 版使用 `HttpWebRequest`，要求 PowerShell 5.1+。
- Bash 版使用 `curl` 和 `jq`，因此额外依赖 `jq`。

## 3. 这个 skill 的优点、弱点和限制是什么？

优点：

- 不需要本地 MCP server，只靠 CLI 就能访问远程搜索服务，安装和调用成本低。
- 同时提供 Python、Node.js、PowerShell、Bash 四种运行时，跨平台适配较强。
- `runtime.conf` 提供快路径，日常调用不必每次重新检测运行时或读取完整文档。
- `doc` 命令是离线的，可以在命令不确定时快速恢复接口说明。
- 垂直领域搜索流程写得比较明确，要求先 `list_domains`，这能减少领域查询格式错误。
- `batch_search` 适合多个独立意图并行查询，能减少 agent 多轮调用。
- `extract` 可以补足搜索摘要不足的问题，适合核验网页原文。
- API key 不是强制要求，匿名访问降低了初次使用门槛。
- `constants.json` 和 `doc_spec.md` 抽成 shared 文件，有利于多语言 CLI 保持一致。

弱点和限制：

- 这是云端搜索服务，本地 CLI 会把查询、URL 和 API key 发送到 `https://api.anysearch.com`。不适合处理密码、个人隐私、商业秘密、未公开研究材料等敏感内容。
- 真实结果质量、可用性、限额、延迟都依赖 AnySearch 服务端，本地 skill 不能保证。
- 匿名访问有较低限额，重度使用需要 API key。
- 垂直领域搜索虽然更准，但会增加一步 `list_domains`，对简单查询有额外开销。
- `extract` 只说明支持 HTML 页面，并且会截断；不适合 PDF、图片、音视频或需要完整大文档抽取的场景。
- `SKILL.md` 要求“运行 CLI 前验证脚本未被原始来源修改”，但本地没有提供 checksum 或签名机制，实际很难严格完成。
- `batch_search` 文档标题写“2-5 queries”，但实现和部分参数说明允许 1-5 个查询，存在轻微契约不一致。
- `README.md`、`.env.example`、`SKILL.md` 中 API key 获取链接表述不完全一致。
- `scripts/generate.py --check` 当前报告四个 CLI 都与生成器模板不一致。这不等于 CLI 已坏，但说明 generated 区块和生成器之间存在维护一致性风险。
- `.env.example` 中出现了一个看起来像真实 API key 的具体值，而不是纯占位符。这是安全卫生风险；如果该 key 真实有效，应移除示例中的真实值并轮换该 key。这里不复述该值。

## 4. 适合谁使用，不适合谁使用？

适合：

- 需要经常查询最新信息、新闻、网页资料或公开文档的 agent。
- 希望用一个统一入口完成搜索、批量搜索和网页提取的开发者。
- 需要 finance、academic、legal、code、health 等垂直搜索能力的使用者。
- 可以接受把查询发送给第三方搜索服务的个人或团队。
- 在不同平台之间切换的用户，因为它提供多语言 CLI。

不适合：

- 必须离线工作的环境。
- 不能把查询内容、URL 或 API key 发送给第三方服务的高保密场景。
- 对搜索来源、排序、覆盖率、可审计性有严格要求的合规/法务/科研系统。
- 只需要本地文件检索、代码库检索或数据库查询的任务。
- 需要完整浏览器渲染、登录态操作、复杂网页交互或动态页面调试的任务。
- 已经有明确指定搜索工具、官方文档源或高优先级检索流程的场景。

## 5. 适合哪些实际场景，主要解决什么需求和痛点？

适合的实际场景：

- 查最新政策、新闻、产品信息、版本变化、开源项目动态。
- 对用户给出的事实进行快速核验，并在需要时用 `extract` 读取原网页。
- 一次性比较多个主题，例如多个公司、多个模型、多个漏洞、多个论文方向。
- 查股票、CVE、DOI、IATA、专利、地理、医疗、法律等结构化或半结构化信息。
- 查代码文档、开发资料、API 用法和技术博客。
- 在 agent 工作流中补足实时网络信息，而不是只依赖模型内置知识。
- 用 `batch_search` 减少多轮搜索，把多个独立查询合并为一次调用。
- 用 `list_domains` 获取垂直搜索的准确 `sub_domain` 和查询格式，减少 agent 猜参数。

主要解决的痛点：

- 模型知识过期，需要实时外部信息。
- 普通搜索对领域查询不够结构化。
- agent 搜索多主题时调用次数多、上下文分散。
- 搜索摘要不够，需要抽取原网页正文。
- 用户不想额外部署 MCP server，但仍希望 agent 有搜索能力。

## 6. 是否有污染 prompt 库、降低 AI 效率或造成安全问题的风险？

有一定风险，但属于可管理范围。

Prompt 污染风险：

- `SKILL.md` 的触发范围很广，几乎覆盖所有“查询最新信息、事实核验、网页提取”的任务。如果长期作为默认搜索 skill 注入，可能与其他更专门的搜索/文档/官方资料技能竞争。
- “recommended search tool” 的措辞偏强，可能让 agent 在已有更高优先级检索规则时也倾向使用它。使用时应服从系统级和项目级规则，例如某些技术问题要求只用官方文档。
- 文档要求垂直领域查询总是先 `list_domains`，对高价值领域查询是优点，但对简单问题可能增加一次调用成本。
- 它通过 `runtime.conf` 和命令速查避免每次运行 `doc`，这一点能降低 token 和工具调用浪费。

效率风险：

- 如果 agent 每次都运行 `doc`，会浪费上下文；不过 `SKILL.md` 已明确要求只在接口未知、命令失败或恢复时运行 `doc`。
- `batch_search` 能提高多意图任务效率。
- 垂直搜索流程需要先查目录，短查询会稍慢，但领域查询更可控。
- Bash 运行时依赖 `jq`，缺失时会直接失败；Python 运行时依赖 `requests`。

安全风险：

- 所有真实搜索和提取请求都会发送到第三方服务端，包括查询词和 URL。
- API key 会从 `.env` 或环境变量加载，并作为 Bearer token 发送。
- `--api_key` 命令行参数可能被 shell 历史或进程列表记录，不建议在敏感环境使用。
- `batch_search --queries @file.json` 会读取本地文件路径；只有显式传入 `@file` 时触发，但 agent 应避免把敏感本地文件作为查询源。
- `.env.example` 当前看起来包含具体 key 值，这是本地仓库中最明显的安全卫生问题。
- `SKILL.md` 中提到 auto-registration 返回新 API key 时必须先征求用户确认再保存，这个规则是必要的；agent 不应自动写 `.env`。

总体判断：

`anysearch` 是一个实用的实时搜索 skill，适合公开信息检索、网页核验和垂直领域查询。它的最大价值是把搜索、批量搜索、垂直路由和 URL 提取统一成简单 CLI；最大风险是第三方服务数据外发、宽泛触发导致与其他搜索规则竞争，以及本地示例 key/生成器一致性带来的维护和安全卫生问题。
