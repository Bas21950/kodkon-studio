from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from app.config import settings


class MediaProbeError(RuntimeError):
    def __init__(self, code: str, user_message: str):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


def find_ffprobe() -> str | None:
    configured = settings.resolved_ffprobe
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("ffprobe")


def find_ffmpeg() -> str | None:
    configured = os.environ.get("FFMPEG_PATH")
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("ffmpeg")


def _probe_media(path: Path, expected_kind: str) -> dict:
    executable = find_ffprobe()
    if not executable:
        raise MediaProbeError("ffprobe_missing", "พบไฟล์แล้ว แต่ไม่พบ ffprobe กรุณาติดตั้ง FFmpeg แล้วเปิดโปรแกรมใหม่")

    command = [
        executable,
        "-v", "error",
        "-show_entries", "format=duration,format_name:stream=codec_type,codec_name,width,height,duration,avg_frame_rate,r_frame_rate:stream_tags=rotate:stream_side_data=rotation",
        "-of", "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeError("probe_timeout", "อ่านข้อมูลวิดีโอนานเกินไป ลองไฟล์ที่เล็กลงหรือแปลงเป็น MP4") from exc
    except OSError as exc:
        raise MediaProbeError("probe_failed", "เปิดไฟล์ด้วย ffprobe ไม่สำเร็จ") from exc

    if result.returncode != 0:
        raise MediaProbeError("invalid_media", "อ่านวิดีโอไม่ได้ ไฟล์อาจเสียหรือรูปแบบไม่รองรับ")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProbeError("invalid_probe_data", "อ่านข้อมูลวิดีโอไม่สำเร็จ") from exc

    streams = data.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if expected_kind == "source_video" and not video:
        raise MediaProbeError("video_stream_missing", "ไฟล์นี้ไม่มีแทร็กวิดีโอ")
    if expected_kind == "music_track" and not audio:
        raise MediaProbeError("audio_stream_missing", "ไฟล์นี้ไม่มีแทร็กเสียง")

    format_info = data.get("format", {})
    selected_stream = video if expected_kind == "source_video" else audio
    duration = format_info.get("duration") or (selected_stream or {}).get("duration")
    try:
        duration_ms = max(0, round(float(duration) * 1000)) if duration is not None else None
    except (TypeError, ValueError):
        duration_ms = None

    rotation = 0
    tags = (video or {}).get("tags") or {}
    side_data = (video or {}).get("side_data_list") or []
    raw_rotation = tags.get("rotate")
    if raw_rotation is None and side_data:
        raw_rotation = side_data[0].get("rotation")
    try:
        rotation = int(round(float(raw_rotation or 0))) % 360
    except (TypeError, ValueError):
        rotation = 0

    width = (video or {}).get("width")
    height = (video or {}).get("height")
    frame_rate = None
    for raw_rate in ((video or {}).get("avg_frame_rate"), (video or {}).get("r_frame_rate")):
        try:
            numerator, denominator = raw_rate.split("/", 1)
            if float(denominator):
                candidate_rate = float(numerator) / float(denominator)
                if candidate_rate > 0:
                    frame_rate = candidate_rate
                    break
        except (AttributeError, ValueError, ZeroDivisionError):
            continue
    if rotation in {90, 270}:
        width, height = height, width

    return {
        "duration_ms": duration_ms,
        "width": width,
        "height": height,
        "has_audio": audio is not None,
        "frame_rate": frame_rate,
        "video_codec": video.get("codec_name") if video else None,
        "container_format": format_info.get("format_name"),
    }


def probe_video(path: Path) -> dict:
    return _probe_media(path, "source_video")


def probe_audio(path: Path) -> dict:
    return _probe_media(path, "music_track")
