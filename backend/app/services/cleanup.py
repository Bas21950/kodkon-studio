from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from app.config import settings


logger = logging.getLogger("kodkon.cleanup")
STALE_AFTER_SECONDS = 24 * 60 * 60


def cleanup_stale_work_files() -> int:
    """Remove only known temporary files left behind by interrupted local jobs."""
    cutoff = time.time() - STALE_AFTER_SECONDS
    candidates: list[Path] = []

    staging_dir = settings.media_dir / ".staging"
    if staging_dir.is_dir() and not staging_dir.is_symlink():
        candidates.extend(path for path in staging_dir.glob("*.upload") if path.is_file())

    work_dir = settings.data_dir / "work"
    if work_dir.is_dir() and not work_dir.is_symlink():
        candidates.extend(path for path in work_dir.glob("ocr-*") if path.is_dir())

    projects_dir = settings.media_dir / "projects"
    if projects_dir.is_dir() and not projects_dir.is_symlink():
        for project_dir in projects_dir.iterdir():
            if project_dir.is_symlink() or not project_dir.is_dir():
                continue
            candidates.extend(path for path in project_dir.glob(".render-*") if path.is_dir())

    removed = 0
    for path in candidates:
        try:
            if path.is_symlink() or path.stat().st_mtime >= cutoff:
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed += 1
        except OSError:
            logger.warning("Could not remove stale temporary item: %s", path, exc_info=True)

    if removed:
        logger.info("Removed %s stale temporary item(s) from interrupted jobs", removed)
    return removed
