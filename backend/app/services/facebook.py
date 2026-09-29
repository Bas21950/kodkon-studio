from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


API_VERSION = os.environ.get("KODKON_FACEBOOK_API_VERSION", "v26.0")
GRAPH_ROOT = f"https://graph.facebook.com/{API_VERSION}"
MAX_POST_IMAGES = 6
MAX_POST_IMAGE_BYTES = 36 * 1024 * 1024


class FacebookApiError(RuntimeError):
    def __init__(self, code: str, user_message: str, *, uncertain: bool = False):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.uncertain = uncertain


def reels_preflight(asset) -> str | None:
    width = asset.width or 0
    height = asset.height or 0
    duration_ms = asset.duration_ms or 0
    rate = asset.frame_rate or 0
    container = (asset.container_format or "").lower()
    if width < 540 or height < 960 or abs((width / height) - (9 / 16)) > 0.01:
        return "Reel ต้องเป็นแนวตั้ง 9:16 และอย่างน้อย 540 × 960 พิกเซล · ปรับต้นฉบับแล้วเรนเดอร์ใหม่"
    if not 4000 <= duration_ms <= 60000:
        return "Reel ต้องยาว 4–60 วินาที · ตัดคลิปหรือปรับช่วงส่งออกใหม่"
    if rate < 23:
        return "Reel ต้องมีอัตราเฟรมอย่างน้อย 23 FPS · เรนเดอร์ MP4 ใหม่หลังตรวจต้นฉบับ"
    if "mp4" not in container and not str(asset.original_name).lower().endswith(".mp4"):
        return "Facebook Reels ต้องส่งออกเป็น MP4"
    return None


def photo_preflight(asset) -> str | None:
    suffix = Path(asset.original_name).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png"}:
        return "โพสต์ภาพรองรับไฟล์ JPG, JPEG หรือ PNG · บันทึกภาพใหม่แล้วลองอีกครั้ง"
    if (asset.byte_size or 0) > 10 * 1024 * 1024:
        return "ภาพโพสต์มีขนาดเกิน 10 MB · ลดขนาดภาพแล้วลองอีกครั้ง"
    return None


def photo_set_preflight(assets) -> str | None:
    if not 1 <= len(assets) <= MAX_POST_IMAGES:
        return f"โพสต์ได้ครั้งละ 1–{MAX_POST_IMAGES} รูป"
    for index, asset in enumerate(assets, start=1):
        error = photo_preflight(asset)
        if error:
            return f"รูปที่ {index}: {error}"
    if sum(asset.byte_size or 0 for asset in assets) > MAX_POST_IMAGE_BYTES:
        return "ภาพทั้งหมดรวมกันต้องไม่เกิน 36 MB"
    return None


def _request(method: str, url: str, token: str, **kwargs) -> dict:
    headers = dict(kwargs.pop("headers", {}))
    headers["Authorization"] = f"Bearer {token}"
    headers.setdefault("User-Agent", "KodKonStudio/0.1")
    try:
        response = httpx.request(method, url, headers=headers, timeout=httpx.Timeout(180.0, connect=20.0), **kwargs)
    except httpx.TimeoutException as exc:
        raise FacebookApiError("timeout", "Facebook ใช้เวลาตอบนานเกินไป ผลลัพธ์อาจยังไม่ชัดเจน", uncertain=True) from exc
    except httpx.RequestError as exc:
        raise FacebookApiError("network_error", "เชื่อม Facebook ไม่สำเร็จ ตรวจอินเทอร์เน็ตและสถานะโพสต์ก่อนลองใหม่", uncertain=True) from exc
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        if response.is_success:
            raise FacebookApiError("invalid_response", "Facebook ตอบกลับมาในรูปแบบที่อ่านไม่ได้", uncertain=True) from exc
        payload = {}
    if not response.is_success or (isinstance(payload, dict) and payload.get("error")):
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        code = str(error.get("code", response.status_code))
        if code == "190":
            message = "Facebook ปฏิเสธ Page Access Token หรือ token หมดอายุ ให้เชื่อมเพจใหม่"
        elif code == "200":
            message = "บัญชีหรือ token ไม่มีสิทธิ์จัดการโพสต์/คอมเมนต์บนเพจนี้"
        else:
            detail = str(error.get("message") or "").strip()
            message = f"Facebook ปฏิเสธคำขอ ({code})" + (f": {detail[:240]}" if detail else "")
        raise FacebookApiError(code, message, uncertain=response.status_code >= 500 and method.upper() == "POST")
    if not isinstance(payload, dict):
        raise FacebookApiError("invalid_response", "Facebook ตอบกลับมาในรูปแบบที่อ่านไม่ได้", uncertain=True)
    return payload


def verify_page(page_id: str, access_token: str) -> dict:
    payload = _request("GET", f"{GRAPH_ROOT}/{page_id}", access_token, params={"fields": "id,name"})
    if str(payload.get("id")) != page_id or not payload.get("name"):
        raise FacebookApiError("page_mismatch", "token นี้ไม่สามารถยืนยันตัวตนของ Page ID ที่ระบุได้")
    identity = _request("GET", f"{GRAPH_ROOT}/me", access_token, params={"fields": "id"})
    if str(identity.get("id")) != page_id:
        raise FacebookApiError(
            "user_token_not_page_token",
            "token นี้เป็น User Access Token · กรุณาใช้ Page Access Token ของเพจเดียวกันจาก /me/accounts",
        )
    return {"id": page_id, "name": str(payload["name"])}


def get_post_insights(post_id: str, access_token: str) -> dict:
    """Read supported lifetime metrics independently so one retired metric cannot hide the rest."""
    metric_names = {
        "views": ("post_media_view",),
        "viewers": ("post_total_media_view_unique",),
        "clicks": ("post_clicks",),
    }
    result: dict[str, Any] = {key: None for key in metric_names}
    errors: list[str] = []
    for key, candidates in metric_names.items():
        for metric in candidates:
            try:
                payload = _request("GET", f"{GRAPH_ROOT}/{post_id}/insights", access_token,
                                   params={"metric": metric, "period": "lifetime"})
            except FacebookApiError as exc:
                errors.append(exc.user_message)
                continue
            rows = payload.get("data", [])
            if rows and isinstance(rows[0], dict):
                values = rows[0].get("values", [])
                if values and isinstance(values[0], dict):
                    value = values[0].get("value")
                    if isinstance(value, (int, float)):
                        result[key] = int(value)
                        break

    try:
        post = _request("GET", f"{GRAPH_ROOT}/{post_id}", access_token,
                        params={"fields": "reactions.summary(true),comments.summary(true),shares"})
        for key, path in (("reactions", "reactions"), ("comments", "comments")):
            summary = post.get(path, {}).get("summary", {}) if isinstance(post.get(path), dict) else {}
            count = summary.get("total_count")
            result[key] = int(count) if isinstance(count, (int, float)) else None
        shares = post.get("shares", {}).get("count") if isinstance(post.get("shares"), dict) else None
        result["shares"] = int(shares) if isinstance(shares, (int, float)) else 0
    except FacebookApiError as exc:
        errors.append(exc.user_message)
        result.update({"reactions": None, "comments": None, "shares": None})
    result["metric_errors"] = list(dict.fromkeys(errors))
    return result


def start_reel(page_id: str, access_token: str) -> tuple[str, str]:
    payload = _request("POST", f"{GRAPH_ROOT}/{page_id}/video_reels", access_token, data={"upload_phase": "start"})
    video_id = str(payload.get("video_id") or "")
    upload_url = str(payload.get("upload_url") or "")
    parsed = urlparse(upload_url)
    if not video_id or parsed.scheme != "https" or parsed.hostname != "rupload.facebook.com":
        raise FacebookApiError("invalid_upload_session", "Facebook ไม่ได้ส่งข้อมูลเริ่มอัปโหลด Reels ที่ถูกต้อง", uncertain=True)
    return video_id, upload_url


def upload_reel(upload_url: str, video_path: Path, access_token: str) -> None:
    file_size = video_path.stat().st_size

    def content():
        with video_path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                yield block

    try:
        response = httpx.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Length": str(file_size),
                "Content-Type": "application/octet-stream",
                "User-Agent": "KodKonStudio/0.1",
            },
            content=content(),
            timeout=httpx.Timeout(900.0, connect=20.0),
        )
    except httpx.TimeoutException as exc:
        raise FacebookApiError("upload_timeout", "หมดเวลาระหว่างส่งวิดีโอ ผลการอัปโหลดอาจยังไม่ชัดเจน", uncertain=True) from exc
    except (httpx.RequestError, OSError) as exc:
        raise FacebookApiError("upload_failed", "ส่งวิดีโอไป Facebook ไม่สำเร็จ ตรวจอินเทอร์เน็ตและสถานะโพสต์ก่อนลองใหม่", uncertain=True) from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.is_success or payload.get("success") is not True:
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        detail = str(error.get("message") or error.get("error_user_msg") or "").strip()
        subcode = error.get("error_subcode")
        if detail and subcode:
            detail = f"{detail} (รหัสย่อย {subcode})"
        if not detail:
            detail = f"คำตอบ success={payload.get('success')}" if isinstance(payload, dict) else "คำตอบที่ไม่ใช่ JSON"
        message = f"Facebook ไม่รับวิดีโอ (HTTP {response.status_code}): {detail[:240]}"
        raise FacebookApiError("upload_rejected", message)


def finish_reel(page_id: str, video_id: str, access_token: str, title: str, caption: str) -> None:
    payload = _request(
        "POST",
        f"{GRAPH_ROOT}/{page_id}/video_reels",
        access_token,
        data={"video_id": video_id, "upload_phase": "finish", "video_state": "PUBLISHED", "title": title[:255], "description": caption},
    )
    if payload.get("success") is not True:
        raise FacebookApiError("publish_rejected", "Facebook ยังไม่ยืนยันการส่ง Reel", uncertain=True)


def publish_photo(page_id: str, access_token: str, image_path: Path, caption: str) -> str:
    mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    try:
        with image_path.open("rb") as image_file:
            payload = _request(
                "POST",
                f"{GRAPH_ROOT}/{page_id}/photos",
                access_token,
                data={"message": caption, "published": "true"},
                files={"source": (image_path.name, image_file, mime_type)},
            )
    except OSError as exc:
        raise FacebookApiError("photo_read_failed", "เปิดภาพโพสต์ไม่สำเร็จ", uncertain=False) from exc
    post_id = str(payload.get("post_id") or payload.get("id") or "")
    if not post_id:
        raise FacebookApiError("missing_photo_post_id", "Facebook ไม่ได้คืนรหัสโพสต์ภาพ ตรวจหน้าเพจก่อนลองใหม่", uncertain=True)
    return post_id


def publish_photos(page_id: str, access_token: str, image_paths: list[Path], caption: str) -> str:
    if len(image_paths) == 1:
        return publish_photo(page_id, access_token, image_paths[0], caption)

    media_ids: list[str] = []
    for image_path in image_paths:
        mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        try:
            with image_path.open("rb") as image_file:
                payload = _request(
                    "POST",
                    f"{GRAPH_ROOT}/{page_id}/photos",
                    access_token,
                    data={"published": "false", "temporary": "true"},
                    files={"source": (image_path.name, image_file, mime_type)},
                )
        except OSError as exc:
            raise FacebookApiError("photo_read_failed", "เปิดภาพโพสต์ไม่สำเร็จ", uncertain=False) from exc
        media_id = str(payload.get("id") or "")
        if not media_id:
            raise FacebookApiError("missing_photo_id", "Facebook ไม่ได้ยืนยันการอัปโหลดภาพ ตรวจหน้าเพจก่อนลองใหม่", uncertain=True)
        media_ids.append(media_id)

    attached_media = {
        f"attached_media[{index}]": json.dumps({"media_fbid": media_id})
        for index, media_id in enumerate(media_ids)
    }
    payload = _request(
        "POST",
        f"{GRAPH_ROOT}/{page_id}/feed",
        access_token,
        data={"message": caption, **attached_media},
    )
    post_id = str(payload.get("id") or "")
    if not post_id:
        raise FacebookApiError("missing_photo_post_id", "Facebook ไม่ได้คืนรหัสโพสต์ภาพ ตรวจหน้าเพจก่อนลองใหม่", uncertain=True)
    return post_id


def get_reel_status(video_id: str, access_token: str) -> dict:
    payload = _request("GET", f"{GRAPH_ROOT}/{video_id}", access_token, params={"fields": "status"})
    status = payload.get("status")
    if not isinstance(status, dict):
        raise FacebookApiError("missing_status", "ยังอ่านสถานะประมวลผล Reel จาก Facebook ไม่ได้", uncertain=True)
    return status


def post_comment(video_id: str, access_token: str, message: str) -> str:
    payload = _request("POST", f"{GRAPH_ROOT}/{video_id}/comments", access_token, data={"message": message})
    comment_id = str(payload.get("id") or "")
    if not comment_id:
        raise FacebookApiError("missing_comment_id", "Facebook ไม่ได้คืนรหัสคอมเมนต์", uncertain=True)
    return comment_id
