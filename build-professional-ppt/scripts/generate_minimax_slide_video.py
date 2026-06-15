#!/usr/bin/env python3
"""Generate MiniMax narration audio and stitch final slide images into a video."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import ssl
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import websockets


WS_URL = "wss://api.minimaxi.com/ws/v1/t2a_v2"
DEFAULT_MODEL = "speech-2.8-hd"
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

VOICE_PRESETS = {
    "male": "Chinese (Mandarin)_Reliable_Executive",
    "female": "Chinese (Mandarin)_News_Anchor",
    "male_executive": "Chinese (Mandarin)_Reliable_Executive",
    "male_announcer": "Chinese (Mandarin)_Male_Announcer",
    "female_presenter": "Chinese (Mandarin)_News_Anchor",
    "female_sweet": "Chinese (Mandarin)_Sweet_Lady",
    "male_radio": "Chinese (Mandarin)_Radio_Host",
    "male_gentle": "Chinese (Mandarin)_Gentleman",
    "female_warm": "Chinese (Mandarin)_Warm_Bestie",
    "male_young": "male-qn-jingying",
    "female_mature": "female-chengshu",
}


@dataclass
class SlideNarration:
    page_no: int
    title: str
    open_line: str
    explanation: str
    transition: str

    @property
    def speech_text(self) -> str:
        parts = [self.open_line.strip(), self.explanation.strip(), self.transition.strip()]
        return "\n".join(part for part in parts if part)


def natural_sort_key(value: str) -> list[object]:
    key: list[object] = []
    for part in re.split(r"(\d+)", value):
        if part:
            key.append(int(part) if part.isdigit() else part.lower())
    return key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate per-slide MiniMax TTS audio, subtitles, and an MP4 video.",
    )
    parser.add_argument("--script", default="成品目录/03-讲稿/speech_script.md")
    parser.add_argument("--image-dir", default="成品目录/01-逐页成图")
    parser.add_argument("--out-root", default="成品目录/06-视频导出")
    parser.add_argument("--video-name", default="自动旁白版.mp4")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--voice-id", default=None, help="MiniMax voice_id. Overrides --voice-preset.")
    parser.add_argument(
        "--voice-preset",
        default="male",
        choices=sorted(VOICE_PRESETS),
        help="Convenient preset for common Chinese presentation voices.",
    )
    parser.add_argument("--sample-rate", type=int, default=32000)
    parser.add_argument("--bitrate", type=int, default=128000)
    parser.add_argument("--audio-format", default="mp3", choices=["mp3", "pcm", "flac"])
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--volume", type=float, default=1.0)
    parser.add_argument("--pitch", type=int, default=0)
    parser.add_argument(
        "--list-voice-presets",
        action="store_true",
        help="Print bundled voice presets and exit without requiring MINIMAX_API_KEY.",
    )
    parser.add_argument(
        "--subtitle-mode",
        default="srt",
        choices=["none", "srt", "soft", "burn"],
        help="none: no subtitles; srt: external SRT; soft: mux SRT into MP4; burn: render subtitles into video.",
    )
    parser.add_argument("--subtitle-font-size", type=int, default=22)
    parser.add_argument("--subtitle-max-chars", type=int, default=34)
    parser.add_argument("--disable-ssl-verify", action="store_true")
    parser.add_argument("--force", action="store_true", help="Rebuild audio, segments, subtitles, and video.")
    return parser.parse_args()


def extract_field(section_text: str, field_name: str) -> str:
    pattern = rf"^###\s+{re.escape(field_name)}\s*$\n(?P<body>.*?)(?=^###\s+|\Z)"
    match = re.search(pattern, section_text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    lines: list[str] = []
    for raw_line in match.group("body").strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lines.append(line[2:].strip() if line.startswith("- ") else line)
    return "\n".join(lines).strip()


def parse_speech_script(script_path: Path) -> list[SlideNarration]:
    text = script_path.read_text(encoding="utf-8")
    parts = re.split(r"^##\s+第\s*(\d+)\s*页\s*$", text, flags=re.MULTILINE)
    narrations: list[SlideNarration] = []
    for idx in range(1, len(parts), 2):
        page_no = int(parts[idx])
        section_text = parts[idx + 1]
        narrations.append(
            SlideNarration(
                page_no=page_no,
                title=extract_field(section_text, "页面标题"),
                open_line=extract_field(section_text, "开口句"),
                explanation=extract_field(section_text, "展开解释"),
                transition=extract_field(section_text, "转场句"),
            )
        )
    if not narrations:
        raise RuntimeError(f"No slide narration sections found in {script_path}")
    return narrations


def collect_slide_images(image_dir: Path) -> list[Path]:
    images = [
        path
        for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    ]
    return sorted(images, key=lambda path: natural_sort_key(path.name))


def page_number_from_filename(path: Path) -> int | None:
    match = re.match(r"(\d+)", path.name)
    return int(match.group(1)) if match else None


async def synthesize_audio(
    text: str,
    output_path: Path,
    api_key: str,
    *,
    model: str,
    voice_id: str,
    sample_rate: int,
    bitrate: int,
    audio_format: str,
    channel: int,
    speed: float,
    volume: float,
    pitch: int,
    disable_ssl_verify: bool,
) -> None:
    headers = {"Authorization": f"Bearer {api_key}"}
    ssl_context = None
    if disable_ssl_verify:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    async with websockets.connect(WS_URL, additional_headers=headers, ssl=ssl_context) as ws:
        connected = json.loads(await ws.recv())
        if connected.get("event") != "connected_success":
            raise RuntimeError(f"MiniMax connection failed: {connected}")

        await ws.send(
            json.dumps(
                {
                    "event": "task_start",
                    "model": model,
                    "voice_setting": {
                        "voice_id": voice_id,
                        "speed": speed,
                        "vol": volume,
                        "pitch": pitch,
                        "english_normalization": False,
                    },
                    "audio_setting": {
                        "sample_rate": sample_rate,
                        "bitrate": bitrate,
                        "format": audio_format,
                        "channel": channel,
                    },
                },
                ensure_ascii=False,
            )
        )
        started = json.loads(await ws.recv())
        if started.get("event") != "task_started":
            raise RuntimeError(f"MiniMax task_start failed: {started}")

        await ws.send(json.dumps({"event": "task_continue", "text": text}, ensure_ascii=False))
        chunks = bytearray()
        while True:
            response = json.loads(await ws.recv())
            if response.get("event") == "task_failed":
                raise RuntimeError(f"MiniMax synthesis failed: {response}")
            audio_hex = response.get("data", {}).get("audio")
            if audio_hex:
                chunks.extend(bytes.fromhex(audio_hex))
            if response.get("is_final"):
                break

        await ws.send(json.dumps({"event": "task_finish"}))
        output_path.write_bytes(bytes(chunks))


def ensure_ffmpeg() -> tuple[str, str]:
    ffmpeg = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True, check=True).stdout.strip()
    ffprobe = subprocess.run(["which", "ffprobe"], capture_output=True, text=True, check=True).stdout.strip()
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg/ffprobe not found in PATH.")
    return ffmpeg, ffprobe


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def media_is_valid(ffprobe: str, media_path: Path, expected_codec_types: str | Iterable[str]) -> bool:
    if not media_path.exists() or media_path.stat().st_size <= 0:
        return False
    expected_types = {expected_codec_types} if isinstance(expected_codec_types, str) else set(expected_codec_types)
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(media_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    try:
        payload = json.loads(result.stdout)
        duration = float(payload.get("format", {}).get("duration", 0) or 0)
    except (json.JSONDecodeError, ValueError):
        return False
    stream_types = {stream.get("codec_type") for stream in payload.get("streams", [])}
    return expected_types.issubset(stream_types) and duration > 0.1


def media_duration_seconds(ffprobe: str, media_path: Path) -> float:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def render_segment(ffmpeg: str, image_path: Path, audio_path: Path, segment_path: Path) -> None:
    video_filter = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
    run(
        [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-c:v",
            "libx264",
            "-tune",
            "stillimage",
            "-vf",
            video_filter,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            "-movflags",
            "+faststart",
            str(segment_path),
        ]
    )


def concat_segments(ffmpeg: str, segment_paths: Iterable[Path], concat_file: Path, output_video: Path) -> None:
    concat_file.write_text(
        "\n".join(f"file '{segment.as_posix()}'" for segment in segment_paths) + "\n",
        encoding="utf-8",
    )
    run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output_video)])


def normalize_subtitle_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_subtitle_chunks(text: str, max_chars: int) -> list[str]:
    normalized = normalize_subtitle_text(text)
    if not normalized:
        return []
    raw_parts = [part.strip() for part in re.split(r"(?<=[。！？；;.!?])", normalized) if part.strip()]
    chunks: list[str] = []
    current = ""
    for part in raw_parts:
        if current and len(current) + len(part) <= max_chars:
            current += part
        else:
            if current:
                chunks.append(current)
            current = part
        while len(current) > max_chars:
            chunks.append(current[:max_chars])
            current = current[max_chars:]
    if current:
        chunks.append(current)
    return chunks


def srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(narrations: list[SlideNarration], durations: list[float], srt_path: Path, max_chars: int) -> None:
    entries: list[str] = []
    cursor = 0.0
    index = 1
    for narration, duration in zip(narrations, durations, strict=True):
        chunks = split_subtitle_chunks(narration.speech_text, max_chars)
        if not chunks:
            cursor += duration
            continue
        total_chars = sum(max(1, len(chunk)) for chunk in chunks)
        local_cursor = cursor
        for chunk in chunks:
            chunk_duration = duration * max(1, len(chunk)) / total_chars
            start = local_cursor
            end = min(cursor + duration, local_cursor + chunk_duration)
            entries.append(f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{chunk}\n")
            index += 1
            local_cursor = end
        cursor += duration
    srt_path.write_text("\n".join(entries), encoding="utf-8")


def subtitle_filter_path(path: Path) -> str:
    # ffmpeg subtitles filter treats ':' and '\' specially.
    value = path.as_posix().replace("\\", "\\\\").replace(":", "\\:")
    return value.replace("'", "\\'")


def mux_soft_subtitles(ffmpeg: str, video_path: Path, srt_path: Path, output_path: Path) -> None:
    run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(srt_path),
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            "mov_text",
            str(output_path),
        ]
    )


def burn_subtitles(ffmpeg: str, video_path: Path, srt_path: Path, output_path: Path, font_size: int) -> None:
    style = f"FontName=PingFang SC,FontSize={font_size},Outline=1,Shadow=0,MarginV=32"
    vf = f"subtitles='{subtitle_filter_path(srt_path)}':force_style='{style}'"
    run([ffmpeg, "-y", "-i", str(video_path), "-vf", vf, "-c:a", "copy", str(output_path)])


async def main() -> None:
    args = parse_args()
    if args.list_voice_presets:
        for preset, voice_id in sorted(VOICE_PRESETS.items()):
            print(f"{preset}: {voice_id}")
        return

    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise SystemExit("Missing MINIMAX_API_KEY environment variable.")

    script_path = Path(args.script).resolve()
    image_dir = Path(args.image_dir).resolve()
    out_root = Path(args.out_root).resolve()
    audio_dir = out_root / "audio"
    segment_dir = out_root / "segments"
    subtitle_dir = out_root / "subtitles"
    manifest_path = out_root / "manifest.json"
    concat_file = out_root / "segments.txt"
    srt_path = subtitle_dir / "slides.srt"
    final_video_path = out_root / args.video_name
    plain_video_path = final_video_path if args.subtitle_mode in {"none", "srt"} else out_root / f"{final_video_path.stem}-plain.mp4"

    out_root.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    segment_dir.mkdir(parents=True, exist_ok=True)
    subtitle_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg, ffprobe = ensure_ffmpeg()
    narrations = parse_speech_script(script_path)
    image_map = {
        page_number_from_filename(path): path
        for path in collect_slide_images(image_dir)
        if page_number_from_filename(path) is not None
    }
    voice_id = args.voice_id or VOICE_PRESETS[args.voice_preset]

    manifest = []
    segment_paths: list[Path] = []
    durations: list[float] = []

    for narration in narrations:
        image_path = image_map.get(narration.page_no)
        if image_path is None:
            raise RuntimeError(f"Missing image for page {narration.page_no}")

        audio_path = audio_dir / f"{narration.page_no:02d}-{image_path.stem}.{args.audio_format}"
        segment_path = segment_dir / f"{narration.page_no:02d}-{image_path.stem}.mp4"
        segment_paths.append(segment_path)

        if args.force or not media_is_valid(ffprobe, audio_path, "audio"):
            remove_if_exists(audio_path)
            await synthesize_audio(
                narration.speech_text,
                audio_path,
                api_key,
                model=args.model,
                voice_id=voice_id,
                sample_rate=args.sample_rate,
                bitrate=args.bitrate,
                audio_format=args.audio_format,
                channel=args.channel,
                speed=args.speed,
                volume=args.volume,
                pitch=args.pitch,
                disable_ssl_verify=args.disable_ssl_verify,
            )
        if not media_is_valid(ffprobe, audio_path, "audio"):
            raise RuntimeError(f"Invalid audio after synthesis: {audio_path}")

        audio_mtime = audio_path.stat().st_mtime
        segment_mtime = segment_path.stat().st_mtime if segment_path.exists() else 0
        if args.force or not media_is_valid(ffprobe, segment_path, "video") or audio_mtime >= segment_mtime:
            remove_if_exists(segment_path)
            render_segment(ffmpeg, image_path, audio_path, segment_path)
        if not media_is_valid(ffprobe, segment_path, "video"):
            raise RuntimeError(f"Invalid segment after render: {segment_path}")

        duration = media_duration_seconds(ffprobe, audio_path)
        durations.append(duration)
        manifest.append(
            {
                "page_no": narration.page_no,
                "title": narration.title,
                "image": str(image_path),
                "audio": str(audio_path),
                "segment": str(segment_path),
                "duration_seconds": round(duration, 3),
                "voice_id": voice_id,
                "speech_text": narration.speech_text,
            }
        )

    invalid_segments = [segment for segment in segment_paths if not media_is_valid(ffprobe, segment, "video")]
    if invalid_segments:
        names = ", ".join(segment.name for segment in invalid_segments)
        raise RuntimeError(f"Refusing concat because invalid segments remain: {names}")

    if args.subtitle_mode != "none":
        write_srt(narrations, durations, srt_path, args.subtitle_max_chars)

    video_is_current = media_is_valid(ffprobe, plain_video_path, ("video", "audio"))
    video_mtime = plain_video_path.stat().st_mtime if plain_video_path.exists() else 0
    segments_newer_than_video = any(segment.stat().st_mtime >= video_mtime for segment in segment_paths)
    if args.force or not video_is_current or segments_newer_than_video:
        remove_if_exists(plain_video_path)
        concat_segments(ffmpeg, segment_paths, concat_file, plain_video_path)
    if not media_is_valid(ffprobe, plain_video_path, ("video", "audio")):
        raise RuntimeError(f"Invalid plain video after concat: {plain_video_path}")

    if args.subtitle_mode == "soft":
        remove_if_exists(final_video_path)
        mux_soft_subtitles(ffmpeg, plain_video_path, srt_path, final_video_path)
    elif args.subtitle_mode == "burn":
        remove_if_exists(final_video_path)
        burn_subtitles(ffmpeg, plain_video_path, srt_path, final_video_path, args.subtitle_font_size)

    if not media_is_valid(ffprobe, final_video_path, ("video", "audio")):
        raise RuntimeError(f"Invalid final video: {final_video_path}")

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Voice ID: {voice_id}")
    print(f"Generated audio: {audio_dir}")
    print(f"Generated segments: {segment_dir}")
    if args.subtitle_mode != "none":
        print(f"Generated subtitles: {srt_path}")
    print(f"Generated video: {final_video_path}")
    print(f"Generated manifest: {manifest_path}")


if __name__ == "__main__":
    asyncio.run(main())
