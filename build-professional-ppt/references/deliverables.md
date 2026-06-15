# 交付物与目录规范

这个技能的目标不是只得到一组最终页面图，而是沉淀一套后续还能维护和复用的风格、模版、施工资产和正式交付。

但默认流程不再要求额外生成“章节分镜板”“10 页总览拼图”“第一批参考视觉页”。这些只在用户明确要求时，才作为可选补充产物存在。

## 目录结论

正式交付目录固定使用六类业务目录：

- `风格目录`
- `模版目录`
- `设计规范`
- `PPT大纲`
- `素材目录`
- `成品目录`

如需保留工程缓存，可以额外使用 `outputs/<deck-name>/`，但它不能替代正式业务目录。

## 推荐目录

```text
<project-root>/
  风格目录/
    00-风格总表.md
    01-手绘白板风/
      style.md
      refs/
      moodboard/
      prompts.md
      sample-pages/
    02-项目参考样式-当前成图/
      style.md
      refs/
      moodboard/
      prompts.md
      sample-pages/
    03-教育-信息图课堂风/
      style.md
      refs/
      moodboard/
      prompts.md
      sample-pages/
    04-教育-校园杂志风/
      style.md
      refs/
      moodboard/
      prompts.md
      sample-pages/
    05-办公-策略简报风/
      style.md
      refs/
      moodboard/
      prompts.md
      sample-pages/
    06-办公-培训工作坊风/
      style.md
      refs/
      moodboard/
      prompts.md
      sample-pages/
    07-产品-故事演示风/
      style.md
      refs/
      moodboard/
      prompts.md
      sample-pages/
    08-产品-界面主导风/
      style.md
      refs/
      moodboard/
      prompts.md
      sample-pages/
    old/

  模版目录/
    00-模版总表.md
    01-汇报材料/
      章节编排.md
      逐页清单.md
      内容要求.md
      适用场景.md
    02-课程/
      章节编排.md
      逐页清单.md
      内容要求.md
      适用场景.md
    03-培训/
      章节编排.md
      逐页清单.md
      内容要求.md
      适用场景.md
    04-产品介绍/
      章节编排.md
      逐页清单.md
      内容要求.md
      适用场景.md
    05-项目方案/
      章节编排.md
      逐页清单.md
      内容要求.md
      适用场景.md
    06-路演融资/
      章节编排.md
      逐页清单.md
      内容要求.md
      适用场景.md
    old/

  设计规范/
    design.md
    research_brief.md
    设计规范效果图.png
    element_source_log.md
    master_selection.md
    confirmation_log.md
    review_report.md
    process_log.md
    old/

  PPT大纲/
    narrative_plan.md
    PPT大纲-逐页内容.md
    slide_speech_map.md
    old/

  素材目录/
    00-调研与风格板/
      01-调研风格板.png
      02-moodboard.png
      03-设计规范效果图.png
      04-官方元素参考/
    01-母版图/
      00-风格总板或组件总板.png
      01-封面空母版.png
      02-目录页或章节页空母版.png
      03-内容页空母版-右承载.png
      04-内容页空母版-左承载.png
      05-内容页空母版-上下留白.png
      06-内容页空母版-中间留白.png
      07-内容页空母版-全白承载.png
      08-结尾页空母版.png
      09-可选-复杂页空白变体.png
    03-逐页素材/
      01-封面/
        00-施工卡/
          内容与素材清单.md
        01-空背景图/
        02-页面框定/
        03-插图与子图/
        04-复杂示意图分件/
        05-整页成图/
        06-拼装预览/
        07-局部微调/
        08-定稿参考/
        old/
      02-章节引题/
        ...

  成品目录/
    01-逐页成图/
      old/
    03-讲稿/
      old/
    04-PDF导出/
      old/
    05-汇总交付/
      old/
    06-视频导出/
      audio/
      segments/
      subtitles/
      old/
      manifest.json
      自动旁白版.mp4
```

技能内置示例目录：

```text
build-professional-ppt/
  assets/
    master-examples/
      handdrawn-whiteboard/
        01-cover-empty-master.png
        02-agenda-or-section-empty-master.png
        03-content-empty-master-a.png
        04-content-empty-master-b.png
        05-ending-empty-master.png
        old/
      non-handdrawn-editorial/
        01-cover-empty-master.png
        02-agenda-or-section-empty-master.png
        03-content-empty-master-a.png
        04-content-empty-master-b.png
        05-ending-empty-master.png
        old/
      tech-futuristic/
        01-cover-empty-master.png
        02-agenda-or-section-empty-master.png
        03-content-empty-master-a.png
        04-content-empty-master-b.png
        05-ending-empty-master.png
        old/
```

这些示例图用于帮助 AI 理解“什么是母版”，不作为具体项目的最终交付物。

## 确认关口要求

在正式逐页成图前，至少要补齐：

- `设计规范/confirmation_log.md`
- `设计规范/设计规范效果图.png`
- `设计规范/element_source_log.md`

其中至少记录三次确认：

- 设计确认
- 母版确认
- 大纲确认

没有这三项中的明确通过记录，不应进入正式逐页成图阶段。

`设计规范/设计规范效果图.png` 的作用是：

- 在设计确认阶段给用户快速看懂整体视觉方向
- 把封面气质、色盘、字体、图像语言、纹理、图示语言和页面节奏合成在一张图里
- 作为母版阶段之前的视觉确认板，而不是母版本身

`设计规范/element_source_log.md` 的作用是：

- 记录哪些元素来自真实官方来源
- 记录哪些位置只能使用通用 fallback
- 防止在设计确认板、母版和正式页里混入“看起来像真的”假元素

## 一致性结论

下列内容必须始终一致：

- 最终页面成图
- `PPT大纲*.md`
- `slide_speech_map.md`
- `speech_script.md`
- 最终 `.pptx`
- 最终 PDF 页序
- 最终 `.docx`
- 最终 `.mp4`
- 最终字幕 `.srt`
- `review_report.md`

最低要求：

- 页数一致
- 页序一致
- 页面标题一致
- 主判断一致
- 章节名、案例名、架构名一致

## 风格目录要求

`风格目录/` 不是参考图堆放区，而是可复用的风格资产库。

至少维护：

- `01-手绘白板风/`
- `02-项目参考样式-当前成图/`

其中 `02-项目参考样式-当前成图/` 的来源优先是：

- 项目根目录已有 `成图/`
- 或 `成品目录/01-逐页成图/`
- 或历史正式页面

每个风格文件夹至少包含：

- `style.md`
- `refs/`
- `moodboard/`
- `prompts.md`
- `sample-pages/`

`style.md` 至少写清：

- 风格名称
- 适用领域
- 风格关键词
- 适配页型
- 布局节奏
- 颜色和图像处理方式
- 应避免的误用

## 模版目录要求

`模版目录/` 用于沉淀常见 PPT 需求的章节编排，不允许每次都从零想页序。

至少维护：

- `01-汇报材料/`
- `02-课程/`
- `03-培训/`
- `04-产品介绍/`

每个模版文件夹至少包含：

- `章节编排.md`
- `逐页清单.md`
- `内容要求.md`
- `适用场景.md`

## 设计规范要求

`设计规范/` 至少包含：

- `design.md`
- `research_brief.md`
- `master_selection.md`
- `review_report.md`
- `process_log.md`
- `old/`

作用：

- 定义设计目标
- 记录调研结论
- 固定母版选择
- 记录审查与微调
- 记录过程变更

## 大纲目录要求

`PPT大纲/` 至少包含：

- `narrative_plan.md`
- `PPT大纲*.md`
- `slide_speech_map.md`
- `old/`

作用：

- 固定叙事主线
- 固定逐页内容
- 固定页面和讲稿映射

## 素材目录要求

`素材目录/` 至少包含：

- `00-调研与风格板/`
- `01-母版图/`
- `03-逐页素材/`

每一页都必须有独立目录，且至少沉淀一组过程素材，不允许只剩最终成图。

## 母版目录要求

`素材目录/01-母版图/` 里放的是一组真正可复用的空效果模板，不是只有一张风格说明板。

至少包含：

- 封面空母版
- 目录页或章节页空母版
- `4-6` 张内容页空母版
- 结尾页空母版

可选包含：

- 复杂页空白变体
- 风格总板
- 组件总板
- 标题系统总板

注意：

- 风格总板、组件总板不等于母版页
- 母版页必须是空图，后续用于填充真实内容
- 母版页应以留白承载为先，视觉元素尽量压在边缘、底部或单侧
- 预画了具体流程、关系、模块骨架的图，不算基础母版页

## 逐页素材目录详细规范

推荐命名：

- `01-封面/`
- `02-章节引题/`
- `03-现实背景/`
- `09-整体架构/`
- `14-典型案例-琴房管理员/`

每页推荐固定子目录：

- `00-施工卡/`
- `01-空背景图/`
- `02-页面框定/`
- `03-插图与子图/`
- `04-复杂示意图分件/`
- `05-整页成图/`
- `06-拼装预览/`
- `07-局部微调/`
- `08-定稿参考/`
- `old/`

其中：

- `02-页面框定/` 仅复杂页默认使用
- `04-复杂示意图分件/` 仅复杂页默认使用
- `06-拼装预览/` 仅复杂页默认使用

归类规则：

- 完全空背景图放 `01-空背景图/`
- 页面结构框定图放 `02-页面框定/`
- 普通主视觉、案例图、小插图、简单子图放 `03-插图与子图/`
- 架构页、流程页、复杂示意图分件放 `04-复杂示意图分件/`
- 直接整页成图放 `05-整页成图/`
- 多分件拼装过程图放 `06-拼装预览/`
- 微调后的局部纹理、小图标、局部重绘素材放 `07-局部微调/`
- 最终交接图、定稿对照说明放 `08-定稿参考/`

额外要求：

- `01-空背景图/` 中只能放完全空背景，不放半成品页面
- `05-整页成图/` 中必须是带真实标题和真实内容的整页图，不放“只有效果没有文字”的展示图

## 成品目录要求

`成品目录/` 至少包含：

- `01-逐页成图/`
- `03-讲稿/`
- `04-PDF导出/`
- `05-汇总交付/`
- `06-视频导出/`

作用：

- 沉淀最终页面、讲稿、PDF、PPT、Word、视频和交付包
- 不和过程素材混放

推荐放置规则：

- `成品目录/04-PDF导出/` 只放正式 `.pdf`
- `成品目录/05-汇总交付/` 放正式 `.pptx`、`.docx` 和最终打包交付文件
- `成品目录/06-视频导出/` 放逐页语音、视频片段、字幕、校验清单和最终 `.mp4`

推荐文件：

- `成品目录/04-PDF导出/<项目名>-汇报.pdf`
- `成品目录/05-汇总交付/<项目名>-汇报.pptx`
- `成品目录/05-汇总交付/<项目名>-讲稿.docx`
- `成品目录/05-汇总交付/<项目名>-汇报资料.docx`
- `成品目录/06-视频导出/<项目名>-自动旁白版.mp4`
- `成品目录/06-视频导出/subtitles/slides.srt`
- `成品目录/06-视频导出/manifest.json`

## 页面变更时必须同步的文件

### 新增页面时

至少同步：

- `PPT大纲/PPT大纲*.md`
- `PPT大纲/slide_speech_map.md`
- `素材目录/03-逐页素材/<页码-页名>/`
- `成品目录/01-逐页成图/`
- `成品目录/03-讲稿/`
- `成品目录/04-PDF导出/`
- `成品目录/05-汇总交付/`
- `成品目录/06-视频导出/`
- `设计规范/review_report.md`
- `设计规范/process_log.md`

### 删减页面时

至少同步：

- `PPT大纲/PPT大纲*.md`
- `PPT大纲/slide_speech_map.md`
- 当前页素材目录 `old/`
- `成品目录/01-逐页成图/old/`
- `成品目录/03-讲稿/old/`
- `成品目录/04-PDF导出/old/`
- `成品目录/05-汇总交付/old/`
- `成品目录/06-视频导出/old/`
- `设计规范/review_report.md`
- `设计规范/process_log.md`

### 修改页面时

至少同步：

- `PPT大纲/PPT大纲*.md`
- 如页型变化，还要同步 `设计规范/design.md`
- 当前页素材目录和 `old/`
- `成品目录/01-逐页成图/`
- `成品目录/03-讲稿/`
- `成品目录/04-PDF导出/`
- `成品目录/05-汇总交付/`
- `成品目录/06-视频导出/`
- `设计规范/review_report.md`
- `设计规范/process_log.md`

## 过程管理结论

过程管理至少包含两件事：

1. 变更留痕
2. 旧版归档

必须保留：

- `设计规范/process_log.md`

旧文件归档规则：

- 旧文件不能直接删除
- 替换正式文件前，先把旧版移入最近的 `old/`
- `old/` 文件建议带日期或版本号

推荐命名：

- `slide-09-整体架构-2026-04-23-v1.png`
- `speech_script-2026-04-23-v2.md`
- `项目名-汇报-2026-04-23-v1.pdf`
