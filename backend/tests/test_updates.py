from __future__ import annotations

import hashlib
import json
from urllib.error import HTTPError

import pytest

from app.services import updates


class FakeResponse:
    def __init__(self, body: bytes, url: str = "https://objects.githubusercontent.com/release.zip"):
        self.body = body
        self.url = url
        self.headers = {"Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            body, self.body = self.body, b""
            return body
        body, self.body = self.body[:size], self.body[size:]
        return body

    def geturl(self) -> str:
        return self.url


def _release(version: str = "0.3.0", repository: str = "owner/repo") -> dict:
    package = f"kodkon-studio-{version}-windows-portable.zip"
    base = f"https://github.com/{repository}/releases/download/v{version}"
    return {
        "tag_name": f"v{version}",
        "html_url": f"https://github.com/{repository}/releases/tag/v{version}",
        "published_at": "2026-09-26T00:00:00Z",
        "body": "## เปลี่ยนแปลง\n- เพิ่มระบบอัปเดต",
        "assets": [
            {"name": package, "browser_download_url": f"{base}/{package}"},
            {"name": f"{package}.sha256", "browser_download_url": f"{base}/{package}.sha256"},
        ],
    }


def test_latest_release_exposes_version_notes_and_install_assets(monkeypatch):
    payload = json.dumps(_release()).encode()
    monkeypatch.setattr(updates, "_request", lambda *_args, **_kwargs: FakeResponse(payload, "https://api.github.com/repos/owner/repo/releases/latest"))

    result = updates.get_latest_update("0.2.0", "owner/repo")

    assert result["latest_version"] == "0.3.0"
    assert result["update_available"] is True
    assert result["installable"] is True
    assert "เพิ่มระบบอัปเดต" in result["notes"]
    assert result["package_url"].endswith(".zip")


def test_latest_release_is_not_an_update_when_versions_match(monkeypatch):
    payload = json.dumps(_release("0.2.0")).encode()
    monkeypatch.setattr(updates, "_request", lambda *_args, **_kwargs: FakeResponse(payload))

    result = updates.get_latest_update("0.2.0", "owner/repo")

    assert result["update_available"] is False
    assert result["installable"] is False


def test_no_release_is_a_normal_empty_update_state(monkeypatch):
    def not_found(*_args, **_kwargs):
        raise HTTPError("https://api.github.com/repos/owner/repo/releases/latest", 404, "Not Found", {}, None)

    monkeypatch.setattr(updates, "_request", not_found)

    result = updates.get_latest_update("0.2.0", "owner/repo")

    assert result["latest_version"] is None
    assert result["update_available"] is False
    assert result["installable"] is False


def test_release_assets_must_belong_to_the_configured_public_repository(monkeypatch):
    release = _release()
    release["assets"][0]["browser_download_url"] = "https://example.com/evil.zip"
    payload = json.dumps(release).encode()
    monkeypatch.setattr(updates, "_request", lambda *_args, **_kwargs: FakeResponse(payload))

    with pytest.raises(updates.UpdateError, match="ไม่ตรงกับ GitHub repository"):
        updates.get_latest_update("0.2.0", "owner/repo")


def test_downloaded_update_must_match_published_sha256(monkeypatch):
    archive = b"fake zip bytes"
    digest = hashlib.sha256(archive).hexdigest()
    update = {
        "update_available": True,
        "installable": True,
        "package_url": "https://github.com/owner/repo/releases/download/v0.3.0/app.zip",
        "checksum_url": "https://github.com/owner/repo/releases/download/v0.3.0/app.zip.sha256",
    }
    monkeypatch.setattr(
        updates,
        "_request",
        lambda url, **_kwargs: FakeResponse(f"{digest}  app.zip".encode()) if url.endswith(".sha256") else FakeResponse(archive),
    )

    progress = []
    path = updates.download_verified_update(update, lambda received, total: progress.append((received, total)))
    try:
        assert path.read_bytes() == archive
        assert progress[-1] == (len(archive), len(archive))
    finally:
        path.unlink(missing_ok=True)


def test_update_progress_survives_process_restart_and_finishes_on_new_version(tmp_path):
    update_id = "a" * 32
    status_path = tmp_path / f"kodkon-update-status-{update_id}.json"
    updates.set_update_progress(update_id, "0.4.6", "restarting", 94, "กำลังเปิดโปรแกรมใหม่", status_path)

    pending = updates.get_update_progress(update_id, "0.4.5", status_path)
    complete = updates.get_update_progress(update_id, "0.4.6", status_path)

    assert pending is not None and pending["status"] == "restarting"
    assert complete is not None and complete["status"] == "completed"
    assert complete["progress"] == 100


def test_bad_sha256_aborts_and_removes_the_temporary_package(monkeypatch):
    update = {
        "update_available": True,
        "installable": True,
        "package_url": "https://github.com/owner/repo/releases/download/v0.3.0/app.zip",
        "checksum_url": "https://github.com/owner/repo/releases/download/v0.3.0/app.zip.sha256",
    }
    monkeypatch.setattr(
        updates,
        "_request",
        lambda url, **_kwargs: FakeResponse(("0" * 64 + "  app.zip").encode()) if url.endswith(".sha256") else FakeResponse(b"tampered"),
    )

    with pytest.raises(updates.UpdateError, match="SHA-256 ไม่ผ่าน"):
        updates.download_verified_update(update)
