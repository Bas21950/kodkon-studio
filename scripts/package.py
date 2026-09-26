from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".venv", "node_modules", ".git"}


def app_version() -> str:
    config = (ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")
    match = re.search(r'app_version:\s*str\s*=\s*"([^"]+)"', config)
    return match.group(1) if match else "0.1.0"


def package_files() -> list[Path]:
    files: set[Path] = set()
    exact = [
        "README.md",
        "backend/alembic.ini",
        "backend/pyproject.toml",
        "backend/requirements.txt",
        "frontend/index.html",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/tsconfig.app.json",
        "frontend/tsconfig.json",
        "frontend/tsconfig.node.json",
        "frontend/vite.config.ts",
        "frontend/dist/index.html",
        "docs/DEVELOPMENT_PLAN.md",
    ]
    for relative in exact:
        path = ROOT / relative
        if path.is_file():
            files.add(path)
    recursive = ["backend/app", "backend/alembic", "frontend/dist", "frontend/public", "frontend/src", "scripts", "docs"]
    for relative in recursive:
        base = ROOT / relative
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
                continue
            if path.suffix == ".pyc" or path.name.endswith(".log"):
                continue
            files.add(path)
    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="สร้าง portable ZIP สำหรับ กดก่อนคิดทีหลัง Studio")
    parser.add_argument("--output", type=Path, help="ตำแหน่งไฟล์ ZIP ที่ต้องการ")
    args = parser.parse_args()
    version = app_version()
    output = args.output or ROOT / "release" / f"kodkon-studio-{version}-windows-portable.zip"
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    files = package_files()
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        raise SystemExit("ไม่พบ frontend/dist/index.html; รัน npm run build ก่อน")
    install_prefix = Path("App") / "KodKon Studio"
    install_files = [
        (ROOT / "scripts" / "installer" / "Start Studio.bat", Path("Start Studio.bat")),
        (ROOT / "scripts" / "installer" / "Start Studio.vbs", Path("Start Studio.vbs")),
        (ROOT / "scripts" / "installer" / "Start Studio.ps1", Path("Start Studio.ps1")),
        (ROOT / "scripts" / "installer" / "README.txt", Path("README.txt")),
    ]
    missing_templates = [str(source.relative_to(ROOT)) for source, _ in install_files if not source.is_file()]
    if missing_templates:
        raise SystemExit(f"ไม่พบไฟล์ launcher สำหรับติดตั้ง: {', '.join(missing_templates)}")
    included_paths = [*(install_prefix / path.relative_to(ROOT) for path in files), *(destination for _, destination in install_files)]
    manifest = {
        "name": "กดก่อนคิดทีหลัง Studio",
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": "Windows 10/11 x64",
        "includes": [path.as_posix() for path in included_paths],
        "secrets_included": False,
        "data_included": False,
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in files:
            archive.write(path, (install_prefix / path.relative_to(ROOT)).as_posix())
        for source, destination in install_files:
            archive.write(source, destination.as_posix())
        archive.writestr("package-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr((install_prefix / "frontend" / ".portable-build").as_posix(), "Prebuilt frontend included in this portable package.\n")
    digest_state = hashlib.sha256()
    with output.open("rb") as packaged:
        while chunk := packaged.read(1024 * 1024):
            digest_state.update(chunk)
    print(f"Portable package created: {output}")
    print(f"Size: {output.stat().st_size:,} bytes | SHA-256: {digest_state.hexdigest()}")
    print("ZIP excludes virtual environments, user data, and DPAPI secrets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
