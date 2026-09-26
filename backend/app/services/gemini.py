from __future__ import annotations

import json
import base64
from typing import Any

import httpx
import wave
import io
import logging
import random
import time


class GeminiError(RuntimeError):
    def __init__(self, code: str, user_message: str, retry_after: str | None = None):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.retry_after = retry_after


logger = logging.getLogger(__name__)


def generate_speech(api_key: str, text: str, voice: str = "Kore") -> bytes:
    """Generate a 24 kHz mono WAV with Gemini TTS."""
    prompt = "Read this Thai product voiceover naturally, with a warm, friendly conversational tone, clear Thai pronunciation, and a moderate pace. Do not add or omit words:\n" + text
    try:
        response = httpx.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={"model": "gemini-3.1-flash-tts-preview", "input": prompt,
                  "response_format": {"type": "audio"},
                  "generation_config": {"speech_config": [{"voice": voice}]}},
            timeout=httpx.Timeout(240.0, connect=20.0),
        )
    except httpx.TimeoutException as exc:
        raise GeminiError("timeout", "Gemini ใช้เวลาสร้างเสียงนานเกินไป ลองใหม่ภายหลัง") from exc
    except httpx.RequestError as exc:
        raise GeminiError("network_error", "เชื่อมต่อ Gemini เพื่อสร้างเสียงไม่สำเร็จ") from exc
    if response.status_code == 429:
        raise GeminiError("quota_exceeded", "ถึงขีดจำกัดการสร้างเสียงของ Gemini แล้ว รอให้โควตารีเซ็ตก่อนลองใหม่", response.headers.get("Retry-After"))
    if response.status_code in {401, 403}:
        raise GeminiError("invalid_api_key", "Gemini ปฏิเสธ API key ตรวจคีย์หรือสิทธิ์ใน Google AI Studio")
    if response.status_code >= 400:
        try:
            provider_message = str(response.json().get("error", {}).get("message", ""))[:240]
        except (ValueError, TypeError, AttributeError):
            provider_message = ""
        logger.warning("Gemini TTS request rejected (status=%s): %s", response.status_code, provider_message)
        detail = f" ({provider_message})" if provider_message else ""
        raise GeminiError("request_rejected", f"Gemini ปฏิเสธคำขอสร้างเสียง{detail}")
    try:
        payload = response.json()
        audio = payload.get("output_audio")
        # The SDK exposes output_audio as a convenience property. The REST
        # resource may instead return audio blocks in steps[].content[].
        if not isinstance(audio, dict) or not audio.get("data"):
            audio = next(
                block
                for step in payload.get("steps", [])
                for block in step.get("content", [])
                if block.get("type") == "audio" and block.get("data")
            )
        encoded = audio["data"]
        if isinstance(encoded, str) and encoded.startswith("data:") and "," in encoded:
            encoded = encoded.split(",", 1)[1]
        raw = base64.b64decode(encoded)
        if not raw:
            raise ValueError("empty audio")
        mime_type = str(audio.get("mime_type") or "audio/l16").lower().split(";", 1)[0].strip()
        if mime_type == "audio/wav" or raw[:4] == b"RIFF":
            # Validate that the provider returned a readable WAV before saving.
            with wave.open(io.BytesIO(raw), "rb") as wav:
                if wav.getnframes() <= 0:
                    raise ValueError("empty WAV")
            return raw
        if mime_type in {"audio/l16", "audio/pcm", "audio/raw", "audio/x-pcm"}:
            output = io.BytesIO()
            with wave.open(output, "wb") as wav:
                wav.setnchannels(int(audio.get("channels") or 1))
                wav.setsampwidth(2)
                wav.setframerate(int(audio.get("sample_rate") or 24000))
                wav.writeframes(raw)
            return output.getvalue()
        raise ValueError(f"unsupported audio format: {mime_type}")
    except (ValueError, KeyError, StopIteration, TypeError, wave.Error) as exc:
        steps = payload.get("steps", []) if "payload" in locals() and isinstance(payload, dict) else []
        logger.warning(
            "Gemini TTS response did not contain decodable audio (keys=%s, status=%s, steps=%s)",
            sorted(payload.keys()) if "payload" in locals() and isinstance(payload, dict) else [],
            payload.get("status") if "payload" in locals() and isinstance(payload, dict) else None,
            [
                [
                    {"type": item.get("type"), "keys": sorted(item.keys()), "mime_type": item.get("mime_type"), "data_length": len(item.get("data", "")) if isinstance(item.get("data"), str) else None}
                    for item in step.get("content", []) if isinstance(item, dict)
                ]
                for step in steps if isinstance(step, dict)
            ],
        )
        response_keys = ", ".join(sorted(payload.keys())) if "payload" in locals() and isinstance(payload, dict) else "JSON"
        status = payload.get("status") if "payload" in locals() and isinstance(payload, dict) else "อ่านไม่ได้"
        logger.warning("Gemini TTS audio parse failure: cause=%s, status=%s, keys=%s", type(exc).__name__, status, response_keys)
        raise GeminiError(
            "invalid_response",
            f"Gemini ส่งเสียงกลับมาในรูปแบบที่อ่านไม่ได้ (สถานะ {status}; {str(exc)[:120] or type(exc).__name__})",
        ) from exc


def generate_json(api_key: str, model: str, prompt: str, schema: dict[str, Any], images: list[tuple[str, bytes]] | None = None, max_output_tokens: int = 4096, url_context: bool = False, retry_transient: bool = True) -> dict[str, Any]:
    parts: list[dict[str, Any]] = [{"text": prompt}]
    for mime_type, data in images or []:
        import base64
        parts.append({"inlineData": {"mimeType": mime_type, "data": base64.b64encode(data).decode("ascii")}})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    request_body = {
        "contents": [{"role": "user", "parts": parts}],
        **({"tools": [{"url_context": {}}]} if url_context else {}),
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "temperature": 0.2,
            "maxOutputTokens": max_output_tokens,
        },
    }
    response = None
    max_attempts = 4 if retry_transient else 1
    for attempt in range(max_attempts):
        try:
            response = httpx.post(
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=request_body,
                timeout=httpx.Timeout(120.0, connect=20.0),
            )
        except httpx.TimeoutException as exc:
            raise GeminiError("timeout", "Gemini ใช้เวลาตอบนานเกินไป ลองใหม่ภายหลัง") from exc
        except httpx.RequestError as exc:
            raise GeminiError("network_error", "เชื่อมต่อ Gemini ไม่สำเร็จ ตรวจอินเทอร์เน็ตแล้วลองใหม่") from exc
        if response.status_code not in {500, 502, 503, 504} or attempt == max_attempts - 1:
            break
        delay = min(2 ** attempt, 8) + random.uniform(0, 0.25)
        logger.warning(
            "Gemini generateContent returned transient HTTP %s; retrying (%s/%s, wait=%.2fs, model=%s, image_count=%s, image_bytes=%s)",
            response.status_code,
            attempt + 1,
            max_attempts - 1,
            delay,
            model,
            len(images or []),
            sum(len(data) for _, data in (images or [])),
        )
        time.sleep(delay)
    assert response is not None
    if response.status_code == 429:
        raise GeminiError("quota_exceeded", "ถึงขีดจำกัดการใช้งาน Gemini แล้ว รอให้โควตารีเซ็ตก่อนลองใหม่", response.headers.get("Retry-After"))
    if response.status_code in {401, 403}:
        raise GeminiError("invalid_api_key", "Gemini ปฏิเสธ API key ตรวจคีย์หรือสิทธิ์ใน Google AI Studio")
    if response.status_code >= 500:
        provider_status = ""
        provider_code = ""
        try:
            provider_error = response.json().get("error", {})
            provider_status = str(provider_error.get("status", ""))[:40]
            provider_code = str(provider_error.get("code", ""))[:12]
        except (ValueError, TypeError, AttributeError):
            pass
        logger.error(
            "Gemini generateContent failed (http_status=%s, provider_status=%s, provider_code=%s, model=%s, image_count=%s, image_bytes=%s)",
            response.status_code,
            provider_status or "unknown",
            provider_code or "unknown",
            model,
            len(images or []),
            sum(len(data) for _, data in (images or [])),
        )
        status_detail = f" {provider_status}" if provider_status else ""
        retry_detail = " แม้ลองซ้ำแล้ว" if max_attempts > 1 else ""
        raise GeminiError("provider_error", f"Google Gemini ตอบข้อผิดพลาด {response.status_code}{status_detail}{retry_detail}")
    if response.status_code >= 400:
        provider_code = ""
        provider_message = ""
        try:
            provider_error = response.json().get("error", {})
            provider_code = str(provider_error.get("status", ""))[:40]
            provider_message = " ".join(str(provider_error.get("message", "")).split())[:240]
        except (ValueError, TypeError, AttributeError):
            pass
        if api_key:
            provider_message = provider_message.replace(api_key, "[ปกปิด API key]")
        logger.warning(
            "Gemini generateContent request rejected (http_status=%s, provider_status=%s, model=%s): %s",
            response.status_code,
            provider_code or "unknown",
            model,
            provider_message or "no provider message",
        )
        detail = f" · {provider_message}" if provider_message else ""
        status = f" {provider_code}" if provider_code else ""
        raise GeminiError("request_rejected", f"Gemini ปฏิเสธคำขอ ({response.status_code}{status}){detail}")
    try:
        payload = response.json()
        candidate = payload["candidates"][0]
        text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
        result = json.loads(text)
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise GeminiError("invalid_response", "คำตอบจาก Gemini ไม่อยู่ในรูปแบบที่โปรแกรมอ่านได้") from exc
    if not isinstance(result, dict):
        raise GeminiError("invalid_response", "คำตอบจาก Gemini ไม่ใช่ข้อมูล JSON ที่ถูกต้อง")
    if url_context:
        result["_url_context_metadata"] = candidate.get("url_context_metadata") or payload.get("url_context_metadata") or {}
    return result


def url_context_retrieved(result: dict[str, Any]) -> bool:
    """True only when Gemini confirms that it retrieved at least one supplied URL."""
    metadata = result.get("_url_context_metadata")
    if not isinstance(metadata, dict):
        return False
    entries = metadata.get("url_metadata") or metadata.get("urlMetadata") or []
    if not isinstance(entries, list):
        return False
    return any(
        isinstance(item, dict)
        and "SUCCESS" in str(item.get("url_retrieval_status") or item.get("urlRetrievalStatus") or "").upper()
        for item in entries
    )
