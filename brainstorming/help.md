# brainstorming skill 研究报告

## 研究范围

本次只研究本地已安装的 `D:\Code\skills\brainstorming` skill，没有安装、同步、修复、删除或改写其他技能。

已检查的本地文件：

- `SKILL.md`
- `.skillfish.json`

这个 skill 没有脚本、测试、示例目录、引用资料或外部项目依赖。`.skillfish.json` 显示它是 `manual` 来源的本地自定义 skill，sha 为 `local-custom-20260529`。

由于 `SKILL.md` 没有引用外部 API、工具、公共仓库或需要核验的外部服务，本次没有进行联网调研。

## 1. 这个 skill 是做什么的，提供什么功能？

`brainstorming` 是一个结构化头脑风暴和想法成型 skill。它不是随机给一大串点子，而是把用户模糊的想法、产品概念、研究方向、内容主题、命名问题、功能构思或创意卡点，逐步整理成清晰选项、取舍判断和下一步行动。

它适合处理这些任务：

- 把一个早期、模糊、还没想清楚的想法变成更具体的概念。
- 为产品、功能、SaaS、工具、游戏、工作流等生成方向和 MVP 切入点。
- 为文章、演讲、课程、论文、视频等内容寻找角度、结构、hook 和受众承诺。
- 为产品名、品牌名、标题、tagline、定位语生成命名领域和候选列表。
- 为 AI/LLM、论文、实验、课题等研究方向梳理问题、创新点和最小实验。
- 在用户卡住、没思路、选择困难时，重构问题并给出 2 到 3 条前进路径。
- 当用户明确要求决策时，基于假设给出推荐方向和理由。

它的核心流程是：

```text
frame the question -> diverge -> explore -> converge -> choose next action
```

也就是：

1. 先界定问题。
2. 再发散出不同方向。
3. 选择强方向深入探索。
4. 收敛比较取舍。
5. 给出下一步行动。

## 2. 这个 skill 的结构、文件内容、注入方式和流程是什么？

目录结构很简单：

```text
brainstorming/
  SKILL.md
  .skillfish.json
```

文件作用：

- `SKILL.md`：主提示文件，定义触发场景、工作原则、会话分类、五步工作流、输出模板和对话规则。
- `.skillfish.json`：本地 skillfish 元数据，记录版本、名称、来源、路径、分支和本地 sha。它不包含具体工作流指令。

当这个 skill 被注入后，agent 会按 `SKILL.md` 的流程工作：

1. 先判断用户请求属于哪种 brainstorming 类型。
2. 如果类型明显，直接进入；如果不明显，只问一个简短问题：是产品、内容、研究、命名，还是只是探索。
3. 在 Frame 阶段，用一段话重述目标、受众、约束和本轮需要澄清的决策。
4. 如果上下文很薄，只问一个高杠杆问题，而不是问一串问卷。
5. 在 Diverge 阶段，用不同“lane”生成想法，例如 obvious but solid、adjacent、inversion、constraint-driven、weird but useful、bold bet。
6. 通常先产生 6 到 12 个原始想法，再归并成 3 到 5 个方向。
7. 在 Explore 阶段，对强方向说明核心机制、用户价值、差异化、风险和快速验证方式。
8. 只在有帮助时使用创意方法，例如 How Might We、SCAMPER、Analogy、Constraint prompt、Six hats、Morphological matrix。
9. 在 Converge 阶段，用简单矩阵比较方向，包括为什么适合、上行空间、风险、快速测试和推荐。
10. 在 Handoff 阶段，根据用户目标给出下一步：继续问问题、给决策、产出 brief/outline/name shortlist/experiment plan，或在想法选定后移交给规划/编码。

它内置了 4 种输出形状：

- `Quick Brainstorm`：用于轻量发散，包含 framing、directions、best bet、next question。
- `Idea Brief`：用于形成具体概念，包含 pitch、problem、core idea、first version、risks、fast test。
- `Naming / Positioning`：用于命名和定位，包含 naming territories、shortlist、recommendation。
- `Research Direction`：用于研究方向，包含 research angle、novelty claim、baseline、experiment、failure mode。

## 3. 这个 skill 的优点、弱点和限制是什么？

优点：

- 边界清楚：它把自己定义为 thinking partner，而不是随机点子生成器。
- 流程完整：从 frame 到 diverge、explore、converge、handoff，覆盖了从模糊到可行动的全过程。
- 会话类型分类明确，能适配 seed shaping、product/feature、content/narrative、naming/positioning、research direction、stuck mode。
- 强调少问问题，一次只问一个关键问题，减少用户负担。
- 强调保留用户的品味和约束，不把所有想法套成通用创业、设计或效率模板。
- 强调 3 到 5 个强方向，而不是长而散的列表。
- 取舍维度比较实用，包括 novelty、feasibility、effort、risk、audience fit、time to test。
- 明确禁止默认创建文件、规格、幻灯片或计划，能控制范围。
- 如果想法依赖市场、工具、竞品、法律、价格或近期产品，要求先调研，避免脱离现实。
- 如果用户要求决策，它要求 agent 直接决策，不长期停留在“都可以”。

弱点和限制：

- 没有脚本、测试、示例或评估文件，无法通过自动化验证它的输出质量。
- 这是纯提示型 skill，效果高度依赖 agent 的执行能力和对用户语境的理解。
- 对真实市场、竞品、法律、价格、工具生态等依赖当前信息的任务，它本身不提供检索能力，只要求“research first”。
- 没有给出针对不同领域的深层专业知识库，例如教育、医疗、法律、硬科技、艺术创作、商业战略等。
- 没有提供冲突处理模板，例如用户同时要求“最创新”和“最快落地”时如何强制排序。
- “不要创建 artifacts 除非用户要求”和“handoff 里可产出 brief/outline/name shortlist”之间需要 agent 判断，边界可能有轻微歧义。
- 对团队协作、多人共创、工作坊 facilitation 没有特别流程。
- 对已经非常明确的执行任务不适合；如果误触发，可能拖慢实现。

总体看，它是一个轻量但结构完整的创意协作提示，不是完整的产品战略框架、市场研究框架或研究方法论工具箱。

## 4. 适合谁使用，不适合谁使用？

适合：

- 有一个模糊想法，但还不知道怎么落成概念的人。
- 想做产品、工具、游戏、SaaS、功能设计，但需要比较不同方向的人。
- 写文章、做演讲、做课程、拍视频前需要找角度的人。
- 想做品牌命名、标题、tagline、定位的人。
- 做 AI/LLM 或学术研究选题，需要把想法变成研究问题和最小实验的人。
- 已经卡住，需要别人帮助重构问题和给路径的人。
- 想听明确推荐，而不是只听“各有优劣”的人。

不适合：

- 已经确定要实现某个功能，只需要写代码的人。
- 需要严肃市场调研、竞品分析、法律判断、价格分析，但不允许联网或查资料的人。
- 需要完整商业计划书、PRD、论文大纲、PPT、设计稿等交付物，但用户没有明确要求生成 artifact 的场景。
- 想要大量无筛选随机点子的人。
- 需要高度专业、领域特定的咨询，例如医学治疗方案、法律合规判断、金融投资建议。
- 需要用数据、实验或外部事实验证，而不是只做概念发散的任务。

## 5. 适合哪些实际场景，主要解决什么需求和痛点？

适合的实际场景：

- “我有个 app 想法，但不知道该做成什么样。”
- “帮我 brainstorm 一个 SaaS 的 MVP wedge。”
- “这个游戏机制有点普通，帮我找几个更有趣的方向。”
- “我要写一篇文章，但不知道角度。”
- “帮我给这个产品起名，偏克制、专业、不要太可爱。”
- “我想做一个 LLM 研究课题，但不知道创新点在哪里。”
- “我卡住了，帮我把这个问题换几个角度看。”
- “这几个方向你帮我选一个。”

主要解决的痛点：

- 用户脑子里有想法，但还没形成清楚问题。
- 用户选项太少，容易陷在第一个念头里。
- 用户选项太多，但没有取舍标准。
- 用户的想法变成了通用模板，缺少个人品味和具体约束。
- 用户需要发散，但又需要最后收敛到可行动的下一步。
- 用户需要一个能“陪他想”的结构化伙伴，而不是直接跳到写代码或写文档。

## 6. 是否有污染 prompt 库、降低 AI 效率或造成安全问题的风险？

有一定 prompt 污染和效率风险，但安全风险较低。

Prompt 污染风险：

- 触发范围较广，涵盖想法、产品、研究、内容、命名、功能、创意卡点等。如果 agent 判断不准，可能在用户已经要执行时仍进入 brainstorm 模式。
- 它鼓励 structured ideation，可能让简单请求被过度结构化。
- 它要求不要默认创建文件或计划，这能控制范围，但如果用户真正想要 artifact，agent 需要及时识别并切换输出形状。
- 和 `frontend-design`、`research-one-pager`、`math-modeling-topic-selector`、`paper-audit`、代码实现类 skill 之间可能有边界重叠。正确做法是先用它完成想法收敛，再移交给更专门的 skill。

效率风险：

- 如果每次都完整执行 frame、diverge、explore、converge、handoff，会让轻量请求变慢。
- 它已经要求“conversation lightweight”和“ask only the minimum questions needed”，这能降低效率损失。
- 对当前市场、竞品或近期工具相关想法，它要求先调研；这会增加时间，但能避免不可靠建议。
- 如果用户只想要 3 个名字或 5 个点子，应该用 Quick Brainstorm，而不是完整矩阵分析。

安全风险：

- 这个 skill 本身不要求执行命令、读写文件、联网、调用 API 或处理密钥，因此技术安全风险较低。
- 主要风险是建议质量风险：如果用于医疗、法律、金融、合规、高风险研究方向，可能给出未经验证的创意建议。
- 它要求依赖当前信息时先 research，这有助于避免过时或凭空判断。
- 它明确不应在纯实现任务中使用，除非用户仍在塑造要构建的东西，这能减少不必要的操作偏移。

总体判断：

`brainstorming` 是一个简洁、实用、边界相对清楚的创意协作 skill。它最适合把“还没想清楚”的东西变成少数可比较方向，并最终选出下一步。它的最大价值是结构化发散与收敛；最大风险是误触发后把执行任务拖回讨论，或在缺少现实调研时给出听起来合理但未经验证的方向。
