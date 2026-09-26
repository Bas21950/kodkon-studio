from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings


BACKUP_FORMAT = "kodkon-studio-backup"
BACKUP_VERSION = 1


def create_backup_archive() -> tuple[Path, str]:
    """Create a portable data backup without DPAPI secrets or transient work files."""
    created_at = datetime.now(timezone.utc)
    filename = f"kodkon-studio-backup-{created_at:%Y%m%d-%H%M%S-UTC}.zip"
    descriptor, archive_name = tempfile.mkstemp(prefix="kodkon-studio-backup-", suffix=".zip")
    os.close(descriptor)
    archive_path = Path(archive_name)

    try:
        with tempfile.TemporaryDirectory(prefix="kodkon-studio-db-snapshot-") as snapshot_dir:
            snapshot_path = Path(snapshot_dir) / "database.sqlite3"
            with closing(sqlite3.connect(settings.database_path)) as source, closing(sqlite3.connect(snapshot_path)) as snapshot:
                source.backup(snapshot)
            with closing(sqlite3.connect(snapshot_path)) as snapshot:
                result = snapshot.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise RuntimeError("ตรวจสอบฐานข้อมูลระหว่างสำรองไม่ผ่าน")

            media_files: list[tuple[Path, str, int]] = []
            media_bytes = 0
            media_root = settings.media_dir.resolve()
            for item in media_root.rglob("*"):
                if item.is_symlink() or not item.is_file():
                    continue
                relative = item.relative_to(media_root)
                if ".staging" in relative.parts or any(part.startswith(".render-") for part in relative.parts):
                    continue
                resolved = item.resolve()
                if not resolved.is_relative_to(media_root):
                    continue
                size = resolved.stat().st_size
                media_files.append((resolved, relative.as_posix(), size))
                media_bytes += size

            manifest = {
                "format": BACKUP_FORMAT,
                "version": BACKUP_VERSION,
                "created_at": created_at.isoformat(),
                "app_version": settings.app_version,
                "database": "database/kodkon-studio.sqlite3",
                "media_files": len(media_files),
                "media_bytes": media_bytes,
                "secrets_included": False,
            }
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                archive.write(snapshot_path, manifest["database"])
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                for path, relative, _size in media_files:
                    archive.write(path, f"media/{relative}")
        return archive_path, filename
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise


def remove_backup_archive(path: Path) -> None:
    path.unlink(missing_ok=True)
