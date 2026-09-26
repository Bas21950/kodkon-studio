from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.database import SessionLocal
from app.models import AICache
from app.services.ai_settings import get_model
from app.services.gemini import GeminiError, generate_json
from app.services.secret_store import load_gemini_key


def get_gemini_json(task: str, prompt: str, schema: dict[str, Any], images: list[tuple[str, bytes]] | None = None, max_output_tokens: int = 4096, url_context: bool = False) -> tuple[dict[str, Any], str]:
    model = get_model()
    content_fingerprint = {
        "task": task,
        "model": model,
        "prompt": prompt,
        "schema": schema,
        "images": [hashlib.sha256(image).hexdigest() for _, image in (images or [])],
        "url_context": url_context,
    }
    cache_key = hashlib.sha256(json.dumps(content_fingerprint, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    with SessionLocal() as session:
        cached = session.get(AICache, cache_key)
        if cached:
            return json.loads(cached.response_json), cached.model

    api_key = load_gemini_key()
    if not api_key:
        raise GeminiError("missing_api_key", "ยังไม่ได้บันทึก Gemini API key ในหน้าตั้งค่า")
    actual_model = model
    try:
        result = generate_json(
            api_key,
            model,
            prompt,
            schema,
            images,
            max_output_tokens,
            url_context,
        )
    except GeminiError as primary_error:
        fallback_model = "gemini-3.5-flash-lite"
        if primary_error.code != "provider_error" or model != "gemini-3.1-flash-lite":
            raise
        try:
            result = generate_json(
                api_key,
                fallback_model,
                prompt,
                schema,
                images,
                max_output_tokens,
                url_context,
            )
            actual_model = fallback_model
        except GeminiError as fallback_error:
            raise GeminiError(
                "provider_error",
                f"รุ่น {model} ใช้งานไม่ได้ ({primary_error.user_message}) และรุ่นสำรอง {fallback_model} ใช้ไม่ได้ ({fallback_error.user_message})",
            ) from fallback_error
    record = AICache(
        cache_key=cache_key,
        task=task,
        model=actual_model,
        response_json=json.dumps(result, ensure_ascii=False),
        created_at=datetime.now(timezone.utc),
    )
    with SessionLocal.begin() as session:
        if session.get(AICache, cache_key) is None:
            session.add(record)
    return result, actual_model
