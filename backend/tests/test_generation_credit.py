from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app import generation_credit as subject
from app.credit_accounting import ReservationReceipt, TerminalReceipt
from app.models import Asset, AssetKind, GenerationMode, Job, utc_now


def job(mode=GenerationMode.T2I, model="imagen-4.0-fast-generate-001", *, owner=None):
    return Job(id=uuid4(), owner_user_id=owner or UUID(int=7), mode=mode,
               model=model, parameters={"number_of_images": 2} if mode == GenerationMode.T2I
               else {"duration_sec": 4})


class Rows:
    def __init__(self, rows): self.rows = rows
    def all(self): return self.rows


class Session:
    def __init__(self, assets=(), jobs=()):
        self.results = [list(assets), list(jobs)]
    async def scalars(self, _statement): return Rows(self.results.pop(0))


async def test_admission_maps_model_and_attaches_trusted_metadata(monkeypatch):
    seen = {}
    async def reserve(_session, *, request, now):
        seen["request"] = request
        return ReservationReceipt(uuid4(), request.operation_key, "held", 100, "v1", False)
    monkeypatch.setattr(subject, "reserve", reserve)
    item = job()
    result = await subject.admit_generation(object(), job=item, now=utc_now())
    request = seen["request"]
    assert request.estimates == (subject.UsageEstimate("imagen_fast_image", 2),)
    assert result.reservation_id == UUID(item.parameters[subject.CREDIT_PARAMETER_KEY]["reservation_id"])
    assert item.prompt is None


async def test_pipeline_reserves_once_and_shares_metadata(monkeypatch):
    calls = []
    async def reserve(_session, *, request, now):
        calls.append(request)
        return ReservationReceipt(uuid4(), request.operation_key, "held", 1, "v1", False)
    monkeypatch.setattr(subject, "reserve", reserve)
    parent = job()
    child = job(GenerationMode.I2V, "veo-3.0-fast-generate-001", owner=parent.owner_user_id)
    child.parent_job_id = parent.id
    await subject.admit_generation(object(), job=parent, pipeline_child=child, now=utc_now())
    assert len(calls) == 1
    assert calls[0].estimates == (subject.UsageEstimate("imagen_fast_image", 2),
                                  subject.UsageEstimate("veo_fast_ms", 4000))
    assert parent.parameters[subject.CREDIT_PARAMETER_KEY]["reservation_id"] == child.parameters[subject.CREDIT_PARAMETER_KEY]["reservation_id"]


@pytest.mark.parametrize("model", ["unknown", "veo-3.0-fast-generate-001"])
async def test_invalid_model_or_mode_fails_before_reserve(monkeypatch, model):
    called = False
    async def reserve(*_args, **_kwargs):
        nonlocal called; called = True
    monkeypatch.setattr(subject, "reserve", reserve)
    with pytest.raises(subject.GenerationCreditError):
        await subject.admit_generation(object(), job=job(model=model), now=utc_now())
    assert not called


def managed(item, *, role="standalone", parent=None, child=None):
    top = parent or item.id
    item.parameters[subject.CREDIT_PARAMETER_KEY] = {
        "version": 1, "role": role, "reservation_id": str(uuid4()),
        "reserve_key": f"g7r_{top.hex}", "terminal_key": f"g7t_{top.hex}",
        "top_level_job_id": str(top), "parent_job_id": str(parent) if parent else None,
        "child_job_id": str(child) if child else None, "estimates": [],
    }
    return item


async def test_success_settles_persisted_image_count(monkeypatch):
    item = managed(job())
    assets = [Asset(id=uuid4(), job_id=item.id, kind=AssetKind.IMAGE,
                    local_path="x", mime="image/png") for _ in range(2)]
    seen = {}
    async def settle(*_args, **kwargs):
        seen.update(kwargs)
        return TerminalReceipt(UUID(item.parameters[subject.CREDIT_PARAMETER_KEY]["reservation_id"]),
                               kwargs["operation_key"], "settled", 100, 0, 1, utc_now(), False)
    monkeypatch.setattr(subject, "settle", settle)
    result = await subject.terminalize_generation(Session(assets, [item]), job=item,
        succeeded=True, reason_code=None, now=utc_now())
    assert seen["usage"].lines == (subject.UsageLine("imagen_fast_image", 2, "platform_measured"),)
    assert result.status == "settled"


async def test_failure_releases_without_deliverable(monkeypatch):
    item = managed(job())
    seen = {}
    async def release(*_args, **kwargs):
        seen.update(kwargs)
        return TerminalReceipt(UUID(item.parameters[subject.CREDIT_PARAMETER_KEY]["reservation_id"]),
                               kwargs["operation_key"], "released", 0, 100, 0, utc_now(), False)
    monkeypatch.setattr(subject, "release", release)
    result = await subject.terminalize_generation(Session([], [item]), job=item,
        succeeded=False, reason_code="provider_failed", now=utc_now())
    assert seen["usage"].lines == () and result.status == "released"


async def test_asset_kind_must_match_reserved_model(monkeypatch):
    item = managed(job())
    asset = Asset(id=uuid4(), job_id=item.id, kind=AssetKind.VIDEO,
                  local_path="x", mime="video/mp4", duration_sec=1)
    with pytest.raises(subject.GenerationCreditError, match="delivery_invalid"):
        await subject.terminalize_generation(Session([asset], [item]), job=item,
            succeeded=True, reason_code=None, now=utc_now())


async def test_legacy_job_is_unmanaged():
    result = await subject.terminalize_generation(object(), job=job(), succeeded=True,
                                                   reason_code=None, now=utc_now())
    assert result.status == "unmanaged"


async def test_legacy_retry_shape_uses_worker_default(monkeypatch):
    seen = {}
    async def reserve(_session, *, request, now):
        seen["estimate"] = request.estimates
        return ReservationReceipt(uuid4(), request.operation_key, "held", 1, "v1", False)
    monkeypatch.setattr(subject, "reserve", reserve)
    item = job(); item.parameters = {}
    await subject.admit_generation(object(), job=item, now=utc_now())
    assert seen["estimate"] == (subject.UsageEstimate("imagen_fast_image", 1),)
