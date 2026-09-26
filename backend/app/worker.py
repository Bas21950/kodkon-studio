from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
import io
import wave
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import Asset, FacebookPage, GeneratedCopy, Job, JobEvent, MusicTrack, Project, Publication, PublicationEvent, Render, Revision
from app.services.ai_jobs import complete_copy_generation, complete_ocr, complete_translation
from app.services.gemini import GeminiError, generate_speech
from app.services.secret_store import load_gemini_key
from app.services.facebook import FacebookApiError, finish_reel, get_reel_status, photo_set_preflight, post_comment, publish_photos, reels_preflight, start_reel, upload_reel
from app.services.publication_media import publication_media_asset_ids
from app.services.probing import MediaProbeError, probe_audio, probe_video
from app.services.rendering import RenderError, render_video
from app.storage import UnsafeStoragePath, resolve_media_path
from app.services.secret_store import SecretStoreError, load_facebook_page_token

logger = logging.getLogger("kodkon.worker")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def recover_interrupted_jobs() -> None:
    """Recover jobs left running after the single local server exited."""
    with SessionLocal.begin() as session:
        interrupted = session.scalars(select(Job).where(Job.state == "running")).all()
        for job in interrupted:
            if job.job_type in {"facebook_publish_reel", "facebook_publish_photo", "facebook_check_reel", "facebook_post_comment"}:
                try:
                    publication_id = json.loads(job.payload_json or "{}").get("publication_id")
                except json.JSONDecodeError:
                    publication_id = None
                publication = session.get(Publication, publication_id) if publication_id else None
                safely_repeatable = job.job_type == "facebook_check_reel" or (job.job_type in {"facebook_publish_reel", "facebook_publish_photo"} and publication and publication.remote_stage == "queued")
                if safely_repeatable:
                    job.state = "queued"
                    job.error_code = None
                    job.error_message = None
                    if publication and job.job_type == "facebook_check_reel":
                        publication.next_poll_at = now_utc() + timedelta(seconds=30)
                    session.add(JobEvent(job_id=job.id, event_type="recovered", message="งานตรวจสถานะ Facebook ที่ปลอดภัยถูกนำกลับเข้าคิว", created_at=now_utc()))
                    continue
                if publication:
                    publication.last_error = "โปรแกรมหยุดระหว่างส่งคำขอ Facebook ผลลัพธ์ยังไม่ชัดเจน ตรวจเพจก่อนดำเนินการต่อเพื่อป้องกันโพสต์ซ้ำ"
                    publication.updated_at = now_utc()
                    if job.job_type == "facebook_post_comment":
                        publication.comment_status = "needs_attention"
                    else:
                        publication.status = "needs_attention"
                    session.add(PublicationEvent(publication_id=publication.id, event_type="recovery_ambiguous", message=publication.last_error, created_at=now_utc()))
                job.state = "failed"
                job.error_code = "external_result_uncertain"
                job.error_message = "ผลลัพธ์จาก Facebook ยังไม่ชัดเจน จึงหยุดอัตโนมัติเพื่อป้องกันการส่งซ้ำ"
                job.finished_at = now_utc()
                session.add(JobEvent(job_id=job.id, event_type="attention_required", message=job.error_message, created_at=now_utc()))
                continue
            job.state = "queued"
            job.error_code = None
            job.error_message = None
            session.add(JobEvent(job_id=job.id, event_type="recovered", message="งานที่ค้างจากการปิดโปรแกรมถูกนำกลับเข้าคิว", created_at=now_utc()))


def process_due_publications() -> None:
    """Start due publication, status-check, and comment jobs without duplicate enqueue."""
    now = now_utc()
    with SessionLocal.begin() as session:
        active_page = session.scalar(select(FacebookPage).where(FacebookPage.is_active.is_(True)).limit(1))
        due = session.scalars(
            select(Publication)
            .where(Publication.status == "scheduled", Publication.scheduled_at <= now)
            .order_by(Publication.scheduled_at.asc())
        ).all()
        for publication in due:
            scheduled = publication.scheduled_at
            if scheduled and scheduled.tzinfo is None:
                scheduled = scheduled.replace(tzinfo=timezone.utc)
            if scheduled and now - scheduled > timedelta(minutes=10):
                _block_publication(session, publication, "เลยเวลาที่ตั้งไว้นานเกิน 10 นาทีแล้ว · เลือกเวลาใหม่หรือกดเผยแพร่เอง", "missed_schedule", now)
                continue
            if active_page is None or not _facebook_token_present(active_page.id):
                _block_publication(session, publication, "ถึงเวลาแล้ว แต่ยังไม่ได้เชื่อม Facebook Page จึงยังไม่ได้เผยแพร่", "schedule_blocked", now)
                continue
            if publication.page_id and publication.page_id != active_page.id:
                _block_publication(session, publication, "เพจที่บันทึกในรายการไม่ตรงกับเพจที่เลือกอยู่ · ตรวจเพจแล้วจัดเวลาใหม่", "page_mismatch", now)
                continue
            image_post = publication.media_type == "image"
            if image_post:
                assets = [session.get(Asset, asset_id) for asset_id in publication_media_asset_ids(publication)]
                if not assets or any(asset is None or asset.state != "ready" or asset.kind != "post_image" for asset in assets):
                    _block_publication(session, publication, "ไม่พบภาพโพสต์บางรูปหรือไฟล์ยังไม่พร้อม", "asset_missing", now)
                    continue
                preflight_error = photo_set_preflight(assets)
            else:
                asset = session.get(Asset, publication.render_asset_id) if publication.render_asset_id else None
                if asset is None or asset.state != "ready":
                    _block_publication(session, publication, "ไม่พบ MP4 ที่เรนเดอร์เสร็จสำหรับรายการนี้", "asset_missing", now)
                    continue
                preflight_error = reels_preflight(asset)
            if preflight_error:
                _block_publication(session, publication, preflight_error, "photo_preflight_failed" if image_post else "reel_preflight_failed", now)
                continue
            job_type = "facebook_publish_photo" if image_post else "facebook_publish_reel"
            _queue_facebook_job(session, publication, job_type, {"publication_id": publication.id}, now, active_page)

        processing = session.scalars(select(Publication).where(
            Publication.status == "processing",
            Publication.next_poll_at.is_not(None),
            Publication.next_poll_at <= now,
        )).all()
        for publication in processing:
            if publication.publish_started_at and now - _aware_utc(publication.publish_started_at) > timedelta(minutes=20):
                _block_publication(session, publication, "Facebook ใช้เวลาประมวลผลนานเกิน 20 นาที · ตรวจสถานะโพสต์บนเพจก่อน", "processing_timeout", now)
                continue
            if not _facebook_token_present(publication.page_id):
                _block_publication(session, publication, "Page token หายหรือหมดอายุระหว่างรอประมวลผล · เชื่อมเพจใหม่แล้วตรวจสถานะบน Facebook", "page_token_missing", now)
                continue
            if not _has_pending_job(session, publication.id, "facebook_check_reel"):
                _queue_facebook_job(session, publication, "facebook_check_reel", {"publication_id": publication.id}, now)
                publication.next_poll_at = now + timedelta(seconds=45)

        awaiting_comment = session.scalars(select(Publication).where(
            Publication.status == "published",
            Publication.comment_status == "waiting_for_publish",
            Publication.comment_text != "",
        )).all()
        for publication in awaiting_comment:
            if not _facebook_token_present(publication.page_id):
                publication.comment_status = "needs_attention"
                publication.last_error = "โพสต์แล้ว แต่ Page token ไม่พร้อมสำหรับคอมเมนต์"
                continue
            if not _has_pending_job(session, publication.id, "facebook_post_comment"):
                publication.comment_status = "queued"
                _queue_facebook_job(session, publication, "facebook_post_comment", {"publication_id": publication.id}, now)


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _facebook_token_present(page_id: str | None) -> bool:
    if not page_id:
        return False
    try:
        return bool(load_facebook_page_token(page_id))
    except SecretStoreError:
        return False


def _has_pending_job(session, publication_id: str, job_type: str) -> bool:
    for job in session.scalars(select(Job).where(Job.job_type == job_type, Job.state.in_(["queued", "running"]))):
        try:
            if json.loads(job.payload_json or "{}").get("publication_id") == publication_id:
                return True
        except json.JSONDecodeError:
            continue
    return False


def _queue_facebook_job(session, publication: Publication, job_type: str, payload: dict, now: datetime, page: FacebookPage | None = None) -> Job:
    job = Job(
        id=str(uuid.uuid4()), project_id=publication.project_id, asset_id=publication.render_asset_id,
        revision_id=publication.revision_id, job_type=job_type,
        payload_json=json.dumps(payload, ensure_ascii=False), state="queued", progress=0, max_attempts=1,
    )
    if job_type in {"facebook_publish_reel", "facebook_publish_photo"}:
        if page:
            publication.page_id = page.id
            publication.page_name = page.name
        publication.status = "publishing"
        publication.remote_stage = "queued"
        publication.publish_started_at = now
        publication.next_poll_at = None
        publication.comment_status = "waiting_for_publish" if publication.comment_text.strip() else "not_set"
        publication.last_error = None
        label = "โพสต์ภาพ" if job_type == "facebook_publish_photo" else "Facebook Reel"
        event_type, message = "publish_queued", f"ส่งรายการเข้า worker เพื่อเผยแพร่ {label}"
    elif job_type == "facebook_check_reel":
        event_type, message = "status_check_queued", "กำลังตรวจสถานะประมวลผลวิดีโอบน Facebook"
    else:
        publication.comment_status = "queued"
        event_type, message = "comment_queued", "คิวคอมเมนต์ Affiliate หลังยืนยันว่าโพสต์สำเร็จ"
    publication.updated_at = now
    session.add(job)
    session.flush()
    session.add(JobEvent(job_id=job.id, event_type="queued", message=message, created_at=now))
    session.add(PublicationEvent(publication_id=publication.id, event_type=event_type, message=message, created_at=now))
    return job


def _block_publication(session, publication: Publication, message: str, event_type: str, now: datetime) -> None:
    publication.status = "needs_attention"
    publication.last_error = message[:500]
    publication.updated_at = now
    publication.next_poll_at = None
    if publication.comment_text.strip() and publication.status != "published":
        publication.comment_status = "needs_attention"
    session.add(PublicationEvent(publication_id=publication.id, event_type=event_type, message=message, created_at=now))


def claim_next_job() -> dict | None:
    with SessionLocal() as session:
        job = session.scalar(select(Job).where(Job.state == "queued").order_by(Job.created_at.asc()).limit(1))
        if job is None:
            return None
        result = session.execute(
            update(Job)
            .where(Job.id == job.id, Job.state == "queued")
            .values(state="running", progress=5, started_at=now_utc(), attempts=Job.attempts + 1)
        )
        if result.rowcount != 1:
            session.rollback()
            return None
        messages = {
            "probe_asset": "เริ่มอ่านรายละเอียดไฟล์",
            "render_video": "เริ่มเรนเดอร์วิดีโอ",
            "facebook_publish_reel": "เริ่มส่ง Reel ไป Facebook",
            "facebook_publish_photo": "เริ่มส่งภาพไป Facebook",
            "facebook_check_reel": "เริ่มตรวจสถานะ Reel บน Facebook",
            "facebook_post_comment": "เริ่มส่งคอมเมนต์ไป Facebook",
        }
        message = messages.get(job.job_type, "เริ่มงาน")
        session.add(JobEvent(job_id=job.id, event_type="started", message=message, created_at=now_utc()))
        data = {
            "id": job.id,
            "asset_id": job.asset_id,
            "revision_id": job.revision_id,
            "payload_json": job.payload_json,
            "job_type": job.job_type,
        }
        session.commit()
        return data


def _fail_probe(job_id: str, asset_id: str, message: str, code: str) -> None:
    with SessionLocal.begin() as session:
        asset = session.get(Asset, asset_id)
        job = session.get(Job, job_id)
        if asset:
            asset.state = "failed"
            asset.error_message = message[:500]
        if job:
            job.state = "failed"
            job.error_code = code
            job.error_message = message[:500]
            job.finished_at = now_utc()
            session.add(JobEvent(job_id=job_id, event_type="failed", message=message[:500], created_at=now_utc()))


def complete_probe(job_data: dict) -> None:
    job_id = job_data["id"]
    asset_id = job_data["asset_id"]
    try:
        with SessionLocal() as session:
            asset = session.get(Asset, asset_id)
            if asset is None:
                raise MediaProbeError("asset_missing", "ไม่พบไฟล์ของงานนี้")
            media_path = resolve_media_path(asset.relative_path)
            if not media_path.is_file():
                raise MediaProbeError("asset_file_missing", "ไม่พบไฟล์ในโฟลเดอร์ข้อมูลของโปรแกรม")
            metadata = probe_audio(media_path) if asset.kind == "music_track" else probe_video(media_path)

        with SessionLocal.begin() as session:
            asset = session.get(Asset, asset_id)
            job = session.get(Job, job_id)
            if asset is None or job is None:
                return
            asset.state = "ready"
            asset.duration_ms = metadata["duration_ms"]
            asset.width = metadata["width"]
            asset.height = metadata["height"]
            asset.has_audio = metadata["has_audio"]
            asset.frame_rate = metadata.get("frame_rate")
            asset.video_codec = metadata["video_codec"]
            asset.container_format = metadata["container_format"]
            asset.error_message = None
            job.state = "succeeded"
            job.progress = 100
            job.finished_at = now_utc()
            job.error_code = None
            job.error_message = None
            session.add(JobEvent(job_id=job_id, event_type="completed", message="อ่านรายละเอียดไฟล์เรียบร้อย", created_at=now_utc()))
    except (MediaProbeError, UnsafeStoragePath) as exc:
        message = exc.user_message if isinstance(exc, MediaProbeError) else str(exc)
        code = exc.code if isinstance(exc, MediaProbeError) else "unsafe_path"
        _fail_probe(job_id, asset_id, message, code)
    except Exception:
        logger.exception("Unexpected error while processing probe job %s", job_id)
        _fail_probe(job_id, asset_id, "อ่านรายละเอียดไฟล์ไม่สำเร็จ เกิดข้อผิดพลาดภายในโปรแกรม", "internal_error")


def complete_voiceover(job_data: dict) -> None:
    asset_id = job_data.get("asset_id")
    try:
        payload = json.loads(job_data.get("payload_json") or "{}")
        with SessionLocal() as session:
            asset = session.get(Asset, asset_id)
            revision = session.get(Revision, job_data.get("revision_id"))
            copy = session.scalar(select(GeneratedCopy).where(GeneratedCopy.revision_id == job_data.get("revision_id")))
            if asset is None or revision is None or copy is None or not copy.script_text.strip():
                raise RuntimeError("ไม่พบบทพากย์หรือไฟล์ปลายทาง")
            output_path = resolve_media_path(asset.relative_path)
            script = copy.script_text.strip()
        key = load_gemini_key()
        if not key:
            raise GeminiError("missing_api_key", "ยังไม่ได้บันทึก Gemini API key ในหน้าตั้งค่า")
        wav_bytes = generate_speech(key, script, payload.get("voice", "Kore"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(wav_bytes)
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
            duration_ms = round(wav.getnframes() * 1000 / wav.getframerate())
        with SessionLocal.begin() as session:
            asset = session.get(Asset, asset_id)
            job = session.get(Job, job_data["id"])
            if asset is None or job is None:
                return
            asset.state = "ready"; asset.byte_size = len(wav_bytes); asset.sha256 = hashlib.sha256(wav_bytes).hexdigest()
            asset.duration_ms = duration_ms; asset.has_audio = True; asset.container_format = "wav"; asset.error_message = None
            job.state = "succeeded"; job.progress = 100; job.finished_at = now_utc(); job.error_code = None; job.error_message = None
            session.add(JobEvent(job_id=job.id, event_type="completed", message=f"สร้างเสียงพากย์ไทยแล้ว ({duration_ms // 1000} วินาที)", created_at=now_utc()))
    except GeminiError as exc:
        _fail_voiceover(job_data, exc.user_message, exc.code)
    except Exception as exc:
        logger.exception("Unexpected error while generating voiceover job %s", job_data.get("id"))
        _fail_voiceover(job_data, str(exc) or "สร้างเสียงพากย์ไม่สำเร็จ", "voiceover_failed")


def _fail_voiceover(job_data: dict, message: str, code: str) -> None:
    with SessionLocal.begin() as session:
        asset = session.get(Asset, job_data.get("asset_id"))
        job = session.get(Job, job_data.get("id"))
        if asset:
            asset.state = "failed"; asset.error_message = message[:500]
        if job:
            job.state = "failed"; job.error_code = code; job.error_message = message[:500]; job.finished_at = now_utc()
            session.add(JobEvent(job_id=job.id, event_type="failed", message=message[:500], created_at=now_utc()))


def _fail_render(job_data: dict, payload: dict, message: str, code: str) -> None:
    with SessionLocal.begin() as session:
        job = session.get(Job, job_data["id"])
        asset = session.get(Asset, payload.get("output_asset_id"))
        render = session.get(Render, payload.get("render_id"))
        revision = session.get(Revision, job_data.get("revision_id"))
        if asset:
            asset.state = "failed"
            asset.error_message = message[:500]
        if job:
            job.state = "failed"
            job.error_code = code
            job.error_message = message[:500]
            job.finished_at = now_utc()
            session.add(JobEvent(job_id=job.id, event_type="failed", message=message[:500], created_at=now_utc()))
        if render:
            render.state = "failed"
            render.error_message = message[:500]
            render.finished_at = now_utc()
        if revision:
            revision.state = "render_failed"


def complete_render(job_data: dict) -> None:
    payload = json.loads(job_data.get("payload_json") or "{}")
    try:
        with SessionLocal() as session:
            revision = session.scalar(
                select(Revision)
                .options(
                    selectinload(Revision.source_asset),
                    selectinload(Revision.subtitles),
                    selectinload(Revision.overlays),
                )
                .where(Revision.id == job_data["revision_id"])
            )
            output_asset = session.get(Asset, payload.get("output_asset_id"))
            if revision is None or output_asset is None or revision.source_asset is None:
                raise RenderError("ข้อมูลของงานเรนเดอร์ไม่ครบ")
            source = revision.source_asset
            if source.state != "ready":
                raise RenderError("วิดีโอต้นฉบับไม่พร้อมใช้งานแล้ว")
            source_path = resolve_media_path(source.relative_path)
            if not source_path.is_file():
                raise RenderError("ไม่พบไฟล์วิดีโอต้นฉบับในโฟลเดอร์ข้อมูล")
            settings_value = json.loads(revision.settings_json or "{}")
            music_path = None
            if settings_value.get("audio_mode") == "music":
                if settings_value.get("music_library_id"):
                    music = session.get(MusicTrack, settings_value["music_library_id"])
                    if music is None:
                        raise RenderError("ไม่พบไฟล์เพลงในคลังเพลงแล้ว")
                else:
                    music = session.get(Asset, settings_value.get("music_asset_id"))
                    if music is None or music.project_id != revision.project_id or music.kind != "music_track" or music.state != "ready":
                        raise RenderError("ไฟล์เพลงไม่พร้อมใช้งานแล้ว")
                music_path = resolve_media_path(music.relative_path)
                if not music_path.is_file():
                    raise RenderError("ไม่พบไฟล์เพลงในโฟลเดอร์ข้อมูล")
            voiceover_path = None
            voiceover_id = settings_value.get("voiceover_asset_id")
            if voiceover_id:
                voiceover = session.get(Asset, voiceover_id)
                if voiceover is None or voiceover.project_id != revision.project_id or voiceover.kind != "voiceover_audio" or voiceover.state != "ready":
                    raise RenderError("เสียงพากย์ไทยยังไม่พร้อม กรุณาสร้างเสียงใหม่")
                voiceover_path = resolve_media_path(voiceover.relative_path)
                if not voiceover_path.is_file():
                    raise RenderError("ไม่พบไฟล์เสียงพากย์ไทยในโฟลเดอร์ข้อมูล")
            source_duration = source.duration_ms
            subtitle_data = [
                {"start_ms": item.start_ms, "end_ms": item.end_ms, "source_text": item.source_text, "translated_text": item.translated_text}
                for item in revision.subtitles
            ]
            overlay_data = [
                {"x": item.x, "y": item.y, "width": item.width, "height": item.height, "start_ms": item.start_ms, "end_ms": item.end_ms, "color": item.color, "opacity": item.opacity}
                for item in revision.overlays
            ]
            output_path = resolve_media_path(output_asset.relative_path)
            output_asset_id = output_asset.id

        render_video(
            source_path,
            output_path,
            subtitle_data,
            overlay_data,
            settings_value,
            source_duration,
            music_path,
            source_has_audio=bool(source.has_audio),
            voiceover_path=voiceover_path,
        )
        metadata = probe_video(output_path)
        digest = hashlib.sha256()
        with output_path.open("rb") as output_file:
            for chunk in iter(lambda: output_file.read(1024 * 1024), b""):
                digest.update(chunk)

        with SessionLocal.begin() as session:
            job = session.get(Job, job_data["id"])
            asset = session.get(Asset, output_asset_id)
            render = session.get(Render, payload.get("render_id"))
            revision = session.get(Revision, job_data["revision_id"])
            if job is None or asset is None or render is None or revision is None:
                return
            asset.state = "ready"
            asset.byte_size = output_path.stat().st_size
            asset.sha256 = digest.hexdigest()
            asset.duration_ms = metadata["duration_ms"]
            asset.width = metadata["width"]
            asset.height = metadata["height"]
            asset.has_audio = metadata["has_audio"]
            asset.frame_rate = metadata.get("frame_rate")
            asset.video_codec = metadata["video_codec"]
            asset.container_format = metadata["container_format"]
            asset.error_message = None
            job.state = "succeeded"
            job.progress = 100
            job.finished_at = now_utc()
            job.error_code = None
            job.error_message = None
            render.state = "succeeded"
            render.finished_at = now_utc()
            revision.state = "rendered"
            session.add(JobEvent(job_id=job.id, event_type="completed", message=f"เรนเดอร์เสร็จแล้ว ({asset.byte_size} ไบต์)", created_at=now_utc()))
    except (RenderError, MediaProbeError, UnsafeStoragePath) as exc:
        message = exc.user_message if isinstance(exc, MediaProbeError) else str(exc)
        code = exc.code if isinstance(exc, MediaProbeError) else "render_failed"
        _fail_render(job_data, payload, message, code)
    except Exception:
        logger.exception("Unexpected error while rendering job %s", job_data["id"])
        _fail_render(job_data, payload, "เรนเดอร์ไม่สำเร็จ เกิดข้อผิดพลาดภายในโปรแกรม", "internal_error")


def _finish_external_job(job_id: str, *, error_code: str | None = None, error_message: str | None = None) -> None:
    with SessionLocal.begin() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        job.state = "failed" if error_message else "succeeded"
        job.progress = 100 if not error_message else job.progress
        job.error_code = error_code
        job.error_message = error_message[:500] if error_message else None
        job.finished_at = now_utc()
        session.add(JobEvent(
            job_id=job.id,
            event_type="failed" if error_message else "completed",
            message=(error_message or "งาน Facebook เสร็จแล้ว")[:500],
            created_at=now_utc(),
        ))


def complete_facebook_publish(job_data: dict) -> None:
    payload = json.loads(job_data.get("payload_json") or "{}")
    publication_id = payload.get("publication_id")
    try:
        with SessionLocal.begin() as session:
            publication = session.get(Publication, publication_id)
            if publication is None or publication.status != "publishing" or publication.remote_stage != "queued":
                raise FacebookApiError("publication_state", "รายการไม่อยู่ในสถานะที่พร้อมเผยแพร่")
            page = session.get(FacebookPage, publication.page_id) if publication.page_id else None
            asset = session.get(Asset, publication.render_asset_id) if publication.render_asset_id else None
            project = session.get(Project, publication.project_id)
            if page is None or asset is None or project is None or asset.state != "ready":
                raise FacebookApiError("publication_data_missing", "ข้อมูลเพจหรือไฟล์ MP4 ไม่พร้อมเผยแพร่")
            token = load_facebook_page_token(page.id)
            if not token:
                raise FacebookApiError("page_token_missing", "ไม่พบ Page Access Token ให้เชื่อมเพจใหม่")
            local_error = reels_preflight(asset)
            if local_error:
                raise FacebookApiError("reel_preflight_failed", local_error)
            video_path = resolve_media_path(asset.relative_path)
            if not video_path.is_file():
                raise FacebookApiError("asset_file_missing", "ไม่พบไฟล์ MP4 ในโฟลเดอร์ข้อมูลของโปรแกรม")
            page_id = page.id
            title = project.product_name or project.title
            caption = publication.caption
            publication.remote_stage = "starting"
            publication.updated_at = now_utc()

        remote_video_id, upload_url = start_reel(page_id, token)
        with SessionLocal.begin() as session:
            publication = session.get(Publication, publication_id)
            if publication is None:
                raise FacebookApiError("publication_missing", "รายการโพสต์ถูกลบระหว่างเผยแพร่", uncertain=True)
            publication.remote_video_id = remote_video_id
            publication.remote_stage = "session_started"
            publication.updated_at = now_utc()
            session.add(PublicationEvent(publication_id=publication_id, event_type="upload_session_created", message="Facebook สร้าง session สำหรับอัปโหลด Reel แล้ว", created_at=now_utc()))

        upload_reel(upload_url, video_path, token)
        with SessionLocal.begin() as session:
            publication = session.get(Publication, publication_id)
            if publication is None:
                raise FacebookApiError("publication_missing", "รายการโพสต์ถูกลบระหว่างเผยแพร่", uncertain=True)
            publication.remote_stage = "uploaded"
            publication.updated_at = now_utc()
            session.add(PublicationEvent(publication_id=publication_id, event_type="video_uploaded", message="ส่งไฟล์วิดีโอไป Facebook แล้ว รอเริ่มประมวลผล", created_at=now_utc()))

        finish_reel(page_id, remote_video_id, token, title, caption)
        with SessionLocal.begin() as session:
            publication = session.get(Publication, publication_id)
            if publication is None:
                raise FacebookApiError("publication_missing", "รายการโพสต์ถูกลบหลังสั่งเผยแพร่", uncertain=True)
            now = now_utc()
            publication.status = "processing"
            publication.remote_stage = "finish_requested"
            publication.next_poll_at = now + timedelta(seconds=20)
            publication.last_error = None
            publication.updated_at = now
            session.add(PublicationEvent(publication_id=publication_id, event_type="publish_requested", message="ส่งคำสั่งเผยแพร่แล้ว · รอ Facebook ประมวลผลก่อนคอมเมนต์", created_at=now))
        _finish_external_job(job_data["id"])
    except (FacebookApiError, SecretStoreError, UnsafeStoragePath, OSError) as exc:
        message = exc.user_message if isinstance(exc, FacebookApiError) else str(exc)
        uncertain = isinstance(exc, FacebookApiError) and exc.uncertain
        _fail_facebook_publish(job_data, publication_id, message, getattr(exc, "code", "publish_failed"), uncertain)
    except Exception:
        logger.exception("Unexpected Facebook publish error for job %s", job_data["id"])
        _fail_facebook_publish(job_data, publication_id, "เกิดข้อผิดพลาดระหว่างส่งไป Facebook · ตรวจหน้าเพจก่อนส่งซ้ำ", "internal_error", True)


def complete_facebook_publish_photo(job_data: dict) -> None:
    payload = json.loads(job_data.get("payload_json") or "{}")
    publication_id = payload.get("publication_id")
    try:
        with SessionLocal.begin() as session:
            publication = session.get(Publication, publication_id)
            if publication is None or publication.media_type != "image" or publication.status != "publishing" or publication.remote_stage != "queued":
                raise FacebookApiError("publication_state", "รายการภาพไม่อยู่ในสถานะที่พร้อมเผยแพร่")
            page = session.get(FacebookPage, publication.page_id) if publication.page_id else None
            assets = [session.get(Asset, asset_id) for asset_id in publication_media_asset_ids(publication)]
            if page is None or not assets or any(asset is None or asset.state != "ready" or asset.kind != "post_image" for asset in assets):
                raise FacebookApiError("publication_data_missing", "ไม่พบภาพโพสต์หรือข้อมูลเพจที่พร้อมใช้งาน")
            token = load_facebook_page_token(page.id)
            if not token:
                raise FacebookApiError("page_token_missing", "ไม่พบ Page Access Token ให้เชื่อมเพจใหม่")
            local_error = photo_set_preflight(assets)
            if local_error:
                raise FacebookApiError("photo_preflight_failed", local_error)
            image_paths = [resolve_media_path(asset.relative_path) for asset in assets]
            if any(not image_path.is_file() for image_path in image_paths):
                raise FacebookApiError("asset_file_missing", "ไม่พบภาพโพสต์บางรูปในโฟลเดอร์ข้อมูลของโปรแกรม")
            page_id = page.id
            caption = publication.caption
            # A stopped request after this point may have reached Meta. Recovery
            # therefore asks for manual reconciliation instead of posting twice.
            publication.remote_stage = "uploading"
            publication.updated_at = now_utc()

        post_id = publish_photos(page_id, token, image_paths, caption)
        with SessionLocal.begin() as session:
            publication = session.get(Publication, publication_id)
            job = session.get(Job, job_data["id"])
            if publication is None:
                raise FacebookApiError("publication_missing", "รายการโพสต์ถูกลบหลังส่งภาพ", uncertain=True)
            now = now_utc()
            publication.status = "published"
            publication.remote_stage = "published"
            # This shared object ID is used by the existing comment worker for
            # both a Reel video ID and a photo/feed post ID.
            publication.remote_video_id = post_id
            publication.external_post_id = post_id
            publication.published_at = now
            publication.next_poll_at = None
            publication.last_error = None
            publication.comment_status = "waiting_for_publish" if publication.comment_text.strip() else "not_set"
            publication.updated_at = now
            image_count = len(image_paths)
            session.add(PublicationEvent(publication_id=publication_id, event_type="published", message=f"Facebook ยืนยันว่าเผยแพร่ภาพ {image_count} รูปแล้ว", created_at=now))
            if job:
                job.state = "succeeded"
                job.progress = 100
                job.finished_at = now
                job.error_code = None
                job.error_message = None
                session.add(JobEvent(job_id=job.id, event_type="completed", message=f"เผยแพร่ภาพ {image_count} รูปบน Facebook สำเร็จ", created_at=now))
    except (FacebookApiError, SecretStoreError, UnsafeStoragePath, OSError) as exc:
        message = exc.user_message if isinstance(exc, FacebookApiError) else str(exc)
        uncertain = isinstance(exc, FacebookApiError) and exc.uncertain
        _fail_facebook_publish(job_data, publication_id, message, getattr(exc, "code", "photo_publish_failed"), uncertain)
    except Exception:
        logger.exception("Unexpected Facebook photo publish error for job %s", job_data["id"])
        _fail_facebook_publish(job_data, publication_id, "ส่งภาพไป Facebook ไม่สำเร็จ · ตรวจหน้าเพจก่อนลองใหม่", "photo_internal_error", True)


def _fail_facebook_publish(job_data: dict, publication_id: str, message: str, code: str, uncertain: bool) -> None:
    with SessionLocal.begin() as session:
        publication = session.get(Publication, publication_id) if publication_id else None
        job = session.get(Job, job_data["id"])
        if publication:
            now = now_utc()
            safe_to_retry = not uncertain and (not publication.remote_video_id or code == "upload_rejected")
            publication.status = "needs_attention"
            if safe_to_retry:
                publication.remote_stage = None
                publication.remote_video_id = None
                publication.publish_started_at = None
            publication.last_error = message[:500]
            publication.next_poll_at = None
            publication.updated_at = now
            if publication.remote_video_id and publication.comment_text.strip():
                publication.comment_status = "needs_attention"
            session.add(PublicationEvent(
                publication_id=publication.id,
                event_type="publish_uncertain" if uncertain else "publish_failed",
                message=message[:500], created_at=now,
            ))
        if job:
            job.state = "failed"
            job.error_code = code[:80]
            job.error_message = message[:500]
            job.finished_at = now_utc()
            session.add(JobEvent(job_id=job.id, event_type="attention_required" if uncertain else "failed", message=message[:500], created_at=now_utc()))
    if uncertain:
        logger.warning("Facebook publish result needs manual reconciliation for job %s", job_data["id"])


def complete_facebook_status_check(job_data: dict) -> None:
    payload = json.loads(job_data.get("payload_json") or "{}")
    publication_id = payload.get("publication_id")
    try:
        with SessionLocal() as session:
            publication = session.get(Publication, publication_id)
            if publication is None or not publication.remote_video_id or not publication.page_id:
                raise FacebookApiError("remote_video_missing", "ไม่พบรหัส Reel หรือเพจสำหรับตรวจสถานะ")
            token = load_facebook_page_token(publication.page_id)
            if not token:
                raise FacebookApiError("page_token_missing", "Page Access Token ใช้ไม่ได้ ให้เชื่อมเพจใหม่")
            video_id = publication.remote_video_id
            comment_text = publication.comment_text.strip()
        status = get_reel_status(video_id, token)
        publish_phase = str((status.get("publishing_phase") or {}).get("status", "")).lower()
        processing_phase = str((status.get("processing_phase") or {}).get("status", "")).lower()
        video_status = str(status.get("video_status", "")).lower()
        failed_remote = publish_phase in {"error", "failed"} or processing_phase in {"error", "failed"} or video_status in {"error", "failed"}
        published_remote = publish_phase in {"complete", "completed", "published"} or video_status in {"published", "complete", "completed", "ready"}
        with SessionLocal.begin() as session:
            publication = session.get(Publication, publication_id)
            job = session.get(Job, job_data["id"])
            if publication is None:
                return
            now = now_utc()
            if failed_remote:
                publication.status = "failed"
                publication.last_error = "Facebook แจ้งว่าการประมวลผล Reel ไม่สำเร็จ"
                publication.next_poll_at = None
                publication.updated_at = now
                session.add(PublicationEvent(publication_id=publication.id, event_type="remote_processing_failed", message=publication.last_error, created_at=now))
            elif published_remote:
                publication.status = "published"
                publication.remote_stage = "published"
                publication.external_post_id = publication.remote_video_id
                publication.published_at = now
                publication.next_poll_at = None
                publication.last_error = None
                publication.comment_status = "waiting_for_publish" if comment_text else "not_set"
                publication.updated_at = now
                session.add(PublicationEvent(publication_id=publication.id, event_type="published", message="Facebook ยืนยันว่า Reel เผยแพร่แล้ว", created_at=now))
                if comment_text and not _has_pending_job(session, publication.id, "facebook_post_comment"):
                    _queue_facebook_job(session, publication, "facebook_post_comment", {"publication_id": publication.id}, now)
            else:
                publication.next_poll_at = now + timedelta(seconds=45)
                publication.updated_at = now
                session.add(PublicationEvent(publication_id=publication.id, event_type="still_processing", message="Facebook ยังประมวลผล Reel อยู่ · โปรแกรมจะตรวจสถานะอีกครั้ง", created_at=now))
            if job:
                job.state = "succeeded" if not failed_remote else "failed"
                job.progress = 100 if not failed_remote else job.progress
                job.error_code = "remote_processing_failed" if failed_remote else None
                job.error_message = publication.last_error if failed_remote else None
                job.finished_at = now
                session.add(JobEvent(job_id=job.id, event_type="completed" if not failed_remote else "failed", message="ตรวจสถานะ Facebook แล้ว", created_at=now))
    except FacebookApiError as exc:
        _reschedule_status_check(job_data, publication_id, exc.user_message, exc.code)
    except SecretStoreError as exc:
        _reschedule_status_check(job_data, publication_id, str(exc), "secret_store_error")
    except Exception:
        logger.exception("Unexpected Facebook status check error for job %s", job_data["id"])
        _reschedule_status_check(job_data, publication_id, "ตรวจสถานะ Facebook ไม่สำเร็จ จะลองอ่านสถานะอีกครั้ง", "status_check_error")


def _reschedule_status_check(job_data: dict, publication_id: str, message: str, code: str) -> None:
    with SessionLocal.begin() as session:
        publication = session.get(Publication, publication_id) if publication_id else None
        job = session.get(Job, job_data["id"])
        if publication and publication.status == "processing":
            publication.next_poll_at = now_utc() + timedelta(seconds=90)
            publication.last_error = message[:500]
            publication.updated_at = now_utc()
        if job:
            job.state = "failed"
            job.error_code = code[:80]
            job.error_message = message[:500]
            job.finished_at = now_utc()
            session.add(JobEvent(job_id=job.id, event_type="failed", message=message[:500], created_at=now_utc()))


def complete_facebook_comment(job_data: dict) -> None:
    payload = json.loads(job_data.get("payload_json") or "{}")
    publication_id = payload.get("publication_id")
    try:
        with SessionLocal() as session:
            publication = session.get(Publication, publication_id)
            if publication is None or publication.status != "published" or not publication.remote_video_id or not publication.page_id:
                raise FacebookApiError("post_not_ready", "ยังไม่มีโพสต์ยืนยันแล้วสำหรับคอมเมนต์")
            token = load_facebook_page_token(publication.page_id)
            if not token:
                raise FacebookApiError("page_token_missing", "Page Access Token ใช้ไม่ได้ ให้เชื่อมเพจใหม่")
            video_id = publication.remote_video_id
            message = publication.comment_text
        comment_id = post_comment(video_id, token, message)
        with SessionLocal.begin() as session:
            publication = session.get(Publication, publication_id)
            job = session.get(Job, job_data["id"])
            if publication:
                now = now_utc()
                publication.comment_status = "published"
                publication.remote_comment_id = comment_id
                publication.last_error = None
                publication.updated_at = now
                session.add(PublicationEvent(publication_id=publication.id, event_type="comment_published", message="โพสต์คอมเมนต์ลิงก์ Affiliate สำเร็จ", created_at=now))
            if job:
                job.state = "succeeded"
                job.progress = 100
                job.finished_at = now_utc()
                session.add(JobEvent(job_id=job.id, event_type="completed", message="คอมเมนต์ Facebook สำเร็จ", created_at=now_utc()))
    except (FacebookApiError, SecretStoreError) as exc:
        uncertain = isinstance(exc, FacebookApiError) and exc.uncertain
        message = exc.user_message if isinstance(exc, FacebookApiError) else str(exc)
        with SessionLocal.begin() as session:
            publication = session.get(Publication, publication_id) if publication_id else None
            job = session.get(Job, job_data["id"])
            if publication:
                publication.comment_status = "needs_attention" if uncertain else "failed"
                publication.last_error = message[:500]
                publication.updated_at = now_utc()
                session.add(PublicationEvent(publication_id=publication.id, event_type="comment_uncertain" if uncertain else "comment_failed", message=message[:500], created_at=now_utc()))
            if job:
                job.state = "failed"
                job.error_code = getattr(exc, "code", "comment_failed")
                job.error_message = message[:500]
                job.finished_at = now_utc()
                session.add(JobEvent(job_id=job.id, event_type="attention_required" if uncertain else "failed", message=message[:500], created_at=now_utc()))
        if uncertain:
            logger.warning("Facebook comment result needs manual reconciliation for job %s", job_data["id"])
    except Exception:
        logger.exception("Unexpected Facebook comment error for job %s", job_data["id"])
        complete_facebook_comment_failure(job_data, publication_id, "ผลลัพธ์คอมเมนต์ไม่ชัดเจน ตรวจ Facebook ก่อนส่งซ้ำ", "comment_result_uncertain", True)


def complete_facebook_comment_failure(job_data: dict, publication_id: str, message: str, code: str, uncertain: bool) -> None:
    with SessionLocal.begin() as session:
        publication = session.get(Publication, publication_id) if publication_id else None
        job = session.get(Job, job_data["id"])
        if publication:
            publication.comment_status = "needs_attention" if uncertain else "failed"
            publication.last_error = message[:500]
            publication.updated_at = now_utc()
            session.add(PublicationEvent(publication_id=publication.id, event_type="comment_uncertain" if uncertain else "comment_failed", message=message[:500], created_at=now_utc()))
        if job:
            job.state = "failed"
            job.error_code = code
            job.error_message = message[:500]
            job.finished_at = now_utc()
            session.add(JobEvent(job_id=job.id, event_type="attention_required" if uncertain else "failed", message=message[:500], created_at=now_utc()))


async def worker_loop() -> None:
    last_schedule_check = 0.0
    while True:
        if asyncio.get_running_loop().time() - last_schedule_check >= 3:
            try:
                await asyncio.to_thread(process_due_publications)
            except Exception:
                logger.exception("Could not process due publication schedules")
            last_schedule_check = asyncio.get_running_loop().time()
        job_data = await asyncio.to_thread(claim_next_job)
        if job_data is None:
            await asyncio.sleep(0.75)
            continue
        if job_data["job_type"] == "probe_asset":
            await asyncio.to_thread(complete_probe, job_data)
        elif job_data["job_type"] == "render_video":
            await asyncio.to_thread(complete_render, job_data)
        elif job_data["job_type"] == "ocr_subtitles":
            await asyncio.to_thread(complete_ocr, job_data)
        elif job_data["job_type"] == "translate_subtitles":
            await asyncio.to_thread(complete_translation, job_data)
        elif job_data["job_type"] in {"generate_copy", "generate_script", "generate_caption"}:
            await asyncio.to_thread(complete_copy_generation, job_data)
        elif job_data["job_type"] == "generate_voiceover":
            await asyncio.to_thread(complete_voiceover, job_data)
        elif job_data["job_type"] == "facebook_publish_reel":
            await asyncio.to_thread(complete_facebook_publish, job_data)
        elif job_data["job_type"] == "facebook_publish_photo":
            await asyncio.to_thread(complete_facebook_publish_photo, job_data)
        elif job_data["job_type"] == "facebook_check_reel":
            await asyncio.to_thread(complete_facebook_status_check, job_data)
        elif job_data["job_type"] == "facebook_post_comment":
            await asyncio.to_thread(complete_facebook_comment, job_data)
        else:
            with SessionLocal.begin() as session:
                job = session.get(Job, job_data["id"])
                if job:
                    job.state = "failed"
                    job.error_code = "unknown_job_type"
                    job.error_message = "ชนิดงานนี้ยังไม่รองรับในรุ่นปัจจุบัน"
                    job.finished_at = now_utc()
