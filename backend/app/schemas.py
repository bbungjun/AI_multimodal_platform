from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models import (
    Asset,
    AssetKind,
    GenerationMode,
    Job,
    JobState,
    OutboxEventStatus,
)
from app.prompt_enhancement import (
    DEFAULT_CREATIVITY_PRESET,
    PROVIDER_PROMPT_PARAMETER_KEY,
    CreativityPreset,
    temperature_for_preset,
)


class GenerationRequestBase(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    model: str = Field(min_length=1, max_length=128)
    auto_enhance: bool = False
    enhancement_id: UUID | None = None


class PromptEnhanceRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    target_mode: GenerationMode
    target_model: str = Field(min_length=1, max_length=128)
    creativity_preset: CreativityPreset = DEFAULT_CREATIVITY_PRESET


class PipelineCreateRequest(BaseModel):
    image_prompt: str = Field(min_length=1, max_length=4000)
    video_prompt: str = Field(min_length=1, max_length=4000)
    image_model: str = Field(min_length=1, max_length=128)
    video_model: str = Field(min_length=1, max_length=128)
    image_aspect_ratio: str = Field(default="1:1", min_length=3, max_length=16)
    video_aspect_ratio: str = Field(default="16:9", min_length=3, max_length=16)
    duration_sec: int = Field(default=4, ge=1, le=8)


class VertexReadinessResponse(BaseModel):
    ready: bool
    status: str
    credentials: str
    project: str
    location: str


class HealthResponse(BaseModel):
    ok: bool
    ready: bool
    service: str
    db: Literal["up", "down"]
    vertex: VertexReadinessResponse


class OpsDispatchResponse(BaseModel):
    mode: str
    queue: str | None = None
    task_acks_late: bool
    task_reject_on_worker_lost: bool
    worker_prefetch_multiplier: int


class OpsJobsResponse(BaseModel):
    total: int
    active: int
    blocked: int
    resumable_polling: int
    by_state: dict[JobState, int]


class OpsOutboxResponse(BaseModel):
    total: int
    pending: int
    published: int
    failed: int
    by_status: dict[OutboxEventStatus, int]


class OpsRecentFailureResponse(BaseModel):
    id: UUID
    mode: GenerationMode
    model: str
    code: str | None = None
    message: str | None = None
    retryable: bool | None = None
    dead_letter: bool
    updated_at: datetime


class OpsHealthResponse(BaseModel):
    ok: bool
    db: Literal["up", "down"]
    service: str
    dispatch: OpsDispatchResponse
    jobs: OpsJobsResponse
    outbox: OpsOutboxResponse
    recent_failures: list[OpsRecentFailureResponse] = Field(default_factory=list)


class T2IRequest(GenerationRequestBase):
    mode: Literal["t2i"] = "t2i"
    aspect_ratio: str = Field(default="1:1", min_length=3, max_length=16)
    number_of_images: int = Field(default=1, ge=1, le=4)


class T2VRequest(GenerationRequestBase):
    mode: Literal["t2v"] = "t2v"
    aspect_ratio: str = Field(default="16:9", min_length=3, max_length=16)
    duration_sec: int = Field(default=4, ge=1, le=8)


class I2VRequest(GenerationRequestBase):
    mode: Literal["i2v"] = "i2v"
    source_asset_id: UUID
    aspect_ratio: str = Field(default="16:9", min_length=3, max_length=16)
    duration_sec: int = Field(default=4, ge=1, le=8)


GenerationCreate = Annotated[
    Union[T2IRequest, T2VRequest, I2VRequest],
    Field(discriminator="mode"),
]


class StateHistoryEntry(BaseModel):
    state: JobState
    at: datetime
    detail: dict[str, Any] | None = None


class AssetResponse(BaseModel):
    id: UUID
    job_id: UUID
    kind: AssetKind
    local_path: str
    mime: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    duration_sec: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def url(self) -> str:
        return f"/files/{self.local_path}"


class PromptEnhancementResponse(BaseModel):
    id: UUID
    original: str
    enhanced: str
    components: dict[str, Any]
    target_mode: GenerationMode
    target_model: str
    llm_model: str
    creativity_preset: CreativityPreset = DEFAULT_CREATIVITY_PRESET
    temperature: float = temperature_for_preset(DEFAULT_CREATIVITY_PRESET)
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobResponse(BaseModel):
    id: UUID
    mode: GenerationMode
    model: str
    state: JobState
    prompt: str
    enhanced_prompt: str | None = None
    enhancement_id: UUID | None = None
    parent_job_id: UUID | None = None
    retry_of_job_id: UUID | None = None
    source_asset_id: UUID | None = None
    blocked: bool
    vertex_operation_name: str | None = None
    attempts: int
    parameters: dict[str, Any] = Field(default_factory=dict)
    state_history: list[StateHistoryEntry] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    vertex_charged: bool
    created_at: datetime
    updated_at: datetime
    assets: list[AssetResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


GenerationResponse = JobResponse


def job_response_from_job(
    job: Job,
    *,
    assets: list[Asset] | list[AssetResponse] | None = None,
) -> JobResponse:
    return JobResponse(
        id=job.id,
        mode=job.mode,
        model=job.model,
        state=job.state,
        prompt=job.prompt,
        enhanced_prompt=job.enhanced_prompt,
        enhancement_id=job.enhancement_id,
        parent_job_id=job.parent_job_id,
        retry_of_job_id=job.retry_of_job_id,
        source_asset_id=job.source_asset_id,
        blocked=job.blocked,
        vertex_operation_name=job.vertex_operation_name,
        attempts=job.attempts,
        parameters=_public_job_parameters(job.parameters or {}),
        state_history=job.state_history or [],
        error=job.error,
        vertex_charged=job.vertex_charged,
        created_at=job.created_at,
        updated_at=job.updated_at,
        assets=[
            asset
            if isinstance(asset, AssetResponse)
            else AssetResponse.model_validate(asset)
            for asset in assets or []
        ],
    )


def _public_job_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in parameters.items()
        if key != PROVIDER_PROMPT_PARAMETER_KEY
    }


class PipelineResponse(BaseModel):
    id: UUID
    parent: JobResponse
    child: JobResponse
