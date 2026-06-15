# 场景提示词模板库

这份文档是 `imagegen` 提示词工程库。使用时先选场景，再填变量，不要临场自由发挥。

## 使用方式

默认执行链路：

1. 找到最接近当前阶段和场景的提示词模板
2. 把模板里的变量替换成当前项目需求
3. 判断本次动作属于：
   - `生图`
   - `微调图`
4. 调用 `imagegen`
5. 检查结果是否满足当前页目标
6. 归档到对应素材目录

母版确认和大纲确认通过后，默认只使用“正式页成图”相关模板。

- 默认直接进入整页成图模板，不再生成新的风格总板、母版组总览、章节分镜板、页型缩略图拼板、10 页总览或“第一批参考视觉页”。
- `1-9` 号模板主要服务调研、设计确认和母版阶段，或在用户明确要求重做这些阶段时使用。
- 普通内容页默认链路是：`选母版 -> 套整页成图模板 -> 直接图文一体成图`。
- 只有复杂架构页、流程页、功能页才默认进入复杂分件模板。

每次调用 `imagegen` 前，先确定五件事：

1. 当前阶段：调研、母版、结构框定、整页成图、复杂分件、微调
2. 当前场景：汇报、课程、培训、产品、架构、案例、结尾
3. 当前页型：封面、目录、章节、内容、架构、流程、案例、尾页
4. 当前风格：标准风格或项目参考样式
5. 当前文字：只给真实要上图的短文本

所有模板都默认：

- `16:9`
- 直接服务 PPT 成图
- 不用代码排版
- 不生成假字
- 不让风格板替代母版

所有模板还默认遵守一条真实性规则：

- 机构、学校、品牌、产品相关的具体元素，优先使用官方或用户提供的真实素材线索
- 如果缺少真实线索，就使用通用元素，不要伪造一个“很像真的”建筑、石刻、校牌、界面或地标
- 高风险元素一律禁止凭空编造：具体教学楼、校训石、校印浮雕、产品 UI、品牌专属建筑、官方题字

## 1. 调研风格板模板

适用：
- 学校、机构、品牌、产品项目开工前

```text
Use case: ui-mockup
Asset type: research moodboard
Project type: [school / public institution / enterprise / product / course]
Primary request: Create a visual research moodboard for a professional presentation deck about [project name]
Source cues to reflect: [official colors], [official imagery], [architecture or product cues], [brand tone]
Style target: [formal / academic / warm / strategic / product-led / hand-drawn]
Composition: 16:9 board with clear zones for color, typography mood, image treatment, layout rhythm, and visual motifs
Constraints: no final slide layout, no fake paragraphs, no watermark
Avoid: generic AI style, unrelated buildings, neon dashboard overload, decorative clutter, fake official-looking buildings
```

## 2. 风格总板模板

适用：
- 展示标题、卡片、图标、配色、组件语言

注意：
- 这不是母版。

```text
Use case: ui-mockup
Asset type: style system board, not a slide master
Primary request: Create a style system board for a PPT deck in [style name]
Include: title style samples, card style samples, icon language, color palette, texture treatment, page rhythm thumbnails
Composition: 16:9, organized design board, multiple component zones
Constraints: this is not a master slide, no final business content, no fake data
Avoid: treating this as a fillable slide template
```

## 2.5 设计规范效果图模板

适用：
- 风格确认阶段给用户看的一页设计规范板

注意：
- 这不是母版。
- 这也不是最终正式页。
- 它是“给用户确认视觉方向”的单页规范效果图。

```text
Use case: ui-mockup
Asset type: design confirmation board for user review, not a master slide
Primary request: Create a one-page design specification confirmation board for a professional PPT deck about [topic]
Style direction: [style name]
Institution or brand cues: [school / government / hospital / company / product cues]
Must include:
- one cover or opening slide preview
- color palette
- typography direction
- image language references
- texture and material references
- icon or diagram language
- page rhythm with 4-6 sample slide thumbnails
- visual keywords or short strategic labels
Composition: 16:9, structured design board, premium and readable, suitable for user confirmation before master-slide generation
Text policy: only short supplied labels and headings, no long fake paragraphs, no lorem ipsum
Constraints: this board should explain the design system clearly at a glance, but it must not be mistaken for a fillable master slide
Element sourcing: use verified official elements when available; if unavailable, use generic books, classrooms, devices, icons, textures, abstract waves, grids, and data graphics instead of invented institutional landmarks
Avoid: loose collage without structure, fake long text, full master-slide set, completed business slides, placeholder boxes, random unrelated imagery, fake institutional architecture
```

## 3. 母版组总览模板

适用：
- 用户明确要求看母版总览时
- 母版确认阶段需要一张概览图时

注意：
- 这不是默认必做产物。
- 母版一旦确认通过，后续不要再默认回头生成这类总览图。

```text
Use case: ui-mockup
Asset type: empty master set overview
Primary request: Create an overview image showing a set of empty PPT master slides for [project type]
Masters included: cover, agenda or section, right-bearing content, left-bearing content, wide process, center structure, heavy content, architecture/process, ending
Style direction: [style name or project reference style]
Composition: 16:9 overview board with small blank slide thumbnails, each thumbnail visibly empty and fillable
Constraints: no readable final content, no fake paragraphs, no fake chart labels
Avoid: a decorative style board without real blank slide masters
```

## 4. 封面空母版模板

```text
Use case: ui-mockup
Asset type: empty cover master slide
Primary request: Create a blank cover master for a professional PPT deck about [topic]
Style direction: [style name]
Visual identity cues: [brand / campus / product / industry cues]
Composition: 16:9, large clean title safe area, optional visual area, subtitle/date/author safe area
Whitespace rule: keep a large blank zone for later title and subtitle filling
Mood: [formal / warm / academic / bold / hand-drawn]
Constraints: no readable title, no fake subtitle, no watermark, no final content
Avoid: overfilled background, random UI panels, fake presentation text, fake school or brand landmarks
```

## 5. 目录页或章节页空母版模板

```text
Use case: ui-mockup
Asset type: empty agenda or section master slide
Primary request: Create a blank agenda/section master for a PPT deck about [topic]
Style direction: [style name]
Composition: 16:9, clear section title safe zone, optional chapter number area, calm transition atmosphere
Whitespace rule: reserve a large empty area for later section title or agenda text
Page role: [agenda / section divider / transition]
Constraints: no readable agenda items, no fake chapter names, no final content
Avoid: making it look like a completed slide, do not draw title bars, empty rounded rectangles, circular badges, avatar placeholders, or any obvious text containers
```

## 6. 内容页空母版模板

适用：
- 右承载、左承载、上下留白、中间留白、全白承载

```text
Use case: ui-mockup
Asset type: empty content master slide
Primary request: Create a blank content slide master using the [right-bearing / left-bearing / top-bottom / center / heavy-content] layout
Style direction: [style name]
Composition: 16:9, stable title safe zone, content safe zone, visual safe zone, conclusion strip safe zone if needed
Visual treatment: [subtle texture / clean whiteboard / editorial photo area / light cards / marker lines]
Whitespace rule: keep the main writing area light, calm, and fillable for later real text and charts
Constraints: no readable text, no fake cards with labels, no fake data, no final content, no pre-drawn business structure
Avoid: overcrowded decoration, no room for actual content, identical rhythm to adjacent masters, relationship diagrams that consume the writing area, title bars or empty UI placeholder boxes, fake institution-specific scenery
```

## 7. 复杂页空白变体模板（可选）

```text
Use case: infographic-diagram
Asset type: optional empty complex-page variant
Primary request: Create a blank complex-page background variant for a slide about [topic]
Style direction: [style name]
Composition: 16:9, clear title safe zone, central diagram safe zone, side explanation safe zones, bottom conclusion safe zone
Structure hint: leave space for a later architecture/process rendering, do not pre-draw the actual modules, arrows, or labels
Constraints: no readable labels, no fake module names, no fake arrows with text, no final content
Avoid: over-complex topology, tiny nodes, glowing tech clutter, semi-finished diagrams
```

## 8. 尾页空母版模板

```text
Use case: ui-mockup
Asset type: empty ending master slide
Primary request: Create a blank ending slide master for a professional PPT deck about [topic]
Style direction: [style name]
Composition: 16:9, large closing message safe area, optional contact/thanks safe area, calm visual closure
Mood: [warm / formal / confident / ceremonial / hopeful]
Constraints: no readable thank-you text, no fake contact info, no watermark
Avoid: reopening new content, dense visual elements
```

## 9. 科技风母版组专用模板

适用：
- AI、系统平台、数字化、产品技术汇报

```text
Use case: ui-mockup
Asset type: empty PPT master slide in a futuristic technology style
Primary request: Create a blank [cover / agenda or section / content A / content B / ending] master slide for a professional PPT deck about [topic]
Style direction: tech-futuristic, premium and restrained
Visual language: midnight navy background, cyan and electric-blue light trails, subtle holographic grid, refined data-flow atmosphere
Composition: 16:9, large calm blank safe area for later title and body content, visual energy pushed to edges, bottom band, or one side depending on page role
Role difference:
- cover: strongest opening atmosphere
- agenda or section: transition feel, calmer than cover
- content A: one-sided visual emphasis with large writing area
- content B: different whitespace rhythm from content A without changing palette
- ending: visual closure, calm and conclusive
Constraints: no readable text, no fake labels, no UI panel clutter, no placeholder bars, no rounded empty cards, no pre-drawn business structure
Avoid: cyberpunk purple overload, game HUD, dashboard screenshots, semi-finished diagrams, identical composition across all five masters
```

## 10. 汇报材料整页成图模板

```text
Use case: ui-mockup
Asset type: full slide image
Scenario: formal report deck
Slide type: [background / judgment / solution / mechanism / case / value / summary]
Master used: [master name]
Style direction: [style name or project reference style]
Main message: [one-sentence judgment]
Actual text to render:
- title: [title]
- key points: [3-5 short points]
- conclusion: [short conclusion]
Visual subject: [institution scene / service scene / architecture diagram / symbolic visual]
Composition: 16:9, professional report slide, clear hierarchy, one main judgment
Constraints: render only supplied text, no fake labels, no lorem ipsum, no watermark
Avoid: policy poster stiffness, generic AI dashboard, too much decoration
```

## 11. 课程整页成图模板

```text
Use case: ui-mockup
Asset type: full slide image
Scenario: course deck
Slide type: [learning objectives / concept explanation / knowledge map / example / exercise / summary]
Master used: [master name]
Style direction: [hand-drawn / classroom infographic / campus editorial]
Main teaching point: [one sentence]
Actual text to render:
- title: [title]
- learning points: [3-5 short points]
- activity or reminder: [optional short line]
Visual subject: [knowledge map / classroom icon / concept illustration / example scene]
Composition: 16:9, learner-friendly, clear reading order, not childish unless requested
Constraints: use only supplied text, no fake classroom labels, no dense micro-text
Avoid: childish poster style, too many colors, long paragraph blocks
```

## 12. 培训整页成图模板

```text
Use case: ui-mockup
Asset type: full slide image
Scenario: training deck
Slide type: [method / steps / role / checklist / exercise / recap]
Master used: [master name]
Style direction: [workshop / whiteboard / strategy brief]
Main training action: [what the audience should learn or do]
Actual text to render:
- title: [title]
- steps or checklist: [3-6 short items]
- takeaway: [short action sentence]
Visual subject: [workflow / sticky notes / checklist / role map / scenario sketch]
Composition: 16:9, practical, action-oriented, easy to follow
Constraints: use only supplied text, no fake checklist items, no watermark
Avoid: decorative workshop clutter, overly cute icons, unreadable small notes
```

## 13. 产品介绍整页成图模板

```text
Use case: ui-mockup
Asset type: full slide image
Scenario: product introduction deck
Slide type: [problem / value proposition / product overview / feature / scenario / roadmap / comparison]
Master used: [master name]
Style direction: [product story / UI-led / strategic]
Main product message: [one sentence]
Actual text to render:
- title: [title]
- value points: [3-5 short points]
- CTA or conclusion: [optional short line]
Visual subject: [product UI / device mockup / user scenario / feature diagram]
Composition: 16:9, product-led, clear focus, UI or scenario supports the message
Constraints: use only supplied text, no fake app UI text unless provided, no lorem ipsum
Avoid: piling up many screenshots, generic SaaS dashboard, feature list without story
```

## 14. 复杂架构图分件模板

```text
Use case: infographic-diagram
Asset type: complex slide sub-panel
Scenario: architecture or system diagram
Panel role: [top conclusion / left input / center engine / right output / bottom governance / side explanation]
Master used: [master name]
Style direction: [style name]
Actual text to render:
- panel heading: [heading]
- labels: [short labels]
- note: [optional short note]
Visual structure: [layers / hub-spoke / pipeline / swimlane / matrix]
Composition: self-contained panel, consistent with the full slide, easy to assemble later
Constraints: use only supplied labels, no fake modules, no tiny unreadable text
Avoid: full-page complexity inside one sub-panel, mismatched icon style
```

## 15. 案例页整页成图模板

```text
Use case: ui-mockup
Asset type: full slide image
Scenario: case study slide
Slide type: case story
Master used: [master name]
Style direction: [style name]
Case name: [case name]
Main case message: [one-sentence result or lesson]
Actual text to render:
- title: [title]
- scene: [short scene]
- method: [short method]
- result: [short result]
- conclusion: [short conclusion]
Visual subject: [case scene / service journey / before-after / product-in-use]
Composition: 16:9, scene + method + result are clearly separated, one case per page
Constraints: no fake names, no fake metrics unless supplied, no lorem ipsum
Avoid: only pretty scene with no business logic, too many mini cases
```

## 15. 审查微调提示词模板

```text
Use case: ui-mockup
Asset type: slide consistency review board
Primary request: Create a review board comparing selected slides for consistency
Review targets: title zones, master usage, card style, icon language, image treatment, spacing rhythm
Style direction: current deck style
Composition: 16:9, side-by-side fragments or thumbnail strips, clear visual comparison
Constraints: no new content, no fake labels, do not invent a new style
Avoid: decorative redesign, changing the deck direction
```
