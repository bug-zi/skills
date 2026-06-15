# MiniMax TTS 视频导出 Playbook

本文件只服务最终导出阶段：把已经定稿的逐页成图和讲稿合成为自动旁白视频。它不能参与母版、页面布局、文字排版或视觉生产。

官方参考：

- MiniMax WebSocket TTS：https://platform.minimaxi.com/docs/guides/speech-t2a-websocket
- MiniMax system voice id：https://platform.minimaxi.com/docs/faq/system-voice-id

## 使用边界

允许：

- 用 MiniMax TTS 生成逐页语音
- 用 `ffmpeg` 把每页最终图片和语音合成视频片段
- 用 `ffmpeg` 合并片段为最终 MP4
- 生成外置字幕、软字幕或硬字幕
- 用 `ffprobe` 校验音频、片段和最终视频

禁止：

- 用脚本重画页面
- 用脚本贴标题、正文、卡片或图表
- 用字幕弥补页面内容缺失
- 把 API key 写入脚本、日志、仓库或交付文件

## 标准命令

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

## 声音选择

先查看内置预设：

```bash
python3 /Users/wwyz/.codex/skills/build-professional-ppt/scripts/generate_minimax_slide_video.py \
  --list-voice-presets
```

常用 PPT 预设：

| 预设 | voice_id | 用途 |
|---|---|---|
| `male` | `Chinese (Mandarin)_Reliable_Executive` | 正式汇报、稳重男声 |
| `female` | `Chinese (Mandarin)_News_Anchor` | 正式播报、清晰女声 |
| `male_announcer` | `Chinese (Mandarin)_Male_Announcer` | 新闻式男声 |
| `female_presenter` | `Chinese (Mandarin)_News_Anchor` | 女主持/女播报 |
| `female_sweet` | `Chinese (Mandarin)_Sweet_Lady` | 轻松课程、培训 |
| `male_radio` | `Chinese (Mandarin)_Radio_Host` | 旁白感、电台男声 |
| `male_gentle` | `Chinese (Mandarin)_Gentleman` | 温和男声 |
| `female_warm` | `Chinese (Mandarin)_Warm_Bestie` | 温暖女声 |
| `male_young` | `male-qn-jingying` | 年轻男声 |
| `female_mature` | `female-chengshu` | 成熟女声 |

如果需要使用官方完整音色表中的其它声音，直接传入：

```bash
--voice-id "官方 voice_id"
```

截至本 playbook 更新时，官方系统音色表里中文普通话和粤语系统音色覆盖青年男声、青年女声、播报、主持、温暖、成熟、儿童、角色化和粤语等类别。不要在 skill 里硬背完整列表；如需完整清单，打开官方 `system voice id` 页面核对最新表。

## 模型选择

默认模型：

```bash
--model speech-2.8-hd
```

如账号权限或速度要求不同，可按 MiniMax 官方文档切换，例如：

```bash
--model speech-2.8-turbo
```

如果接口返回无权限或模型不存在，不要猜模型名；先回到官方 WebSocket TTS 文档核对当前可用模型。

## 字幕模式

```bash
--subtitle-mode none
```

不生成字幕。

```bash
--subtitle-mode srt
```

生成外置 `subtitles/slides.srt`，适合后期再编辑字幕。

```bash
--subtitle-mode soft
```

把字幕作为软字幕封装进 MP4，适合播放器可开关字幕的场景。

```bash
--subtitle-mode burn
```

把字幕烧录到画面中，适合直接播放和分享。

## 输出目录

```text
成品目录/06-视频导出/
  audio/
    01-*.mp3
  segments/
    01-*.mp4
  subtitles/
    slides.srt
  manifest.json
  项目名-自动旁白版.mp4
  old/
```

`manifest.json` 至少记录每页标题、页图路径、音频路径、片段路径、时长、voice_id 和讲稿文字，方便回溯。

## 校验规则

视频导出不能只看“文件存在”。

必须用 `ffprobe` 或脚本内置校验确认：

- 每个音频文件存在、非 0B，并且有有效音频流
- 每个片段存在、非 0B，并且有有效视频流
- 最终 MP4 同时包含视频流和音频流
- 字幕模式不是 `none` 时，`subtitles/slides.srt` 存在
- `manifest.json` 的页数和最终页图、讲稿页数一致

如果发现损坏文件：

- 不要只补一页糊弄过去
- 先定位是音频坏、片段坏还是总视频坏
- 清理对应旧文件到 `old/` 或删除缓存片段
- 重新生成并全量校验

## 讲稿格式

默认读取 `speech_script.md` 中的逐页结构：

```markdown
## 第 1 页

### 页面标题
...

### 开口句
...

### 展开解释
...

### 转场句
...
```

每页字幕和语音只来自这三段讲稿内容，不从页面图片里 OCR，也不重新改写页面内容。
