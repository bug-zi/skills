# frontend-taste-light 研究说明

## 1. 这个 skill 是做什么的，提供哪些功能？

`frontend-taste-light` 是一个轻量的前端页面审美优化 skill，核心目标是帮助 Codex 在创建、重做、美化或审查前端网页和 UI 时，减少常见的“AI 味”。

它不负责生成某种固定模板，也不是大型 UI/UX 资料库。它更像一个设计判断闸门：在动手做页面前先判断页面类型、用户任务、信息密度和品牌气质，然后用一组简洁规则约束视觉方向、布局、动效、图标、媒体、响应式和交互状态。

它提供的功能包括：

- 判断页面类型：landing、product page、dashboard、admin、tool、portfolio、content site、game、app shell 等。
- 判断用户意图：浏览、比较、决策、操作、配置、监控、创建、错误恢复等。
- 识别并禁止常见 AI 前端反模式。
- 给不同页面类型提供不同设计策略。
- 提供字体、颜色、布局、动效、图标和媒体的设计约束。
- 给实现阶段提供响应式、可访问性、状态覆盖和文本溢出等底线。
- 提供交付前的 final taste check。

## 2. 这个 skill 的结构是什么？注入后如何工作？

当前 skill 结构很简单：

```text
frontend-taste-light/
├── SKILL.md
└── help.md
```

`SKILL.md` 是唯一工作文件，包含 YAML frontmatter 和正文规则。

frontmatter:

- `name`: `frontend-taste-light`
- `description`: 明确触发场景，包括前端网页、React 组件、landing page、dashboard、portfolio、product page、web app UI 的创建、重做、美化或审查；同时排除后端、小型非视觉 bug、文档、PPT、HTML 报告等任务。

正文流程：

1. `First Read`: 先判断页面类型、用户意图、信息密度和品牌信号。
2. `Hard Anti-AI Rules`: 避免紫蓝渐变 hero、装饰 orb、玻璃卡、三卡片 hero、假 dashboard、emoji 图标等常见 AI 味。
3. `Page-Type Rules`: 针对 landing/product、tool/web app、dashboard/admin、portfolio/editorial 分别给出策略。
4. `Design Moves`: 对 typography、color、layout、motion、icons/media 给出简洁约束。
5. `Implementation Guardrails`: 检查 hover/focus/loading/empty/error/mobile/keyboard/touch/text wrapping 等实现状态。
6. `Final Taste Check`: 交付前自查页面是否具体、可用、真实、移动端稳定、视觉一致。

当 prompt 被注入后，它不会要求 Codex 调用额外脚本，也不会要求生成设计系统文件。它只是改变 Codex 的前端设计判断方式，让 Codex 在实际写 UI 代码时避免默认套模板。

## 3. 它有什么优点？有什么缺点或限制？

优点：

- 非常轻量，正文短，不容易污染上下文。
- 触发范围清楚，明确排除了 PPT、HTML 报告、文档和后端任务。
- 直接命中 AI 前端最常见问题：紫蓝渐变、装饰 orb、玻璃拟态、三卡片 hero、假数据、无意义大标题。
- 能区分 landing、tool、dashboard、portfolio，不会把所有页面都做成营销首页。
- 与现有 Codex 前端设计规则兼容，特别是 lucide 图标、移动端、文本不溢出、状态覆盖等要求。
- 不强制安装依赖、不强制跑脚本、不强制生成图片，符合最小范围原则。
- 可以和 `frontend-design`、`frontend-design-review`、`ui-ux-pro-max` 分工协作。

缺点和限制：

- 它是判断型 skill，不提供现成模板、组件库或代码脚手架。
- 对具体行业风格、颜色系统、字体组合没有详细资料，需要 Codex 自己判断，或必要时调用其他资料库。
- 没有提供示例 before/after，因此对新手 agent 的执行稳定性可能不如重型 taste skill。
- 没有专门覆盖移动 app、React Native、Flutter 或原生端，只面向前端网页和 web UI。
- 没有专门的视觉验收工具链，比如截图对比、Lighthouse、accessibility audit；这些仍需按具体项目另行执行。
- 对“大胆创意型页面”的激发能力不如 `frontend-design`，它更偏克制审美闸门。

## 4. 适合谁？不适合谁？

适合：

- 经常让 Codex 做网页、React UI、landing page、dashboard、产品页、portfolio 的用户。
- 想减少 AI 味，但不想启用大型前端设计 prompt 的用户。
- 已经有项目代码，只想让页面更真实、更具体、更有产品感的前端开发者。
- 需要一个常驻轻量审美约束，而不是完整设计系统生成器的人。
- 想把 PPT/HTML 报告类 skill 和通用前端设计 skill 分开管理的人。

不适合：

- 需要完整品牌系统、色板、字体库、组件库推荐的人。
- 需要自动生成高保真设计稿、图片参考或视觉模板的人。
- 主要做后端、API、数据库、脚本、运维的人。
- 主要做 PPT、HTML 报告、文档排版的人，这类任务应交给专门 skill。
- 想要固定强风格输出的人，例如杂志风、赛博风、极简日式、品牌官网套件等。

## 5. 适合哪些实际场景？解决什么痛点？

适合场景：

- “帮我把这个页面改得不像 AI 生成。”
- “美化这个 React 页面。”
- “做一个更专业的 dashboard。”
- “这个 landing page 太模板了，帮我重做。”
- “优化这个后台页面的视觉层次。”
- “帮我 review 一下这个 UI 有没有 AI 味。”
- “让这个 portfolio 更具体、更像真实项目。”

主要解决的痛点：

- AI 默认会生成很相似的 SaaS 首页。
- 页面经常有无意义的渐变、光斑、玻璃卡和大 slogan。
- 工具类页面容易被做成 marketing page，而不是可用工作区。
- dashboard 容易出现假图表、假头像和没有单位的数据卡。
- 视觉元素没有服务产品任务，只是在装饰。
- 移动端、文本溢出、状态、focus、loading/empty/error 经常被忽略。

## 6. 是否有 prompt 污染、效率下降或安全风险？

prompt 污染风险较低。

这个 skill 只有一个短 `SKILL.md`，没有大规模参考资料、脚本、模板或资源库。它不会在每次任务中要求额外读取文件，也不会默认调用网络、安装依赖、生成图片或创建设计系统，所以对上下文和执行效率的影响较小。

效率风险主要来自触发范围。如果用户只是做很小的 CSS 修补，而描述中出现“UI”或“页面”，它可能会被触发。不过 frontmatter 已经排除了 “small non-visual bug fixes”，可以降低误触发。

安全风险较低。

它不包含执行脚本、不处理凭证、不调用外部 API、不要求下载素材。唯一需要注意的是：它鼓励使用真实产品截图、对象照片或品牌资产，但同时明确要求不要 invent logos、screenshots、metrics 或 brand assets。因此实际执行时仍应遵守素材来源和版权边界。

总体判断：这个 skill 适合作为本地 skill 库里的轻量前端审美规则，能补足 `frontend-design` 过于创意化、`ui-ux-pro-max` 过重、`frontend-design-review` 偏审查的空档。
