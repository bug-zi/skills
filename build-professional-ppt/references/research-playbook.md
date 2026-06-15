# 调研查资料与定设计 Playbook

这一步是学校或机构型汇报的起点。先查真实来源，再定设计，不要一上来就凭印象做图。

开始前先记住一条硬规则：

- 先找真实元素，找不到就退回通用元素，不要伪造。

## 适用场景

- 学校汇报
- 高校项目申报
- 政府单位、医院、文化机构、国企汇报
- 任何必须体现真实机构身份的正式 PPT

## 调研优先级

优先看官方来源，顺序如下：

1. 官方网站首页
2. 官方简介页
3. 校史、院训、办学理念、品牌故事
4. 官方新闻与专题页
5. 官方宣传图、建筑图、校园风光
6. logo、校色、视觉识别资料
7. 招生简章、宣传册、视频封面、海报

如果官方资料不足，再看这些补充来源：

- 官方公众号
- 官方视频号或宣传片
- 官方媒体报道

避免：

- 先看第三方百科总结
- 先看别人做过的泛化模板
- 只凭“这个学校应该很文艺/很科技”做主观判断

## 调研要提取什么

至少提取六类信息：

### 1. 身份锚点

- 最有辨识度的建筑
- 最常出现的门头、雕塑、场馆、地标
- 官方视觉里最常出现的实景

### 2. 风格气质

- 是庄重、艺术、学术、治理、科技，还是公共服务型
- 官方页面更偏克制、热烈、现代，还是传统

### 3. 色彩线索

- 官网高频主色
- 辅助色
- 是否偏暖色、冷色、中性色

### 4. 版式线索

- 官网或宣传图更偏大图、大留白，还是信息密集
- 标题通常是横向标题、竖向信息条，还是居中标题

### 5. 图片线索

- 更常用建筑、人物、活动、器物，还是抽象图形
- 图片是纪实、艺术化，还是仪式感表达

### 6. 避免项

- 哪些 AI 风格会让机构身份消失
- 哪些常见科技蓝、紫光、赛博 UI 明显不适合

## 调研时必须主动找的设计元素

至少主动找下面这些：

- logo、校徽、院徽、品牌标志
- 官网主色、辅助色
- 官方建筑照片或真实场景
- 常见门头、雕塑、场馆、器物
- 官方纹理、底纹、宣传板式
- 真实教材、平台、设备、课堂场景

如果找不到某一类元素：

- 不要编一个“很像真的”版本
- 直接回退到通用元素
- 并记录到 `设计规范/element_source_log.md`

具体规则参考：

- `references/element-sourcing.md`

## 调研产物

至少输出这些内容：

- `research_brief.md`
- `element_source_log.md`
- 官方来源清单
- 官网截图或代表性宣传图截图
- 建筑和场景参考图板
- 调研阶段生成的风格板

## `research_brief.md` 建议结构

```text
项目对象：
官方来源：
机构核心气质：
视觉身份锚点：
高频颜色：
高频场景：
推荐风格关键词：
推荐避免项：
建议内容页模版：
```

## 调研阶段如何用 `imagegen`

调研不是只收集截图，还要把判断转成视觉方向。

这一阶段建议用 `imagegen` 生成：

- 风格板
- moodboard
- 基于官方气质的方向试验图
- “真实身份 + 视觉再解释”的概念图

但要遵守：

- 具体建筑、校牌、石刻、场馆、产品界面要先有真实来源
- 没有真实来源时，只能用通用元素，不要让 AI 自己补一个假的机构元素

## 调研阶段提示词骨架

```text
Use case: ui-mockup
Asset type: research moodboard
Primary request: Create a style board for a formal presentation deck based on the official visual identity of [institution]
Scene/backdrop: institutional research board
Subject: text-free moodboard combining architecture, atmosphere, color cues, and presentation tone
Style/medium: restrained editorial design board
Composition/framing: 16:9, clear blocks for architecture, color, atmosphere, and layout direction
Lighting/mood: aligned with the institution's official tone
Constraints: no readable text, no watermark, no generic sci-fi styling, preserve authentic institutional cues
Avoid: random futuristic campus, unrelated landmarks, generic corporate blue dashboard, fake campus buildings, fake institutional seals
```

## 调研完成的判断标准

满足下面四条，才算可以进入母版阶段：

- 已经找到真实官方来源
- 已经明确代表性建筑、颜色和场景
- 已经知道该像什么、不该像什么
- 已经把调研结论变成一张或一组风格板
- 已经把真实元素和通用 fallback 记录进 `element_source_log.md`
