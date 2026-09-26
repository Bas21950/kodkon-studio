from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import sqlite3
import stat
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path, PurePosixPath


FORMAT = "kodkon-studio-backup"
FORMAT_VERSION = 1
DATABASE_MEMBER = "database/kodkon-studio.sqlite3"
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "backend" / "alembic" / "versions"


def default_data_dir() -> Path:
    configured = os.environ.get("KODKON_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "KodKonStudio"
    return Path.home() / "AppData" / "Local" / "KodKonStudio"


def ensure_app_stopped() -> None:
    try:
        with socket.create_connection(("127.0.0.1", 8765), timeout=0.3):
            raise RuntimeError("ปิด กดก่อนคิดทีหลัง Studio ก่อนกู้คืนข้อมูล แล้วลองอีกครั้ง")
    except OSError:
        return


def validate_archive(archive: zipfile.ZipFile) -> dict:
    names: set[str] = set()
    manifest = None
    has_database = False
    for item in archive.infolist():
        name = item.filename
        if name in names:
            raise ValueError("ไฟล์สำรองมีชื่อไฟล์ซ้ำ")
        names.add(name)
        if "\\" in name:
            raise ValueError("ไฟล์สำรองมีเส้นทางที่ไม่ถูกต้อง")
        path = PurePosixPath(name)
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} or ":" in part for part in path.parts):
            raise ValueError("ไฟล์สำรองมีเส้นทางที่ไม่ปลอดภัย")
        if stat.S_ISLNK(item.external_attr >> 16):
            raise ValueError("ไฟล์สำรองมี symbolic link ที่ไม่รองรับ")
        if item.is_dir():
            continue
        if name == "manifest.json":
            try:
                manifest = json.loads(archive.read(item))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("อ่านข้อมูลกำกับไฟล์สำรองไม่สำเร็จ") from exc
        elif name == DATABASE_MEMBER:
            has_database = True
        elif not name.startswith("media/"):
            raise ValueError("ไฟล์สำรองมีรายการนอกฐานข้อมูลและสื่อ")
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise ValueError("ไฟล์นี้ไม่ใช่ไฟล์สำรองของ Studio")
    if manifest.get("version") != FORMAT_VERSION or manifest.get("secrets_included") is not False:
        raise ValueError("เวอร์ชันไฟล์สำรองไม่รองรับ")
    if manifest.get("database") != DATABASE_MEMBER or not has_database:
        raise ValueError("ไฟล์สำรองไม่มีฐานข้อมูลที่ต้องใช้")
    return manifest


def extract_validated(archive: zipfile.ZipFile, target: Path) -> None:
    root = target.resolve()
    for item in archive.infolist():
        if item.is_dir() or item.filename == "manifest.json":
            continue
        member_path = PurePosixPath(item.filename)
        output = root.joinpath(*member_path.parts)
        if not output.resolve().is_relative_to(root):
            raise ValueError("พบไฟล์ที่อยู่นอกโฟลเดอร์กู้คืน")
        output.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(item, "r") as source, output.open("xb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)


def validate_database(path: Path) -> None:
    try:
        with closing(sqlite3.connect(path)) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            versions = {row[0] for row in db.execute("SELECT version_num FROM alembic_version")} if "alembic_version" in tables else set()
    except sqlite3.DatabaseError as exc:
        raise ValueError("ฐานข้อมูลในไฟล์สำรองเสียหายหรือเปิดไม่ได้") from exc
    required = {"alembic_version", "projects", "assets"}
    if not result or result[0] != "ok" or not required.issubset(tables):
        raise ValueError("ฐานข้อมูลในไฟล์สำรองตรวจสอบไม่ผ่าน")
    known_revisions = set()
    for migration in MIGRATIONS_DIR.glob("*.py"):
        source = migration.read_text(encoding="utf-8")
        match = re.search(r"(?m)^revision\s*=\s*['\"]([^'\"]+)['\"]", source)
        if match:
            known_revisions.add(match.group(1))
    if not versions or not versions.issubset(known_revisions):
        raise ValueError("ฐานข้อมูลสำรองมาจากเวอร์ชันใหม่กว่าหรือไม่รองรับโดยโปรแกรมนี้")


def create_rollback_backup(data_dir: Path) -> Path | None:
    database = data_dir / "kodkon-studio.sqlite3"
    media = data_dir / "media"
    if not database.is_file():
        return None
    backup_dir = data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-UTC")
    backup_path = backup_dir / f"pre-restore-{timestamp}.zip"
    with tempfile.TemporaryDirectory(prefix="kodkon-rollback-") as temp_dir:
        snapshot = Path(temp_dir) / "database.sqlite3"
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(snapshot)) as destination:
            source.backup(destination)
        manifest = {
            "format": FORMAT,
            "version": FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": DATABASE_MEMBER,
            "secrets_included": False,
        }
        with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            archive.write(snapshot, DATABASE_MEMBER)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            if media.is_dir() and not media.is_symlink():
                for item in media.rglob("*"):
                    if item.is_symlink() or not item.is_file():
                        continue
                    relative = item.relative_to(media)
                    if ".staging" in relative.parts or any(part.startswith(".render-") for part in relative.parts):
                        continue
                    archive.write(item, f"media/{relative.as_posix()}")
    return backup_path


def install_restore(stage: Path, data_dir: Path) -> None:
    staged_database = stage / DATABASE_MEMBER
    staged_media = stage / "media"
    data_dir.mkdir(parents=True, exist_ok=True)
    media_target = data_dir / "media"
    database_target = data_dir / "kodkon-studio.sqlite3"
    old_media = stage / "previous-media"
    old_database = stage / "previous-database.sqlite3"
    old_sidecars: list[tuple[Path, Path]] = []
    media_moved = False
    database_moved = False
    try:
        if media_target.exists():
            os.replace(media_target, old_media)
            media_moved = True
        os.replace(staged_media, media_target)
        if database_target.exists():
            os.replace(database_target, old_database)
            database_moved = True
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{database_target}{suffix}")
            if sidecar.exists():
                saved = Path(f"{old_database}{suffix}")
                os.replace(sidecar, saved)
                old_sidecars.append((sidecar, saved))
        os.replace(staged_database, database_target)
    except Exception:
        if database_target.exists() and database_moved:
            database_target.unlink(missing_ok=True)
        if database_moved:
            os.replace(old_database, database_target)
        for sidecar, saved in old_sidecars:
            if saved.exists():
                os.replace(saved, sidecar)
        if media_target.exists():
            shutil.rmtree(media_target)
        if media_moved:
            os.replace(old_media, media_target)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="กู้คืนข้อมูล กดก่อนคิดทีหลัง Studio จากไฟล์สำรอง")
    parser.add_argument("backup", type=Path, help="ไฟล์ .zip ที่ดาวน์โหลดจากหน้าตั้งค่า Studio")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir(), help="โฟลเดอร์ข้อมูลของ Studio")
    parser.add_argument("--yes", action="store_true", help="ยืนยันการแทนที่ข้อมูลโดยไม่ถามซ้ำ")
    args = parser.parse_args()
    archive_path = args.backup.expanduser().resolve()
    data_dir = args.data_dir.expanduser().resolve()
    if not archive_path.is_file():
        print("ไม่พบไฟล์สำรอง", file=sys.stderr)
        return 2

    try:
        ensure_app_stopped()
        with zipfile.ZipFile(archive_path, "r") as archive:
            manifest = validate_archive(archive)
            with tempfile.TemporaryDirectory(prefix="kodkon-restore-") as temp_dir:
                stage = Path(temp_dir)
                extract_validated(archive, stage)
                (stage / "media").mkdir(parents=True, exist_ok=True)
                validate_database(stage / DATABASE_MEMBER)
                print(f"ไฟล์สำรองผ่านการตรวจสอบ · สร้างเมื่อ {manifest.get('created_at', 'ไม่ทราบเวลา')}")
                if not args.yes:
                    print("การกู้คืนจะแทนที่โปรเจกต์และไฟล์วิดีโอปัจจุบัน โดยไม่รวม API keys และ Page tokens")
                    if input("พิมพ์ RESTORE เพื่อยืนยัน: ").strip() != "RESTORE":
                        print("ยกเลิกแล้ว ไม่มีการเปลี่ยนแปลงข้อมูล")
                        return 1
                rollback = create_rollback_backup(data_dir)
                install_restore(stage, data_dir)
        if rollback:
            print(f"เก็บข้อมูลเดิมไว้ที่: {rollback}")
        print("กู้คืนเสร็จแล้ว เปิดโปรแกรมใหม่ได้ คีย์ AI และ Facebook อาจต้องบันทึกใหม่")
        return 0
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"กู้คืนไม่สำเร็จ: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
