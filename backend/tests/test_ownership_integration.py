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


async def _file_ops_request(path, *, role="user", row=None, owner=None, error=None,
                            method="GET", headers=None):
    """Assembled authentication/authorization, only the auth store and SQL are fake."""
    current = SimpleNamespace(id=ACTOR.id, role=role)
    authenticate = AsyncMock(return_value=current)
    if error:
        authenticate.side_effect = AuthError(error)
    session = SimpleNamespace(execute=AsyncMock(return_value=Mock(
        one_or_none=lambda: (row, owner) if row else None)))
    async def db():
        yield session
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[auth_dependencies.get_auth_service] = lambda: SimpleNamespace(authenticate=authenticate)
    app.dependency_overrides[generations.get_session] = db
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url="http://test") as client:
            response = await client.request(method, path, headers=headers)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
    return response, session, authenticate


@pytest.mark.parametrize("kind", ["foreign", "missing", "null_owner", "wrong_job"])
@pytest.mark.parametrize("header", [None, "bytes=0-2", "bytes=99999-", "bad"])
async def test_file_ops_denial_before_storage_or_range(kind, header, monkeypatch):
    from app.api import files
    job_id = UUID(int=451)
    row = None if kind == "missing" else SimpleNamespace(local_path=f"{job_id}/output.png",
        job_id=UUID(int=452) if kind == "wrong_job" else job_id)
    owner = None if kind == "null_owner" else (UUID(int=452) if kind == "foreign" else ACTOR.id)
    resolve, parse, stream = Mock(), Mock(), Mock()
    monkeypatch.setattr(files.storage, "resolve_asset_path", resolve)
    monkeypatch.setattr(files, "_parse_range", parse)
    monkeypatch.setattr(files, "_iter_file", stream)
    response, _, _ = await _file_ops_request(f"/files/{job_id}/output.png", row=row, owner=owner,
                                            headers={"Range": header} if header else None)
    assert response.status_code == 404 and response.json() == {"detail": "content_not_found"}
    assert "content-range" not in response.headers and "accept-ranges" not in response.headers
    resolve.assert_not_called(); parse.assert_not_called(); stream.assert_not_called()


@pytest.mark.parametrize("path", ["/api/ops/health", "/api/ops/metrics", "/metrics"])
@pytest.mark.parametrize("role,error,status", [("user",None,403), ("master","invalid_session",401),
                                             ("master","oauth_provider_unavailable",503)])
async def test_file_ops_ops_denied_before_collectors(path, role, error, status, monkeypatch):
    from app.api import ops, metrics
    collect, snapshot, render = AsyncMock(), Mock(), Mock()
    monkeypatch.setattr(ops, "collect_ops_health", collect)
    monkeypatch.setattr(ops.runtime_metrics, "snapshot", snapshot)
    monkeypatch.setattr(metrics, "render_prometheus_metrics", render)
    response, _, _ = await _file_ops_request(path, role=role, error=error,
                                            headers={"X-Role":"master"})
    assert response.status_code == status
    assert response.json()["detail"] == (AuthError(error).code if error else "master_required")
    collect.assert_not_called(); snapshot.assert_not_called(); render.assert_not_called()


@pytest.mark.parametrize("error,status", [("invalid_session",401),("session_expired",401),
    ("session_revoked",401),("user_suspended",401),("oauth_provider_unavailable",503)])
async def test_file_ops_session_before_path_query_and_range(error,status,monkeypatch):
    from app.api import files
    resolve = Mock()
    monkeypatch.setattr(files.storage,"resolve_asset_path",resolve)
    response, session, authenticate = await _file_ops_request("/files/not-a-uuid/output.png",error=error,
                                                            headers={"Range":"bad"})
    assert response.status_code == status and response.json()=={"detail":AuthError(error).code}
    assert authenticate.await_count == 1
    session.execute.assert_not_called(); resolve.assert_not_called()


@pytest.mark.parametrize("path", ["/files/probe", "/api/ops/probe", "/metrics"])
@pytest.mark.parametrize("code", [200,206,400,401,403,404,405,416,422,500])
async def test_file_ops_cache_all_statuses(path, code):
    from fastapi import Response
    from app.main import ContentApplication
    instance = ContentApplication()
    async def endpoint():
        if code == 500:
            raise RuntimeError("fixed_failure")
        return Response(status_code=code, headers={"Cache-Control":"public, max-age=1"})
    instance.add_api_route(path,endpoint,methods=["GET"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=instance,raise_app_exceptions=False),base_url="http://test") as client:
        response = await client.get(path)
    assert response.status_code == code
    assert response.headers.get_list("cache-control") == ["private, no-store"]
    assert "fixed_failure" not in response.text


@pytest.mark.parametrize("path", ["/files", "/api/ops", "/metrics"])
async def test_file_ops_cache_stream_no_buffering(path):
    from app.main import PrivateContentResponses
    events = [{"type":"http.response.start","status":206,"headers":[]},
              {"type":"http.response.body","body":b"a","more_body":True},
              {"type":"http.response.body","body":b"b","more_body":False}]
    sent=[]
    async def downstream(scope,receive,send):
        for index,event in enumerate(events):
            await send(event)
            assert len(sent)==index+1
        raise RuntimeError("stream_failure")
    async def send(event):
        sent.append(event)
    with pytest.raises(RuntimeError,match="stream_failure"):
        await PrivateContentResponses(downstream)({"type":"http","path":path},None,send)
    assert sent[1] is events[1] and sent[2] is events[2]
    assert sent[0]["headers"]==[(b"cache-control",b"private, no-store")]


@pytest.mark.parametrize("path", ["/files-extra", "/api/ops-extra", "/metrics-extra", "/api/health/live"])
async def test_file_ops_no_cache_prefix_overmatch(path):
    response, _, _ = await _file_ops_request(path)
    assert "cache-control" not in response.headers


@pytest.mark.parametrize("raw_suffix", [b"%6futput.png",b"output%2epng",b"%252e%252e/other",b"../output.png",b"./output.png",b"/output.png",b"output.png%00"])
async def test_file_ops_raw_asgi_alias_before_storage(raw_suffix,monkeypatch):
    from urllib.parse import unquote
    from app.api import files
    raw=b"/files/00000000-0000-0000-0000-000000000123/"+raw_suffix
    path=unquote(raw.decode())
    previous=app.dependency_overrides.copy()
    app.dependency_overrides[auth_dependencies.require_user]=lambda: ACTOR
    query=AsyncMock(return_value=Mock(one_or_none=lambda:None))
    async def db():
        yield SimpleNamespace(execute=query)
    app.dependency_overrides[generations.get_session]=db
    resolve=Mock(); monkeypatch.setattr(files.storage,"resolve_asset_path",resolve)
    scope={"type":"http","asgi":{"version":"3.0","spec_version":"2.4"},"http_version":"1.1",
           "method":"GET","scheme":"http","path":path,"raw_path":raw,"root_path":"",
           "query_string":b"","headers":[],"server":("test",80),"client":("127.0.0.1",1)}
    events=[]
    async def receive():
        return {"type":"http.request","body":b"","more_body":False}
    async def send(event):
        events.append(event)
    try:
        await app(scope,receive,send)
    finally:
        app.dependency_overrides.clear(); app.dependency_overrides.update(previous)
    assert events[0]["status"]==404
    assert (b"cache-control",b"private, no-store") in events[0]["headers"]
    resolve.assert_not_called(); query.assert_not_called()


@pytest.mark.parametrize("path", ["/files/00000000-0000-0000-0000-000000000123/output.png", "/metrics"])
async def test_file_ops_head_no_data_or_storage(path,monkeypatch):
    from app.api import files
    resolve=Mock(); monkeypatch.setattr(files.storage,"resolve_asset_path",resolve)
    response, session, auth = await _file_ops_request(path,method="HEAD")
    assert response.status_code==405 and response.content==b""
    assert response.headers["cache-control"]=="private, no-store"
    assert "content-range" not in response.headers and "accept-ranges" not in response.headers
    resolve.assert_not_called(); session.execute.assert_not_called(); auth.assert_not_called()


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
        assert response.headers["cache-control"] == "private, no-store"
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


@pytest.mark.parametrize("code", [200,201,204,401,403,404,405,422,500])
async def test_access_cache_all_response_statuses_and_unhandled500(code):
    from fastapi import Response
    from app.main import ContentApplication
    instance = ContentApplication()
    @instance.get("/api/generations/probe")
    async def probe():
        if code == 500:
            raise RuntimeError("fixed_failure")
        return Response(status_code=code,headers={"Cache-Control":"public, max-age=3600"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=instance,raise_app_exceptions=False),base_url="http://test") as client:
        response = await client.get("/api/generations/probe")
    assert response.status_code==code
    assert response.headers.get_list("cache-control")==["private, no-store"]
    assert "fixed_failure" not in response.text


async def test_access_cache_redirect_head_and_exact_prefix():
    from fastapi import Response
    from app.main import ContentApplication
    instance=ContentApplication()
    @instance.get("/api/assets/probe")
    async def probe():
        return Response()
    @instance.get("/api/health")
    async def health():
        return Response(headers={"Cache-Control":"public, max-age=1"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=instance),base_url="http://test") as client:
        redirect=await client.get("/api/assets/probe/")
        head=await client.head("/api/assets/probe")
        unrelated=await client.get("/api/assets-unrelated")
        health=await client.get("/api/health")
    assert redirect.status_code==307 and redirect.headers["cache-control"]=="private, no-store"
    assert head.status_code==405 and head.content==b"" and head.headers["cache-control"]=="private, no-store"
    assert "cache-control" not in unrelated.headers
    assert health.headers["cache-control"]=="public, max-age=1"


async def test_access_cache_streaming_not_buffered_or_exception_swallowed():
    from app.main import PrivateContentResponses
    sent=[]
    async def send(message):
        sent.append(message)
    async def stream(scope,receive,send):
        await send({"type":"http.response.start","status":200,"headers":[]})
        await send({"type":"http.response.body","body":b"a","more_body":True})
        assert len(sent)==2
        await send({"type":"http.response.body","body":b"b","more_body":False})
        raise RuntimeError("fixed_stream_failure")
    with pytest.raises(RuntimeError,match="fixed_stream_failure"):
        await PrivateContentResponses(stream)({"type":"http","path":"/api/generations"},None,send)
    assert [message.get("body") for message in sent[1:]]==[b"a",b"b"]


async def test_access_delete_commit_failure_retains_existing_nonatomic_risk(monkeypatch):
    target=_job_with_asset()
    session=FakeGenerationSession(jobs=[target],scalar_results=[[],[],[]],commit_error=RuntimeError("fixed_commit_failure"))
    deleted=Mock()
    monkeypatch.setattr(generations.storage,"delete_file",deleted)
    with pytest.raises(RuntimeError,match="fixed_commit_failure"):
        await _delete_generation(f"/api/generations/{target.id}",session)
    deleted.assert_called_once()
    assert session.commit_count==1  # Files already removed; no false atomicity claim.


async def test_access_delete_refetch_collection_change_fails_before_storage(monkeypatch):
    target=_job_with_asset()
    session=FakeGenerationSession(jobs=[target])
    async def refresh(row,**kwargs):
        row.assets=[]
    session.refresh=refresh
    deleted=Mock()
    monkeypatch.setattr(generations.storage,"delete_file",deleted)
    response=await _delete_generation(f"/api/generations/{target.id}",session)
    assert response.status_code==409
    deleted.assert_not_called()
