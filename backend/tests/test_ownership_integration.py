"""Assembled ASGI contracts with explicit fakes; real HTTP/DB proofs use the harness."""
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest

from app.api import generations, pipelines, assets, auth_dependencies
from app.auth.service import AuthError
from app.main import app
from app.models import Job, JobState, GenerationMode
from test_generation_api import ACTOR, FakeGenerationSession, _job_with_asset, _get_generations, _delete_generation
from test_pipeline_api import FakePipelineSession, _get_pipeline, _job as pipeline_job


@pytest.mark.parametrize("role", ["user","master"])
@pytest.mark.parametrize("missing", [False,True])
async def test_access_foreign_delete_is_uniform404_without_storage(role,missing,monkeypatch):
    row = _job_with_asset()
    row.owner_user_id = UUID(int=102)
    session = FakeGenerationSession(jobs=[] if missing else [row])
    spy = Mock()
    monkeypatch.setattr(generations.storage,"delete_file",spy)
    response = await _delete_generation(f"/api/generations/{row.id}",session,
        actor=SimpleNamespace(id=ACTOR.id,role=role))
    assert response.status_code == 404 and response.json() == {"detail":"content_not_found"}
    assert session.deleted == [] and session.commit_count == 0
    spy.assert_not_called()


@pytest.mark.parametrize("role", ["user","master"])
async def test_access_job_read_master_exception(role):
    row = _job_with_asset()
    row.owner_user_id = UUID(int=102)
    response = await _get_generations(f"/api/generations/{row.id}",FakeGenerationSession(jobs=[row]),
        actor=SimpleNamespace(id=ACTOR.id,role=role))
    assert response.status_code == (200 if role=="master" else 404)


@pytest.mark.parametrize("relation", ["parent_job_id","retry_of_job_id","source_asset_id"])
async def test_access_delete_cross_owner_reference409_before_files(relation,monkeypatch):
    target, dependent = _job_with_asset(), _job_with_asset()
    dependent.owner_user_id = UUID(int=102)
    dependent.state = JobState.GENERATING
    setattr(dependent,relation,target.assets[0].id if relation=="source_asset_id" else target.id)
    refs = [[dependent] if relation=="parent_job_id" else [],
            [dependent] if relation=="source_asset_id" else [],
            [dependent] if relation=="retry_of_job_id" else []]
    session = FakeGenerationSession(jobs=[target,dependent],scalar_results=refs)
    spy = Mock()
    monkeypatch.setattr(generations.storage,"delete_file",spy)
    response = await _delete_generation(f"/api/generations/{target.id}",session)
    assert response.status_code == 409 and response.json()=={"detail":"ownership_reference_mismatch"}
    assert getattr(dependent,relation) is not None
    assert session.deleted == [] and session.commit_count == 0
    spy.assert_not_called()


async def test_access_pipeline_foreign_first_child_not_hidden_by_own_child():
    parent = _job_with_asset()
    child = pipeline_job(mode=GenerationMode.I2V,model="fixture",prompt="fixture",parent_job_id=parent.id)
    child.owner_user_id = UUID(int=102)
    own = pipeline_job(mode=GenerationMode.I2V,model="fixture",prompt="fixture",parent_job_id=parent.id)
    response = await _get_pipeline(f"/api/pipelines/{parent.id}",
        FakePipelineSession(jobs=[parent],child_rows=[child,own]),actor=SimpleNamespace(id=ACTOR.id,role="master"))
    assert response.status_code == 404 and response.json()=={"detail":"content_not_found"}


@pytest.mark.parametrize("path", ["/api/generations","/api/generations/"+str(UUID(int=1)),
    "/api/pipelines/"+str(UUID(int=1)),"/api/assets/"+str(UUID(int=1))])
@pytest.mark.parametrize("code", [401,503])
async def test_access_actual_auth_dependency_errors_before_content(path,code,monkeypatch):
    content = FakeGenerationSession()
    async def session():
        yield content
    service = SimpleNamespace(authenticate=AsyncMock(side_effect=AuthError(
        "oauth_provider_unavailable" if code==503 else "session_expired")))
    app.dependency_overrides[auth_dependencies.get_auth_service]=lambda:service
    app.dependency_overrides[generations.get_session]=session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            response = await client.get(path)
        assert response.status_code == code
        assert content.scalar_statements == [] and content.get_calls == []
    finally:
        app.dependency_overrides.pop(generations.get_session,None)
        app.dependency_overrides.pop(auth_dependencies.get_auth_service,None)


@pytest.mark.parametrize("origin", [None,"http://untrusted.invalid"])
async def test_access_delete_origin_before_auth_and_storage(origin,monkeypatch):
    auth = AsyncMock()
    app.dependency_overrides[auth_dependencies.get_auth_service]=lambda:SimpleNamespace(authenticate=auth)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            response = await client.delete("/api/generations/"+str(uuid4()),headers={} if origin is None else {"Origin":origin})
        assert response.status_code == 403
        auth.assert_not_called()
    finally:
        app.dependency_overrides.pop(auth_dependencies.get_auth_service,None)


async def test_access_list_corrupt_reference_returns_whole404():
    row, reference = _job_with_asset(), _job_with_asset()
    reference.owner_user_id = UUID(int=102)
    row.retry_of_job_id = reference.id
    response = await _get_generations("/api/generations",FakeGenerationSession(jobs=[row,reference],scalar_results=[[row]]))
    assert response.status_code==404 and response.json()=={"detail":"content_not_found"}
