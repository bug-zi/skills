# 交付导出 Playbook

这份文档用于说明如何导出 `PPT`、`PDF`、`Word`、`Video` 四类交付文件。

最重要的原则只有两条：

1. 导出必须发生在最终页面成图稳定之后。
2. 导出是封装，不是重新做视觉，不允许在导出阶段重画页面。

## 导出源文件

导出阶段只允许使用这些最终资产：

- `成品目录/01-逐页成图/`
- `PPT大纲/PPT大纲*.md`
- `PPT大纲/slide_speech_map.md`
- `成品目录/03-讲稿/speech_script.md`
- `成品目录/03-讲稿/speaker_notes.md`

不要使用：

- `素材目录/` 里的中间稿
- 候选图
- 旧版文件
- 未定稿图片

视频导出还需要：

- `MINIMAX_API_KEY` 环境变量
- `ffmpeg`
- `ffprobe`

## 一、导出 PPT

### 定义

本 skill 里的 `PPT 导出` 默认指：

- 把最终逐页成图封装进 `.pptx`
- 一页图对应一张 slide
- 可附带讲稿备注

它不是：

- 重新在 PowerPoint 里做一套可编辑版式
- 重新排文字
- 重新画图形、卡片、母版

### 正确做法

默认源：

- `成品目录/01-逐页成图/`

默认输出：

- `成品目录/05-汇总交付/<项目名>-汇报.pptx`

允许的装配方式：

- 以最终页图作为整页背景或整页主图
- 一张页图放一页
- 如需要，可同步写入 speaker notes

允许的备注来源：

- `speaker_notes.md`
- `slide_speech_map.md`

### 禁止做法

- 不要在导出阶段重排版
- 不要重新在 PPT 里写标题、正文、卡片
- 不要把导出 `.pptx` 当成重新生产页面的机会
- 不要用 JS/Python/HTML 重新生成一套视觉再导出 `.pptx`

### 导出前检查

至少检查：

1. 页序是否与最终页图一致
2. 页数是否完整
3. 每页是否是一图一页
4. 是否误把中间稿装进 `.pptx`

## 二、导出 PDF

### 定义

`PDF 导出` 指把最终逐页成图按顺序合成正式 PDF。

### 正确做法

默认源：

- `成品目录/01-逐页成图/`

默认输出：

- `成品目录/04-PDF导出/<项目名>-汇报.pdf`

推荐使用现有脚本：

```bash
python3 scripts/export_slide_images_to_pdf.py \
  --input-dir "成品目录/01-逐页成图" \
  --output "成品目录/04-PDF导出/项目名-汇报.pdf"
```

### 禁止做法

- 不要用 PDF 导出脚本承担绘图或排版
- 不要把 PDF 导出脚本扩展成页面生成器
- 不要混入中间稿和候选图

### 导出前检查

至少检查：

1. 页序
2. 页数
3. 首尾页
4. 是否有裁切、拉伸、压缩失真

## 三、导出 Word

### 定义

`Word 导出` 默认有两种模式：

1. `讲稿版 DOCX`
2. `汇报资料版 DOCX`

### 1. 讲稿版 DOCX

适用：

- 领导讲稿
- 演讲提词稿
- 汇报讲解稿

默认源：

- `speech_script.md`
- `speaker_notes.md`
- `slide_speech_map.md`

默认输出：

- `成品目录/05-汇总交付/<项目名>-讲稿.docx`

说明：

- Word 内容来自最终讲稿 markdown
- 如需插图，只插最终页图缩略图，不重新排版页面

### 2. 汇报资料版 DOCX

适用：

- 会后留档
- 汇报材料归档
- 配套说明文档

默认源：

- `PPT大纲*.md`
- `slide_speech_map.md`
- 最终页图

默认输出：

- `成品目录/05-汇总交付/<项目名>-汇报资料.docx`

说明：

- 可以按“页标题 + 页面缩略图 + 要点说明”的形式导出
- 文档以说明和归档为目的，不是重新做 PPT

### 禁止做法

- 不要在 Word 导出阶段重写内容
- 不要让 Word 成为重新排版页面的地方
- 不要把页面重新拆成 Word 表格或形状再做一次

## 四、导出视频

### 定义

`Video 导出` 指把最终逐页成图和最终讲稿合成为自动旁白视频。

默认链路：

1. 每页最终成图保持不变。
2. 按页读取 `speech_script.md`。
3. 调用 MiniMax TTS 生成逐页语音。
4. 用 `ffmpeg` 把每页图片和对应语音合成为视频片段。
5. 按页序合并为最终 `.mp4`。
6. 按需生成 `srt`、软字幕或硬字幕。

它不是：

- 重新生成页面
- 用代码贴标题或正文
- 用视频脚本排版 PPT
- 用字幕替代页面里的正式文字

### 正确做法

默认源：

- `成品目录/01-逐页成图/`
- `成品目录/03-讲稿/speech_script.md`

默认输出：

- `成品目录/06-视频导出/audio/`
- `成品目录/06-视频导出/segments/`
- `成品目录/06-视频导出/subtitles/slides.srt`
- `成品目录/06-视频导出/manifest.json`
- `成品目录/06-视频导出/<项目名>-自动旁白版.mp4`

推荐使用现有脚本：

```bash
export MINIMAX_API_KEY="填入你的 MiniMax API key"

python3 /Users/wwyz/.codex/skills/build-professional-ppt/scripts/generate_minimax_slide_video.py \
  --script "成品目录/03-讲稿/speech_script.md" \
  --image-dir "成品目录/01-逐页成图" \
  --out-root "成品目录/06-视频导出" \
  --video-name "项目名-自动旁白版.mp4" \
  --voice-preset male \
  --subtitle-mode burn
```

不要把 API key 写进脚本、`design.md`、日志或交付文件。

### 声音切换

查看内置声音预设：

```bash
python3 /Users/wwyz/.codex/skills/build-professional-ppt/scripts/generate_minimax_slide_video.py \
  --list-voice-presets
```

常用方式：

- `--voice-preset male`：正式沉稳男声
- `--voice-preset female`：新闻播报女声
- `--voice-preset male_announcer`：播报男声
- `--voice-preset female_sweet`：甜美女声
- `--voice-id "官方 voice_id"`：手动指定 MiniMax 官方系统音色

### 字幕模式

- `--subtitle-mode none`：不生成字幕
- `--subtitle-mode srt`：生成外置 `slides.srt`
- `--subtitle-mode soft`：把字幕作为软字幕封装进 MP4
- `--subtitle-mode burn`：把字幕烧录进画面

### 导出前检查

至少检查：

1. 页图数量、讲稿页数、音频数量是否一致
2. 每段音频是否有效，不允许 0B 空壳文件
3. 每个视频片段是否包含有效视频流
4. 最终 MP4 是否同时包含音频流和视频流
5. 如启用字幕，`slides.srt` 是否存在且时间轴覆盖全片
6. 是否误把旧片段或损坏片段合并进总视频

### 禁止做法

- 不要用视频脚本生成或修改页面视觉
- 不要用字幕后贴来弥补页面内容缺失
- 不要复用损坏的音频、片段或旧总视频
- 不要把 MiniMax API key 写入仓库或交付目录

更完整的 MiniMax TTS 和字幕说明见 `references/minimax-tts-video-playbook.md`。

## 五、导出顺序建议

推荐顺序：

1. 最终逐页成图定稿
2. 讲稿文件定稿
3. 导出 PDF
4. 如用户需要，再导出 PPT
5. 如用户需要，再导出 Word
6. 如用户需要，再导出 Video
7. 把 PDF/PPT/Word 归到 `成品目录/05-汇总交付/` 或对应目录，把视频归到 `成品目录/06-视频导出/`

## 六、工具边界

导出阶段允许：

- PDF 合成脚本
- 文档导出能力
- 演示文稿封装能力
- MiniMax TTS
- `ffmpeg` / `ffprobe`
- 视频合成与字幕后处理脚本
- 命令行文件管理

导出阶段不允许：

- 重新调用代码排版引擎生成新页面
- 把导出工具升级成页面生产工具
- 用导出为借口绕过 `imagegen`

## 七、命名建议

推荐文件名：

- `<项目名>-汇报.pdf`
- `<项目名>-汇报.pptx`
- `<项目名>-讲稿.docx`
- `<项目名>-汇报资料.docx`
- `<项目名>-自动旁白版.mp4`
- `slides.srt`

## 八、最重要的边界

一句话记住：

`PPT / PDF / Word / Video 都只能导出最终成果，不能反过来替代页面生产。`
