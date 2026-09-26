from __future__ import annotations

from pathlib import Path

from app.config import settings


class UnsafeStoragePath(ValueError):
    pass


def resolve_media_path(relative_path: str) -> Path:
    root = settings.media_dir.resolve()
    relative = Path(relative_path)
    if relative.is_absolute() or any(part in {"..", "."} for part in relative.parts):
        raise UnsafeStoragePath("ไฟล์ที่ร้องขออยู่นอกโฟลเดอร์ข้อมูลของโปรแกรม")
    candidate = (root / relative).resolve()
    # Windows packaged apps can redirect LocalAppData child folders into the
    # package's LocalCache. Resolve the storage root through an existing child
    # so both sides of the containment check use the same physical path.
    physical_root = root
    try:
        for child in root.iterdir():
            if child.is_dir():
                resolved_child = child.resolve()
                if resolved_child.parent != root:
                    physical_root = resolved_child.parent
                    break
    except OSError:
        pass
    if candidate == physical_root or not candidate.is_relative_to(physical_root):
        raise UnsafeStoragePath("ไฟล์ที่ร้องขออยู่นอกโฟลเดอร์ข้อมูลของโปรแกรม")
    return candidate
