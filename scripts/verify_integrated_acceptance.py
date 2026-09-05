"""G11A test-only HTTP acceptance; never a product authentication entrypoint."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from mock_auth_support import HarnessError, ScopedClient, verify_cycles
from verify_ownership import code_revision
from smoke_mock_golden_path import poll_generation, assert_completed_job, PNG_SIGNATURE

GROUPS = ("identity", "usage", "prompt", "generation", "administration",
          "concurrency", "suspension", "audit")


def validate_results(rows, revision):
    if not isinstance(rows, list) or len(rows) != 2:
        raise HarnessError("integration_incomplete")
    for index, row in enumerate(rows, 1):
        if (row.get("passed") is not True or row.get("cleanup") is not True
                or row.get("code_revision") != revision or row.get("cycle") != index
                or row.get("suite") != "custom" or row.get("scenarios") != 8
                or type(row.get("admission_checks")) is not int or row["admission_checks"] < 40):
            raise HarnessError("integration_incomplete")
    return {"provider": "mock", "code_revision": revision, "cycles": 2,
            "groups": list(GROUPS), "checks": [r["admission_checks"] for r in rows],
            "cleanup_remaining": 0, "passed": True, "live_verified": False}


def scenarios(runtime, identity):
    checks = 0
    group = GROUPS[0]

    def check(value):
        nonlocal checks
        if not value:
            raise HarnessError("integration_assertion")
        checks += 1

    def request(client, path, *, method="GET", payload=None, status=200):
        body, headers, _ = client.request_bytes(method, path, payload=payload, expected_status=status)
        check(True)
        cache = {k.lower(): v for k, v in headers.items()}.get("cache-control", "")
        check("private" in cache and "no-store" in cache)
        return json.loads(body)

    try:
        a, b, master = (identity.client(runtime.base_url, name) for name in ("a", "b", "master"))
        anon = ScopedClient(runtime.base_url, secret=None, deadline=runtime.deadline)
        request(anon, "/api/usage/me", status=401)
        actor = request(a, "/api/auth/me")
        request(a, "/api/master/overview", status=403)
        request(master, "/api/master/overview")
        target = actor["id"]
        route = "/api/master/users/" + target + "/commands"

        group = "usage"
        initial = request(a, "/api/usage/me")
        other = request(b, "/api/usage/me")
        check(initial["plan"] == "free" and initial["concurrency"] == {"active_requests": 0, "limit": 1})
        check(len(initial["usage"]) == 7)
        cycle = initial["cycle"]
        check((datetime.fromisoformat(cycle["renews_at"]) - datetime.fromisoformat(cycle["starts_at"])).total_seconds() == 2592000)

        group = "prompt"
        prompt = {"request_id": str(uuid4()), "prompt": "fixture", "target_mode": "t2i",
                  "target_model": "imagen-4.0-fast-generate-001"}
        enhanced = request(a, "/api/prompts/enhance", method="POST", payload=prompt, status=201)
        charged = request(a, "/api/usage/me")
        check(charged["cycle"]["charged_microcredits"] > initial["cycle"]["charged_microcredits"])
        replay = request(a, "/api/prompts/enhance", method="POST", payload=prompt, status=201)
        check(replay["id"] == enhanced["id"])
        check(request(a, "/api/usage/me") == charged)

        group = "generation"
        payload = {"mode": "t2i", "model": "imagen-4.0-fast-generate-001", "prompt": "fixture"}
        job = request(a, "/api/generations", method="POST", payload=payload, status=201)
        completed = poll_generation(a, job_id=job["id"], deadline=runtime.deadline, interval_sec=0.5)
        asset = assert_completed_job(completed)
        content, _, _ = a.request_bytes("GET", asset["url"], expected_status=200)
        check(content.startswith(PNG_SIGNATURE))
        request(b, "/api/generations/" + job["id"], status=404)
        after = request(a, "/api/usage/me")
        check(after["cycle"]["charged_microcredits"] > charged["cycle"]["charged_microcredits"])
        check(after["concurrency"]["active_requests"] == 0 and after["credit"]["held_microcredits"] == 0)
        check(request(b, "/api/usage/me") == other)

        group = "administration"
        plan = {"request_id": str(uuid4()), "action": "plan_change",
                "reason_code": "entitlement_change", "target_plan": "pro"}
        request(a, route, method="POST", payload=plan, status=403)
        result = request(master, route, method="POST", payload=plan)
        check(result["replayed"] is False)
        check(request(master, route, method="POST", payload=plan)["replayed"] is True)
        pro = request(a, "/api/usage/me")
        check(pro["plan"] == "pro" and pro["concurrency"]["limit"] == 3)
        bonus = {"request_id": str(uuid4()), "action": "bonus_grant",
                 "reason_code": "support_adjustment", "amount_microcredits": 1000000}
        request(master, route, method="POST", payload=bonus)
        credited = request(a, "/api/usage/me")
        check(credited["credit"]["available_microcredits"] == pro["credit"]["available_microcredits"] + 1000000)
        check(request(master, route, method="POST", payload=bonus)["replayed"] is True)
        check(request(a, "/api/usage/me") == credited)

        group = "concurrency"
        runtime.assert_owned()
        runtime.docker(*runtime.compose, "stop", "dispatcher", "worker")
        held = [request(a, "/api/generations", method="POST", payload=payload, status=201) for _ in range(3)]
        full = request(a, "/api/usage/me")
        check(full["concurrency"] == {"active_requests": 3, "limit": 3})
        check(full["credit"]["held_microcredits"] > 0)
        request(a, "/api/generations", method="POST", payload=payload, status=429)
        check(request(a, "/api/usage/me") == full)
        check(request(b, "/api/usage/me") == other)

        group = "suspension"
        suspend = {"request_id": str(uuid4()), "action": "suspend", "reason_code": "account_policy"}
        request(master, route, method="POST", payload=suspend)
        request(a, "/api/usage/me", status=401)
        for pending in held:
            check(request(master, "/api/generations/" + pending["id"])["state"] == "cancelled")
        rows = request(master, "/api/master/users")["items"]
        suspended = next(row for row in rows if row["id"] == target)
        check(suspended["status"] == "suspended")
        reactivate = {"request_id": str(uuid4()), "action": "reactivate", "reason_code": "account_reactivated"}
        request(master, route, method="POST", payload=reactivate)
        request(a, "/api/auth/me", status=401)
        request(a, "/api/usage/me", status=401)
        check(request(b, "/api/usage/me") == other)

        group = "audit"
        audits = request(master, "/api/master/audit")["items"]
        expected = {item["request_id"] for item in (plan, bonus, suspend, reactivate)}
        check(len(audits) == 4 and {row["request_id"] for row in audits} == expected)
        check(all(row["target_id"] == target for row in audits))
        check(checks >= 40)
        runtime.admission_checks = checks
        return len(GROUPS)
    except Exception:
        # No exception repr, HTTP body, actor ID, prompt or secret crosses evidence.
        print(json.dumps({"integration_failed_group": group}), flush=True)
        raise HarnessError("integration_failed") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Two owned mock integrated HTTP cycles")
    parser.parse_args(argv)
    evidence = ROOT / ".omo/evidence/issue-153"
    evidence.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex[:12]
    rows = []
    try:
        revision = code_revision()
        rows = verify_cycles(ROOT / ".env.example", 2, scenario=scenarios)
        result = validate_results(rows, revision)
    except (Exception, KeyboardInterrupt):
        result = {"passed": False, "live_verified": False, "failure_code": "integration_incomplete"}
    (evidence / ("integration-" + run_id + ".json")).write_text(
        json.dumps({"result": result, "cycles": rows}, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
