from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


GITHUB_REPOSITORY = os.environ.get("KODKON_GITHUB_REPOSITORY", "Bas21950/kodkon-studio")
GITHUB_API_VERSION = "2026-03-10"
MAX_RELEASE_JSON_BYTES = 2 * 1024 * 1024
MAX_RELEASE_ASSET_BYTES = 512 * 1024 * 1024
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")
SHA256_PATTERN = re.compile(r"^([a-fA-F0-9]{64})\s+")


class UpdateError(RuntimeError):
    pass


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value.strip())
    if not match:
        raise UpdateError("รูปแบบเวอร์ชันบน GitHub ไม่ถูกต้อง")
    return tuple(int(part) for part in match.groups())


def _request(url: str, *, accept: str, timeout: int = 15):
    request = Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "KodKonStudio-Updater",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
    )
    return urlopen(request, timeout=timeout)


def _asset_url(asset: dict, repository: str) -> str:
    url = asset.get("browser_download_url")
    parts = urlsplit(url or "")
    expected_prefix = f"/{repository}/releases/download/"
    if parts.scheme != "https" or parts.hostname != "github.com" or not parts.path.startswith(expected_prefix):
        raise UpdateError("ลิงก์ไฟล์อัปเดตไม่ตรงกับ GitHub repository ที่ตั้งไว้")
    return url


def get_latest_update(current_version: str, repository: str | None = None) -> dict:
    repository = repository or GITHUB_REPOSITORY
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise UpdateError("ยังตั้งค่า GitHub repository ไม่ถูกต้อง")
    api_url = f"https://api.github.com/repos/{repository}/releases/latest"
    try:
        with _request(api_url, accept="application/vnd.github+json") as response:
            raw = response.read(MAX_RELEASE_JSON_BYTES + 1)
        if len(raw) > MAX_RELEASE_JSON_BYTES:
            raise UpdateError("ข้อมูล Release จาก GitHub มีขนาดใหญ่ผิดปกติ")
        release = json.loads(raw)
    except HTTPError as exc:
        if exc.code == 404:
            return {
                "current_version": current_version,
                "latest_version": None,
                "update_available": False,
                "release_url": f"https://github.com/{repository}/releases",
                "published_at": None,
                "notes": "ยังไม่มี Release สำหรับโปรแกรมนี้บน GitHub",
                "installable": False,
                "package_url": None,
                "checksum_url": None,
            }
        raise UpdateError(f"GitHub ตอบกลับ HTTP {exc.code} ขณะตรวจสอบเวอร์ชัน") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UpdateError("เชื่อมต่อ GitHub เพื่อตรวจสอบเวอร์ชันไม่สำเร็จ") from exc

    tag = release.get("tag_name")
    if not isinstance(tag, str):
        raise UpdateError("Release บน GitHub ไม่มีหมายเลขเวอร์ชัน")
    latest_version = tag.removeprefix("v")
    is_newer = _version_tuple(latest_version) > _version_tuple(current_version)
    assets = release.get("assets") if isinstance(release.get("assets"), list) else []
    package_name = f"kodkon-studio-{latest_version}-windows-portable.zip"
    package_asset = next((item for item in assets if item.get("name") == package_name), None)
    checksum_asset = next((item for item in assets if item.get("name") == f"{package_name}.sha256"), None)
    installable = bool(is_newer and package_asset and checksum_asset)

    return {
        "current_version": current_version,
        "latest_version": latest_version,
        "update_available": is_newer,
        "release_url": release.get("html_url") or f"https://github.com/{repository}/releases/tag/{tag}",
        "published_at": release.get("published_at"),
        "notes": release.get("body") or "Release นี้ยังไม่มีบันทึกรายการเปลี่ยนแปลง",
        "installable": installable,
        "package_url": _asset_url(package_asset, repository) if package_asset else None,
        "checksum_url": _asset_url(checksum_asset, repository) if checksum_asset else None,
    }


def download_verified_update(update: dict) -> Path:
    package_url = update.get("package_url")
    checksum_url = update.get("checksum_url")
    if not update.get("update_available") or not update.get("installable") or not package_url or not checksum_url:
        raise UpdateError("Release ล่าสุดยังไม่มีไฟล์อัปเดตที่ติดตั้งได้")

    try:
        with _request(checksum_url, accept="text/plain") as response:
            checksum_text = response.read(4096).decode("ascii", errors="strict")
        match = SHA256_PATTERN.match(checksum_text)
        if not match:
            raise UpdateError("ไฟล์ตรวจสอบ SHA-256 ของอัปเดตไม่ถูกต้อง")
        expected_digest = match.group(1).lower()

        with _request(package_url, accept="application/octet-stream", timeout=120) as response:
            final_host = urlsplit(response.geturl()).hostname or ""
            if final_host != "github.com" and not final_host.endswith(".githubusercontent.com"):
                raise UpdateError("ปลายทางดาวน์โหลดไม่ใช่ GitHub")
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_RELEASE_ASSET_BYTES:
                raise UpdateError("ไฟล์อัปเดตใหญ่เกินขนาดที่กำหนด")
            digest = hashlib.sha256()
            temp = tempfile.NamedTemporaryFile(prefix="kodkon-update-", suffix=".zip", delete=False)
            archive_path = Path(temp.name)
            total = 0
            try:
                with temp:
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_RELEASE_ASSET_BYTES:
                            raise UpdateError("ไฟล์อัปเดตใหญ่เกินขนาดที่กำหนด")
                        digest.update(chunk)
                        temp.write(chunk)
            except Exception:
                archive_path.unlink(missing_ok=True)
                raise
        if digest.hexdigest() != expected_digest:
            archive_path.unlink(missing_ok=True)
            raise UpdateError("ตรวจสอบ SHA-256 ไม่ผ่าน · ยกเลิกการติดตั้งเพื่อความปลอดภัย")
        return archive_path
    except HTTPError as exc:
        raise UpdateError(f"ดาวน์โหลด Release จาก GitHub ไม่สำเร็จ (HTTP {exc.code})") from exc
    except (URLError, TimeoutError, UnicodeDecodeError, ValueError) as exc:
        raise UpdateError("ดาวน์โหลดหรืออ่านไฟล์ตรวจสอบอัปเดตไม่สำเร็จ") from exc
