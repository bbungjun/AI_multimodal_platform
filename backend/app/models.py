from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class GenerationMode(StrEnum):
    T2I = "t2i"
    T2V = "t2v"
    I2V = "i2v"


class JobState(StrEnum):
    PENDING = "pending"
    ENHANCING = "enhancing"
    QUEUED = "queued"
    GENERATING = "generating"
    POLLING = "polling"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AssetKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


generation_mode_enum = Enum(
    GenerationMode,
    name="generation_mode",
    values_callable=enum_values,
)
job_state_enum = Enum(
    JobState,
    name="job_state",
    values_callable=enum_values,
)
asset_kind_enum = Enum(
    AssetKind,
    name="asset_kind",
    values_callable=enum_values,
)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    mode: Mapped[GenerationMode] = mapped_column(generation_mode_enum, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[JobState] = mapped_column(
        job_state_enum,
        nullable=False,
        default=JobState.PENDING,
        index=True,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    enhanced_prompt: Mapped[str | None] = mapped_column(Text)
    enhancement_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prompt_enhancements.id", ondelete="SET NULL"),
    )
    parent_job_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        index=True,
    )
    source_asset_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "assets.id",
            name="fk_jobs_source_asset_id_assets",
            ondelete="SET NULL",
            use_alter=True,
        ),
    )
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vertex_operation_name: Mapped[str | None] = mapped_column(String(512))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    state_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    vertex_charged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    enhancement: Mapped[PromptEnhancement | None] = relationship(
        "PromptEnhancement",
        back_populates="jobs",
        foreign_keys=[enhancement_id],
    )
    parent_job: Mapped[Job | None] = relationship(
        "Job",
        remote_side=[id],
        foreign_keys=[parent_job_id],
    )
    source_asset: Mapped[Asset | None] = relationship(
        "Asset",
        foreign_keys=[source_asset_id],
    )
    assets: Mapped[list[Asset]] = relationship(
        "Asset",
        back_populates="job",
        cascade="all, delete-orphan",
        foreign_keys="Asset.job_id",
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[AssetKind] = mapped_column(asset_kind_enum, nullable=False)
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_sec: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    job: Mapped[Job] = relationship(
        "Job",
        back_populates="assets",
        foreign_keys=[job_id],
    )


class PromptEnhancement(Base):
    __tablename__ = "prompt_enhancements"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    original: Mapped[str] = mapped_column(Text, nullable=False)
    enhanced: Mapped[str] = mapped_column(Text, nullable=False)
    components: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    target_mode: Mapped[GenerationMode] = mapped_column(generation_mode_enum, nullable=False)
    target_model: Mapped[str] = mapped_column(String(128), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    jobs: Mapped[list[Job]] = relationship(
        "Job",
        back_populates="enhancement",
        foreign_keys="Job.enhancement_id",
    )
