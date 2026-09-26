from __future__ import annotations

import re
import uuid

from app.schemas import SubtitleSegmentWrite

TIMESTAMP = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})$")


def parse_timestamp(value: str) -> int:
    match = TIMESTAMP.match(value.strip())
    if not match:
        raise ValueError(f"รูปแบบเวลาไม่ถูกต้อง: {value.strip()}")
    hours, minutes, seconds, fraction = match.groups()
    millis = int(fraction.ljust(3, "0")[:3])
    return (((int(hours) * 60 + int(minutes)) * 60) + int(seconds)) * 1000 + millis


def parse_srt(text: str) -> list[SubtitleSegmentWrite]:
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized) > 2_000_000:
        raise ValueError("ไฟล์ซับยาวเกิน 2 MB")
    blocks = re.split(r"\n\s*\n", normalized.strip()) if normalized.strip() else []
    results: list[SubtitleSegmentWrite] = []
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.split("\n") if line.strip()]
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            continue
        if time_index + 1 >= len(lines):
            raise ValueError("พบช่วงซับที่ไม่มีข้อความ")
        start_part, end_part = (part.strip().split()[0] for part in lines[time_index].split("-->", 1))
        start_ms = parse_timestamp(start_part)
        end_ms = parse_timestamp(end_part)
        if end_ms <= start_ms:
            raise ValueError("เวลาจบซับต้องอยู่หลังเวลาเริ่ม")
        text_value = "\n".join(lines[time_index + 1:]).strip()
        results.append(SubtitleSegmentWrite(
            stable_id=str(uuid.uuid4()),
            start_ms=start_ms,
            end_ms=end_ms,
            source_text=text_value,
            translated_text="",
            review_flag=False,
        ))
    if not results and normalized.strip():
        raise ValueError("ไม่พบช่วงเวลา SRT รูปแบบ 00:00:01,000 --> 00:00:03,000")
    return results


def format_srt_timestamp(value_ms: int) -> str:
    value_ms = max(0, value_ms)
    hours, rem = divmod(value_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def serialize_srt(items) -> str:
    blocks = []
    for index, item in enumerate(items, start=1):
        text_value = (item.translated_text or item.source_text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not text_value.strip():
            continue
        blocks.append(
            f"{index}\n{format_srt_timestamp(item.start_ms)} --> {format_srt_timestamp(item.end_ms)}\n{text_value.strip()}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")
