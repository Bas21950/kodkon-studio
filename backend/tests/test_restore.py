from __future__ import annotations

import importlib.util
import json
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path


RESTORE_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "restore_data.py"
SPEC = importlib.util.spec_from_file_location("kodkon_restore_data", RESTORE_SCRIPT)
assert SPEC and SPEC.loader
restore = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restore)


def make_database(path: Path, title: str, revision: str = "0005_facebook_pages") -> None:
    db = sqlite3.connect(path)
    try:
        db.executescript(
            "CREATE TABLE alembic_version (version_num TEXT);"
            "CREATE TABLE projects (id TEXT PRIMARY KEY, title TEXT);"
            "CREATE TABLE assets (id TEXT PRIMARY KEY);"
        )
        db.execute("INSERT INTO alembic_version VALUES (?)", (revision,))
        db.execute("INSERT INTO projects VALUES ('project-1', ?)", (title,))
        db.commit()
    finally:
        db.close()


def test_restore_validates_and_replaces_only_database_and_media(tmp_path: Path):
    data_dir = tmp_path / "app-data"
    (data_dir / "media" / "projects").mkdir(parents=True)
    (data_dir / "media" / "projects" / "old.mp4").write_bytes(b"old video")
    (data_dir / "secrets").mkdir()
    (data_dir / "secrets" / "token.dpapi").write_bytes(b"keep this")
    make_database(data_dir / "kodkon-studio.sqlite3", "old project")

    backup_db = tmp_path / "backup.sqlite3"
    make_database(backup_db, "restored project")
    archive_path = tmp_path / "backup.zip"
    manifest = {
        "format": restore.FORMAT,
        "version": restore.FORMAT_VERSION,
        "database": restore.DATABASE_MEMBER,
        "secrets_included": False,
    }
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.write(backup_db, restore.DATABASE_MEMBER)
        archive.writestr("media/projects/new.mp4", b"new video")

    stage = tmp_path / "stage"
    stage.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        restore.validate_archive(archive)
        restore.extract_validated(archive, stage)
    (stage / "media").mkdir(exist_ok=True)
    restore.validate_database(stage / restore.DATABASE_MEMBER)
    restore.install_restore(stage, data_dir)

    with closing(sqlite3.connect(data_dir / "kodkon-studio.sqlite3")) as db:
        assert db.execute("SELECT title FROM projects WHERE id='project-1'").fetchone()[0] == "restored project"
    assert (data_dir / "media" / "projects" / "new.mp4").read_bytes() == b"new video"
    assert not (data_dir / "media" / "projects" / "old.mp4").exists()
    assert (data_dir / "secrets" / "token.dpapi").read_bytes() == b"keep this"


def test_restore_rejects_path_traversal(tmp_path: Path):
    archive_path = tmp_path / "unsafe.zip"
    manifest = {
        "format": restore.FORMAT,
        "version": restore.FORMAT_VERSION,
        "database": restore.DATABASE_MEMBER,
        "secrets_included": False,
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("database/kodkon-studio.sqlite3", b"db")
        archive.writestr("media/../../outside.txt", b"unsafe")
    with zipfile.ZipFile(archive_path) as archive:
        try:
            restore.validate_archive(archive)
        except ValueError as exc:
            assert "เส้นทาง" in str(exc)
        else:
            raise AssertionError("path traversal entry should be rejected")


def test_restore_rejects_unknown_database_revision(tmp_path: Path):
    database = tmp_path / "future.sqlite3"
    make_database(database, "future project", "0006_future_schema")
    try:
        restore.validate_database(database)
    except ValueError as exc:
        assert "เวอร์ชันใหม่กว่า" in str(exc)
    else:
        raise AssertionError("unknown migration revision should be rejected")
