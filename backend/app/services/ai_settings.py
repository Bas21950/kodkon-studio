from __future__ import annotations

import json
import os

from app.config import settings

DEFAULT_MODEL = "gemini-3.5-flash-lite"
ALLOWED_MODELS = {
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
}


def get_model() -> str:
    path = settings.data_dir / "ai-settings.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        model = value.get("model")
        if model in ALLOWED_MODELS:
            return model
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return DEFAULT_MODEL


def set_model(model: str) -> None:
    if model not in ALLOWED_MODELS:
        raise ValueError("รุ่นโมเดลนี้ไม่อยู่ในรายการฟรีที่โปรแกรมรองรับ")
    path = settings.data_dir / "ai-settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"model": model}, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)
