from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    product_name: Mapped[str | None] = mapped_column(String(200))
    product_details: Mapped[str | None] = mapped_column(Text)
    product_source_details: Mapped[str | None] = mapped_column(Text)
    review_evidence: Mapped[str | None] = mapped_column(Text)
    product_average_rating: Mapped[float | None] = mapped_column(Float)
    product_review_count: Mapped[int | None] = mapped_column(Integer)
    product_review_summary: Mapped[str | None] = mapped_column(Text)
    product_data_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discount_text: Mapped[str | None] = mapped_column(String(400))
    copy_style: Mapped[str] = mapped_column(String(32), nullable=False, default="problem_solution")
    affiliate_url: Mapped[str | None] = mapped_column(String(2048))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    assets: Mapped[list[Asset]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="Asset.created_at.desc()")
    jobs: Mapped[list[Job]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="Job.created_at.desc()")
    revisions: Mapped[list[Revision]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="Revision.version.desc()")
    publications: Mapped[list[Publication]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="Publication.created_at.desc()")


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        Index("ix_assets_project_id", "project_id"),
        Index("ix_assets_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="source_video")
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="processing")
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    has_audio: Mapped[bool | None] = mapped_column(Boolean)
    frame_rate: Mapped[float | None] = mapped_column()
    video_codec: Mapped[str | None] = mapped_column(String(80))
    container_format: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="assets")
    jobs: Mapped[list[Job]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    source_revisions: Mapped[list[Revision]] = relationship(back_populates="source_asset", foreign_keys="Revision.source_asset_id")


class MusicTrack(Base):
    __tablename__ = "music_tracks"
    __table_args__ = (Index("ix_music_tracks_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_state_created_at", "state", "created_at"),
        Index("ix_jobs_project_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("assets.id", ondelete="CASCADE"))
    revision_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("revisions.id", ondelete="SET NULL"))
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="jobs")
    asset: Mapped[Asset | None] = relationship(back_populates="jobs")
    revision: Mapped[Revision | None] = relationship(back_populates="jobs")
    events: Mapped[list[JobEvent]] = relationship(back_populates="job", cascade="all, delete-orphan", order_by="JobEvent.created_at")


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job_id_created_at", "job_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    job: Mapped[Job] = relationship(back_populates="events")


class Revision(Base):
    __tablename__ = "revisions"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_revisions_project_version"),
        Index("ix_revisions_project_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_asset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("assets.id", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default='{"audio_mode":"mute","subtitle_style":{"font_size":52,"font_color":"#FFFFFF","box_color":"#111111","box_opacity":0.92,"margin_bottom":80}}')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="revisions")
    source_asset: Mapped[Asset | None] = relationship(back_populates="source_revisions", foreign_keys=[source_asset_id])
    subtitles: Mapped[list[SubtitleSegment]] = relationship(back_populates="revision", cascade="all, delete-orphan", order_by="SubtitleSegment.position")
    overlays: Mapped[list[OverlayRegion]] = relationship(back_populates="revision", cascade="all, delete-orphan", order_by="OverlayRegion.created_at")
    generated_copy: Mapped[GeneratedCopy | None] = relationship(back_populates="revision", cascade="all, delete-orphan", uselist=False)
    renders: Mapped[list[Render]] = relationship(back_populates="revision", cascade="all, delete-orphan", order_by="Render.created_at.desc()")
    jobs: Mapped[list[Job]] = relationship(back_populates="revision")


class SubtitleSegment(Base):
    __tablename__ = "subtitle_segments"
    __table_args__ = (
        UniqueConstraint("revision_id", "stable_id", name="uq_subtitle_revision_stable_id"),
        Index("ix_subtitle_revision_position", "revision_id", "position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    revision_id: Mapped[str] = mapped_column(String(36), ForeignKey("revisions.id", ondelete="CASCADE"), nullable=False)
    stable_id: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    translated_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ocr_confidence: Mapped[float | None] = mapped_column()
    review_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    revision: Mapped[Revision] = relationship(back_populates="subtitles")


class OverlayRegion(Base):
    __tablename__ = "overlay_regions"
    __table_args__ = (Index("ix_overlays_revision_id", "revision_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    revision_id: Mapped[str] = mapped_column(String(36), ForeignKey("revisions.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False, default="ปิดซับเดิม")
    x: Mapped[float] = mapped_column(nullable=False)
    y: Mapped[float] = mapped_column(nullable=False)
    width: Mapped[float] = mapped_column(nullable=False)
    height: Mapped[float] = mapped_column(nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#111111")
    opacity: Mapped[float] = mapped_column(nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    revision: Mapped[Revision] = relationship(back_populates="overlays")


class GeneratedCopy(Base):
    __tablename__ = "generated_copy"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    revision_id: Mapped[str] = mapped_column(String(36), ForeignKey("revisions.id", ondelete="CASCADE"), nullable=False, unique=True)
    script_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    caption_candidates_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    selected_caption: Mapped[str] = mapped_column(Text, nullable=False, default="")
    comment_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    review_score: Mapped[float | None] = mapped_column(Float)
    review_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model_name: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    revision: Mapped[Revision] = relationship(back_populates="generated_copy")


class Render(Base):
    __tablename__ = "renders"
    __table_args__ = (Index("ix_renders_revision_created", "revision_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    revision_id: Mapped[str] = mapped_column(String(36), ForeignKey("revisions.id", ondelete="CASCADE"), nullable=False)
    output_asset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("assets.id", ondelete="SET NULL"))
    settings_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    revision: Mapped[Revision] = relationship(back_populates="renders")


class Publication(Base):
    """Immutable content snapshot plus local publication/scheduling state."""

    __tablename__ = "publications"
    __table_args__ = (
        Index("ix_publications_status_scheduled", "status", "scheduled_at"),
        Index("ix_publications_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    revision_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("revisions.id", ondelete="SET NULL"))
    render_asset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("assets.id", ondelete="SET NULL"))
    media_asset_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    page_id: Mapped[str | None] = mapped_column(String(40))
    platform: Mapped[str] = mapped_column(String(40), nullable=False, default="facebook_page")
    media_type: Mapped[str] = mapped_column(String(16), nullable=False, default="video")
    page_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    comment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_set")
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    affiliate_url: Mapped[str | None] = mapped_column(String(2048))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_post_id: Mapped[str | None] = mapped_column(String(200))
    remote_stage: Mapped[str | None] = mapped_column(String(40))
    remote_video_id: Mapped[str | None] = mapped_column(String(200))
    remote_comment_id: Mapped[str | None] = mapped_column(String(200))
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="publications")
    events: Mapped[list[PublicationEvent]] = relationship(back_populates="publication", cascade="all, delete-orphan", order_by="PublicationEvent.created_at")


class PublicationEvent(Base):
    __tablename__ = "publication_events"
    __table_args__ = (Index("ix_publication_events_publication_created", "publication_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    publication_id: Mapped[str] = mapped_column(String(36), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    publication: Mapped[Publication] = relationship(back_populates="events")


class FacebookPage(Base):
    __tablename__ = "facebook_pages"
    __table_args__ = (Index("ix_facebook_pages_active", "is_active"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tasks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AICache(Base):
    __tablename__ = "ai_cache"
    __table_args__ = (Index("ix_ai_cache_task_created", "task", "created_at"),)

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    task: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
