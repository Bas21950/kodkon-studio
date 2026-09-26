from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.services import ai_cache, ai_settings
from app.services.gemini import GeminiError


def test_legacy_25_selection_uses_current_default(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_settings, "settings", SimpleNamespace(data_dir=tmp_path))
    (tmp_path / "ai-settings.json").write_text(
        '{"model":"gemini-2.5-flash-lite"}', encoding="utf-8"
    )

    assert ai_settings.get_model() == "gemini-3.5-flash-lite"


def test_31_server_error_falls_back_to_35(monkeypatch):
    session = SimpleNamespace(records=[])
    session.get = lambda *_args: None
    session.add = lambda record: session.records.append(record)

    class SessionFactory:
        def __call__(self):
            return nullcontext(session)

        def begin(self):
            return nullcontext(session)

    monkeypatch.setattr(ai_cache, "SessionLocal", SessionFactory())
    monkeypatch.setattr(ai_cache, "get_model", lambda: "gemini-3.1-flash-lite")
    monkeypatch.setattr(ai_cache, "load_gemini_key", lambda: "test-key")
    seen_models = []

    def generate(_api_key, model, *_args, **_kwargs):
        seen_models.append(model)
        if model == "gemini-3.1-flash-lite":
            raise GeminiError("provider_error", "503 UNAVAILABLE")
        return {"ok": True}

    monkeypatch.setattr(ai_cache, "generate_json", generate)

    result, model = ai_cache.get_gemini_json("test", "prompt", {})

    assert result == {"ok": True}
    assert seen_models == ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
    assert model == "gemini-3.5-flash-lite"
    assert session.records[0].model == "gemini-3.5-flash-lite"


def test_quota_error_does_not_try_another_model(monkeypatch):
    session = SimpleNamespace(records=[])
    session.get = lambda *_args: None
    session.add = lambda record: session.records.append(record)

    class SessionFactory:
        def __call__(self):
            return nullcontext(session)

        def begin(self):
            return nullcontext(session)

    monkeypatch.setattr(ai_cache, "SessionLocal", SessionFactory())
    monkeypatch.setattr(ai_cache, "get_model", lambda: "gemini-3.1-flash-lite")
    monkeypatch.setattr(ai_cache, "load_gemini_key", lambda: "test-key")
    seen_models = []

    def generate(_api_key, model, *_args, **_kwargs):
        seen_models.append(model)
        raise GeminiError("quota_exceeded", "429 quota exceeded")

    monkeypatch.setattr(ai_cache, "generate_json", generate)

    with pytest.raises(GeminiError, match="quota exceeded") as error:
        ai_cache.get_gemini_json("quota-test", "prompt", {})

    assert error.value.code == "quota_exceeded"
    assert seen_models == ["gemini-3.1-flash-lite"]
