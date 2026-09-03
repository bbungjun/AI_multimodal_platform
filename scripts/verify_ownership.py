"""Run the credential-free G4 harness; no product login or external services."""
import argparse
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

from mock_auth_support import HarnessError, ROOT, verify_cycles


def content_id(case, kind):
    from uuid import uuid5, NAMESPACE_URL
    return str(uuid5(NAMESPACE_URL, "ownership-content/" + case + "/" + kind))


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
    prompt = {"prompt":"fixture","target_mode":"t2i","target_model":"imagen-4.0-fast-generate-001"}
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
            result = expect(client,"/api/prompts/enhance",prompt,201)
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
        for path,payload in (routes[0],routes[2],routes[3]):
            actor_a.request_bytes("POST",path,payload=payload,expected_status=500)
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
    import smoke_mock_golden_path as golden
    import smoke_mock_retry_flow as retry
    import smoke_mock_i2v_duplicate_guard as duplicate
    for module in (golden, retry, duplicate):
        remaining = runtime.deadline - time.monotonic()
        if remaining <= 0:
            raise HarnessError("cycle_deadline")
        args = SimpleNamespace(timeout_sec=min(90, remaining), poll_interval_sec=0.5,
                               keep_job=False, keep_jobs=False)
        module.run_smoke(args, client=identity.client(runtime.base_url, "a"))
    return 3


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.example")
    parser.add_argument("--cycles", type=int, choices=(1, 2), default=2)
    args = parser.parse_args(argv)
    try:
        results = verify_cycles(args.env_file, args.cycles, scenario=scenarios)
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"phase": "preflight", "provider": "mock", "passed": False}), file=sys.stderr)
        return 1
    return 0 if len(results) == args.cycles and all(row["passed"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
