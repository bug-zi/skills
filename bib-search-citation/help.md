# bib-search-citation skill 研究报告

## 研究范围

本次只研究本地已安装的 `D:\Code\skills\bib-search-citation` skill，没有安装、同步、修复、删除或改写其他技能。

已检查的本地文件：

- `SKILL.md`
- `agents/openai.yaml`
- `references/query-syntax.md`
- `examples/compact-query.md`
- `examples/raw-bib-export.md`
- `examples/preview-summary.md`
- `scripts/search_bib.py`
- `scripts/preview_bib_search.py`
- `tests/test_bib_search.py`
- `tests/fixtures/library.bib`
- `tests/fixtures/preview_input.json`
- `evals/trigger_eval.json`
- `evals/evals.json`

本次运行过的本地验证：

- 用 fixture `.bib` 执行 `search_bib.py`，确认 compact query 可以返回 JSON、过滤条件、分数、flags、LaTeX 和 Typst citation snippets。
- 用 fixture JSON 执行 `preview_bib_search.py`，确认 preview 能输出人类可读摘要并截断长字段。

外部核验来源：

- Zotero 官方文档支持导出 BibLaTeX/BibTeX 等格式，和该 skill 对 Zotero `.bib` 导出的定位一致。
- Typst 官方文档支持通过 `.bib` bibliography 和 `@key` / `#cite(<key>)` 形式引用，和该 skill 生成 Typst snippet 的方式一致。
- `uv` 官方文档确认 `uv run python ...` 是可用于运行 Python 脚本的入口，和 `SKILL.md` 的命令形态一致。

本次没有联网查找新论文，也没有修改任何 `.bib` 文献库。

## 1. 这个 skill 是做什么的，提供什么功能？

`bib-search-citation` 是一个面向本地 BibTeX/BibLaTeX 文献库的检索和引用生成 skill。它的核心用途不是写论文、润色相关工作或在线发现新文献，而是在用户已经有一个本地 `.bib` 文件时，从里面查找、过滤、预览、导出条目，并生成 LaTeX / Typst 引用片段。

它主要提供这些功能：

- 从本地 `.bib` 文件中按主题词检索文献条目。
- 支持紧凑查询表达式，例如 `mamba forecasting author:Cheng year>=2024 has:code cite:both limit:5`。
- 支持 JSON search spec，适合复杂、可复用、结构化的查询。
- 按作者、年份、entry type、DOI、eprint/arXiv、PDF、code、keywords、annotation、abstract 等条件过滤。
- 支持通用字段过滤，例如 `annotation:CodeAvailable`、`keywords:mamba`、`abstract:photovoltaic`。
- 支持否定过滤，例如 `-type:misc`、`-has:pdf`、`-annotation:survey`。
- 返回稳定 JSON，方便后续工具继续处理。
- 按 relevance、year_desc、year_asc、title 排序。
- 生成 LaTeX citation snippets：`\cite{key}`、`\parencite{key}`、`\textcite{key}`。
- 生成 Typst citation snippets：`@key` 或 `#cite(<key>)`，复杂 key 会生成 label 形式。
- 按需返回原始 BibTeX 条目，适合精确导出或人工核对。
- 把 JSON 搜索结果渲染成简洁的人类可读 preview。

一句话概括：它是“从本地 `.bib` 文献库里找条目并生成引用片段”的工具，不是“帮你发现和确认全网最新论文”的工具。

## 2. 这个 skill 的结构、文件内容、注入方式和流程是什么？

目录结构可以概括为：

```text
bib-search-citation/
  SKILL.md
  agents/
    openai.yaml
  evals/
    evals.json
    trigger_eval.json
  examples/
    compact-query.md
    preview-summary.md
    raw-bib-export.md
  references/
    query-syntax.md
  scripts/
    preview_bib_search.py
    search_bib.py
  tests/
    test_bib_search.py
    fixtures/
      library.bib
      preview_input.json
```

核心文件作用：

- `SKILL.md`：主提示文件，定义触发场景、禁用场景、模块路由、输入要求、输出契约、工作流和安全边界。
- `agents/openai.yaml`：给 agent UI/运行时看的显示名、短描述和默认 prompt。
- `references/query-syntax.md`：详细说明 compact query 和 JSON spec 的映射方式。
- `examples/compact-query.md`：普通主题检索、过滤和 citation snippet 生成示例。
- `examples/raw-bib-export.md`：返回原始 BibTeX 条目的示例。
- `examples/preview-summary.md`：先生成 JSON，再用 preview 脚本渲染摘要的示例。
- `scripts/search_bib.py`：核心脚本，负责解析 `.bib`、解析查询、过滤、评分、排序、输出 JSON 和 citation snippets。
- `scripts/preview_bib_search.py`：渲染器，只负责把 `search_bib.py` 的 JSON 输出转换成简洁摘要。
- `tests/test_bib_search.py`：行为测试，覆盖 JSON contract、citation snippets、raw BibTeX、filter-only query、空结果和 preview。
- `tests/fixtures/library.bib`：测试用 `.bib` 文献库。
- `tests/fixtures/preview_input.json`：测试 preview 截断和渲染的输入。
- `evals/trigger_eval.json`：触发/不触发样例，规定哪些请求应使用这个 skill。
- `evals/evals.json`：功能评估样例，规定典型请求应如何路由和回答。

当这个 skill 被注入时，agent 的典型工作流是：

1. 判断用户是否提供或指向了本地 `.bib` 文件。
2. 如果用户请求是本地文献库检索、过滤、引用片段、原始 BibTeX 导出或 preview，就启用这个 skill。
3. 如果用户是在写论文、修引用编译错误、在线找新论文、审稿或润色相关工作，则不使用这个 skill。
4. 将用户请求转换成 compact query 或 JSON spec。
5. 运行：

```bash
uv run python -B <skill_dir>/scripts/search_bib.py --bib <library.bib> --query '<compact query>'
```

或运行 `--spec-json` / `--spec-file`。

6. 检查 JSON payload，而不是只凭命令运行结果直接回答。
7. 如果需要人类可读摘要，再把 JSON 传给：

```bash
uv run python -B <skill_dir>/scripts/preview_bib_search.py --input results.json
```

8. 按输出契约向用户报告匹配数量、过滤条件、前几条结果、citation snippets、必要时的 raw BibTeX。

`search_bib.py` 的内部流程：

1. 解析 CLI 参数，要求 `--bib` 和 `--query` / `--spec-json` / `--spec-file` 三选一。
2. 把 compact query 解析为 spec，或读取 JSON spec。
3. 手写解析 `.bib` 条目，不依赖外部 BibTeX parser。
4. 规范化字段，包括 title、shorttitle、author、year、venue、doi、eprint、keywords、annotation、abstract 等。
5. 推断 flags，例如是否有 DOI、abstract、keywords、annotation、shorttitle、eprint、pdf、code。
6. 根据 filters 过滤条目。
7. 根据加权字段给主题查询打分。
8. 按指定 sort 排序，按 limit 截断。
9. 返回 JSON，其中包含 `meta` 和 `results`。

`preview_bib_search.py` 的内部流程：

1. 从 `--input` 文件或 stdin 读取 JSON。
2. 校验 payload 必须是对象且包含 `results` 数组。
3. 渲染 query、sort、returned/matched/total、filters。
4. 对每条结果渲染 key、entry type、score、flags、title、authors、year/venue、DOI、eprint、keywords、annotation、abstract 和 citation lines。
5. 对 keywords、annotation、abstract 做长度截断。
6. 不渲染 `raw_bib`，避免 preview 暴露整段原始条目。

## 3. 这个 skill 的优点、弱点和限制是什么？

优点：

- 任务边界清楚：只面向本地 `.bib` 检索和 citation snippet，不扩展到论文写作或在线发现。
- 支持 compact query，用户和 agent 都可以快速表达过滤条件。
- 支持 JSON spec，复杂检索可以结构化、可保存、可复用。
- 输出 JSON contract 稳定，适合后续脚本、预览器或 agent 继续处理。
- 支持 Zotero 常见扩展字段，如 `shorttitle`、`annotation`、`keywords`、`abstract`、`file`、URL、DOI、eprint 等。
- 能推断 `has:code` 和 `has:pdf`，对科研库筛选很实用。
- 同时支持 LaTeX 和 Typst citation snippets，适合混合写作工作流。
- `preview_bib_search.py` 把机器 JSON 和人类摘要分开，职责划分合理。
- 不依赖外部 BibTeX parser，脚本轻量，fixture 测试可直接运行。
- 安全边界写得比较好，明确要求把 `.bib` 字段内容视作不可信数据，不把摘要、注释、标题当作指令执行。

弱点和限制：

- `.bib` 解析器是手写的，虽然能处理常见花括号、括号、引号和转义，但不等于完整 BibTeX/BibLaTeX 解析器。复杂宏、字符串拼接、crossref、非常规嵌套或损坏文件可能解析不完整。
- 只按本地 `.bib` 已有字段检索，不能补全缺失 DOI、作者、venue、URL 或摘要。
- relevance scoring 是启发式加权，不是语义检索；同义词、缩写、概念相近但字面不同的论文可能漏掉。
- `has:code` 是关键词/URL/annotation/abstract 等字段的文本推断，不保证真的有可运行代码。
- `has:pdf` 也是从 `file`、`pdf`、`url` 字段推断，不保证文件真实存在或可打开。
- citation snippets 只基于 citation key 生成，不校验 LaTeX/Biber 或 Typst 项目是否真的能编译。
- raw BibTeX 是解析到的原始条目片段，不代表整份 `.bib` 格式完全正确。
- 对大型 `.bib` 文件是线性扫描，没有索引；超大库会随条目数线性变慢。
- 默认要求 `uv run python -B`，如果本地没有 `uv`，这个 skill 的推荐命令会失败。
- 不做在线元数据核验，DOI、arXiv、URL 只是本地字段证据，不是内容真实性证明。

本地验证中发现：

- fixture 搜索命令可以正确返回 `Doe2024Mamba`，并生成 LaTeX/Typst snippets。
- preview 命令可以正确渲染 `preview_input.json`，并截断长 keywords、annotation、abstract。
- 测试文件覆盖了主要功能，但没有覆盖非常复杂的 BibTeX 宏、字符串拼接、crossref 或大型库性能。

## 4. 适合谁使用，不适合谁使用？

适合：

- 已经维护本地 `.bib` / Zotero export 的科研人员、学生、工程师。
- 需要在大型文献库里快速找某主题、某作者、某年份、某字段内容的人。
- 需要从本地库生成 LaTeX 或 Typst 引用片段的人。
- 想用 structured JSON 把 bibliography 检索接到其他工具链的人。
- 想快速导出某个原始 BibTeX 条目做人工核对的人。
- 使用 Zotero、BibTeX、BibLaTeX、LaTeX、Typst 写作的人。

不适合：

- 没有本地 `.bib` 文件、只想联网找最新论文的人。
- 想让 agent 自动补全或编造缺失文献信息的人。
- 想修 `.tex` / `.typ` 编译错误、Biber 错误或引用完整性问题的人。
- 想写、润色、审稿、扩写 related work 的人。
- 需要严格语义检索、向量检索或数据库级索引的大型文献平台。
- 需要证明某篇论文支持某个具体 manuscript claim 的场景；这个 skill 只能说明 `.bib` 字段中有什么。
- 对 `.bib` 格式复杂性要求很高，需要完整 BibTeX/BibLaTeX parser 的工具链。

## 5. 适合哪些实际场景，主要解决什么需求和痛点？

适合的实际场景：

- “在我的 `references.bib` 里找 2024 年以后的 Mamba forecasting 论文。”
- “找作者名包含 Cheng 且有 DOI 的 article 条目。”
- “找 annotation 包含 CodeAvailable、abstract 提到 photovoltaic 的条目。”
- “按年份倒序列出 newest transformer forecasting papers。”
- “给我某个 citation key 或关键词最匹配的 raw BibTeX。”
- “把命中的条目输出为 LaTeX 和 Typst 引用片段。”
- “先跑 JSON 检索，再给我一个简洁 preview。”
- “从 Zotero 导出的 `.bib` 里筛选带代码、带 PDF、带摘要、带关键词的条目。”

主要解决的痛点：

- 本地 `.bib` 很大，人工搜索 author/year/keyword/annotation/abstract 很慢。
- Zotero 导出字段多且混杂，普通文本搜索难以组合多个过滤条件。
- 写 LaTeX/Typst 时需要快速拿到正确 citation key 和 citation snippet。
- 需要在不改动文献库的前提下，查找和预览候选条目。
- 需要机器可读 JSON 给后续 agent 或脚本继续处理。
- 需要区分“本地文献库证据”和“论文内容主张证明”。

## 6. 是否有污染 prompt 库、降低 AI 效率或造成安全问题的风险？

总体风险较低，但有几个需要注意的点。

Prompt 污染风险：

- 触发范围相对克制，明确要求只在本地 `.bib` 检索、过滤、预览和 citation snippet 生成时使用。
- `Do Not Use` 边界清楚，避免和 LaTeX 论文写作、论文审稿、在线文献发现等技能混用。
- 仍有一个边界场景：“整理 Zotero 导出的参考文献，按主题分组列出来”在 trigger eval 中标为应触发，但这可能接近文献整理/分类任务。如果用户期待写作型总结，应小心不要扩展成 related-work 写作。
- 它提供较长的查询语法说明，但实际使用时不需要每次全文复述；agent 应直接构造 compact query 或 JSON spec。

效率风险：

- 对大 `.bib` 文件是线性扫描，没有索引或缓存，超大库会慢。
- relevance scoring 是纯文本启发式，不适合复杂语义发现；如果用户需求是“概念相近论文”，可能需要外部语义检索或人工扩大关键词。
- 如果 agent 不先明确 `.bib` 路径，可能浪费时间在找文件上；`SKILL.md` 要求路径不明确且选择有风险时只问一个澄清问题。
- `preview_bib_search.py` 只是 renderer，不应替代 JSON payload 检查；否则可能丢失机器字段细节。

安全风险：

- `.bib` 字段内容可能包含 prompt-like 文本，尤其是 `annotation`、`abstract`、`note`、`url`。`SKILL.md` 已明确要求把这些当作不可信数据，不能当指令执行。
- raw BibTeX 可能包含本地文件路径、Zotero storage 路径、PDF 路径、私有 URL 或注释内容；只有用户明确要求时才应输出。
- `--query`、`--spec-json`、`--spec-file` 是 agent 构造的命令参数，应避免从 `.bib` 字段或用户文本中拼接任意 shell 命令。
- `--spec-file` 和 `--bib` 会读取本地文件；应只读取用户指定或任务直接需要的文件。
- citation snippets 可能包含特殊 citation key。Typst 生成器对复杂 key 有 label fallback，但 LaTeX snippet 只是直接包进 `\cite{...}`，不保证所有特殊 key 在用户项目中安全可用。

总体判断：

`bib-search-citation` 是一个边界清晰、实用性很强的本地 bibliography 检索 skill。它最适合解决“我已有 `.bib`，帮我快速找条目、筛字段、生成引用片段、导出原始 BibTeX”的问题。最大价值在于 compact query、稳定 JSON、LaTeX/Typst 双 citation snippets 和 Zotero 字段适配；最大限制在于手写 BibTeX 解析、启发式文本评分、无在线元数据核验，以及不能把 `.bib` 字段当作文献内容真实性证明。
