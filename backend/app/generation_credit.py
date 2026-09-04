"""Imagen/Veo credit admission and terminal accounting behind one deep Interface."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.credit_accounting import (
    CreditAccountingError, ReservationRequest, UsageEstimate, UsageLine,
    UsageReport, release, reserve, settle,
)
from app.models import Asset, AssetKind, GenerationMode, Job

CREDIT_PARAMETER_KEY = "_generation_credit_v1"

_MODEL_METERS = {
    "imagen-4.0-fast-generate-001": "imagen_fast_image",
    "imagen-4.0-generate-001": "imagen_standard_image",
    "imagen-4.0-ultra-generate-001": "imagen_ultra_image",
    "veo-3.0-fast-generate-001": "veo_fast_ms",
    "veo-3.0-generate-001": "veo_standard_ms",
}
_RELEASE_REASONS = frozenset({
    "provider_failed", "provider_timeout", "provider_rate_limited",
    "cancelled_before_delivery", "delivery_failed",
})


class GenerationCreditError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AdmissionReceipt:
    reservation_id: UUID
    reserved_microcredits: int
    replayed: bool


@dataclass(frozen=True)
class TerminalResult:
    status: str
    consumed_microcredits: int = 0
    released_microcredits: int = 0
    replayed: bool = False


def _fail(code="generation_credit_invalid"):
    raise GenerationCreditError(code)


def _accounting(error: CreditAccountingError):
    raise GenerationCreditError(error.code) from None


def _estimate(job: Job) -> UsageEstimate:
    meter = _MODEL_METERS.get(job.model)
    if meter is None:
        _fail("generation_credit_model_unsupported")
    if ((job.mode == GenerationMode.T2I) != meter.startswith("imagen_")):
        _fail("generation_credit_model_unsupported")
    params = job.parameters or {}
    key = "number_of_images" if job.mode == GenerationMode.T2I else "duration_sec"
    # Pre-G7 failed Jobs may omit parameters; preserve the worker's historical
    # defaults when admitting their first billed retry.
    value = params.get(key, 1 if job.mode == GenerationMode.T2I else 4)
    if type(value) is not int or value <= 0:
        _fail()
    units = value if job.mode == GenerationMode.T2I else value * 1000
    return UsageEstimate(meter, units)


def _metadata(*, job: Job, reservation_id: UUID, role: str,
              top_level_id: UUID, parent_id: UUID | None,
              child_id: UUID | None, estimates: tuple[UsageEstimate, ...]):
    return {
        "version": 1, "role": role,
        "reservation_id": str(reservation_id),
        "reserve_key": f"g7r_{top_level_id.hex}",
        "terminal_key": f"g7t_{top_level_id.hex}",
        "top_level_job_id": str(top_level_id),
        "parent_job_id": str(parent_id) if parent_id else None,
        "child_job_id": str(child_id) if child_id else None,
        "estimates": [{"meter": item.meter, "maximum_units": item.maximum_units}
                      for item in estimates],
    }


async def admit_generation(session, *, job: Job, now: datetime,
                           pipeline_child: Job | None = None) -> AdmissionReceipt:
    if not isinstance(job.id, UUID) or not isinstance(job.owner_user_id, UUID):
        _fail()
    estimates = (_estimate(job),)
    role = "standalone"
    if pipeline_child is not None:
        if (pipeline_child.owner_user_id != job.owner_user_id
                or pipeline_child.parent_job_id != job.id
                or job.mode != GenerationMode.T2I
                or pipeline_child.mode != GenerationMode.I2V):
            _fail("ownership_reference_mismatch")
        estimates = tuple(sorted((estimates[0], _estimate(pipeline_child)),
                                 key=lambda item: item.meter))
        role = "pipeline_parent"
    reserve_key = f"g7r_{job.id.hex}"
    try:
        receipt = await reserve(session, request=ReservationRequest(
            user_id=job.owner_user_id, operation_key=reserve_key,
            estimates=estimates), now=now)
    except CreditAccountingError as error:
        _accounting(error)
    parent_id = job.id if pipeline_child is not None else None
    child_id = pipeline_child.id if pipeline_child is not None else None
    job.parameters = {**(job.parameters or {}), CREDIT_PARAMETER_KEY: _metadata(
        job=job, reservation_id=receipt.reservation_id, role=role,
        top_level_id=job.id, parent_id=parent_id, child_id=child_id,
        estimates=estimates)}
    if pipeline_child is not None:
        pipeline_child.parameters = {**(pipeline_child.parameters or {}), CREDIT_PARAMETER_KEY: _metadata(
            job=pipeline_child, reservation_id=receipt.reservation_id,
            role="pipeline_child", top_level_id=job.id, parent_id=job.id,
            child_id=pipeline_child.id, estimates=estimates)}
    return AdmissionReceipt(receipt.reservation_id, receipt.reserved_microcredits, receipt.replayed)


def strip_credit_metadata(parameters: dict | None) -> dict:
    return {key: value for key, value in (parameters or {}).items()
            if key != CREDIT_PARAMETER_KEY}


def _parse(job: Job):
    raw = (job.parameters or {}).get(CREDIT_PARAMETER_KEY)
    if raw is None:
        return None
    try:
        if raw.get("version") != 1 or raw.get("role") not in {
            "standalone", "pipeline_parent", "pipeline_child"}:
            _fail()
        reservation_id = UUID(raw["reservation_id"])
        top_id = UUID(raw["top_level_job_id"])
        parent_id = UUID(raw["parent_job_id"]) if raw.get("parent_job_id") else None
        child_id = UUID(raw["child_job_id"]) if raw.get("child_job_id") else None
        if raw["reserve_key"] != f"g7r_{top_id.hex}" or raw["terminal_key"] != f"g7t_{top_id.hex}":
            _fail()
        return raw["role"], reservation_id, top_id, parent_id, child_id, raw["terminal_key"]
    except (KeyError, TypeError, ValueError, AttributeError):
        _fail()


async def _usage(session, job_ids: tuple[UUID, ...]) -> tuple[UsageLine, ...]:
    assets = list((await session.scalars(select(Asset).where(
        Asset.job_id.in_(job_ids)).order_by(Asset.id))).all())
    images: dict[str, int] = {}
    videos: dict[str, int] = {}
    models = {row.id: row.model for row in list((await session.scalars(
        select(Job).where(Job.id.in_(job_ids)))).all())}
    for asset in assets:
        meter = _MODEL_METERS.get(models.get(asset.job_id, ""))
        if meter is None:
            _fail()
        if asset.kind == AssetKind.IMAGE:
            if not meter.startswith("imagen_"):
                _fail("generation_credit_delivery_invalid")
            images[meter] = images.get(meter, 0) + 1
        elif asset.kind == AssetKind.VIDEO:
            if not meter.startswith("veo_"):
                _fail("generation_credit_delivery_invalid")
            if asset.duration_sec is None or asset.duration_sec <= 0:
                _fail()
            videos[meter] = videos.get(meter, 0) + round(asset.duration_sec * 1000)
        else:
            _fail("generation_credit_delivery_invalid")
    return tuple(UsageLine(meter, units, "platform_measured")
                 for meter, units in sorted({**images, **videos}.items()) if units > 0)


async def terminalize_generation(session, *, job: Job, succeeded: bool,
                                 reason_code: str | None, now: datetime) -> TerminalResult:
    parsed = _parse(job)
    if parsed is None:
        return TerminalResult("unmanaged")
    role, reservation_id, top_id, parent_id, child_id, terminal_key = parsed
    ids = ((parent_id, child_id) if role == "pipeline_child" else (job.id,))
    ids = tuple(item for item in ids if item is not None)
    usage_lines = await _usage(session, ids)
    if succeeded and role == "pipeline_parent":
        if not usage_lines:
            _fail("generation_credit_delivery_missing")
        return TerminalResult("held")
    if succeeded or (role == "pipeline_child" and usage_lines):
        if not usage_lines:
            _fail("generation_credit_delivery_missing")
        try:
            receipt = await settle(
                session, user_id=job.owner_user_id, reservation_id=reservation_id,
                usage=UsageReport(usage_lines),
                delivery="partial" if not succeeded else "delivered",
                operation_key=terminal_key, now=now)
        except CreditAccountingError as error:
            _accounting(error)
        return TerminalResult(receipt.status, receipt.consumed_microcredits,
                              receipt.released_microcredits, receipt.replayed)
    if reason_code not in _RELEASE_REASONS:
        _fail()
    try:
        receipt = await release(
            session, user_id=job.owner_user_id, reservation_id=reservation_id,
            usage=UsageReport(()), reason_code=reason_code,
            operation_key=terminal_key, now=now)
    except CreditAccountingError as error:
        _accounting(error)
    return TerminalResult(receipt.status, receipt.consumed_microcredits,
                          receipt.released_microcredits, receipt.replayed)
