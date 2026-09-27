from __future__ import annotations

import ipaddress
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def validate_http_url(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    value = value.strip()
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").rstrip(".").casefold()
        port = parsed.port
    except ValueError as exc:
        raise ValueError("ใส่ลิงก์เว็บไซต์ที่ถูกต้อง") from exc
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ValueError("ใส่ลิงก์ที่ขึ้นต้นด้วย http:// หรือ https://")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
        raise ValueError("ลิงก์สินค้าต้องเป็นเว็บไซต์สาธารณะ")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError("ลิงก์สินค้าต้องเป็นเว็บไซต์สาธารณะ")
    if port not in {None, 80, 443}:
        raise ValueError("ไม่รองรับพอร์ตของเว็บไซต์นี้")
    return value


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    product_name: str | None = Field(default=None, max_length=200)
    product_details: str | None = Field(default=None, max_length=24000)
    review_evidence: str | None = Field(default=None, max_length=6000)
    discount_text: str | None = Field(default=None, max_length=400)
    copy_style: Literal["problem_solution", "friendly_review", "direct_offer"] = "problem_solution"
    affiliate_url: str | None = Field(default=None, max_length=2048)
    source_url: str | None = Field(default=None, max_length=2048)

    @field_validator("title", "product_name", "product_details", "review_evidence", "discount_text", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("affiliate_url", "source_url")
    @classmethod
    def check_url(cls, value: str | None) -> str | None:
        return validate_http_url(value)


class ProjectPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    product_name: str | None = Field(default=None, max_length=200)
    product_details: str | None = Field(default=None, max_length=24000)
    review_evidence: str | None = Field(default=None, max_length=6000)
    discount_text: str | None = Field(default=None, max_length=400)
    copy_style: Literal["problem_solution", "friendly_review", "direct_offer"] | None = None
    affiliate_url: str | None = Field(default=None, max_length=2048)
    source_url: str | None = Field(default=None, max_length=2048)

    @field_validator("title", "product_name", "product_details", "review_evidence", "discount_text", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("affiliate_url", "source_url")
    @classmethod
    def check_url(cls, value: str | None) -> str | None:
        return validate_http_url(value)


class ImagePostCopyGenerate(BaseModel):
    product_details: str = Field(default="", max_length=24000)
    affiliate_url: str = Field(min_length=1, max_length=2048)

    @field_validator("product_details", mode="before")
    @classmethod
    def trim_product_details(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("affiliate_url")
    @classmethod
    def check_affiliate_url(cls, value: str) -> str:
        return validate_http_url(value)


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    kind: str
    original_name: str
    byte_size: int
    state: Literal["uploading", "processing", "ready", "failed"]
    duration_ms: int | None
    width: int | None
    height: int | None
    has_audio: bool | None
    frame_rate: float | None
    video_codec: str | None
    container_format: str | None
    error_message: str | None
    created_at: datetime


class MusicTrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_name: str
    byte_size: int
    duration_ms: int | None
    created_at: datetime


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    asset_id: str | None
    job_type: str
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: int
    attempts: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    product_name: str | None
    product_details: str | None
    product_source_details: str | None = None
    review_evidence: str | None = None
    product_average_rating: float | None = None
    product_review_count: int | None = None
    product_review_summary: str | None = None
    product_data_read_at: datetime | None = None
    discount_text: str | None = None
    copy_style: str
    affiliate_url: str | None
    source_url: str | None
    created_at: datetime
    updated_at: datetime
    assets: list[AssetRead] = Field(default_factory=list)
    jobs: list[JobRead] = Field(default_factory=list)


class AssetUploadRead(BaseModel):
    asset: AssetRead
    job: JobRead


class SubtitleSegmentWrite(BaseModel):
    stable_id: str = Field(min_length=1, max_length=64)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    source_text: str = Field(default="", max_length=1200)
    translated_text: str = Field(default="", max_length=1200)
    review_flag: bool = False

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("เวลาจบซับต้องอยู่หลังเวลาเริ่ม")
        return self


class SubtitleBatchWrite(BaseModel):
    items: list[SubtitleSegmentWrite] = Field(max_length=5000)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [item.stable_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("รหัสซับซ้ำกัน")
        return self


class SubtitleSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stable_id: str
    position: int
    start_ms: int
    end_ms: int
    source_text: str
    translated_text: str
    ocr_confidence: float | None
    review_flag: bool


class OverlayWrite(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(default="ปิดซับเดิม", max_length=120)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    color: str = Field(default="#111111", pattern=r"^#[0-9a-fA-F]{6}$")
    opacity: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def valid_bounds(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("เวลาจบกรอบต้องอยู่หลังเวลาเริ่ม")
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("กรอบต้องอยู่ภายในขอบวิดีโอ")
        return self


class OverlayBatchWrite(BaseModel):
    items: list[OverlayWrite] = Field(max_length=200)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("รหัสกรอบซ้ำกัน")
        return self


class OverlayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    x: float
    y: float
    width: float
    height: float
    start_ms: int
    end_ms: int
    color: str
    opacity: float


class RevisionSettingsWrite(BaseModel):
    audio_mode: Literal["mute", "music"] = "mute"
    source_audio_enabled: bool = False
    music_asset_id: str | None = None
    music_library_id: str | None = None
    music_volume: float = Field(default=0.22, ge=0, le=1)
    music_fade_ms: int = Field(default=700, ge=0, le=10000)
    voiceover_asset_id: str | None = None
    voiceover_volume: float = Field(default=1.0, ge=0, le=2)
    subtitle_style: dict[str, Any] = Field(default_factory=dict)


class SrtImportRequest(BaseModel):
    content: str = Field(max_length=2_000_000)


class EditorRead(BaseModel):
    id: str
    project_id: str
    version: int
    state: str
    source_asset: AssetRead | None
    voiceover_asset: AssetRead | None = None
    settings: dict[str, Any]
    subtitles: list[SubtitleSegmentRead]
    overlays: list[OverlayRead]
    renders: list["RenderRead"] = Field(default_factory=list)


class RenderRead(BaseModel):
    id: str
    revision_id: str
    output_asset: AssetRead | None
    state: str
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None


class PublicationCreate(BaseModel):
    render_asset_id: str
    caption: str = Field(min_length=1, max_length=5000)
    comment_text: str = Field(default="", max_length=2000)

    @field_validator("caption")
    @classmethod
    def require_caption(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ใส่แคปชั่นก่อนเตรียมโพสต์")
        return value.strip()


class PublicationPatch(BaseModel):
    caption: str | None = Field(default=None, min_length=1, max_length=5000)
    comment_text: str | None = Field(default=None, max_length=2000)
    scheduled_at: datetime | None = None

    @field_validator("caption")
    @classmethod
    def require_caption_if_present(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("แคปชั่นห้ามเว้นว่าง")
        return value.strip() if value is not None else value

    @model_validator(mode="after")
    def require_some_change(self):
        if not self.model_fields_set:
            raise ValueError("ไม่มีข้อมูลที่แก้ไข")
        return self


class PublicationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    event_type: str
    message: str
    created_at: datetime


class PublicationRead(BaseModel):
    id: str
    project_id: str
    project_title: str
    revision_id: str | None
    render_asset: AssetRead | None
    media_assets: list[AssetRead] = Field(default_factory=list)
    page_id: str | None
    platform: str
    media_type: Literal["video", "image"] = "video"
    page_name: str | None
    status: str
    comment_status: str
    caption: str
    comment_text: str
    affiliate_url: str | None
    scheduled_at: datetime | None
    published_at: datetime | None
    external_post_id: str | None
    remote_stage: str | None
    remote_video_id: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    events: list[PublicationEventRead] = Field(default_factory=list)


class GeminiKeyWrite(BaseModel):
    api_key: str = Field(min_length=20, max_length=4096)


class GeminiModelWrite(BaseModel):
    model: str = Field(pattern=r"^(gemini-3\.1-flash-lite|gemini-3\.5-flash-lite)$")


class GeneratedCopyWrite(BaseModel):
    script_text: str = Field(default="", max_length=12000)
    caption_candidates: list[str] = Field(default_factory=list, max_length=5)
    selected_caption: str = Field(default="", max_length=5000)
    comment_text: str = Field(default="", max_length=2000)
    review_score: float | None = Field(default=None, ge=0, le=5)
    review_summary: str = Field(default="", max_length=1200)


class GeneratedCopyPartWrite(BaseModel):
    part: Literal["script", "caption"] = "script"


class VoiceoverRequest(BaseModel):
    voice: Literal["Kore", "Aoede", "Sulafat", "Achird", "Leda", "Charon"] = "Kore"


class GeneratedCopyRead(BaseModel):
    script_text: str
    caption_candidates: list[str]
    selected_caption: str
    comment_text: str
    review_score: float | None = None
    review_summary: str = ""
    model_name: str | None
    updated_at: datetime | None


class HealthRead(BaseModel):
    status: str
    app: str
    version: str
    database: str
    ffmpeg_available: bool
    ffprobe_available: bool


class CapabilitiesRead(BaseModel):
    app: str
    version: str
    ffmpeg_available: bool
    ffprobe_available: bool
    max_upload_bytes: int
    storage_available_bytes: int
    data_directory_name: str


class FacebookConnectWrite(BaseModel):
    page_id: str = Field(min_length=5, max_length=40, pattern=r"^\d+$")
    page_access_token: str = Field(min_length=20, max_length=4096)


class FacebookPageRead(BaseModel):
    id: str
    name: str
    tasks: list[str]
    is_active: bool
    token_configured: bool
    connected_at: datetime
