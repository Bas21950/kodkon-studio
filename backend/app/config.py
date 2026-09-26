from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def default_data_dir() -> Path:
    root = os.environ.get("KODKON_DATA_DIR")
    if root:
        return Path(root).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "KodKonStudio"
    return Path.home() / "AppData" / "Local" / "KodKonStudio"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = default_data_dir()
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024
    ffprobe_path: str | None = os.environ.get("FFPROBE_PATH")
    app_version: str = "0.3.0"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "kodkon-studio.sqlite3"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def resolved_ffprobe(self) -> str | None:
        return self.ffprobe_path or os.environ.get("FFPROBE_PATH")


settings = Settings()


def ensure_data_directories() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
