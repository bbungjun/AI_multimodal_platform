"""Run the credential-free G4 harness; no product login or external services."""
import argparse
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from mock_auth_support import (HarnessError, ROOT, measured, phase, verify_cycles,
    command, validate_aggregate, failure_code)


def content_id(case, kind):
    from uuid import uuid5, NAMESPACE_URL
    return str(uuid5(NAMESPACE_URL, "ownership-content/" + case + "/" + kind))


@measured("admission")
def admission_proof(runtime, identity):
    # Quiesce only this run's owned consumers; admission rows remain deterministic.
    from urllib.request import Request
    from mock_auth_support import ScopedClient, http_transport, safe_url
    runtime.assert_owned()
    runtime.docker(*runtime.compose, "stop", "dispatcher", "worker")
    checks = 0
    records = []
    def expect(client, path, payload, status):
        nonlocal checks
        result = client.request_json("POST", path, payload=payload, expected_status=status)
        checks += 1
        return result
    generation = {"mode":"t2i","model":"imagen-4.0-fast-generate-001","prompt":"fixture"}
    prompt = {"request_id":content_id("admission","prompt"),"prompt":"fixture",
              "target_mode":"t2i","target_model":"imagen-4.0-fast-generate-001"}
    pipeline = {"image_prompt":"fixture","video_prompt":"fixture",
                "image_model":"imagen-4.0-fast-generate-001","video_model":"veo-3.0-fast-generate-001"}
    routes = [("/api/generations",generation), ("/api/prompts/enhance",prompt),
              ("/api/pipelines",pipeline), ("/api/generations/"+content_id("a","retry")+"/retry",None)]
    try:
        runtime.admission_fixture("prepare")
        before = runtime.admission_fixture("counts")
        clients = [ScopedClient(runtime.base_url,secret=None)]
        clients += [identity.client(runtime.base_url,case) for case in
                    ("idle","absolute","revoked","suspended","synthetic","logout")]
        for client in clients:
            for path,payload in routes:
                expect(client,path,payload,401)
        for origin in (None,"http://untrusted.invalid"):
            for path,payload in routes:
                headers = {"Content-Type":"application/json"}
                if origin:
                    headers["Origin"] = origin
                _,_,code = http_transport(Request(safe_url(runtime.base_url,path),
                    data=json.dumps(payload).encode() if payload is not None else b"",
                    headers=headers,method="POST"))
                if code != 403:
                    raise HarnessError("admission_origin_failed")
                checks += 1
        actor_a = identity.client(runtime.base_url,"a")
        for field in ("owner_user_id","user_id","role"):
            for path,payload in routes[:3]:
                expect(actor_a,path,{**payload,field:"forged"},422)
        if runtime.admission_fixture("counts") != before:
            raise HarnessError("rejected_admission_wrote_rows")
        # Every actor, including Master, owns each newly admitted writer result.
        for case in ("a","b","master"):
            client = identity.client(runtime.base_url,case)
            for mode in ("t2i","t2v","i2v"):
                payload = dict(generation,mode=mode)
                if mode != "t2i":
                    payload["model"] = "veo-3.0-fast-generate-001"
                if mode == "i2v":
                    payload["source_asset_id"] = content_id(case,"asset")
                result = expect(client,"/api/generations",payload,201)
                records.append(dict(case=case,kind="job",id=result["id"],retry=False))
            owned_prompt = dict(prompt, request_id=content_id(case,"prompt"))
            result = expect(client,"/api/prompts/enhance",owned_prompt,201)
            records.append(dict(case=case,kind="prompt",id=result["id"],retry=False))
            result = expect(client,"/api/pipelines",pipeline,201)
            records.append(dict(case=case,kind="pipeline",id=result["id"],retry=False))
            result = expect(client,"/api/generations/"+content_id(case,"retry")+"/retry",None,201)
            records.append(dict(case=case,kind="job",id=result["id"],retry=True))
        verified = runtime.admission_fixture("assert_rows",records)
        if verified != {"rows_checked":18,"owners":True,"outbox":True,"lineage":True}:
            raise HarnessError("persisted_admission_proof_failed")
        checks += verified["rows_checked"]
        before = runtime.admission_fixture("counts")
        for case in ("a","b","master"):
            client = identity.client(runtime.base_url,case)
            foreign = "b" if case != "b" else "a"
            for reference in (foreign,"missing"):
                result = expect(client,"/api/generations",
                    dict(generation,enhancement_id=content_id(reference,"enhancement")),404)
                if result != {"detail":"content_not_found"}:
                    raise HarnessError("foreign_detail_leak")
                result = expect(client,"/api/generations",
                    dict(generation,mode="i2v",source_asset_id=content_id(reference,"asset")),404)
                if result != {"detail":"content_not_found"}:
                    raise HarnessError("foreign_detail_leak")
                result = expect(client,"/api/generations/"+content_id(reference,"retry")+"/retry",None,404)
                if result != {"detail":"content_not_found"}:
                    raise HarnessError("foreign_detail_leak")
            # Own semantic failures retain400/409, including an already active source.
            expect(client,"/api/generations",
                   dict(generation,mode="t2v",model="veo-3.0-fast-generate-001",
                        enhancement_id=content_id(case,"enhancement")),400)
            expect(client,"/api/generations",
                   dict(generation,mode="i2v",model="veo-3.0-fast-generate-001",
                        source_asset_id=content_id(case,"asset")),409)
            expect(client,"/api/generations/"+content_id(case,"parent")+"/retry",None,409)
        if runtime.admission_fixture("counts") != before:
            raise HarnessError("foreign_admission_wrote_rows")
        # Real DB fault after Job insertion proves transaction rollback for outbox writers.
        runtime.admission_fixture("arm_commit_failure")
        fault_actor = identity.client(runtime.base_url,"master")
        for client,(path,payload) in ((fault_actor,routes[0]),(fault_actor,routes[2]),(actor_a,routes[3])):
            client.request_bytes("POST",path,payload=payload,expected_status=500)
            checks += 1
        runtime.admission_fixture("disarm_commit_failure")
        if runtime.admission_fixture("counts") != before:
            raise HarnessError("failed_commit_wrote_rows")
        runtime.admission_checks = checks
    finally:
        # Any failure still reaches verify_cycles' guarded whole-project cleanup.
        runtime.admission_fixture("clear")
        runtime.docker(*runtime.compose,"start","dispatcher","worker")
    return checks


def scenarios(runtime, identity):
    admission_proof(runtime, identity)
    access_proof(runtime,identity)
    import smoke_mock_golden_path as golden
    import smoke_mock_retry_flow as retry
    import smoke_mock_i2v_duplicate_guard as duplicate
    with phase(runtime, "smokes"):
        for module in (golden, retry, duplicate):
            remaining = runtime.deadline - time.monotonic()
            if remaining <= 0:
                raise HarnessError("cycle_deadline")
            args = SimpleNamespace(timeout_sec=min(90, remaining), poll_interval_sec=0.5,
                                   keep_job=False, keep_jobs=False,
                                   prompt_request_id=content_id("a", "golden"))
            module.run_smoke(args, client=identity.client(runtime.base_url, "a"))
    execution_proof(runtime, identity)
    return 3


scenarios.requires_access = True
scenarios.suite = "ownership"


def file_ops_scenarios(runtime, identity):
    import smoke_mock_golden_path as golden
    import smoke_mock_retry_flow as retry
    import smoke_mock_i2v_duplicate_guard as duplicate
    from mock_auth_support import E2E_STAGES
    runtime.e2e_completed={case:dict.fromkeys(E2E_STAGES,False) for case in ("a","b")}
    def actor_flow(case):
        with phase(runtime, "e_" + case):
            run_actor(case)
    def run_actor(case):
        client=TrackedActor(runtime,identity,case)
        modules=(golden,retry,duplicate) if case=="a" else (golden,retry)
        for module in modules:
            remaining=runtime.deadline-time.monotonic()
            if remaining<=0:
                raise HarnessError("cycle_deadline")
            args=SimpleNamespace(timeout_sec=min(90,remaining),poll_interval_sec=0.5,
                                 keep_job=False,keep_jobs=False,
                                 prompt_request_id=content_id(case,"golden"))
            module.run_smoke(args,client=client)
        pipeline_end_to_end(runtime,client)
    # Sequential bounded clients avoid executor shutdown waits on a failed actor.
    # No assertion/workload is dropped; each actor still executes its complete flow.
    for case in ("a", "b"):
        actor_flow(case)
    if not all(all(stages.values()) for stages in runtime.e2e_completed.values()):
        raise HarnessError("actor_flow_incomplete")
    runtime.file_ops_completed["E"]=True
    return 2


file_ops_scenarios.requires_file_ops = True
file_ops_scenarios.suite = "file-ops"


def file_id(case, kind="job"):
    from uuid import uuid5,NAMESPACE_URL
    return str(uuid5(NAMESPACE_URL,"ownership-files/"+case+"/"+kind))


def file_check(runtime, condition):
    if not condition:
        raise HarnessError("file_ops_assertion_failed")
    runtime.file_ops_checks+=1


def private_request(runtime,client,path,code=200,*,method="GET",headers=None):
    body,raw_headers,status=client.request_bytes(method,path,expected_status=code,headers=headers)
    result={k.lower():v for k,v in raw_headers.items()}
    file_check(runtime,status==code and result.get("cache-control")=="private, no-store")
    if code in (401,403,404):
        expected={401:"authentication_required",403:"master_required",404:"content_not_found"}[code]
        file_check(runtime,json.loads(body)=={"detail":expected})
        file_check(runtime,"content-range" not in result and "accept-ranges" not in result)
    return body,result


def file_ops_before_auth(runtime,identity):
    from mock_auth_support import FILE_OPS_GROUPS,ScopedClient
    runtime.file_ops_completed=dict.fromkeys(FILE_OPS_GROUPS,False)
    runtime.file_ops_checks=0
    if runtime.access_fixture("prepare_files")!={"prepared":True}:
        raise HarnessError("file_fixture_failed")
    clients={c:identity.client(runtime.base_url,c) for c in ("a","b","master")}
    for case in ("a","b"):
        path="/files/"+file_id(case)+"/output.bin"
        for who in ("a","b","master"):
            permitted=who==case or who=="master"
            body,headers=private_request(runtime,clients[who],path,200 if permitted else 404)
            if permitted:
                file_check(runtime,body==b"0123456789" and headers.get("content-length")=="10")
            for header,code,expected in (("bytes=2-4",206,b"234"),("bytes=7-",206,b"789"),
                ("bytes=-2",206,b"89"),("bytes=8-99",206,b"89"),("items=0-1",400,None),
                ("bytes=0-1,3-4",400,None),("bytes=99-",416,None)):
                body,headers=private_request(runtime,clients[who],path,code if permitted else 404,headers={"Range":header})
                if permitted and expected is not None:
                    file_check(runtime,body==expected and headers.get("content-length")==str(len(expected))
                        and headers.get("accept-ranges")=="bytes")
                    start={"bytes=2-4":2,"bytes=7-":7,"bytes=-2":8,"bytes=8-99":8}[header]
                    file_check(runtime,headers.get("content-range")==f"bytes {start}-{start+len(expected)-1}/10")
                if permitted and code==416:
                    file_check(runtime,headers.get("content-range")=="bytes */10")
        for probe in ("encoded","encoded_slash","double","traversal","dot","duplicate","head"):
            body,headers,code=clients[case].file_probe(probe,file_id(case),expected_status=405 if probe=="head" else 404)
            lower={k.lower():v for k,v in headers.items()}
            file_check(runtime,lower.get("cache-control")=="private, no-store" and "content-range" not in lower)
            file_check(runtime,body==b"" if probe=="head" else json.loads(body)=={"detail":"content_not_found"})
    for case in ("orphan","missing","confused","absent"):
        for client in clients.values():
            private_request(runtime,client,"/files/"+file_id(case)+"/output.bin",404,headers={"Range":"bad"})
    runtime.file_ops_completed["F"]=True
    ops=("/api/ops/health","/api/ops/metrics","/metrics")
    negative={"anonymous":ScopedClient(runtime.base_url,secret=None),
              **{c:identity.client(runtime.base_url,c) for c in ("idle","absolute","revoked","suspended","synthetic")}}
    for path in ops:
        for case,client in clients.items():
            body,headers=private_request(runtime,client,path,200 if case=="master" else 403)
            if case=="master":
                if path=="/metrics":
                    file_check(runtime,headers.get("content-type","").startswith("text/plain;")
                        and b"creativeops_http_requests_total" in body)
                else:
                    file_check(runtime,type(json.loads(body)) is dict)
        for client in negative.values():
            private_request(runtime,client,path,401)
    anonymous=negative["anonymous"]
    for path in ("/api/health","/api/health/live"):
        _,headers,code=anonymous.request_bytes("GET",path,expected_status=200)
        file_check(runtime,code==200 and "cache-control" not in {k.lower():v for k,v in headers.items()})
    runtime.file_ops_completed["O"]=True
    runtime.file_logout_client=identity.client(runtime.base_url,"logout")
    path="/files/"+file_id("logout")+"/output.bin"
    body,_=private_request(runtime,runtime.file_logout_client,path)
    file_check(runtime,body==b"0123456789")
    body,_=private_request(runtime,runtime.file_logout_client,path,206,headers={"Range":"bytes=0-2"})
    file_check(runtime,body==b"012")
    for client in negative.values():
        private_request(runtime,client,path,401,headers={"Range":"bad"})
    print(json.dumps({"file_ops_group":"F_O"}),flush=True)


def file_ops_after_auth(runtime,identity):
    path="/files/"+file_id("logout")+"/output.bin"
    private_request(runtime,runtime.file_logout_client,path,401)
    private_request(runtime,runtime.file_logout_client,path,401,headers={"Range":"bytes=0-2"})
    del runtime.file_logout_client
    runtime.file_ops_completed["V"]=True
    if runtime.access_fixture("clear_files")!={"cleared":True}:
        raise HarnessError("file_cleanup_failed")
    print(json.dumps({"file_ops_group":"V"}),flush=True)


class TrackedActor:
    """Reuse existing smoke assertions, recording only fixed stage booleans."""
    def __init__(self,runtime,identity,case):
        self.runtime=runtime
        self.client=identity.client(runtime.base_url,case)
        self.foreign=identity.client(runtime.base_url,"b" if case=="a" else "a")
        self.stages=runtime.e2e_completed[case]

    def request_json(self,method,path,**kwargs):
        body=self.client.request_json(method,path,**kwargs)
        if method=="POST" and path=="/api/prompts/enhance":
            self.stages["enhance"]=True
        if method=="POST" and path=="/api/generations":
            self.stages["generate"]=True
        if method=="GET" and path.startswith("/api/generations/") and body.get("state")=="completed":
            self.stages["poll"]=True
        if method=="GET" and path.startswith("/api/assets/"):
            self.stages["metadata"]=True
            private_request(self.runtime,self.foreign,path,404)
            private_request(self.runtime,self.foreign,body["url"],404,headers={"Range":"bad"})
            self.stages["foreign"]=True
        if method=="POST" and path.endswith("/retry"):
            source=path.split("/")[-2]
            if body.get("retry_of_job_id")!=source or body.get("id")==source:
                raise HarnessError("actor_retry_lineage_failed")
            self.stages["retry"]=True
        return body

    def request_bytes(self,method,path,**kwargs):
        result=self.client.request_bytes(method,path,**kwargs)
        if method=="GET" and path.startswith("/files/"):
            if result[2]==200: self.stages["file"]=True
            if result[2]==206: self.stages["range"]=True
        if method=="DELETE" and result[2]==204:
            self.stages["delete"]=True
        return result


def pipeline_end_to_end(runtime,client):
    from smoke_mock_golden_path import poll_generation
    pipeline=client.request_json("POST","/api/pipelines",expected_status=201,payload={
        "image_prompt":"fixture","video_prompt":"fixture","image_model":"imagen-4.0-fast-generate-001",
        "video_model":"veo-3.0-fast-generate-001"})
    for kind in ("parent","child"):
        poll_generation(client,job_id=pipeline[kind]["id"],deadline=runtime.deadline,interval_sec=0.5)
    read=client.request_json("GET","/api/pipelines/"+pipeline["id"],expected_status=200)
    if any(read[kind]["state"]!="completed" for kind in ("parent","child")):
        raise HarnessError("actor_pipeline_incomplete")
    client.stages["pipeline"]=True
    private_request(runtime,client.foreign,"/api/pipelines/"+pipeline["id"],404)
    for kind in ("child","parent"):
        client.request_bytes("DELETE","/api/generations/"+pipeline[kind]["id"],expected_status=204)


def access_id(case,kind):
    from uuid import uuid5,NAMESPACE_URL
    return str(uuid5(NAMESPACE_URL,"ownership-access/"+case+"/"+kind))


def delete_race(runtime,client,case):
    runtime.access_fixture("prepare_delete_race",case)
    barrier=Barrier(3)
    admission_path="/api/generations"
    payload={"mode":"i2v","model":"veo-3.0-fast-generate-001","prompt":"fixture",
             "source_asset_id":access_id(case,"parent-asset")}
    if case=="delete_retry":
        admission_path="/api/generations/"+access_id(case,"retry")+"/retry"
        payload=None
    def send(method,path,payload=None):
        barrier.wait(timeout=5)
        body,_,status=client.request_bytes(method,path,payload=payload,expected_status=(201,204,404,409))
        return status,json.loads(body) if body else None
    with ThreadPoolExecutor(max_workers=2) as pool:
        with runtime.delete_source_lock(case):
            deletion=pool.submit(send,"DELETE","/api/generations/"+access_id(case,"parent"))
            admission=pool.submit(send,"POST",admission_path,payload)
            barrier.wait(timeout=5)
            runtime.observe_delete_waiters(case)
        deleted,admitted=deletion.result(timeout=10),admission.result(timeout=10)
    if (deleted[0],admitted[0]) not in ((409,201),(204,404),(204,409)):
        raise HarnessError("access_race_status_failed")
    if admitted[0]==409 and (case!="delete_retry" or admitted[1]!={"detail":"Retry source asset is no longer available."}):
        raise HarnessError("access_race_retry_failed")
    records=[{"kind":"admitted","id":admitted[1]["id"]}] if admitted[0]==201 else []
    if runtime.access_fixture("inspect_delete_race",case,records)!={"race_checks":1}:
        raise HarnessError("access_race_persistence_failed")


@measured("metadata")
def access_proof(runtime,identity):
    from mock_auth_support import ScopedClient,ACCESS_GROUPS,DELETE_CASES
    clients={case:identity.client(runtime.base_url,case) for case in ("a","b","master")}
    completed={group:False for group in ACCESS_GROUPS}
    checks=0
    def check(condition):
        nonlocal checks
        if not condition:
            raise HarnessError("access_assertion_failed")
        checks+=1
    def request(client,path,code=200,*,method="GET",query=None):
        body,headers,status=client.request_bytes(method,path,expected_status=code,query=query)
        check(status==code)
        check({k.lower():v for k,v in headers.items()}.get("cache-control")=="private, no-store")
        data=json.loads(body) if body else None
        if code==404:
            check(data=={"detail":"content_not_found"})
        return data
    runtime.assert_owned()
    print(json.dumps({"proof":"metadata"}),flush=True)
    runtime.docker(*runtime.compose,"stop","dispatcher","worker")
    try:
        check(runtime.access_fixture("prepare_metadata")=={"prepared":True})
        model="imagen-4.0-fast-generate-001"
        for case,client in clients.items():
            permitted={access_id(case,"row-"+str(i)) for i in range(100)}|{
                access_id(case,kind) for kind in ("parent","own-delete","own-dependent","x-parent","x-source","x-retry")}
            first=request(client,"/api/generations",query={"model":model,"limit":20})
            second=request(client,"/api/generations",query={"model":model,"limit":20,"offset":20})
            check(len(first)==20 and len(second)==20)
            check(all(row["id"] in permitted for row in first+second))
            check(not {row["id"] for row in first}&{row["id"] for row in second})
            keys=[(row["created_at"],row["id"]) for row in first+second]
            check(keys==sorted(keys,reverse=True))
            for filters in ({"mode":"t2v"},{"state":"failed"},{"asset_kind":"video"},
                {"mode":"t2v","state":"failed","asset_kind":"video","model":"veo-3.0-fast-generate-001"}):
                rows=request(client,"/api/generations",query=filters)
                check([row["id"] for row in rows]==[access_id(case,"row-1")])
            check(request(client,"/api/generations",query={"model":"absent"})==[])
            if case!="master":
                request(client,"/api/generations",403,query={"scope":"all"})
        all_rows=request(clients["master"],"/api/generations",query={"scope":"all","model":model,"limit":100})
        check(len(all_rows)==100)
        a_ids={access_id("a","row-"+str(i)) for i in range(100)}
        b_ids={access_id("b","row-"+str(i)) for i in range(100)}
        check(any(row["id"] in a_ids for row in all_rows) and any(row["id"] in b_ids for row in all_rows))
        completed["L"]=True
        print(json.dumps({"access_group":"L"}),flush=True)
        for case,client in clients.items():
            for owner in ("a","b","master"):
                for family,kind in (("generations","parent"),("pipelines","parent"),("assets","parent-asset")):
                    code=200 if case==owner or case=="master" else 404
                    response=request(client,"/api/"+family+"/"+access_id(owner,kind),code)
                    if code==200:
                        check(response["id"]==access_id(owner,kind))
                        if family=="pipelines":
                            check(response["child"]["parent_job_id"]==response["parent"]["id"])
            for family in ("generations","pipelines","assets"):
                request(client,"/api/"+family+"/"+access_id("missing","none"),404)
        completed["D"]=completed["P"]=True
        print(json.dumps({"access_group":"D_P"}),flush=True)
        for kind in ("parent","retry","source","enhancement"):
            for client in (clients["a"],clients["master"]):
                request(client,"/api/generations/"+access_id("a","corrupt-"+kind),404)
        for client in (clients["a"],clients["master"]):
            request(client,"/api/generations",404,query={"model":"access-corrupt",
                "scope":"all" if client is clients["master"] else "mine"})
            request(client,"/api/pipelines/"+access_id("a","corrupt-pipeline"),404)
        completed["R"]=True
        print(json.dumps({"access_group":"R"}),flush=True)
        for case,client in clients.items():
            foreign="b" if case!="b" else "a"
            request(client,"/api/generations/"+access_id(foreign,"own-delete"),404,method="DELETE")
            request(client,"/api/generations/"+access_id("missing","none"),404,method="DELETE")
            request(client,"/api/generations/"+access_id(case,"parent"),409,method="DELETE")
            request(client,"/api/generations/"+access_id(case,"child"),409,method="DELETE")
        for kind in ("parent","retry","source"):
            check(request(clients["a"],"/api/generations/"+access_id("a","x-"+kind),409,method="DELETE")
                  =={"detail":"ownership_reference_mismatch"})
        check(runtime.access_fixture("inspect_metadata")=={"inspected":True})
        for case,client in clients.items():
            request(client,"/api/generations/"+access_id(case,"own-delete"),204,method="DELETE")
        check(runtime.access_fixture("inspect_metadata")=={"inspected":True})
        completed["X"]=True
        print(json.dumps({"access_group":"X"}),flush=True)
        negative=[ScopedClient(runtime.base_url,secret=None)]+[identity.client(runtime.base_url,case)
            for case in ("idle","absolute","revoked","suspended","synthetic","logout")]
        for client in negative:
            for path in ("/api/generations","/api/generations/"+access_id("a","parent"),
                         "/api/pipelines/"+access_id("a","parent"),"/api/assets/"+access_id("a","parent-asset")):
                request(client,path,401)
            request(client,"/api/generations/"+access_id("a","parent"),401,method="DELETE")
        request(clients["master"],"/api/generations/"+access_id("a","row-1")+"/retry",404,method="POST")
        completed["S"]=completed["C"]=True
        print(json.dumps({"access_group":"S_C"}),flush=True)
        check(runtime.access_fixture("check_read_queries")=={"query_checks":3})
        completed["Q"]=True
        print(json.dumps({"access_group":"Q"}),flush=True)
        for case in DELETE_CASES:
            delete_race(runtime,clients["a"],case)
        runtime.access_completed=completed
        runtime.access_checks=checks
        runtime.delete_race_checks=2
    finally:
        runtime.access_fixture("clear_metadata")
        runtime.assert_owned()
        runtime.docker(*runtime.compose,"start","dispatcher","worker")


def execution_id(case, kind):
    from uuid import uuid5, NAMESPACE_URL
    return str(uuid5(NAMESPACE_URL, "ownership-execution/" + case + "/" + kind))


def http_race(runtime, client, case):
    runtime.execution_fixture("prepare_race", case)
    create = ("/api/generations", {"mode":"i2v", "model":"veo-3.0-fast-generate-001",
              "prompt":"fixture", "source_asset_id":execution_id(case,"asset")})
    retry1 = ("/api/generations/" + execution_id(case,"retry1") + "/retry", None)
    retry2 = ("/api/generations/" + execution_id(case,"retry2") + "/retry", None)
    requests = {"create_create":(create,create), "create_retry":(create,retry1),
                "retry_retry":(retry1,retry2)}[case]
    barrier = Barrier(3)
    def send(request):
        barrier.wait(timeout=5)
        path, payload = request
        body, _, status = client.request_bytes("POST",path,payload=payload,expected_status=(201,409))
        return status, json.loads(body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        with runtime.source_lock(case):
            futures = [pool.submit(send,request) for request in requests]
            barrier.wait(timeout=5)
            runtime.observe_source_waiters(case)
        results = [future.result(timeout=10) for future in futures]
    if sorted(status for status,_ in results) != [201,409]:
        raise HarnessError("race_status_failed")
    conflict = next(body for status,body in results if status == 409)
    if conflict != {"detail":"An active I2V generation already exists for this source asset."}:
        raise HarnessError("race_conflict_failed")
    if runtime.execution_fixture("check_race",case) != {"race_checks":1}:
        raise HarnessError("race_persistence_failed")
    from uuid import UUID
    return str(UUID(next(body["id"] for status,body in results if status == 201)))


def execution_proof(runtime, identity):
    from mock_auth_support import RACE_CASES
    from smoke_mock_golden_path import poll_generation
    actor_b = identity.client(runtime.base_url,"b")
    runtime.assert_owned()
    runtime.docker(*runtime.compose,"stop","dispatcher","worker")
    try:
        print(json.dumps({"proof":"worker"}),flush=True)
        with phase(runtime, "worker"):
            if runtime.execution_fixture("worker_proof") != {"execution_checks":20}:
                raise HarnessError("worker_proof_incomplete")
        print(json.dumps({"proof":"pipeline"}),flush=True)
        with phase(runtime, "pipeline"):
            if runtime.execution_fixture("pipeline_proof") != {"pipeline_checks":3}:
                raise HarnessError("pipeline_proof_incomplete")
        print(json.dumps({"proof":"http_races"}),flush=True)
        with phase(runtime, "http_races"):
            winners = [(case,http_race(runtime,actor_b,case)) for case in RACE_CASES]
        print(json.dumps({"proof":"expiry"}),flush=True)
        with phase(runtime, "expiry"):
            actor_a = identity.client(runtime.base_url,"a")
            expiry = actor_a.request_json("POST","/api/generations",expected_status=201,
                payload={"mode":"t2i","model":"imagen-4.0-fast-generate-001","prompt":"fixture"})
            print(json.dumps({"proof":"expiry_admitted"}),flush=True)
            if runtime.execution_fixture("expire_session") != {"expired":True}:
                raise HarnessError("session_expiry_failed")
            print(json.dumps({"proof":"session_expired"}),flush=True)
            actor_a.request_bytes("GET","/api/auth/me",expected_status=401)
            print(json.dumps({"proof":"expiry_auth_refused"}),flush=True)
            pipeline_actor = identity.client(runtime.base_url,"master")
            pipeline = pipeline_actor.request_json("POST","/api/pipelines",expected_status=201,
                payload={"image_prompt":"fixture","video_prompt":"fixture",
                         "image_model":"imagen-4.0-fast-generate-001","video_model":"veo-3.0-fast-generate-001"})
    finally:
        runtime.assert_owned()
        runtime.docker(*runtime.compose,"start","dispatcher","worker")
    print(json.dumps({"proof":"celery_completion"}),flush=True)
    with phase(runtime, "celery_completion"):
        print(json.dumps({"proof":"celery_legacy_pipeline"}),flush=True)
        for job_id in [execution_id("pipeline_race","child")]:
            poll_generation(actor_b,job_id=job_id,deadline=runtime.deadline,interval_sec=0.5)
        print(json.dumps({"proof":"celery_race_jobs"}),flush=True)
        for job_id in [value for _,value in winners]:
            poll_generation(actor_b,job_id=job_id,deadline=runtime.deadline,interval_sec=0.5)
        print(json.dumps({"proof":"celery_new_pipeline"}),flush=True)
        for job_id in [pipeline["parent"]["id"], pipeline["child"]["id"]]:
            poll_generation(pipeline_actor,job_id=job_id,deadline=runtime.deadline,interval_sec=0.5)
        print(json.dumps({"proof":"celery_expiry"}),flush=True)
        poll_generation(identity.client(runtime.base_url,"master"),job_id=expiry["id"],deadline=runtime.deadline,interval_sec=0.5)
        for case,_ in winners:
            if runtime.execution_fixture("race_completed",case) != {"race_completed":1}:
                raise HarnessError("race_completion_failed")
        if runtime.execution_fixture("check_completed",records=[{"kind":"pipeline","id":pipeline["id"]},
                {"kind":"expiry","id":expiry["id"]}]) != {"completed_records":2}:
            raise HarnessError("completion_proof_failed")
    runtime.execution_checks = 20
    runtime.pipeline_checks = 4
    runtime.race_checks = 3
    runtime.expiry_checks = 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.example")
    parser.add_argument("--cycles", type=int, choices=(1, 2), default=2)
    parser.add_argument("--suite", choices=("ownership", "file-ops", "all"), default="ownership")
    args = parser.parse_args(argv)
    try:
        summary = run_suites(args.env_file, args.cycles, args.suite)
        print(json.dumps(summary), flush=True)
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"phase": "validate", "provider": "mock", "passed": False,
                          "complete": False, "failure_code": failure_code(error)}), file=sys.stderr)
        return 1
    return 0 if summary["passed"] else 1


def code_revision():
    revision = command(["git", "rev-parse", "HEAD"], timeout=10)
    from re import fullmatch
    if not fullmatch(r"[0-9a-f]{40}", revision):
        raise HarnessError("invalid_code_revision")
    changed = command(["git", "diff", "--name-only", "HEAD"], timeout=10).splitlines()
    untracked = command(["git", "ls-files", "--others", "--exclude-standard"], timeout=10).splitlines()
    if (any(not path.startswith("docs/") for path in changed)
            or any(not path.startswith(".omo/") for path in untracked)):
        raise HarnessError("uncommitted_code")
    return revision


def run_suites(env_file, cycles, suite, *, verify=None):
    if suite not in ("ownership", "file-ops", "all") or type(cycles) is not int or cycles not in (1, 2):
        raise HarnessError("invalid_suite")
    started = time.monotonic()
    revision = code_revision()
    selected = ("ownership", "file-ops") if suite == "all" else (suite,)
    deadline = started + (1800 if suite == "all" else 900)
    rows = []
    verify = verify or verify_cycles
    for name in selected:
        if time.monotonic() >= deadline:
            raise HarnessError("cycle_deadline")
        adapter = scenarios if name == "ownership" else file_ops_scenarios
        current = verify(env_file, cycles, scenario=adapter, command_deadline=deadline)
        # Validate each suite before starting another; failures never become success
        # through a later receipt, and arbitrary payloads are never printed here.
        validate_aggregate(current, (name,), cycles, revision)
        rows.extend(current)
    if code_revision() != revision:
        raise HarnessError("code_revision_changed")
    if time.monotonic() > deadline:
        raise HarnessError("cycle_deadline")
    validate_aggregate(rows, selected, cycles, revision)
    return dict(provider="mock", code_revision=revision, suite=suite, cycles=cycles,
                passed=True, complete=suite == "all" and cycles == 2,
                verified_cycles=len(rows), duration_sec=round(time.monotonic()-started, 3))


if __name__ == "__main__":
    raise SystemExit(main())
