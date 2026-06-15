# `imagegen` 提示词骨架

这个技能要求绝大多数阶段都调用 `imagegen`。重点不是把一张图做漂亮，而是让图片真正服务 PPT 施工。

## 通用规则

- 默认生成 `16:9` 横版。
- 先写清页面用途：封面、章节、内容、案例、架构、流程、尾页。
- 先写清当前使用的是“标准风格”还是“项目参考样式”。
- 如果引用项目已有 `成图/`，要把它写成“项目参考样式”，不要把它误写成通用风格名。
- 先写清布局安全区和阅读路径。
- 空背景阶段必须完全空，不要可读文字、假标签、假流程。
- 最终整页阶段必须是图文一体，不要“先效果后贴字”。
- 复杂示意图阶段要按分区生成，不要一口气生成一团看不清的复杂页面。
- 所有文字只用当前页真实内容，不要生成 lorem ipsum、伪中文、伪英文。

## 调研与风格板阶段

用途：
- 把官网和官方视觉线索整理成可复用的风格方向。

提示词骨架：

```text
Use case: ui-mockup
Asset type: research moodboard
Primary request: Create a style board for a formal presentation deck based on the official identity of [institution or brand]
Subject: architecture, atmosphere, color cues, imagery treatment, and presentation tone
Style/medium: restrained editorial moodboard for a PPT system
Composition/framing: 16:9 board with clear blocks for architecture, texture, color, typography direction, and layout rhythm
Lighting/mood: aligned with the official tone
Constraints: no watermark, no random futuristic city, preserve authentic identity cues
Avoid: generic AI campus, unrelated landmarks, over-neon tech UI
```

## 母版组阶段

用途：
- 生成一组后续可以直接填充内容的空母版页。

提示词骨架：

```text
Use case: ui-mockup
Asset type: empty PPT master set
Primary request: Create one empty presentation master slide for [cover / agenda or section / content / architecture / ending]
Subject: a blank but presentation-ready page template that will be filled with content later
Style/medium: presentation-ready empty master page
Composition/framing: 16:9, clear safe zones for title, content, images, and conclusion areas
Color palette: [core colors]
Materials/textures: [paper grain / ribbon / campus photography / ink line / clean cards]
Constraints: no readable text, no fake body text, no fake data labels, no pseudo finished cards
Avoid: turning the master into a style board, over-decorating, making every page identical
```

补充说明：

- 母版页是空模板，不是风格总板。
- 如需展示标题风格、卡片风格、图标语言、组件语言，可以另做一张风格总板，但不要把它当成母版页。

## 选用或派生空母版页阶段

用途：
- 在逐页施工时，从母版组中选当前页的空母版，必要时派生空白变体。

提示词骨架：

```text
Use case: ui-mockup
Asset type: empty derived master slide
Primary request: Create an empty derived master slide for slide [number] based on the existing master system
Subject: only atmosphere, structure hint, safe negative space, and visual identity, ready to be filled later
Style/medium: presentation-ready blank master variant
Composition/framing: 16:9, reserve clear content area on [left / right / center / top-bottom]
Color palette: [core colors]
Lighting/mood: [formal / warm / academic / strategic / product-demo]
Constraints: no readable text, no fake labels, no fake cards, no fake charts, no pseudo finished page
Avoid: over-dense UI, placeholders, random icons floating everywhere
```

## 页面框定阶段

用途：
- 在正式成图前把阅读路径和分区先锁定。

提示词骨架：

```text
Use case: infographic-diagram
Asset type: page structure frame
Primary request: Create a clean structure frame for slide [number] titled [title]
Subject: title zone, main visual zone, content zones, conclusion zone, and reading path
Style/medium: presentation planning board
Composition/framing: 16:9, clearly separated regions, easy to translate into a full slide image
Constraints: keep the frame clean, do not generate fake body text or decorative overload
Avoid: dense fake cards, tiny labels, messy arrows
```

## 图文一体整页成图阶段

用途：
- 直接生成带真实标题、真实短正文、真实卡片标签和图像的整页图。

提示词骨架：

```text
Use case: ui-mockup
Asset type: full slide image
Primary request: Create a complete presentation slide image for slide [number]
Slide type: [cover / section / content / case / architecture / process / ending]
Style direction: [style name]
Main message: [one-sentence judgment]
Actual text to render:
- title: [title]
- section label: [section label]
- short supporting points:
  1. [point 1]
  2. [point 2]
  3. [point 3]
- conclusion bar: [short conclusion]
Visual subject: [main scene / product UI / architecture / case visual / campus building]
Composition/framing: 16:9, make the text and visual work as one integrated slide, clear reading path
Lighting/mood: [formal / warm / strategic / lively / product-like]
Constraints: render only the supplied text content, no lorem ipsum, no fake English UI, no watermark
Avoid: beautiful but text-free effect board, fake paragraphs, dense unreadable micro-text
```

## 复杂示意图分件阶段

用途：
- 先把复杂页拆成多个可控区块，再拼回整页。

提示词骨架：

```text
Use case: infographic-diagram
Asset type: slide sub-panel
Primary request: Create one sub-panel for a complex presentation slide
Panel role: [left explanation block / center architecture block / right value block / top conclusion strip / bottom flow strip]
Main message: [message for this panel]
Actual text to render:
- heading: [heading]
- bullets or labels: [short list]
Style direction: [style name]
Composition/framing: keep this panel self-contained, with clear edges for later assembly into a 16:9 page
Constraints: use only supplied text, no fake labels, do not behave like a standalone poster disconnected from the page
Avoid: decorative clutter, mismatched palette, inconsistent icon language
```

## 拼装预览阶段

用途：
- 把多个分件合成统一整页时，先验证节奏和统一性。

提示词骨架：

```text
Use case: ui-mockup
Asset type: slide assembly preview
Primary request: Create a unified preview for a complex PPT slide assembled from multiple content panels
Subject: the page should feel like one coherent slide, not a collage
Composition/framing: 16:9, stable title zone, stable content rhythm, strong overall reading order
Constraints: preserve the chosen style, preserve supplied content structure, no extra fake text
Avoid: scrapbook effect, misaligned blocks, random filler ornaments
```

## 局部微调阶段

用途：
- 让页面局部更稳，但不改变主逻辑。

提示词骨架：

```text
Use case: logo-brand
Asset type: local slide accents
Primary request: Create a small set of supporting assets for slide [number]
Subject: icons, card textures, separators, or small local refinements aligned with the current deck style
Style direction: [style name]
Constraints: no text, no watermark, support the page rather than stealing attention
Avoid: new visual language, mascot excess, off-style gradients
```

## 审查与微调阶段

用途：
- 为整套 deck 做统一对比板和微调方向板。

提示词骨架：

```text
Use case: ui-mockup
Asset type: review comparison board
Primary request: Create a presentation review board to compare slide style consistency across a completed deck
Subject: title bands, spacing zones, card systems, image treatment, and rhythm comparison
Style/medium: restrained audit board
Composition/framing: 16:9, comparative, system-focused
Constraints: no fake data labels, stay close to the current deck style
Avoid: inventing a new style, decorative overload
```

## 讲稿阶段

用途：
- 为讲稿、提词卡或节奏板提供视觉支持。

提示词骨架：

```text
Use case: ui-mockup
Asset type: speech rhythm board
Primary request: Create a visual support board for presenter notes and speaking rhythm based on a completed presentation
Subject: cue card base, pacing bands, and section separators
Style/medium: restrained speaking support graphic
Composition/framing: 16:9 or card-based layout, aligned with the final deck
Constraints: no fake long paragraphs, keep it clean and presentation-aligned
Avoid: teleprompter imitation, dashboard clutter
```
