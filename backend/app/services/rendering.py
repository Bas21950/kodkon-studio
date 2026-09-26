from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.probing import MediaProbeError, find_ffmpeg


class RenderError(RuntimeError):
    pass


def _ass_time(milliseconds: int) -> str:
    total_cs = max(0, round(milliseconds / 10))
    hours, remainder = divmod(total_cs, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _ass_color(value: str, alpha: float = 1.0) -> str:
    color = value.lstrip("#")
    red, green, blue = color[0:2], color[2:4], color[4:6]
    transparency = max(0, min(255, round((1 - alpha) * 255)))
    return f"&H{transparency:02X}{blue}{green}{red}"


def _ass_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\r\n", "\n").replace("\r", "\n").replace("\n", r"\N")


def _write_ass(path: Path, subtitles: list[dict], settings: dict) -> None:
    style = settings.get("subtitle_style") or {}
    font_size = max(18, min(96, int(style.get("font_size", 52))))
    font_color = _ass_color(str(style.get("font_color", "#FFFFFF")))
    box_color = _ass_color(str(style.get("box_color", "#111111")), float(style.get("box_opacity", 0.92)))
    margin = max(0, min(600, int(style.get("margin_bottom", 80))))
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Leelawadee UI,{font_size},{font_color},{font_color},&H00000000,{box_color},0,0,3,0,0,2,48,48,{margin},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for item in subtitles:
        text = item.get("translated_text") or item.get("source_text") or ""
        if not text.strip():
            continue
        lines.append(f"Dialogue: 0,{_ass_time(int(item['start_ms']))},{_ass_time(int(item['end_ms']))},Default,,0,0,0,,{_ass_text(text.strip())}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def _video_filter(overlays: list[dict], subtitles: list[dict]) -> str:
    filters: list[str] = []
    for item in overlays:
        red, green, blue = item["color"].lstrip("#")[0:2], item["color"].lstrip("#")[2:4], item["color"].lstrip("#")[4:6]
        color = f"0x{red}{green}{blue}@{max(0, min(1, float(item['opacity']))):.3f}"
        start = max(0, int(item["start_ms"])) / 1000
        end = max(start, int(item["end_ms"]) / 1000)
        filters.append(
            f"drawbox=x=iw*{float(item['x']):.6f}:y=ih*{float(item['y']):.6f}:"
            f"w=iw*{float(item['width']):.6f}:h=ih*{float(item['height']):.6f}:"
            f"color={color}:t=fill:enable='between(t,{start:.3f},{end:.3f})'"
        )
    if any((item.get("translated_text") or item.get("source_text") or "").strip() for item in subtitles):
        filters.append("ass=subtitles.ass")
    return ",".join(filters)


def render_video(
    source_path: Path,
    output_path: Path,
    subtitles: list[dict],
    overlays: list[dict],
    settings: dict,
    duration_ms: int | None,
    music_path: Path | None = None,
    source_has_audio: bool = False,
    voiceover_path: Path | None = None,
) -> None:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RenderError("ไม่พบ FFmpeg กรุณาติดตั้ง FFmpeg แล้วเปิดโปรแกรมใหม่")
    if settings.get("audio_mode") == "music" and music_path is None:
        raise RenderError("เลือกไฟล์เพลงที่พร้อมใช้งานก่อนเรนเดอร์")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = output_path.parent / f".render-{output_path.stem}"
    work_dir.mkdir(parents=True, exist_ok=True)
    subtitle_path = work_dir / "subtitles.ass"
    _write_ass(subtitle_path, subtitles, settings)

    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source_path)]
    video_filter = _video_filter(overlays, subtitles)
    mode = settings.get("audio_mode", "mute")
    include_source_audio = bool(settings.get("source_audio_enabled", False)) and source_has_audio
    include_voiceover = voiceover_path is not None
    if include_voiceover and not voiceover_path.is_file():
        raise RenderError("ไม่พบไฟล์เสียงพากย์ไทย")
    output_has_audio = include_source_audio or (mode == "music" and music_path is not None) or include_voiceover
    if output_has_audio:
        audio_inputs: list[str] = []
        audio_filters: list[str] = []
        next_input = 1
        duration = max(0.1, (duration_ms or 0) / 1000)
        if mode == "music" and music_path is not None:
            command.extend(["-stream_loop", "-1", "-i", str(music_path)])
            volume = max(0.0, min(1.0, float(settings.get("music_volume", 0.22))))
            fade_ms = max(0, min(10000, int(settings.get("music_fade_ms", 700))))
            fade = fade_ms / 1000
            filters = [f"volume={volume:.4f}"]
            if fade > 0:
                filters.append(f"afade=t=in:st=0:d={fade:.3f}")
                if duration > fade:
                    filters.append(f"afade=t=out:st={duration - fade:.3f}:d={fade:.3f}")
            audio_filters.append(f"[{next_input}:a]{','.join(filters)},aresample=24000,atrim=duration={duration:.3f}[amusic]")
            audio_inputs.append("[amusic]"); next_input += 1
        if include_voiceover and voiceover_path is not None:
            command.extend(["-i", str(voiceover_path)])
            volume = max(0.0, min(2.0, float(settings.get("voiceover_volume", 1.0))))
            audio_filters.append(f"[{next_input}:a]volume={volume:.4f},aresample=24000,apad,atrim=duration={duration:.3f}[avoice]")
            audio_inputs.append("[avoice]"); next_input += 1
        if include_source_audio:
            audio_filters.append(f"[0:a]aresample=24000,apad,atrim=duration={duration:.3f}[asource]")
            audio_inputs.insert(0, "[asource]")
        if len(audio_inputs) > 1:
            audio_filters.append(f"{''.join(audio_inputs)}amix=inputs={len(audio_inputs)}:duration=longest:normalize=0,alimiter=limit=0.95,atrim=duration={duration:.3f}[aout]")
        else:
            audio_filters.append(f"{audio_inputs[0]}anull[aout]")
        complex_video = f"[0:v]{video_filter}[vout]" if video_filter else "[0:v]null[vout]"
        command.extend([
            "-filter_complex", f"{complex_video};" + ";".join(audio_filters),
            "-map", "[vout]", "-map", "[aout]", "-t", f"{duration:.3f}",
        ])
    else:
        if video_filter:
            command.extend(["-vf", video_filter])
        command.extend(["-map", "0:v:0", "-an"])

    command.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
        "-metadata:s:v:0", "rotate=0", "-movflags", "+faststart", str(output_path),
    ])
    if output_has_audio:
        command[-1:-1] = ["-c:a", "aac", "-b:a", "192k"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=6 * 60 * 60, check=False, cwd=work_dir)
    except subprocess.TimeoutExpired as exc:
        raise RenderError("เรนเดอร์ใช้เวลานานเกินไป ไฟล์ต้นฉบับอาจใหญ่เกินกำลังเครื่อง") from exc
    except OSError as exc:
        raise RenderError("เปิด FFmpeg ไม่สำเร็จ ตรวจการติดตั้งแล้วลองอีกครั้ง") from exc
    finally:
        subtitle_path.unlink(missing_ok=True)
        try:
            work_dir.rmdir()
        except OSError:
            pass
    if result.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
        output_path.unlink(missing_ok=True)
        detail = (result.stderr or "").strip().splitlines()
        message = detail[-1][:300] if detail else "FFmpeg ส่งออกไฟล์ไม่สำเร็จ"
        raise RenderError(f"เรนเดอร์วิดีโอไม่สำเร็จ: {message}")
