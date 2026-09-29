from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any

from alembic import command
from alembic.config import Config
from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import ensure_data_directories, settings
from app.database import DATABASE_URL, SessionLocal, engine
from app.models import AICache, Asset, FacebookPage, GeneratedCopy, Job, JobEvent, MusicTrack, OverlayRegion, Project, Publication, PublicationEvent, Render, Revision, SubtitleSegment
from app.schemas import (
    AssetUploadRead,
    CapabilitiesRead,
    EditorRead,
    FacebookConnectWrite,
    GeneratedCopyRead,
    GeneratedCopyPartWrite,
    GeneratedCopyWrite,
    GeminiKeyWrite,
    GeminiModelWrite,
    HealthRead,
    ImagePostCopyGenerate,
    JobRead,
    MusicTrackRead,
    OverlayBatchWrite,
    ProjectCreate,
    ProjectPatch,
    ProjectRead,
    PublicationCreate,
    PublicationPatch,
    PublicationRead,
    RenderRead,
    RevisionSettingsWrite,
    SrtImportRequest,
    SubtitleBatchWrite,
    VoiceoverRequest,
)
from app.services.subtitles import parse_srt, serialize_srt
from app.services.backup import create_backup_archive, remove_backup_archive
from app.services.cleanup import cleanup_stale_work_files
from app.services.updates import UpdateError, download_verified_update, get_latest_update, get_update_progress, set_update_progress, update_in_progress
from app.services.ai_settings import ALLOWED_MODELS, get_model, set_model
from app.services.gemini import GeminiError, generate_json
from app.services.ai_cache import get_gemini_json
from app.services.ai_jobs import IMAGE_POST_COPY_SCHEMA, image_post_copy_prompt
from app.services.facebook import API_VERSION, FacebookApiError, MAX_POST_IMAGES, photo_preflight, photo_set_preflight, reels_preflight, verify_page
from app.services.publication_media import publication_media_asset_ids
from app.services.secret_store import SecretStoreError, delete_facebook_page_token, delete_gemini_key, load_facebook_page_token, load_gemini_key, save_facebook_page_token, save_gemini_key
from app.services.probing import MediaProbeError, find_ffmpeg, find_ffprobe, probe_audio
from app.storage import UnsafeStoragePath, resolve_media_path
from app.worker import recover_interrupted_jobs, worker_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kodkon.api")
HANGUL_RUN = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]+")

BACKEND_ROOT = Path(os.environ.get("KODKON_BACKEND_ROOT", Path(__file__).resolve().parents[1]))
PROJECT_ROOT = Path(os.environ.get("KODKON_RESOURCE_ROOT", BACKEND_ROOT.parent))
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
CHUNK_SIZE = 1024 * 1024
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
ALLOWED_AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac", ".opus"}
MAX_PRODUCT_IMAGE_BYTES = 10 * 1024 * 1024
LOCAL_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8765",
    "http://localhost:8765",
}
if os.environ.get("KODKON_PORT", "").isdigit():
    LOCAL_ORIGINS.update({f"http://127.0.0.1:{os.environ['KODKON_PORT']}", f"http://localhost:{os.environ['KODKON_PORT']}"})


def get_db():
    with SessionLocal() as session:
        yield session


async def _read_image_upload(upload: UploadFile) -> tuple[bytes, str, str]:
    raw = await upload.read(MAX_PRODUCT_IMAGE_BYTES + 1)
    if not raw:
        raise HTTPException(status_code=422, detail="ไฟล์ภาพว่างเปล่า")
    if len(raw) > MAX_PRODUCT_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="ภาพแต่ละไฟล์ต้องไม่เกิน 10 MB")
    if raw.startswith(b"\xff\xd8\xff"):
        return raw, "image/jpeg", ".jpg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return raw, "image/png", ".png"
    raise HTTPException(status_code=415, detail="รองรับเฉพาะภาพ JPG หรือ PNG ซึ่งใช้โพสต์หลายภาพบน Facebook ได้")


def migrate_database() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    # Share the application's engine so Alembic and the API cannot migrate
    # different SQLite files because of platform-specific URL parsing.
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_data_directories()
    await asyncio.to_thread(migrate_database)
    await asyncio.to_thread(cleanup_stale_work_files)
    await asyncio.to_thread(recover_interrupted_jobs)
    worker = asyncio.create_task(worker_loop(), name="kodkon-job-worker")
    app.state.worker_task = worker
    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


app = FastAPI(title="กดก่อนคิดทีหลัง Studio", version=settings.app_version, lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(LOCAL_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Requested-With"],
)


@app.middleware("http")
async def local_write_origin_guard(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin not in LOCAL_ORIGINS:
            return JSONResponse(
                {"detail": "คำขอนี้ต้องมาจากหน้าจอของโปรแกรมที่เปิดในเครื่อง"}, status_code=403
            )
    return await call_next(request)


@app.get("/api/settings/ai")
def read_ai_settings():
    try:
        configured = bool(load_gemini_key())
    except SecretStoreError:
        configured = False
    return {
        "provider": "Gemini API",
        "key_configured": configured,
        "model": get_model(),
        "free_models": sorted(ALLOWED_MODELS),
        "key_storage": "Windows DPAPI",
    }


@app.post("/api/image-posts/generate-copy")
async def generate_image_post_copy(
    product_details: str = Form(default=""),
    affiliate_url: str = Form(default=""),
    auto_append_link: bool = Form(default=True),
    image_files: list[UploadFile] = File(default=[]),
):
    product_details = product_details.strip()
    if len(product_details) > 24000:
        raise HTTPException(status_code=422, detail="ข้อมูลสินค้ายาวเกิน 24,000 ตัวอักษร")
    affiliate_url = ImagePostCopyGenerate(product_details=product_details, affiliate_url=affiliate_url).affiliate_url
    if not product_details and not image_files:
        raise HTTPException(status_code=422, detail="กรุณาแนบภาพอย่างน้อย 1 รูป หรือใส่ข้อมูลสินค้า")
    if len(image_files) > MAX_POST_IMAGES:
        raise HTTPException(status_code=422, detail="แนบภาพได้สูงสุด 6 รูป")
    ai_images: list[tuple[str, bytes]] = []
    if not product_details:
        image_payloads = [await _read_image_upload(upload) for upload in image_files]
        if sum(len(raw) for raw, _, _ in image_payloads) > 36 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="ภาพทั้งหมดรวมกันต้องไม่เกิน 36 MB")
        ai_images = [(mime_type, raw) for raw, mime_type, _ in image_payloads]
    try:
        result, model = get_gemini_json(
            task="image_post_copy_v2" if ai_images else "image_post_copy_v1",
            prompt=image_post_copy_prompt(product_details, from_images=bool(ai_images)),
            schema=IMAGE_POST_COPY_SCHEMA,
            **({"images": ai_images} if ai_images else {}),
            max_output_tokens=2500,
        )
    except GeminiError as exc:
        status_code = 429 if exc.code == "quota_exceeded" else 502
        raise HTTPException(status_code=status_code, detail=exc.user_message) from exc

    caption = str(result.get("caption", "")).strip()[:5000]
    comment_text = str(result.get("comment_text", "")).strip()[:2000]
    if not caption or not comment_text:
        raise HTTPException(status_code=502, detail="Gemini ส่งแคปชั่นหรือคอมเมนต์กลับมาไม่ครบ")
    source_hangul = set(HANGUL_RUN.findall(product_details))
    caption = HANGUL_RUN.sub(lambda match: match.group() if match.group() in source_hangul else "", caption)
    comment_text = HANGUL_RUN.sub(lambda match: match.group() if match.group() in source_hangul else "", comment_text)
    caption = re.sub(r"[ \t]{2,}", " ", caption).strip()
    comment_text = re.sub(r"[ \t]{2,}", " ", comment_text).strip()
    caption = re.sub(r"\s+([,.;!?])", r"\1", caption)
    comment_text = re.sub(r"\s+([,.;!?])", r"\1", comment_text)
    if not caption or not comment_text:
        raise HTTPException(status_code=502, detail="AI ส่งข้อความเป็นภาษาอื่นที่ไม่ตรงกับข้อมูลสินค้า · ตรวจข้อมูลแล้วกดสร้างใหม่")
    if not any("\U0001f300" <= char <= "\U0001faff" or "\u2600" <= char <= "\u27bf" for char in caption):
        caption = f"😏 {caption}"
    if not any("\U0001f300" <= char <= "\U0001faff" or "\u2600" <= char <= "\u27bf" for char in comment_text):
        comment_text = f"🛒 {comment_text}"
    if auto_append_link:
        caption = append_image_post_link(caption, affiliate_url, default_label="🛒 พิกัดสินค้า กดดูตรงนี้")
        comment_text = append_image_post_link(comment_text, affiliate_url, default_label="👉 กดสั่ง/ดูรายละเอียด")
    return {"caption": caption, "comment_text": comment_text, "model_name": model}


@app.get("/api/settings/ai/usage")
def read_ai_usage(db: Session = Depends(get_db)):
    """Report AI jobs started by this installation during the current Thai day.

    Google does not expose the account's live remaining Gemini quota through an
    API-key endpoint, so this is deliberately a local activity estimate only.
    """
    thai = timezone(timedelta(hours=7))
    period_start = datetime.now(thai).replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + timedelta(days=1)
    start_utc = period_start.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = period_end.astimezone(timezone.utc).replace(tzinfo=None)
    gemini_job_types = (
        "ocr_subtitles", "translate_subtitles", "generate_copy", "generate_script",
        "generate_caption", "generate_voiceover",
    )
    rows = db.execute(
        select(Job.job_type, Job.state, func.count(Job.id))
        .where(
            Job.job_type.in_(gemini_job_types),
            Job.created_at >= start_utc,
            Job.created_at < end_utc,
        )
        .group_by(Job.job_type, Job.state)
    ).all()
    by_type: dict[str, int] = {}
    by_state: dict[str, int] = {}
    for job_type, state, count in rows:
        by_type[job_type] = by_type.get(job_type, 0) + int(count)
        by_state[state] = by_state.get(state, 0) + int(count)
    return {
        "period_timezone": "Asia/Bangkok",
        "period_resets_at": period_end.isoformat(),
        "ai_jobs_started": sum(by_type.values()),
        "voiceover_jobs_started": by_type.get("generate_voiceover", 0),
        "ai_jobs_succeeded": by_state.get("succeeded", 0),
        "ai_jobs_failed": by_state.get("failed", 0),
        "ai_jobs_pending": by_state.get("queued", 0) + by_state.get("running", 0),
        "image_post_copy_requests": db.scalar(
            select(func.count(AICache.cache_key)).where(
                AICache.task == "image_post_copy_v1",
                AICache.created_at >= start_utc,
                AICache.created_at < end_utc,
            )
        ) or 0,
        "source": "local_jobs",
    }


@app.put("/api/settings/ai/key", status_code=204)
def write_ai_key(payload: GeminiKeyWrite):
    try:
        save_gemini_key(payload.api_key)
    except (SecretStoreError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return None


@app.delete("/api/settings/ai/key", status_code=204)
def remove_ai_key():
    delete_gemini_key()
    return None


def facebook_page_payload(page: FacebookPage) -> dict:
    try:
        tasks = json.loads(page.tasks_json or "[]")
    except json.JSONDecodeError:
        tasks = []
    try:
        token_configured = bool(load_facebook_page_token(page.id))
    except SecretStoreError:
        token_configured = False
    return {
        "id": page.id,
        "name": page.name,
        "tasks": tasks,
        "is_active": page.is_active,
        "token_configured": token_configured,
        "connected_at": page.connected_at,
    }


@app.get("/api/settings/facebook")
def read_facebook_settings(db: Session = Depends(get_db)):
    pages = db.scalars(select(FacebookPage).order_by(FacebookPage.name.asc())).all()
    return {"provider": "Facebook Graph API", "api_version": API_VERSION, "pages": [facebook_page_payload(page) for page in pages]}


@app.post("/api/settings/facebook/connect", status_code=201)
def connect_facebook_page(payload: FacebookConnectWrite, db: Session = Depends(get_db)):
    try:
        verified = verify_page(payload.page_id, payload.page_access_token.strip())
        save_facebook_page_token(payload.page_id, payload.page_access_token)
    except (FacebookApiError, SecretStoreError, ValueError) as exc:
        message = exc.user_message if isinstance(exc, FacebookApiError) else str(exc)
        raise HTTPException(status_code=422 if not isinstance(exc, FacebookApiError) else 502, detail=message) from exc
    try:
        now = datetime.now(timezone.utc)
        page = db.get(FacebookPage, verified["id"])
        if page is None:
            page = FacebookPage(id=verified["id"], name=verified["name"], tasks_json="[]", is_active=True, connected_at=now)
            db.add(page)
        else:
            page.name = verified["name"]
            page.is_active = True
        for other in db.scalars(select(FacebookPage).where(FacebookPage.id != verified["id"])).all():
            other.is_active = False
        db.commit()
        db.refresh(page)
        return facebook_page_payload(page)
    except Exception as exc:
        db.rollback()
        delete_facebook_page_token(payload.page_id)
        logger.exception("Could not save Facebook Page metadata")
        raise HTTPException(status_code=500, detail="บันทึกการเชื่อมเพจไม่สำเร็จ") from exc


@app.post("/api/settings/facebook/{page_id}/test")
def test_facebook_page(page_id: str, db: Session = Depends(get_db)):
    page = db.get(FacebookPage, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="ไม่พบ Facebook Page ที่เชื่อมไว้")
    try:
        token = load_facebook_page_token(page.id)
    except SecretStoreError:
        token = None
    if not token:
        raise HTTPException(status_code=409, detail="ไม่พบ token ที่บันทึกไว้ ให้เชื่อมเพจใหม่")
    try:
        verified = verify_page(page.id, token)
    except FacebookApiError as exc:
        raise HTTPException(status_code=502, detail=exc.user_message) from exc
    page.name = verified["name"]
    db.commit()
    return {"ok": True, "page_id": page.id, "page_name": page.name, "api_version": API_VERSION}


@app.patch("/api/settings/facebook/{page_id}/select")
def select_facebook_page(page_id: str, db: Session = Depends(get_db)):
    page = db.get(FacebookPage, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="ไม่พบ Facebook Page ที่เชื่อมไว้")
    try:
        token_present = bool(load_facebook_page_token(page.id))
    except SecretStoreError:
        token_present = False
    if not token_present:
        raise HTTPException(status_code=409, detail="ไม่พบ token ที่บันทึกไว้ ให้เชื่อมเพจนี้ใหม่")
    for other in db.scalars(select(FacebookPage)).all():
        other.is_active = other.id == page.id
    db.commit()
    db.refresh(page)
    return facebook_page_payload(page)


@app.delete("/api/settings/facebook/{page_id}", status_code=204)
def disconnect_facebook_page(page_id: str, db: Session = Depends(get_db)):
    page = db.get(FacebookPage, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="ไม่พบ Facebook Page ที่เชื่อมไว้")
    delete_facebook_page_token(page.id)
    db.delete(page)
    db.commit()
    return None


@app.patch("/api/settings/ai/model")
def update_ai_model(payload: GeminiModelWrite):
    try:
        set_model(payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"model": get_model()}


@app.post("/api/settings/ai/test")
def test_ai_connection():
    key = load_gemini_key()
    if not key:
        raise HTTPException(status_code=409, detail="บันทึก Gemini API key ก่อนทดสอบ")
    schema = {"type": "OBJECT", "properties": {"ok": {"type": "BOOLEAN"}}, "required": ["ok"]}
    model = get_model()
    try:
        response = generate_json(key, model, "Return JSON with ok set to true.", schema, max_output_tokens=32)
    except GeminiError as exc:
        raise HTTPException(status_code=429 if exc.code == "quota_exceeded" else 502, detail=exc.user_message) from exc
    if response.get("ok") is not True:
        raise HTTPException(status_code=502, detail="Gemini ตอบกลับไม่ตรงรูปแบบ")
    return {"ok": True, "model": model}


@app.get("/api/health", response_model=HealthRead)
def health() -> HealthRead:
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        db_state = "พร้อมใช้งาน"
    except Exception:
        logger.exception("Health check could not access the database")
        db_state = "ขัดข้อง"
    return HealthRead(
        status="ok" if db_state == "พร้อมใช้งาน" else "degraded",
        app="KodKon Studio",
        version=settings.app_version,
        database=db_state,
        ffmpeg_available=find_ffmpeg() is not None,
        ffprobe_available=find_ffprobe() is not None,
    )


@app.get("/api/maintenance/backup")
def download_backup(request: Request):
    if request.headers.get("origin") not in LOCAL_ORIGINS and request.headers.get("sec-fetch-site") != "same-origin":
        raise HTTPException(status_code=403, detail="ดาวน์โหลดไฟล์สำรองได้จากหน้าจอของโปรแกรมที่เปิดในเครื่องเท่านั้น")
    try:
        archive_path, filename = create_backup_archive()
    except Exception as exc:
        logger.exception("Failed to create a local data backup")
        raise HTTPException(status_code=500, detail="สำรองข้อมูลไม่สำเร็จ ตรวจพื้นที่ว่างแล้วลองอีกครั้ง") from exc
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(remove_backup_archive, archive_path),
    )


@app.get("/api/capabilities", response_model=CapabilitiesRead)
def capabilities() -> CapabilitiesRead:
    try:
        free = shutil.disk_usage(settings.data_dir).free
    except OSError:
        free = 0
    return CapabilitiesRead(
        app="กดก่อนคิดทีหลัง Studio",
        version=settings.app_version,
        ffmpeg_available=find_ffmpeg() is not None,
        ffprobe_available=find_ffprobe() is not None,
        max_upload_bytes=settings.max_upload_bytes,
        storage_available_bytes=free,
        data_directory_name=settings.data_dir.name,
    )


@app.get("/api/updates")
def check_application_updates():
    try:
        return get_latest_update(settings.app_version)
    except UpdateError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _update_status_path() -> Path | None:
    value = os.environ.get("KODKON_UPDATE_STATUS_PATH")
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if path.parent != temp_root or not path.name.startswith("kodkon-update-status-") or path.suffix != ".json":
        return None
    return path


def _update_installer_log_tail(log_path: Path) -> str:
    try:
        with log_path.open("rb") as log_file:
            log_file.seek(max(0, log_path.stat().st_size - 4096))
            return log_file.read().decode("utf-8", errors="replace").strip()[-2000:]
    except OSError:
        return ""


def _watch_update_installer(
    installer: subprocess.Popen,
    update_id: str,
    version: str,
    status_path: Path,
    log_path: Path,
    archive_path: Path,
) -> None:
    last_status: tuple[str, int, str] | None = None
    last_change = time.monotonic()
    heartbeat_timeout = 120

    while True:
        progress = get_update_progress(update_id, settings.app_version, status_path)
        now = time.monotonic()
        if progress:
            try:
                progress_value = int(progress.get("progress", 0))
            except (TypeError, ValueError):
                progress_value = 0
            signature = (str(progress.get("status")), progress_value, str(progress.get("message", "")))
            if signature != last_status:
                last_status = signature
                last_change = now
            if progress.get("status") in {"completed", "failed"}:
                return

        exit_code = installer.poll()
        if exit_code is not None:
            details = _update_installer_log_tail(log_path)
            logger.error("Update installer exited before reporting completion (exit=%s): %s", exit_code, details or "no installer output")
            message = "ตัวติดตั้งหยุดก่อนรายงานว่าเสร็จ · เปิดโปรแกรมใหม่แล้วลองอัปเดตอีกครั้ง"
            if details:
                message = f"{message} · {details[-500:]}"
            set_update_progress(update_id, version, "failed", 0, message, status_path)
            archive_path.unlink(missing_ok=True)
            return

        if now - last_change > heartbeat_timeout:
            try:
                installer.terminate()
                installer.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    installer.kill()
                except OSError:
                    pass
            details = _update_installer_log_tail(log_path)
            logger.error("Update installer stopped reporting progress for %ss: %s", heartbeat_timeout, details or "no installer output")
            set_update_progress(
                update_id,
                version,
                "failed",
                0,
                "ตัวติดตั้งไม่รายงานความคืบหน้าเกิน 2 นาที · เปิดโปรแกรมใหม่แล้วลองอีกครั้ง",
                status_path,
            )
            archive_path.unlink(missing_ok=True)
            return

        time.sleep(0.5)


def _install_update_in_background(requested_version: str, update_id: str, status_path: Path, install_root: Path, update_script: Path, process_id: int) -> None:
    version = requested_version
    archive_path: Path | None = None
    set_update_progress(update_id, version, "checking", 2, "กำลังตรวจสอบเวอร์ชันล่าสุดบน GitHub", status_path)
    last_progress = -1

    def report_download(received: int, total: int | None) -> None:
        nonlocal last_progress
        progress = min(72, 4 + int(received * 68 / total)) if total else 8
        if progress != last_progress:
            last_progress = progress
            message = "กำลังดาวน์โหลดไฟล์อัปเดต" if total is None else f"กำลังดาวน์โหลดไฟล์อัปเดต · {progress}%"
            set_update_progress(update_id, version, "downloading", progress, message, status_path)

    def report_fallback() -> None:
        set_update_progress(update_id, version, "downloading", 4, "ช่องทางแรกไม่ตอบสนอง · กำลังใช้ตัวดาวน์โหลด Windows", status_path)

    try:
        update = get_latest_update(settings.app_version)
        if update.get("latest_version") != requested_version or not update.get("update_available") or not update.get("installable"):
            raise UpdateError("เวอร์ชันอัปเดตเปลี่ยนไปแล้ว · ตรวจสอบรายการใหม่ก่อนติดตั้ง")
        set_update_progress(update_id, version, "downloading", 4, "กำลังดาวน์โหลดไฟล์อัปเดตจาก GitHub", status_path)
        archive_path = download_verified_update(update, report_download, report_fallback)
        set_update_progress(update_id, version, "verifying", 76, "ตรวจสอบ SHA-256 ผ่าน · กำลังเตรียมติดตั้ง", status_path)
        powershell = shutil.which("powershell.exe")
        if not powershell:
            raise UpdateError("หา Windows PowerShell ไม่พบ · ไม่ได้ติดตั้งอัปเดต")
        command = [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(update_script),
            "-ArchivePath",
            str(archive_path),
            "-InstallRoot",
            str(install_root),
            "-ProcessId",
            str(process_id),
            "-Version",
            version,
            "-StatusPath",
            str(status_path),
        ]
        set_update_progress(update_id, version, "installing", 80, "ไฟล์ปลอดภัยแล้ว · กำลังเริ่มตัวติดตั้ง", status_path)
        installer_log = status_path.with_suffix(".log")
        with installer_log.open("wb") as log_file:
            installer = subprocess.Popen(
                command,
                cwd=str(install_root),
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        watcher = threading.Thread(
            target=_watch_update_installer,
            args=(installer, update_id, version, status_path, installer_log, archive_path),
            name="kodkon-update-watchdog",
            daemon=True,
        )
        watcher.start()
        archive_path = None  # The updater script or watchdog removes its verified archive.
    except Exception as exc:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
        message = str(exc) if isinstance(exc, UpdateError) else "เริ่มติดตั้งอัปเดตไม่สำเร็จ · " + str(exc)
        logger.exception("Failed to install the verified application update")
        set_update_progress(update_id, version, "failed", 0, message, status_path)


@app.post("/api/updates/install", status_code=202)
async def install_application_update(request: Request, payload: dict = Body(...)):
    if request.headers.get("origin") not in LOCAL_ORIGINS and request.headers.get("sec-fetch-site") != "same-origin":
        raise HTTPException(status_code=403, detail="ติดตั้งอัปเดตได้จากหน้าจอของโปรแกรมที่เปิดในเครื่องเท่านั้น")
    if sys.platform != "win32":
        raise HTTPException(status_code=409, detail="ตัวติดตั้งอัปเดตนี้รองรับ Windows เท่านั้น")

    install_root_value = os.environ.get("KODKON_INSTALL_ROOT")
    powershell = shutil.which("powershell.exe")
    update_script = PROJECT_ROOT / "scripts" / "apply-update.ps1"
    if not install_root_value or not powershell or not update_script.is_file():
        raise HTTPException(status_code=409, detail="เปิดโปรแกรมจาก shortcut บน Desktop หรือ Start Studio.vbs ในโฟลเดอร์ติดตั้งก่อนจึงจะอัปเดตได้")
    install_root = Path(install_root_value).expanduser().resolve()
    expected_project = (install_root / "App" / "KodKon Studio").resolve()
    if expected_project != PROJECT_ROOT.resolve() or not (install_root / "Start Studio.vbs").is_file():
        raise HTTPException(status_code=409, detail="ตำแหน่งติดตั้งไม่ตรงกับตัวโปรแกรมที่กำลังเปิดอยู่")

    with SessionLocal() as session:
        active_job = session.scalar(select(Job.id).where(Job.state.in_(["queued", "running"])).limit(1))
        active_publication = session.scalar(
            select(Publication.id).where(Publication.status.in_(["publishing", "processing"])).limit(1)
        )
    if active_job or active_publication:
        raise HTTPException(status_code=409, detail="ยังมีงานตัดต่อหรือโพสต์กำลังทำงาน · รอให้งานเสร็จก่อนแล้วค่อยอัปเดต")

    if update_in_progress():
        raise HTTPException(status_code=409, detail="กำลังติดตั้งอัปเดตอยู่")

    requested_version = payload.get("version")
    if not isinstance(requested_version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", requested_version):
        raise HTTPException(status_code=422, detail="ไม่พบหมายเลขเวอร์ชันที่ต้องการติดตั้ง")

    try:
        update_id = uuid.uuid4().hex
        status_path = Path(tempfile.gettempdir()) / f"kodkon-update-status-{update_id}.json"
        set_update_progress(update_id, requested_version, "checking", 1, "กำลังเตรียมอัปเดต", status_path)
        worker = threading.Thread(
            target=_install_update_in_background,
            args=(requested_version, update_id, status_path, install_root, update_script, os.getpid()),
            name="kodkon-application-updater",
            daemon=True,
        )
        worker.start()
    except HTTPException:
        raise
    except (UpdateError, OSError, RuntimeError) as exc:
        logger.exception("Failed to start the verified application updater")
        raise HTTPException(status_code=500, detail="เริ่มตัวติดตั้งอัปเดตไม่สำเร็จ") from exc
    return {"status": "checking", "update_id": update_id, "version": requested_version, "message": "กำลังตรวจสอบและเตรียมไฟล์อัปเดต"}


@app.get("/api/updates/progress/{update_id}")
def application_update_progress(update_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", update_id):
        raise HTTPException(status_code=422, detail="รหัสอัปเดตไม่ถูกต้อง")
    target_version = os.environ.get("KODKON_UPDATE_TARGET_VERSION")
    if target_version and target_version == settings.app_version:
        return {"update_id": update_id, "version": target_version, "status": "completed", "progress": 100, "message": "อัปเดตเสร็จแล้ว · โปรแกรมพร้อมใช้งาน"}
    status_path = _update_status_path() or Path(tempfile.gettempdir()) / f"kodkon-update-status-{update_id}.json"
    status = get_update_progress(update_id, settings.app_version, status_path)
    if status is None:
        raise HTTPException(status_code=404, detail="ไม่พบสถานะอัปเดตนี้")
    return status


@app.get("/api/updates/session")
def application_update_session():
    status_path = _update_status_path()
    if status_path is not None and status_path.is_file():
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8-sig"))
            update_id = payload.get("update_id")
            if isinstance(update_id, str) and re.fullmatch(r"[a-f0-9]{32}", update_id):
                progress = get_update_progress(update_id, settings.app_version, status_path)
                if progress and progress.get("status") == "failed":
                    return progress
        except (OSError, json.JSONDecodeError):
            pass
    target_version = os.environ.get("KODKON_UPDATE_TARGET_VERSION")
    if target_version and target_version == settings.app_version:
        return {
            "update_id": "0" * 32,
            "version": target_version,
            "status": "completed",
            "progress": 100,
            "message": "อัปเดตเสร็จแล้ว · โปรแกรมพร้อมใช้งาน",
        }
    return None


@app.get("/api/projects", response_model=list[ProjectRead])
def list_projects(
    q: str | None = Query(default=None, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    statement = (
        select(Project)
        .options(selectinload(Project.assets), selectinload(Project.jobs))
        .order_by(Project.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(Project.title.ilike(pattern) | Project.product_name.ilike(pattern))
    return db.scalars(statement).all()


@app.post("/api/projects", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="ใส่ชื่อโปรเจกต์ก่อนบันทึก")
    project = Project(
        id=str(uuid.uuid4()),
        title=title,
        product_name=payload.product_name or None,
        product_details=payload.product_details or None,
        review_evidence=payload.review_evidence or None,
        discount_text=payload.discount_text or None,
        copy_style=payload.copy_style,
        affiliate_url=payload.affiliate_url or None,
        source_url=payload.source_url or None,
    )
    db.add(project)
    revision = Revision(project_id=project.id, version=1, state="draft")
    db.add(revision)
    db.commit()
    return db.scalar(
        select(Project)
        .options(selectinload(Project.assets), selectinload(Project.jobs))
        .where(Project.id == project.id)
    )


@app.get("/api/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.scalar(
        select(Project)
        .options(selectinload(Project.assets), selectinload(Project.jobs))
        .where(Project.id == project_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="ไม่พบโปรเจกต์นี้")
    return project


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="ไม่พบโปรเจกต์นี้")

    active_job = db.scalar(
        select(Job.id).where(Job.project_id == project_id, Job.state.in_(["queued", "running"])).limit(1)
    )
    if active_job:
        raise HTTPException(status_code=409, detail="โปรเจกต์นี้ยังมีงานอยู่ในคิวหรือกำลังประมวลผล · รอให้งานจบก่อนแล้วค่อยลบ")

    active_publication = db.scalar(
        select(Publication.id).where(
            Publication.project_id == project_id,
            Publication.status.in_(["publishing", "processing"]),
        ).limit(1)
    )
    if active_publication:
        raise HTTPException(status_code=409, detail="โปรเจกต์นี้กำลังส่งโพสต์หรือรอ Facebook ประมวลผล · รอให้สถานะเสร็จก่อนแล้วค่อยลบ")

    try:
        project_dir = resolve_media_path(f"projects/{project.id}/.project-scope").parent
        projects_dir = resolve_media_path("projects/.project-scope").parent
    except UnsafeStoragePath as exc:
        raise HTTPException(status_code=400, detail="ตำแหน่งไฟล์โปรเจกต์ไม่ปลอดภัย จึงยกเลิกการลบ") from exc
    if project_dir == projects_dir or project_dir.parent != projects_dir:
        raise HTTPException(status_code=400, detail="ตำแหน่งไฟล์โปรเจกต์ไม่ปลอดภัย จึงยกเลิกการลบ")

    db.delete(project)
    db.commit()
    try:
        if project_dir.exists():
            shutil.rmtree(project_dir)
    except OSError:
        logger.exception("Project %s was removed from the database, but its media directory could not be deleted", project_id)
    return None


@app.patch("/api/projects/{project_id}", response_model=ProjectRead)
def update_project(project_id: str, payload: ProjectPatch, db: Session = Depends(get_db)):
    project = db.scalar(
        select(Project)
        .options(selectinload(Project.assets), selectinload(Project.jobs))
        .where(Project.id == project_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="ไม่พบโปรเจกต์นี้")
    changes = payload.model_dump(exclude_unset=True)
    if "source_url" in changes:
        new_source_url = changes["source_url"].strip() if isinstance(changes["source_url"], str) else changes["source_url"]
        if new_source_url != project.source_url or not new_source_url:
            project.product_source_details = None
            project.product_average_rating = None
            project.product_review_count = None
            project.product_review_summary = None
            project.product_data_read_at = None
    for field, value in changes.items():
        if field == "title" and (value is None or not value.strip()):
            raise HTTPException(status_code=422, detail="ชื่อโปรเจกต์ห้ามเว้นว่าง")
        setattr(project, field, value.strip() if isinstance(value, str) else value)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return project


def sanitized_filename(filename: str | None, kind: str = "source_video") -> tuple[str, str]:
    provided = (filename or "video.mp4").replace("\\", "/").replace("\x00", "")
    basename = PurePosixPath(provided).name.strip() or "video.mp4"
    suffix = Path(basename).suffix.lower()
    allowed = ALLOWED_AUDIO_SUFFIXES if kind == "music_track" else ALLOWED_VIDEO_SUFFIXES
    if suffix not in allowed:
        if kind == "music_track":
            raise HTTPException(status_code=415, detail="รองรับเพลง MP3, M4A, AAC, WAV, OGG, FLAC และ OPUS")
        raise HTTPException(status_code=415, detail="รองรับวิดีโอ MP4, MOV, M4V, MKV และ WEBM")
    return basename[:255], suffix


@app.post("/api/projects/{project_id}/assets", response_model=AssetUploadRead, status_code=202)
async def upload_video(
    project_id: str,
    file: UploadFile = File(...),
    kind: str = Query(default="source_video", pattern="^(source_video|music_track)$"),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="ไม่พบโปรเจกต์นี้")
    original_name, suffix = sanitized_filename(file.filename, kind)
    # UploadFile is spooled by Starlette; the stream is written in bounded chunks below.
    staging_dir = settings.media_dir / ".staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    temp_path = staging_dir / f"{uuid.uuid4().hex}.upload"
    digest = hashlib.sha256()
    total = 0
    destination: Path | None = None
    try:
        with temp_path.open("wb") as output:
            while chunk := await file.read(CHUNK_SIZE):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="ไฟล์ใหญ่เกินขนาดที่โปรแกรมรองรับ 2 GB")
                digest.update(chunk)
                output.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="ไฟล์วิดีโอว่างเปล่า")

        asset_id = str(uuid.uuid4())
        relative_path = f"projects/{project_id}/{asset_id}{suffix}"
        destination = resolve_media_path(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_path, destination)

        asset = Asset(
            id=asset_id,
            project_id=project_id,
            kind=kind,
            original_name=original_name,
            relative_path=relative_path,
            byte_size=total,
            sha256=digest.hexdigest(),
            state="processing",
        )
        job = Job(
            id=str(uuid.uuid4()),
            project_id=project_id,
            asset_id=asset_id,
            job_type="probe_asset",
            state="queued",
            progress=0,
        )
        db.add_all([asset, job])
        revision = db.scalar(
            select(Revision).where(Revision.project_id == project_id).order_by(Revision.version.desc()).limit(1)
        )
        if revision and kind == "source_video":
            revision.source_asset_id = asset_id
            revision.updated_at = datetime.now(timezone.utc)
        db.flush()
        db.add(JobEvent(job_id=job.id, event_type="queued", message="รับไฟล์แล้ว รออ่านรายละเอียดวิดีโอ", created_at=datetime.now(timezone.utc)))
        project.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(asset)
        return {"asset": asset, "job": job}
    except HTTPException:
        db.rollback()
        temp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        db.rollback()
        temp_path.unlink(missing_ok=True)
        if destination is not None:
            destination.unlink(missing_ok=True)
        logger.exception("Failed to save uploaded media")
        raise HTTPException(status_code=500, detail="บันทึกไฟล์ไม่สำเร็จ ตรวจพื้นที่ว่างแล้วลองอีกครั้ง") from exc
    finally:
        await file.close()


@app.get("/api/assets/{asset_id}/file")
def get_asset_file(asset_id: str, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์นี้")
    try:
        path = resolve_media_path(asset.relative_path)
    except UnsafeStoragePath as exc:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์นี้") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ในโฟลเดอร์ข้อมูล")
    media_type = mimetypes.guess_type(asset.original_name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


@app.get("/api/music-library", response_model=list[MusicTrackRead])
def get_music_library(db: Session = Depends(get_db)):
    return db.scalars(select(MusicTrack).order_by(MusicTrack.created_at.desc())).all()


@app.post("/api/music-library", response_model=MusicTrackRead, status_code=201)
async def upload_music_library(file: UploadFile = File(...), db: Session = Depends(get_db)):
    original_name, suffix = sanitized_filename(file.filename, "music_track")
    staging_dir = settings.media_dir / ".staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    temp_path = staging_dir / f"{uuid.uuid4().hex}.upload"
    digest = hashlib.sha256()
    total = 0
    destination: Path | None = None
    try:
        with temp_path.open("wb") as output:
            while chunk := await file.read(CHUNK_SIZE):
                total += len(chunk)
                if total > 2 * 1024 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="ไฟล์ใหญ่เกินขนาดที่โปรแกรมรองรับ 2 GB")
                digest.update(chunk)
                output.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="ไฟล์เพลงว่างเปล่า")
        try:
            metadata = probe_audio(temp_path)
        except MediaProbeError as exc:
            raise HTTPException(status_code=415, detail=exc.user_message) from exc

        track = MusicTrack(
            id=str(uuid.uuid4()),
            original_name=original_name,
            relative_path=f"music-library/{uuid.uuid4()}{suffix}",
            byte_size=total,
            sha256=digest.hexdigest(),
            duration_ms=metadata.get("duration_ms"),
        )
        destination = resolve_media_path(track.relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_path, destination)
        db.add(track)
        db.commit()
        db.refresh(track)
        return track
    except HTTPException:
        db.rollback()
        temp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        db.rollback()
        temp_path.unlink(missing_ok=True)
        if destination is not None:
            destination.unlink(missing_ok=True)
        logger.exception("Failed to save music library track")
        raise HTTPException(status_code=500, detail="บันทึกไฟล์เพลงไม่สำเร็จ ตรวจพื้นที่ว่างแล้วลองอีกครั้ง") from exc
    finally:
        await file.close()


@app.get("/api/music-library/{track_id}/file")
def get_music_library_file(track_id: str, db: Session = Depends(get_db)):
    track = db.get(MusicTrack, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์เพลงนี้")
    try:
        path = resolve_media_path(track.relative_path)
    except UnsafeStoragePath as exc:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์เพลงนี้") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์เพลงในโฟลเดอร์ข้อมูล")
    media_type = mimetypes.guess_type(track.original_name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


@app.get("/api/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ไม่พบงานนี้")
    return job


def get_revision_or_404(revision_id: str, db: Session) -> Revision:
    revision = db.get(Revision, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="ไม่พบเวอร์ชันตัดต่อนี้")
    return revision


def editor_payload(revision: Revision, db: Session) -> dict:
    try:
        settings_value = json.loads(revision.settings_json or "{}")
    except json.JSONDecodeError:
        settings_value = {}
    return {
        "id": revision.id,
        "project_id": revision.project_id,
        "version": revision.version,
        "state": revision.state,
        "source_asset": revision.source_asset,
        "voiceover_asset": db.get(Asset, settings_value.get("voiceover_asset_id")) if settings_value.get("voiceover_asset_id") else None,
        "settings": settings_value,
        "subtitles": revision.subtitles,
        "overlays": revision.overlays,
        "renders": [
            {
                "id": item.id,
                "revision_id": item.revision_id,
                "output_asset": db.get(Asset, item.output_asset_id) if item.output_asset_id else None,
                "state": item.state,
                "error_message": item.error_message,
                "created_at": item.created_at,
                "finished_at": item.finished_at,
            }
            for item in db.scalars(select(Render).where(Render.revision_id == revision.id).order_by(Render.created_at.desc())).all()
        ],
    }


@app.get("/api/projects/{project_id}/editor", response_model=EditorRead)
def get_latest_editor(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="ไม่พบโปรเจกต์นี้")
    revision = db.scalar(
        select(Revision)
        .options(selectinload(Revision.subtitles), selectinload(Revision.overlays), selectinload(Revision.source_asset))
        .where(Revision.project_id == project_id)
        .order_by(Revision.version.desc())
        .limit(1)
    )
    if revision is None:
        revision = Revision(project_id=project_id, version=1, state="draft")
        db.add(revision)
        db.commit()
        revision = db.scalar(
            select(Revision)
            .options(selectinload(Revision.subtitles), selectinload(Revision.overlays), selectinload(Revision.source_asset))
            .where(Revision.project_id == project_id)
        )
    elif revision.source_asset_id is None:
        source_asset = db.scalar(
            select(Asset).where(Asset.project_id == project_id, Asset.kind == "source_video", Asset.state == "ready")
            .order_by(Asset.created_at.desc()).limit(1)
        )
        if source_asset:
            revision.source_asset_id = source_asset.id
            db.commit()
            db.refresh(revision)
            revision = db.scalar(
                select(Revision)
                .options(selectinload(Revision.subtitles), selectinload(Revision.overlays), selectinload(Revision.source_asset))
                .where(Revision.id == revision.id)
            )
    return editor_payload(revision, db)


@app.post("/api/projects/{project_id}/revisions", response_model=EditorRead, status_code=201)
def create_revision(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="ไม่พบโปรเจกต์นี้")
    previous = db.scalar(
        select(Revision)
        .options(selectinload(Revision.subtitles), selectinload(Revision.overlays), selectinload(Revision.source_asset))
        .where(Revision.project_id == project_id)
        .order_by(Revision.version.desc())
        .limit(1)
    )
    settings_value = json.loads(previous.settings_json) if previous else {
        "audio_mode": "mute",
        "subtitle_style": {"font_size": 52, "font_color": "#FFFFFF", "box_color": "#111111", "box_opacity": 0.92, "margin_bottom": 80},
    }
    revision = Revision(
        project_id=project_id,
        version=(previous.version + 1) if previous else 1,
        source_asset_id=previous.source_asset_id if previous else None,
        state="draft",
        settings_json=json.dumps(settings_value, ensure_ascii=False),
    )
    db.add(revision)
    db.flush()
    if previous:
        for item in previous.subtitles:
            db.add(SubtitleSegment(
                revision_id=revision.id,
                stable_id=item.stable_id,
                position=item.position,
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                source_text=item.source_text,
                translated_text=item.translated_text,
                ocr_confidence=item.ocr_confidence,
                review_flag=item.review_flag,
            ))
        for item in previous.overlays:
            db.add(OverlayRegion(
                revision_id=revision.id,
                label=item.label,
                x=item.x,
                y=item.y,
                width=item.width,
                height=item.height,
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                color=item.color,
                opacity=item.opacity,
            ))
    db.commit()
    revision = db.scalar(
        select(Revision)
        .options(selectinload(Revision.subtitles), selectinload(Revision.overlays), selectinload(Revision.source_asset))
        .where(Revision.id == revision.id)
    )
    return editor_payload(revision, db)


@app.put("/api/revisions/{revision_id}/subtitles", response_model=EditorRead)
def save_subtitles(revision_id: str, payload: SubtitleBatchWrite, db: Session = Depends(get_db)):
    revision = db.scalar(
        select(Revision).options(selectinload(Revision.source_asset))
        .where(Revision.id == revision_id)
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="ไม่พบเวอร์ชันตัดต่อนี้")
    source = revision.source_asset
    if source is None or source.state != "ready":
        raise HTTPException(status_code=409, detail="ต้องเพิ่มวิดีโอและรอให้อ่านไฟล์เสร็จก่อน")
    if source.duration_ms is not None and any(item.end_ms > source.duration_ms for item in payload.items):
        raise HTTPException(status_code=422, detail="เวลาซับเกินความยาวของวิดีโอ")
    db.query(SubtitleSegment).filter(SubtitleSegment.revision_id == revision_id).delete(synchronize_session=False)
    for position, item in enumerate(payload.items):
        db.add(SubtitleSegment(
            revision_id=revision_id,
            stable_id=item.stable_id,
            position=position,
            start_ms=item.start_ms,
            end_ms=item.end_ms,
            source_text=item.source_text.strip(),
            translated_text=item.translated_text.strip(),
            review_flag=item.review_flag,
        ))
    revision.state = "draft"
    revision.updated_at = datetime.now(timezone.utc)
    db.commit()
    return get_editor_by_revision(revision_id, db)


@app.put("/api/revisions/{revision_id}/overlays", response_model=EditorRead)
def save_overlays(revision_id: str, payload: OverlayBatchWrite, db: Session = Depends(get_db)):
    revision = db.scalar(select(Revision).options(selectinload(Revision.source_asset)).where(Revision.id == revision_id))
    if revision is None:
        raise HTTPException(status_code=404, detail="ไม่พบเวอร์ชันตัดต่อนี้")
    source = revision.source_asset
    if source is None or source.state != "ready":
        raise HTTPException(status_code=409, detail="ต้องเพิ่มวิดีโอและรอให้อ่านไฟล์เสร็จก่อน")
    if source.duration_ms is not None and any(item.end_ms > source.duration_ms for item in payload.items):
        raise HTTPException(status_code=422, detail="เวลาปิดทับเกินความยาวของวิดีโอ")
    db.query(OverlayRegion).filter(OverlayRegion.revision_id == revision_id).delete(synchronize_session=False)
    for item in payload.items:
        db.add(OverlayRegion(
            id=item.id,
            revision_id=revision_id,
            label=item.label,
            x=item.x,
            y=item.y,
            width=item.width,
            height=item.height,
            start_ms=item.start_ms,
            end_ms=item.end_ms,
            color=item.color.upper(),
            opacity=item.opacity,
        ))
    revision.state = "draft"
    revision.updated_at = datetime.now(timezone.utc)
    db.commit()
    return get_editor_by_revision(revision_id, db)


def get_editor_by_revision(revision_id: str, db: Session) -> dict:
    revision = db.scalar(
        select(Revision)
        .options(selectinload(Revision.subtitles), selectinload(Revision.overlays), selectinload(Revision.source_asset))
        .where(Revision.id == revision_id)
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="ไม่พบเวอร์ชันตัดต่อนี้")
    return editor_payload(revision, db)


@app.post("/api/revisions/{revision_id}/subtitles/import-srt", response_model=EditorRead)
def import_srt(revision_id: str, payload: SrtImportRequest, db: Session = Depends(get_db)):
    revision = db.scalar(select(Revision).options(selectinload(Revision.source_asset)).where(Revision.id == revision_id))
    if revision is None:
        raise HTTPException(status_code=404, detail="ไม่พบเวอร์ชันตัดต่อนี้")
    if revision.source_asset is None or revision.source_asset.state != "ready":
        raise HTTPException(status_code=409, detail="ต้องเพิ่มวิดีโอและรอให้อ่านไฟล์เสร็จก่อน")
    try:
        items = parse_srt(payload.content)
    except (ValueError, IndexError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if revision.source_asset.duration_ms is not None and any(item.end_ms > revision.source_asset.duration_ms for item in items):
        raise HTTPException(status_code=422, detail="มีช่วงซับที่ยาวเกินวิดีโอ")
    db.query(SubtitleSegment).filter(SubtitleSegment.revision_id == revision_id).delete(synchronize_session=False)
    for position, item in enumerate(items):
        db.add(SubtitleSegment(
            revision_id=revision_id,
            stable_id=item.stable_id,
            position=position,
            start_ms=item.start_ms,
            end_ms=item.end_ms,
            source_text=item.source_text,
            translated_text=item.translated_text,
            review_flag=True,
        ))
    revision.state = "draft"
    revision.updated_at = datetime.now(timezone.utc)
    db.commit()
    return get_editor_by_revision(revision_id, db)


@app.get("/api/revisions/{revision_id}/subtitles/export.srt")
def export_srt(revision_id: str, db: Session = Depends(get_db)):
    revision = db.scalar(select(Revision).options(selectinload(Revision.subtitles)).where(Revision.id == revision_id))
    if revision is None:
        raise HTTPException(status_code=404, detail="ไม่พบเวอร์ชันตัดต่อนี้")
    body = "\ufeff" + serialize_srt(revision.subtitles)
    return PlainTextResponse(body, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": "attachment; filename=thai-subtitles.srt"})


@app.patch("/api/revisions/{revision_id}/settings", response_model=EditorRead)
def save_revision_settings(revision_id: str, payload: RevisionSettingsWrite, db: Session = Depends(get_db)):
    revision = get_revision_or_404(revision_id, db)
    previous = json.loads(revision.settings_json or "{}")
    if payload.audio_mode == "music":
        if bool(payload.music_asset_id) == bool(payload.music_library_id):
            raise HTTPException(status_code=422, detail="เลือกเพลงจากคลังเพลงก่อนใช้เสียงประกอบ")
        if payload.music_library_id:
            music = db.get(MusicTrack, payload.music_library_id)
            if music is None:
                raise HTTPException(status_code=422, detail="ไม่พบเพลงที่เลือกในคลังเพลง")
        else:
            music = db.get(Asset, payload.music_asset_id)
            if music is None or music.project_id != revision.project_id or music.kind != "music_track" or music.state != "ready":
                raise HTTPException(status_code=422, detail="เลือกไฟล์เพลงที่พร้อมใช้งานในโปรเจกต์นี้")
    if payload.voiceover_asset_id:
        voiceover = db.get(Asset, payload.voiceover_asset_id)
        if voiceover is None or voiceover.project_id != revision.project_id or voiceover.kind != "voiceover_audio" or voiceover.state != "ready":
            raise HTTPException(status_code=422, detail="เลือกเสียงพากย์ไทยที่พร้อมใช้งานในโปรเจกต์นี้")
    previous.update(payload.model_dump())
    revision.settings_json = json.dumps(previous, ensure_ascii=False)
    revision.state = "draft"
    revision.updated_at = datetime.now(timezone.utc)
    db.commit()
    return get_editor_by_revision(revision_id, db)


def enqueue_ai_job(revision: Revision, job_type: str, message: str, db: Session, payload: dict | None = None) -> Job:
    existing = db.scalar(select(Job).where(
        Job.revision_id == revision.id,
        Job.job_type == job_type,
        Job.state.in_(["queued", "running"]),
    ).order_by(Job.created_at.desc()).limit(1))
    if existing:
        return existing
    job = Job(
        id=str(uuid.uuid4()), project_id=revision.project_id, revision_id=revision.id,
        job_type=job_type, payload_json=json.dumps(payload or {}, ensure_ascii=False), state="queued", progress=0,
    )
    db.add(job)
    db.flush()
    db.add(JobEvent(job_id=job.id, event_type="queued", message=message, created_at=datetime.now(timezone.utc)))
    db.commit()
    return job


def active_facebook_page(db: Session) -> FacebookPage | None:
    return db.scalar(select(FacebookPage).where(FacebookPage.is_active.is_(True)).limit(1))


def queue_facebook_publish(publication: Publication, page: FacebookPage, db: Session, now: datetime) -> Job:
    job_type = "facebook_publish_photo" if publication.media_type == "image" else "facebook_publish_reel"
    pending_jobs = db.scalars(select(Job).where(
        Job.job_type == job_type,
        Job.state.in_(["queued", "running"]),
    )).all()
    for pending in pending_jobs:
        try:
            if json.loads(pending.payload_json or "{}").get("publication_id") == publication.id:
                return pending
        except json.JSONDecodeError:
            continue
    job = Job(
        id=str(uuid.uuid4()), project_id=publication.project_id, asset_id=publication.render_asset_id,
        revision_id=publication.revision_id, job_type=job_type,
        payload_json=json.dumps({"publication_id": publication.id}, ensure_ascii=False),
        state="queued", progress=0, max_attempts=1,
    )
    publication.page_id = page.id
    publication.page_name = page.name
    publication.status = "publishing"
    publication.comment_status = "waiting_for_publish" if publication.comment_text.strip() else "not_set"
    publication.remote_stage = "queued"
    publication.publish_started_at = now
    publication.next_poll_at = None
    publication.last_error = None
    publication.updated_at = now
    db.add(job)
    db.flush()
    media_label = "โพสต์ภาพ" if publication.media_type == "image" else "Facebook Reel"
    db.add(JobEvent(job_id=job.id, event_type="queued", message=f"ได้รับคำสั่งให้เผยแพร่ {media_label}", created_at=now))
    db.add(PublicationEvent(publication_id=publication.id, event_type="publish_queued", message=f"ส่ง {media_label} เข้าคิวบนเพจ {page.name}", created_at=now))
    return job


def append_affiliate_link(text: str, affiliate_url: str | None, *, default_label: str = "พิกัดสินค้า") -> str:
    value = text.strip()
    if not affiliate_url or affiliate_url in value:
        return value
    link_line = f"{default_label}: {affiliate_url}"
    return f"{value}\n\n{link_line}" if value else link_line


def append_image_post_link(text: str, affiliate_url: str | None, *, default_label: str) -> str:
    value = text.strip()
    if re.search(r"https?://\S+", value, re.IGNORECASE):
        return value
    return append_affiliate_link(value, affiliate_url, default_label=default_label)


def publication_payload(publication: Publication, db: Session) -> dict:
    project = db.get(Project, publication.project_id)
    render_asset = db.get(Asset, publication.render_asset_id) if publication.render_asset_id else None
    media_assets = [
        asset for asset_id in publication_media_asset_ids(publication)
        if (asset := db.get(Asset, asset_id)) is not None
    ] if publication.media_type == "image" else []
    return {
        "id": publication.id,
        "project_id": publication.project_id,
        "project_title": project.title if project else "โปรเจกต์ที่ถูกลบ",
        "revision_id": publication.revision_id,
        "render_asset": render_asset,
        "media_assets": media_assets,
        "page_id": publication.page_id,
        "platform": publication.platform,
        "media_type": publication.media_type,
        "page_name": publication.page_name,
        "status": publication.status,
        "comment_status": publication.comment_status,
        "caption": publication.caption,
        "comment_text": publication.comment_text,
        "affiliate_url": publication.affiliate_url,
        "scheduled_at": publication.scheduled_at,
        "published_at": publication.published_at,
        "external_post_id": publication.external_post_id,
        "remote_stage": publication.remote_stage,
        "remote_video_id": publication.remote_video_id,
        "last_error": publication.last_error,
        "created_at": publication.created_at,
        "updated_at": publication.updated_at,
        "events": publication.events,
    }


@app.get("/api/publications", response_model=list[PublicationRead])
def list_publications(
    status: str | None = Query(default=None, max_length=32),
    project_id: str | None = Query(default=None, max_length=36),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    allowed_statuses = {"draft", "scheduled", "publishing", "processing", "needs_attention", "cancelled", "published", "failed"}
    if status and status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="ตัวกรองสถานะไม่ถูกต้อง")
    statement = select(Publication).order_by(Publication.created_at.desc()).offset(offset).limit(limit)
    if status:
        statement = statement.where(Publication.status == status)
    if project_id:
        statement = statement.where(Publication.project_id == project_id)
    return [publication_payload(item, db) for item in db.scalars(statement).all()]


@app.get("/api/publications/{publication_id}", response_model=PublicationRead)
def get_publication(publication_id: str, db: Session = Depends(get_db)):
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายการโพสต์นี้")
    return publication_payload(publication, db)


@app.post("/api/revisions/{revision_id}/publications", response_model=PublicationRead, status_code=201)
def create_publication(revision_id: str, payload: PublicationCreate, db: Session = Depends(get_db)):
    revision = db.get(Revision, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="ไม่พบเวอร์ชันตัดต่อนี้")
    render = db.scalar(select(Render).where(
        Render.revision_id == revision.id,
        Render.output_asset_id == payload.render_asset_id,
        Render.state == "succeeded",
    ))
    asset = db.get(Asset, payload.render_asset_id)
    if render is None or asset is None or asset.project_id != revision.project_id or asset.kind != "rendered_video" or asset.state != "ready":
        raise HTTPException(status_code=409, detail="ต้องเลือก MP4 ที่เรนเดอร์เสร็จจากเวอร์ชันนี้ก่อน")
    project = db.get(Project, revision.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="ไม่พบโปรเจกต์ของโพสต์นี้")
    caption = append_affiliate_link(payload.caption, project.affiliate_url)
    comment_text = append_affiliate_link(payload.comment_text, project.affiliate_url, default_label="🛒 ดูสินค้า")
    page = active_facebook_page(db)
    now = datetime.now(timezone.utc)
    publication = Publication(
        id=str(uuid.uuid4()),
        project_id=project.id,
        revision_id=revision.id,
        render_asset_id=asset.id,
        page_id=page.id if page else None,
        page_name=page.name if page else None,
        status="draft",
        comment_status="waiting_for_publish" if comment_text else "not_set",
        caption=caption,
        comment_text=comment_text,
        affiliate_url=project.affiliate_url,
        created_at=now,
        updated_at=now,
    )
    db.add(publication)
    db.flush()
    db.add(PublicationEvent(publication_id=publication.id, event_type="draft_created", message="เตรียมดราฟต์พร้อมวิดีโอ แคปชั่น และลิงก์ Affiliate แล้ว", created_at=now))
    db.commit()
    db.refresh(publication)
    return publication_payload(publication, db)


@app.post("/api/image-posts", response_model=PublicationRead, status_code=201)
async def create_image_publication(
    image_files: list[UploadFile] = File(...),
    caption: str = Form(...),
    comment_text: str = Form(default=""),
    affiliate_url: str = Form(default=""),
    auto_append_link: bool = Form(default=True),
    product_details: str = Form(default=""),
    submission_id: str = Form(default=""),
    db: Session = Depends(get_db),
):
    if not caption.strip():
        raise HTTPException(status_code=422, detail="ใส่แคปชั่นก่อนเตรียมโพสต์ภาพ")
    if not 1 <= len(image_files) <= MAX_POST_IMAGES:
        raise HTTPException(status_code=422, detail=f"เลือกรูปได้ตั้งแต่ 1 ถึง {MAX_POST_IMAGES} รูป")
    try:
        publication_id = str(uuid.UUID(submission_id)) if submission_id else str(uuid.uuid4())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="รหัสคำขอบันทึกโพสต์ไม่ถูกต้อง") from exc
    existing = db.get(Publication, publication_id)
    if existing is not None:
        if existing.media_type != "image":
            raise HTTPException(status_code=409, detail="รหัสคำขอบันทึกถูกใช้กับโพสต์อื่นแล้ว")
        return publication_payload(existing, db)
    try:
        project_input = ProjectCreate(
            title=f"โพสต์ภาพสินค้า {datetime.now(timezone(timedelta(hours=7))).strftime('%d-%m %H:%M')}",
            product_details=product_details.strip()[:24000] or None,
            copy_style="friendly_review",
            affiliate_url=affiliate_url.strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info("Saving image post draft (submission_id=%s, image_count=%s)", publication_id, len(image_files))
    image_payloads = [await _read_image_upload(upload) for upload in image_files]
    if sum(len(payload[0]) for payload in image_payloads) > 36 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="ภาพทั้งหมดรวมกันต้องไม่เกิน 36 MB")

    now = datetime.now(timezone.utc)
    project = Project(**project_input.model_dump())
    linked_caption = append_image_post_link(caption.strip()[:5000], project.affiliate_url, default_label="🛒 พิกัดสินค้า กดดูตรงนี้") if auto_append_link else caption.strip()[:5000]
    linked_comment = append_image_post_link(comment_text.strip()[:2000], project.affiliate_url, default_label="👉 กดสั่ง/ดูรายละเอียด") if auto_append_link else comment_text.strip()[:2000]
    saved_paths: list[Path] = []
    try:
        db.add(project)
        db.flush()

        def save_asset(upload: UploadFile, payload: tuple[bytes, str, str], kind: str, fallback_name: str) -> Asset:
            image_bytes, _mime_type, suffix = payload
            asset_id = str(uuid.uuid4())
            relative_path = f"projects/{project.id}/{asset_id}{suffix}"
            image_path = resolve_media_path(relative_path)
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(image_bytes)
            saved_paths.append(image_path)
            safe_original_name = Path((upload.filename or fallback_name).replace("\\", "/")).name[:255] or fallback_name
            asset = Asset(
                id=asset_id,
                project_id=project.id,
                kind=kind,
                original_name=safe_original_name,
                relative_path=relative_path,
                byte_size=len(image_bytes),
                sha256=hashlib.sha256(image_bytes).hexdigest(),
                state="ready",
                created_at=now,
            )
            db.add(asset)
            return asset

        output_assets = [
            save_asset(upload, image_payload, "post_image", f"product-post-{index + 1}.jpg")
            for index, (upload, image_payload) in enumerate(zip(image_files, image_payloads))
        ]
        preflight_error = photo_set_preflight(output_assets)
        if preflight_error:
            raise HTTPException(status_code=422, detail=preflight_error)
        output_asset = output_assets[0]
        page = active_facebook_page(db)
        publication = Publication(
            id=publication_id,
            project_id=project.id,
            revision_id=None,
            render_asset_id=output_asset.id,
            media_asset_ids_json=json.dumps([asset.id for asset in output_assets]),
            page_id=page.id if page else None,
            page_name=page.name if page else None,
            media_type="image",
            status="draft",
            comment_status="waiting_for_publish" if linked_comment else "not_set",
            caption=linked_caption,
            comment_text=linked_comment,
            affiliate_url=project.affiliate_url,
            created_at=now,
            updated_at=now,
        )
        db.add(publication)
        db.flush()
        db.add(PublicationEvent(
            publication_id=publication.id,
            event_type="draft_created",
            message=f"เตรียมดราฟต์โพสต์ภาพ {len(output_assets)} รูปแล้ว · ใช้ภาพที่แนบมาโดยไม่ปรับแต่ง",
            created_at=now,
        ))
        db.commit()
        db.refresh(publication)
        logger.info("Image post draft saved (submission_id=%s)", publication_id)
        return publication_payload(publication, db)
    except IntegrityError:
        db.rollback()
        for path in saved_paths:
            path.unlink(missing_ok=True)
        existing = db.get(Publication, publication_id)
        if existing is not None and existing.media_type == "image":
            return publication_payload(existing, db)
        raise
    except Exception:
        db.rollback()
        for path in saved_paths:
            path.unlink(missing_ok=True)
        logger.exception("Image post draft save failed (submission_id=%s)", publication_id)
        raise


@app.put("/api/publications/{publication_id}/images/{asset_id}", response_model=PublicationRead)
async def replace_publication_image(
    publication_id: str,
    asset_id: str,
    image_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายการโพสต์นี้")
    if publication.media_type != "image":
        raise HTTPException(status_code=409, detail="รายการนี้ไม่ใช่โพสต์ภาพ")
    if publication.status not in {"draft", "scheduled", "needs_attention"} or publication.remote_stage or publication.remote_video_id:
        raise HTTPException(status_code=409, detail="รายการนี้เริ่มส่งไป Facebook แล้ว จึงแก้ภาพไม่ได้")

    asset_ids = publication_media_asset_ids(publication)
    if asset_id not in asset_ids:
        raise HTTPException(status_code=404, detail="ไม่พบภาพนี้ในโพสต์")
    asset = db.get(Asset, asset_id)
    if asset is None or asset.project_id != publication.project_id or asset.kind != "post_image" or asset.state != "ready":
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ภาพต้นฉบับ")

    image_bytes, _mime_type, suffix = await _read_image_upload(image_file)
    assets = [db.get(Asset, current_id) for current_id in asset_ids]
    if any(item is None for item in assets):
        raise HTTPException(status_code=409, detail="ไฟล์ภาพบางรูปไม่พร้อมแก้ไข")
    safe_name = PurePosixPath((image_file.filename or "ภาพสินค้า").replace("\\", "/")).name.strip() or "ภาพสินค้า"
    candidate = SimpleNamespace(original_name=f"{Path(safe_name).stem[:245]}{suffix}", byte_size=len(image_bytes))
    preflight_error = photo_set_preflight([candidate if item.id == asset.id else item for item in assets])
    if preflight_error:
        raise HTTPException(status_code=422, detail=preflight_error)

    try:
        old_path = resolve_media_path(asset.relative_path)
        project_dir = resolve_media_path(f"projects/{publication.project_id}/.project-scope").parent
        if old_path.parent != project_dir:
            raise HTTPException(status_code=400, detail="ตำแหน่งไฟล์ภาพไม่ปลอดภัย จึงยกเลิกการแก้ไข")
        filename = f"{asset.id}-{uuid.uuid4().hex[:10]}{suffix}"
        relative_path = f"projects/{publication.project_id}/{filename}"
        destination = resolve_media_path(relative_path)
        temp_path = destination.with_name(f".{destination.name}.upload")
    except UnsafeStoragePath as exc:
        raise HTTPException(status_code=400, detail="ตำแหน่งไฟล์ภาพไม่ปลอดภัย จึงยกเลิกการแก้ไข") from exc

    committed = False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(image_bytes)
        os.replace(temp_path, destination)
        asset.relative_path = relative_path
        asset.original_name = candidate.original_name
        asset.byte_size = len(image_bytes)
        asset.sha256 = hashlib.sha256(image_bytes).hexdigest()
        publication.updated_at = datetime.now(timezone.utc)
        image_number = asset_ids.index(asset_id) + 1
        db.add(PublicationEvent(
            publication_id=publication.id,
            event_type="image_replaced",
            message=f"เปลี่ยนภาพโพสต์รูปที่ {image_number}",
            created_at=publication.updated_at,
        ))
        db.commit()
        committed = True
    except Exception:
        db.rollback()
        temp_path.unlink(missing_ok=True)
        if destination.exists():
            destination.unlink(missing_ok=True)
        raise

    if committed and old_path != destination:
        try:
            old_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove replaced image file for asset %s", asset_id)
    db.refresh(publication)
    return publication_payload(publication, db)


@app.patch("/api/publications/{publication_id}", response_model=PublicationRead)
def update_publication(publication_id: str, payload: PublicationPatch, db: Session = Depends(get_db)):
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายการโพสต์นี้")
    if publication.status not in {"draft", "scheduled", "needs_attention"}:
        raise HTTPException(status_code=409, detail="รายการนี้ปิดแก้ไขแล้ว")
    if publication.remote_stage or publication.remote_video_id:
        raise HTTPException(status_code=409, detail="มีคำสั่งส่งไป Facebook แล้ว เพื่อป้องกันโพสต์ซ้ำ รายการนี้แก้หรือจัดคิวใหม่ไม่ได้")
    changes = payload.model_dump(exclude_unset=True)
    now = datetime.now(timezone.utc)
    if "caption" in changes:
        publication.caption = changes["caption"].strip() if publication.media_type == "image" else append_affiliate_link(changes["caption"], publication.affiliate_url)
    if "comment_text" in changes:
        publication.comment_text = changes["comment_text"].strip() if publication.media_type == "image" else append_affiliate_link(changes["comment_text"], publication.affiliate_url, default_label="🛒 ดูสินค้า")
        publication.comment_status = "waiting_for_publish" if publication.comment_text else "not_set"
    if "scheduled_at" in changes:
        scheduled_at = changes["scheduled_at"]
        if scheduled_at is None:
            publication.scheduled_at = None
            publication.status = "draft"
            publication.last_error = None
            db.add(PublicationEvent(publication_id=publication.id, event_type="schedule_removed", message="ยกเลิกเวลาที่ตั้งไว้และเก็บเป็นดราฟต์", created_at=now))
        else:
            if scheduled_at.tzinfo is None:
                raise HTTPException(status_code=422, detail="เวลาโพสต์ต้องระบุเขตเวลา")
            scheduled_at = scheduled_at.astimezone(timezone.utc)
            if scheduled_at <= now:
                raise HTTPException(status_code=422, detail="ตั้งเวลาโพสต์ล่วงหน้าจากเวลาปัจจุบัน")
            publication.scheduled_at = scheduled_at
            publication.status = "scheduled"
            page = active_facebook_page(db)
            if page:
                publication.page_id = page.id
                publication.page_name = page.name
            publication.last_error = None
            message = f"ตั้งเวลาไว้ {scheduled_at.astimezone().strftime('%d/%m/%Y %H:%M %Z')} · รอเชื่อม Facebook Page ก่อนเผยแพร่จริง"
            db.add(PublicationEvent(publication_id=publication.id, event_type="scheduled", message=message, created_at=now))
    publication.updated_at = now
    db.commit()
    db.refresh(publication)
    return publication_payload(publication, db)


@app.post("/api/publications/{publication_id}/cancel", response_model=PublicationRead)
def cancel_publication(publication_id: str, db: Session = Depends(get_db)):
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายการโพสต์นี้")
    if publication.status not in {"draft", "scheduled", "needs_attention"}:
        raise HTTPException(status_code=409, detail="รายการนี้ยกเลิกไม่ได้")
    if publication.remote_stage or publication.remote_video_id:
        raise HTTPException(status_code=409, detail="มีคำสั่งส่งไป Facebook แล้ว กรุณาตรวจสถานะเพจก่อน")
    now = datetime.now(timezone.utc)
    publication.status = "cancelled"
    publication.updated_at = now
    db.add(PublicationEvent(publication_id=publication.id, event_type="cancelled", message="ยกเลิกรายการโพสต์แล้ว", created_at=now))
    db.commit()
    db.refresh(publication)
    return publication_payload(publication, db)


@app.post("/api/publications/{publication_id}/publish-now", response_model=PublicationRead, status_code=202)
def publish_publication_now(publication_id: str, db: Session = Depends(get_db)):
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายการโพสต์นี้")
    if publication.status not in {"draft", "scheduled", "needs_attention"} or publication.remote_stage or publication.remote_video_id:
        raise HTTPException(status_code=409, detail="รายการนี้เริ่มเผยแพร่แล้วหรือไม่พร้อมส่ง")
    page = active_facebook_page(db)
    try:
        page_token_present = bool(page and load_facebook_page_token(page.id))
    except SecretStoreError:
        page_token_present = False
    if page is None or not page_token_present:
        raise HTTPException(status_code=409, detail="เชื่อมและเลือก Facebook Page ในหน้าตั้งค่าก่อน")
    if publication.media_type == "image":
        assets = [db.get(Asset, asset_id) for asset_id in publication_media_asset_ids(publication)]
        if not assets or any(asset is None or asset.state != "ready" or asset.kind != "post_image" for asset in assets):
            raise HTTPException(status_code=409, detail="ไฟล์ภาพโพสต์บางรูปไม่พร้อมใช้งานแล้ว")
        preflight_error = photo_set_preflight(assets)
    else:
        asset = db.get(Asset, publication.render_asset_id) if publication.render_asset_id else None
        if asset is None or asset.state != "ready":
            raise HTTPException(status_code=409, detail="ไฟล์ภาพหรือวิดีโอของโพสต์ไม่พร้อมใช้งานแล้ว")
        preflight_error = reels_preflight(asset)
    if preflight_error:
        raise HTTPException(status_code=422, detail=preflight_error)
    publication.scheduled_at = None
    queue_facebook_publish(publication, page, db, datetime.now(timezone.utc))
    db.commit()
    db.refresh(publication)
    return publication_payload(publication, db)


@app.post("/api/publications/{publication_id}/retry-comment", response_model=PublicationRead, status_code=202)
def retry_publication_comment(publication_id: str, db: Session = Depends(get_db)):
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายการโพสต์นี้")
    if publication.status != "published" or publication.comment_status != "failed" or not publication.remote_video_id or not publication.comment_text.strip():
        raise HTTPException(status_code=409, detail="คอมเมนต์นี้ยังลองใหม่ไม่ได้ ตรวจสถานะโพสต์และคอมเมนต์ก่อน")
    try:
        page_token_present = bool(publication.page_id and load_facebook_page_token(publication.page_id))
    except SecretStoreError:
        page_token_present = False
    if not page_token_present:
        raise HTTPException(status_code=409, detail="เชื่อม Facebook Page อีกครั้งก่อนลองคอมเมนต์")
    job = Job(
        id=str(uuid.uuid4()), project_id=publication.project_id, asset_id=publication.render_asset_id,
        revision_id=publication.revision_id, job_type="facebook_post_comment",
        payload_json=json.dumps({"publication_id": publication.id}, ensure_ascii=False), state="queued", progress=0, max_attempts=1,
    )
    now = datetime.now(timezone.utc)
    publication.comment_status = "queued"
    publication.last_error = None
    publication.updated_at = now
    db.add(job)
    db.flush()
    db.add(JobEvent(job_id=job.id, event_type="queued", message="ผู้ใช้สั่งลองส่งคอมเมนต์อีกครั้งหลัง Meta ปฏิเสธคำขอก่อนหน้า", created_at=now))
    db.add(PublicationEvent(publication_id=publication.id, event_type="comment_retry_queued", message="ส่งคอมเมนต์เข้าคิวอีกครั้งตามคำสั่งผู้ใช้", created_at=now))
    db.commit()
    db.refresh(publication)
    return publication_payload(publication, db)


@app.post("/api/revisions/{revision_id}/ocr", response_model=JobRead, status_code=202)
def queue_ocr(revision_id: str, db: Session = Depends(get_db)):
    revision = db.scalar(select(Revision).options(selectinload(Revision.source_asset)).where(Revision.id == revision_id))
    if revision is None:
        raise HTTPException(status_code=404, detail="ไม่พบเวอร์ชันตัดต่อนี้")
    if revision.source_asset is None or revision.source_asset.state != "ready":
        raise HTTPException(status_code=409, detail="วิดีโอต้นฉบับยังไม่พร้อมอ่านซับ")
    if db.scalar(select(SubtitleSegment.id).where(SubtitleSegment.revision_id == revision_id).limit(1)):
        raise HTTPException(status_code=409, detail="เวอร์ชันนี้มีซับอยู่แล้ว บันทึกเวอร์ชันใหม่หรือส่งออกก่อนเริ่มอ่านใหม่")
    if not load_gemini_key():
        raise HTTPException(status_code=409, detail="บันทึก Gemini API key ในหน้าตั้งค่าก่อนอ่านซับ")
    revision.state = "ocr_queued"
    job = enqueue_ai_job(revision, "ocr_subtitles", "ส่งวิดีโอไปอ่านซับด้วย Gemini", db, {"source_asset_id": revision.source_asset_id})
    return job


@app.post("/api/revisions/{revision_id}/translate", response_model=JobRead, status_code=202)
def queue_translation(revision_id: str, db: Session = Depends(get_db)):
    revision = db.scalar(select(Revision).options(selectinload(Revision.subtitles)).where(Revision.id == revision_id))
    if revision is None:
        raise HTTPException(status_code=404, detail="ไม่พบเวอร์ชันตัดต่อนี้")
    if not revision.subtitles:
        raise HTTPException(status_code=409, detail="นำเข้า SRT หรืออ่านซับในวิดีโอก่อนแปล")
    if not load_gemini_key():
        raise HTTPException(status_code=409, detail="บันทึก Gemini API key ในหน้าตั้งค่าก่อนแปล")
    ids = [item.stable_id for item in revision.subtitles if item.source_text.strip()]
    if not ids:
        raise HTTPException(status_code=409, detail="ไม่พบข้อความต้นฉบับให้แปล")
    job = enqueue_ai_job(revision, "translate_subtitles", "ส่งข้อความซับไปแปลเป็นภาษาไทย", db, {"stable_ids": ids})
    return job


@app.get("/api/revisions/{revision_id}/copy", response_model=GeneratedCopyRead)
def read_generated_copy(revision_id: str, db: Session = Depends(get_db)):
    revision = get_revision_or_404(revision_id, db)
    item = db.scalar(select(GeneratedCopy).where(GeneratedCopy.revision_id == revision.id))
    if item is None:
        return GeneratedCopyRead(script_text="", caption_candidates=[], selected_caption="", comment_text="", review_score=None, review_summary="", model_name=None, updated_at=None)
    try:
        captions = json.loads(item.caption_candidates_json or "[]")
    except json.JSONDecodeError:
        captions = []
    return GeneratedCopyRead(script_text=item.script_text, caption_candidates=captions, selected_caption=item.selected_caption, comment_text=item.comment_text, review_score=item.review_score, review_summary=item.review_summary or "", model_name=item.model_name, updated_at=item.updated_at)


@app.put("/api/revisions/{revision_id}/copy", response_model=GeneratedCopyRead)
def save_generated_copy(revision_id: str, payload: GeneratedCopyWrite, db: Session = Depends(get_db)):
    revision = get_revision_or_404(revision_id, db)
    item = db.scalar(select(GeneratedCopy).where(GeneratedCopy.revision_id == revision.id))
    previous_script = item.script_text if item else ""
    if item is None:
        item = GeneratedCopy(revision_id=revision.id)
        db.add(item)
    item.script_text = payload.script_text
    item.caption_candidates_json = json.dumps(payload.caption_candidates, ensure_ascii=False)
    item.selected_caption = payload.selected_caption
    item.comment_text = payload.comment_text
    item.review_score = payload.review_score
    item.review_summary = payload.review_summary
    if previous_script != payload.script_text:
        revision_settings = json.loads(revision.settings_json or "{}")
        revision_settings.pop("voiceover_asset_id", None)
        revision.settings_json = json.dumps(revision_settings, ensure_ascii=False)
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    return read_generated_copy(revision_id, db)


@app.post("/api/revisions/{revision_id}/generate-copy", response_model=JobRead, status_code=202)
def queue_copy_generation(revision_id: str, db: Session = Depends(get_db)):
    revision = db.scalar(select(Revision).options(selectinload(Revision.project)).where(Revision.id == revision_id))
    if revision is None:
        raise HTTPException(status_code=404, detail="ไม่พบเวอร์ชันตัดต่อนี้")
    if not load_gemini_key():
        raise HTTPException(status_code=409, detail="บันทึก Gemini API key ในหน้าตั้งค่าก่อนเขียนข้อความ")
    job = enqueue_ai_job(revision, "generate_copy", "ส่งข้อมูลสินค้าไปเขียนข้อความ", db, {"part": "script"})
    return job


@app.post("/api/revisions/{revision_id}/generate-copy-part", response_model=JobRead, status_code=202)
def queue_copy_part(revision_id: str, payload: GeneratedCopyPartWrite, db: Session = Depends(get_db)):
    revision = db.scalar(select(Revision).options(selectinload(Revision.project)).where(Revision.id == revision_id))
    if revision is None:
        raise HTTPException(status_code=404, detail="ไม่พบเวอร์ชันตัดต่อนี้")
    if not load_gemini_key():
        raise HTTPException(status_code=409, detail="บันทึก Gemini API key ในหน้าตั้งค่าก่อนเขียนข้อความ")
    label = "บทพากย์" if payload.part == "script" else "แคปชั่นและคอมเมนต์"
    return enqueue_ai_job(revision, f"generate_{payload.part}", f"ส่งข้อมูลสินค้าไปเขียน{label}", db, {"part": payload.part})


@app.post("/api/revisions/{revision_id}/generate-voiceover", response_model=JobRead, status_code=202)
def queue_voiceover(revision_id: str, payload: VoiceoverRequest, db: Session = Depends(get_db)):
    revision = get_revision_or_404(revision_id, db)
    if not load_gemini_key():
        raise HTTPException(status_code=409, detail="บันทึก Gemini API key ในหน้าตั้งค่าก่อนสร้างเสียงพากย์")
    copy = db.scalar(select(GeneratedCopy).where(GeneratedCopy.revision_id == revision.id))
    script = copy.script_text.strip() if copy else ""
    if not script:
        raise HTTPException(status_code=409, detail="สร้างหรือเขียนบทพากย์ก่อนทำเสียงพากย์")
    asset_id = str(uuid.uuid4())
    relative_path = f"projects/{revision.project_id}/{asset_id}.wav"
    asset = Asset(id=asset_id, project_id=revision.project_id, kind="voiceover_audio", original_name="เสียงพากย์ไทย.wav", relative_path=relative_path, byte_size=0, sha256="", state="processing", has_audio=True, container_format="wav")
    job = Job(id=str(uuid.uuid4()), project_id=revision.project_id, revision_id=revision.id, asset_id=asset.id, job_type="generate_voiceover", payload_json=json.dumps({"voice": payload.voice}, ensure_ascii=False), state="queued")
    settings_value = json.loads(revision.settings_json or "{}")
    settings_value["voiceover_asset_id"] = asset_id
    settings_value.setdefault("voiceover_volume", 1.0)
    revision.settings_json = json.dumps(settings_value, ensure_ascii=False)
    revision.state = "draft"
    db.add_all([asset, job])
    db.add(JobEvent(job_id=job.id, event_type="queued", message="ส่งบทพากย์ไปสร้างเสียงไทยด้วย Gemini TTS", created_at=datetime.now(timezone.utc)))
    db.commit(); db.refresh(job)
    return job


@app.post("/api/revisions/{revision_id}/render", status_code=202)
def queue_render(revision_id: str, db: Session = Depends(get_db)):
    revision = db.scalar(
        select(Revision).options(selectinload(Revision.source_asset), selectinload(Revision.subtitles), selectinload(Revision.overlays))
        .where(Revision.id == revision_id)
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="ไม่พบเวอร์ชันตัดต่อนี้")
    if revision.source_asset is None or revision.source_asset.state != "ready":
        raise HTTPException(status_code=409, detail="วิดีโอต้นฉบับยังไม่พร้อมเรนเดอร์")
    if any(item.end_ms > (revision.source_asset.duration_ms or item.end_ms) for item in revision.subtitles):
        raise HTTPException(status_code=422, detail="มีช่วงซับยาวเกินวิดีโอต้นฉบับ")
    settings_value = json.loads(revision.settings_json or "{}")
    music = None
    if settings_value.get("audio_mode") == "music":
        if settings_value.get("music_library_id"):
            music = db.get(MusicTrack, settings_value["music_library_id"])
            if music is None:
                raise HTTPException(status_code=422, detail="ไม่พบเพลงที่เลือกในคลังเพลงก่อนเรนเดอร์")
        else:
            music = db.get(Asset, settings_value.get("music_asset_id")) if settings_value.get("music_asset_id") else None
            if music is None or music.project_id != revision.project_id or music.kind != "music_track" or music.state != "ready":
                raise HTTPException(status_code=422, detail="เลือกไฟล์เพลงที่พร้อมใช้งานก่อนเรนเดอร์")
    voiceover = db.get(Asset, settings_value.get("voiceover_asset_id")) if settings_value.get("voiceover_asset_id") else None
    if settings_value.get("voiceover_asset_id") and (voiceover is None or voiceover.project_id != revision.project_id or voiceover.kind != "voiceover_audio" or voiceover.state != "ready"):
        raise HTTPException(status_code=422, detail="เสียงพากย์ไทยยังไม่พร้อม กรุณาสร้างเสียงให้เสร็จก่อนเรนเดอร์")
    pending = db.scalar(select(Render).where(Render.revision_id == revision_id, Render.state.in_(["queued", "running"])))
    if pending:
        raise HTTPException(status_code=409, detail="เวอร์ชันนี้กำลังเรนเดอร์อยู่แล้ว")
    render_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    output_path = f"projects/{revision.project_id}/{asset_id}.mp4"
    fingerprint = {
        "source": revision.source_asset.sha256,
        "settings": settings_value,
        "subtitles": [
            {"start_ms": item.start_ms, "end_ms": item.end_ms, "source_text": item.source_text, "translated_text": item.translated_text}
            for item in revision.subtitles
        ],
        "overlays": [
            {"x": item.x, "y": item.y, "width": item.width, "height": item.height, "start_ms": item.start_ms, "end_ms": item.end_ms, "color": item.color, "opacity": item.opacity}
            for item in revision.overlays
        ],
    }
    asset = Asset(
        id=asset_id,
        project_id=revision.project_id,
        kind="rendered_video",
        original_name=f"{revision.project.title[:175]}-v{revision.version}.mp4",
        relative_path=output_path,
        byte_size=0,
        sha256="",
        state="processing",
    )
    render = Render(
        id=render_id,
        revision_id=revision_id,
        output_asset_id=asset_id,
        settings_hash=hashlib.sha256(json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        state="queued",
    )
    job = Job(
        id=job_id,
        project_id=revision.project_id,
        asset_id=asset_id,
        revision_id=revision_id,
        job_type="render_video",
        payload_json=json.dumps({"render_id": render_id, "output_asset_id": asset_id}, ensure_ascii=False),
        state="queued",
        progress=0,
    )
    revision.state = "render_queued"
    db.add_all([asset, render, job])
    db.add(JobEvent(job_id=job_id, event_type="queued", message="รับงานเรนเดอร์แล้ว รอประมวลผล", created_at=datetime.now(timezone.utc)))
    db.commit()
    return {"render_id": render_id, "asset": asset, "job": job}


if FRONTEND_DIST.joinpath("index.html").is_file():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
