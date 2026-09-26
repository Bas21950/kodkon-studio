from __future__ import annotations

import subprocess
import time
import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.main import app

ORIGIN = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def make_test_video(path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ต้องใช้ FFmpeg เพื่อสร้างคลิปทดสอบ")
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1:r=24",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"สร้างคลิปทดสอบด้วย FFmpeg ไม่ได้: {result.stderr[-300:]}")


def test_health_and_capabilities(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert payload["database"] == "พร้อมใช้งาน"
    assert client.get("/api/capabilities").status_code == 200


def test_update_check_returns_release_notes(client: TestClient, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_latest_update",
        lambda version: {
            "current_version": version,
            "latest_version": "0.3.0",
            "update_available": True,
            "release_url": "https://github.com/Bas21950/kodkon-studio/releases/tag/v0.3.0",
            "published_at": "2026-09-26T00:00:00Z",
            "notes": "- เพิ่มฟังก์ชันใหม่",
            "installable": True,
            "package_url": "https://github.com/Bas21950/kodkon-studio/releases/download/v0.3.0/package.zip",
            "checksum_url": "https://github.com/Bas21950/kodkon-studio/releases/download/v0.3.0/package.zip.sha256",
        },
    )

    response = client.get("/api/updates")

    assert response.status_code == 200
    assert response.json()["update_available"] is True
    assert "เพิ่มฟังก์ชันใหม่" in response.json()["notes"]


def test_update_install_requires_install_root(client: TestClient, monkeypatch):
    monkeypatch.delenv("KODKON_INSTALL_ROOT", raising=False)

    response = client.post("/api/updates/install", headers=ORIGIN, json={})

    assert response.status_code == 409


def test_project_validation_and_listing(client: TestClient):
    rejected = client.post("/api/projects", headers=ORIGIN, json={"title": "งานตัวอย่าง", "affiliate_url": "shopee"})
    assert rejected.status_code == 422

    created = client.post(
        "/api/projects",
        headers=ORIGIN,
        json={"title": "  รีวิวแก้วเก็บเย็น  ", "product_name": "แก้วเก็บความเย็น", "affiliate_url": "https://shopee.co.th/example"},
    )
    assert created.status_code == 201
    project = created.json()
    assert project["title"] == "รีวิวแก้วเก็บเย็น"
    assert project["assets"] == []

    update = client.patch(
        f"/api/projects/{project['id']}",
        headers=ORIGIN,
        json={"product_name": "แก้วเก็บเย็นรุ่นใหม่"},
    )
    assert update.status_code == 200
    assert update.json()["product_name"] == "แก้วเก็บเย็นรุ่นใหม่"
    assert len(client.get("/api/projects?q=รุ่นใหม่").json()) == 1


def test_upload_probe_persists_asset_and_job(client: TestClient, tmp_path: Path):
    project = client.post("/api/projects", headers=ORIGIN, json={"title": "คลิปทดสอบ"}).json()
    video_path = tmp_path / "ทดสอบวิดีโอ.mp4"
    make_test_video(video_path)

    with video_path.open("rb") as video:
        uploaded = client.post(
            f"/api/projects/{project['id']}/assets",
            headers=ORIGIN,
            files={"file": (video_path.name, video, "video/mp4")},
        )
    assert uploaded.status_code == 202
    initial = uploaded.json()
    assert initial["asset"]["state"] == "processing"
    assert initial["job"]["state"] == "queued"

    deadline = time.monotonic() + 10
    refreshed = None
    while time.monotonic() < deadline:
        refreshed = client.get(f"/api/projects/{project['id']}").json()
        if refreshed["assets"][0]["state"] in {"ready", "failed"}:
            break
        time.sleep(0.1)

    asset = refreshed["assets"][0]
    assert asset["state"] == "ready", asset
    assert asset["duration_ms"] is not None and asset["duration_ms"] > 0
    assert asset["width"] == 320
    assert asset["height"] == 240
    assert asset["has_audio"] is True
    assert refreshed["jobs"][0]["state"] == "succeeded"

    media_response = client.get(f"/api/assets/{asset['id']}/file")
    assert media_response.status_code == 200
    assert len(media_response.content) == asset["byte_size"]


def test_unsafe_asset_suffix_is_rejected(client: TestClient):
    project = client.post("/api/projects", headers=ORIGIN, json={"title": "ชนิดไฟล์ไม่รองรับ"}).json()
    response = client.post(
        f"/api/projects/{project['id']}/assets",
        headers=ORIGIN,
        files={"file": ("script.exe", b"not a video", "application/octet-stream")},
    )
    assert response.status_code == 415


def test_write_requests_require_local_ui_origin(client: TestClient):
    response = client.post("/api/projects", json={"title": "blocked"})
    assert response.status_code == 403


def test_backup_download_contains_database_and_excludes_secrets(client: TestClient):
    response = client.get("/api/maintenance/backup", headers=ORIGIN)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        assert "database/kodkon-studio.sqlite3" in names
        assert manifest["format"] == "kodkon-studio-backup"
        assert manifest["secrets_included"] is False
        assert not any("secret" in name.lower() or name.endswith(".dpapi") for name in names)


def test_backup_download_rejects_cross_site_request(client: TestClient):
    response = client.get("/api/maintenance/backup", headers={"Origin": "https://example.com", "Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403
