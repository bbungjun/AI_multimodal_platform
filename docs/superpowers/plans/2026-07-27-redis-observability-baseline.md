# Redis Observability Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secret-safe live Redis runtime sampling and a complete Cloud Monitoring backfill so the Redis/Celery baseline includes broker CPU, memory, clients, commands, latency, network, cache, keyspace, persistence, and queue evidence.

**Architecture:** A new pure `scripts/redis_observability.py` module owns Redis snapshot validation and aggregation. The existing benchmark invokes one worker-Pod probe per GKE sample and stores only whitelisted values. A separate `scripts/export_redis_monitoring_metrics.py` CLI queries every Redis metric descriptor with bounded retries, preserves all observed time series, and summarizes named UTC segments without creating workload.

**Tech Stack:** Python 3.11 standard library, redis-py inside the deployed worker, Google Cloud Monitoring REST API through a non-printed `gcloud` access token, pytest, existing GKE benchmark harness.

## Global Constraints

- Use `AI_PROVIDER=mock`; do not call Gemini, Imagen, Veo, or other paid Vertex APIs.
- Do not create new deployed benchmark traffic while backfilling the existing run.
- Never print or persist Redis host, port, broker URL, password, access token, ADC payload, or service-account JSON.
- Treat Cloud Monitoring as 60-second post-hoc evidence, not phase-exact harness evidence.
- Treat no-series as `not_observed`; do not convert it to numeric zero.
- Use `apply_patch` for repository edits and preserve unrelated work.
- Run focused tests red then green before each production change.

## File Structure

- Create `scripts/redis_observability.py`
  - Safe snapshot schema, validation, counter/gauge/command aggregation, monitoring point normalization, segment summaries, SHA-256 helper.
- Modify `scripts/benchmark_mock_orchestration.py`
  - Add its own `scripts/` directory to `sys.path`, then import the pure helper;
    inline worker-Pod Redis probe, live sample integration, preflight snapshot,
    `redis_summary`.
- Create `scripts/export_redis_monitoring_metrics.py`
  - Release-profile guard, Monitoring REST client, bounded retry, descriptor/time-series export CLI.
- Modify `infra/gcp/release-profile.json`
  - Add non-secret `redis_instance_name`.
- Create `backend/tests/test_redis_observability_script.py`
  - Pure Redis and Monitoring contract tests.
- Modify `backend/tests/test_benchmark_mock_orchestration_script.py`
  - GKE sampler/probe/report integration tests.
- Modify `backend/tests/test_supply_chain_release.py`
  - Pin the expected Redis instance in the non-secret profile.
- Create ignored raw artifact
  `benchmarks/orchestration/runs/redis-celery-20260727T0626Z-redis-monitoring.json`.
- Create committed summary
  `docs/evidence/issue-83-redis-monitoring-backfill.json`.
- Modify `docs/evidence/issue-83-redis-celery-baseline.md`,
  `docs/runbooks/mock-orchestration-benchmark.md`, and `docs/current-work.md`.

---

### Task 1: Safe Redis snapshot and live aggregation

**Files:**
- Create: `scripts/redis_observability.py`
- Create: `backend/tests/test_redis_observability_script.py`

**Interfaces:**
- Produces: `validate_redis_snapshot(value: Any) -> dict[str, Any]`
- Produces: `summarize_redis_samples(samples: list[dict[str, Any]]) -> dict[str, Any]`
- Produces constants: `REDIS_GAUGE_FIELDS`, `REDIS_COUNTER_FIELDS`,
  `REDIS_STATE_FIELDS`, `REDIS_COMMAND_FIELDS`

- [ ] **Step 1: Write failing snapshot-whitelist tests**

Create a representative snapshot containing allowed values plus
`password`, `host`, `port`, `broker_url`, and an unknown command field.
Assert the normalized result contains this shape and no forbidden keys:

```python
normalized = module.validate_redis_snapshot(
    {
        "queue_depth": 4,
        "gauges": {
            "connected_clients": 6,
            "used_memory": 4_600_000,
            "password": "must-not-survive",
        },
        "counters": {
            "total_commands_processed": 100,
            "total_net_input_bytes": 200,
        },
        "states": {"role": "master", "aof_enabled": 0},
        "keyspace": {"db0": {"keys": 3, "expires": 1, "avg_ttl": 500}},
        "commands": {
            "lpush": {
                "calls": 10,
                "usec": 50,
                "usec_per_call": 5.0,
                "raw_payload": "drop-me",
            }
        },
        "broker_url": "redis://private",
    }
)
assert normalized["queue_depth"] == 4
assert normalized["gauges"] == {
    "connected_clients": 6,
    "used_memory": 4_600_000,
}
assert normalized["commands"]["lpush"] == {
    "calls": 10,
    "usec": 50,
    "usec_per_call": 5.0,
}
assert "password" not in repr(normalized).lower()
assert "redis://" not in repr(normalized)
```

- [ ] **Step 2: Run the whitelist test and verify RED**

Run:

```bash
python3 -m pytest -s \
  backend/tests/test_redis_observability_script.py::test_snapshot_validation_keeps_only_safe_whitelisted_fields \
  -q
```

Expected: FAIL because `scripts/redis_observability.py` or
`validate_redis_snapshot` does not exist.

- [ ] **Step 3: Implement the minimal snapshot contract**

Define immutable field tuples and normalize only numeric/bool/string values
explicitly listed by the contract. Accept command names matching
`[a-z0-9_|-]{1,64}` and keyspace names matching `db[0-9]+`. Ignore all extra
keys rather than copying input dictionaries.

- [ ] **Step 4: Run the whitelist test and verify GREEN**

Run the Step 2 command. Expected: `1 passed`.

- [ ] **Step 5: Write failing aggregation tests**

Use two samples ten seconds apart. Assert:

```python
summary = module.summarize_redis_samples(samples)
assert summary["queue_depth"]["max"] == 9
assert summary["counters"]["total_commands_processed"]["delta"] == 40
assert summary["cpu"]["parent_utilization_ratio"] == pytest.approx(0.12)
assert summary["cache_hit_ratio"] == pytest.approx(0.75)
assert summary["commands"]["lpush"]["calls_delta"] == 8
assert summary["commands"]["lpush"]["weighted_usec_per_call"] == pytest.approx(4.0)
```

Add a second test where the final counter is smaller and assert
`{"delta": None, "counter_reset": True}`.

- [ ] **Step 6: Run aggregation tests and verify RED**

Run:

```bash
python3 -m pytest -s backend/tests/test_redis_observability_script.py -q
```

Expected: whitelist test passes; aggregation tests fail because
`summarize_redis_samples` is missing.

- [ ] **Step 7: Implement gauge, counter, CPU, cache, and command aggregation**

Use the existing linear-interpolation percentile rule. Parse sample `at`
timestamps as timezone-aware UTC. Calculate CPU utilization as cumulative CPU
seconds delta divided by elapsed wall seconds. For commands absent at the first
sample, use a zero baseline; if a present counter decreases, mark reset.

- [ ] **Step 8: Run focused tests and commit**

Run:

```bash
python3 -m pytest -s backend/tests/test_redis_observability_script.py -q
git diff --check
```

Expected: all new tests pass and no whitespace errors.

Commit:

```bash
git add scripts/redis_observability.py \
  backend/tests/test_redis_observability_script.py
git commit -m "feat: define safe Redis runtime metrics"
```

---

### Task 2: Integrate live Redis INFO into the GKE harness

**Files:**
- Modify: `scripts/benchmark_mock_orchestration.py` near
  `_redis_queue_depth`, `collect_gke_preflight`, `GkeSampler.sample_once`,
  `_resource_summary`, and `run_benchmark`
- Modify: `backend/tests/test_benchmark_mock_orchestration_script.py`
- Modify: `infra/gcp/release-profile.json`
- Modify: `backend/tests/test_supply_chain_release.py`

**Interfaces:**
- Consumes: `validate_redis_snapshot`, `summarize_redis_samples`, and field
  tuples from Task 1
- Produces: `_redis_runtime_snapshot(*, kubectl, namespace, worker_pod) -> dict`
- Produces report fields: `preflight.gke.initial_redis`,
  `samples[*].redis`, and `redis_summary`

- [ ] **Step 1: Write failing probe and sampler tests**

Monkeypatch `_command_output` to return a safe JSON snapshot and assert:

```python
snapshot = module._redis_runtime_snapshot(
    kubectl="kubectl",
    namespace="creativeops-portfolio",
    worker_pod="worker-1",
)
assert snapshot["queue_depth"] == 0
assert snapshot["gauges"]["connected_clients"] == 6
assert "broker" not in repr(snapshot).lower()
```

Update the sampler test so `sample_once()` contains `sample["redis"]` and no
separate Redis queue command. Add malformed JSON and timeout tests that become
`sample_error`.

- [ ] **Step 2: Run integration tests and verify RED**

Run:

```bash
python3 -m pytest -s \
  backend/tests/test_benchmark_mock_orchestration_script.py \
  -q
```

Expected: FAIL because `_redis_runtime_snapshot` and `redis_summary` are absent.

- [ ] **Step 3: Implement one inline safe Redis probe**

Generate a `python -c` program that:

1. obtains settings without printing them;
2. connects through `settings.celery_broker_url`;
3. calls `INFO`, `INFO commandstats`, `INFO keyspace`, and queue `LLEN`;
4. creates new dictionaries from Task 1 field-name constants;
5. prints only the snapshot JSON;
6. closes Redis in `finally`.

Replace `_redis_queue_depth` with `_redis_runtime_snapshot`; derive preflight
queue depth from `snapshot["queue_depth"]`.

- [ ] **Step 4: Integrate sample and report aggregation**

Store the safe snapshot at `sample["redis"]`. Add:

```python
report["redis_summary"] = summarize_redis_samples(report["samples"])
```

Keep `resource_summary.peak_celery_queue_depth` for backward compatibility by
reading `sample["redis"]["queue_depth"]`.

- [ ] **Step 5: Pin Redis instance in the release profile**

Add:

```json
"redis_instance_name": "creativeops-portfolio-redis"
```

Require this field in `_load_release_profile` and assert it in
`test_release_profile_is_non_secret_and_matches_personal_live_topology`.

- [ ] **Step 6: Run focused tests and local orchestration regression**

Run:

```bash
python3 -m pytest -s \
  backend/tests/test_redis_observability_script.py \
  backend/tests/test_benchmark_mock_orchestration_script.py \
  backend/tests/test_supply_chain_release.py \
  -q

python3 scripts/benchmark_mock_orchestration.py \
  --base-url http://127.0.0.1:8000 \
  --warmup-jobs 1 \
  --steady-jobs 1 \
  --burst-jobs 1 \
  --burst-rounds 1 \
  --steady-concurrency 1 \
  --burst-concurrency 1 \
  --poll-interval-sec 0.1 \
  --phase-timeout-sec 60 \
  --run-id issue83-redis-observability-local \
  --output /tmp/issue83-redis-observability-local.json \
  --execute
```

Expected: focused tests pass; the existing local 3-job flow completes and
cleans up. Local mode does not claim GKE Redis samples.

- [ ] **Step 7: Commit**

```bash
git add scripts/benchmark_mock_orchestration.py \
  backend/tests/test_benchmark_mock_orchestration_script.py \
  backend/tests/test_supply_chain_release.py \
  infra/gcp/release-profile.json
git commit -m "feat: sample Redis runtime during GKE benchmarks"
```

---

### Task 3: Normalize and summarize Cloud Monitoring time series

**Files:**
- Modify: `scripts/redis_observability.py`
- Modify: `backend/tests/test_redis_observability_script.py`

**Interfaces:**
- Produces: `normalize_monitoring_series(descriptor, series) -> dict[str, Any]`
- Produces: `summarize_monitoring_segments(series, segments) -> dict[str, Any]`
- Produces: `sha256_file(path: Path) -> str`

- [ ] **Step 1: Write failing normalization tests**

Cover `int64Value` strings, doubles, booleans, ascending timestamp ordering,
metric labels, allowed resource labels, DELTA versus GAUGE, and an empty series.
Assert no Authorization header or request URL can appear in the normalized
result.

- [ ] **Step 2: Run normalization tests and verify RED**

Run:

```bash
python3 -m pytest -s backend/tests/test_redis_observability_script.py -q
```

Expected: new tests fail because Monitoring helpers do not exist.

- [ ] **Step 3: Implement normalization**

Return:

```python
{
    "metric_type": descriptor["type"],
    "metric_kind": descriptor["metricKind"],
    "value_type": descriptor["valueType"],
    "unit": descriptor.get("unit", ""),
    "metric_labels": {...},
    "resource": {
        "type": "redis_instance",
        "labels": {
            "project_id": "...",
            "region": "...",
            "instance_id": "...",
            "node_id": "...",
        },
    },
    "points": [
        {"start": "...", "end": "...", "value": 1.0},
    ],
}
```

Ignore resource labels outside the explicit four-key whitelist.

- [ ] **Step 4: Write failing segment-summary and hash tests**

Use three named half-open UTC segments and points exactly on boundaries.
Assert DELTA sums, GAUGE p50/p95/max/last, observed-zero preservation,
not-observed metric listing, and SHA-256 of a temporary artifact.

- [ ] **Step 5: Run segment tests and verify RED**

Run the Task 3 focused file. Expected: only the new summary/hash tests fail.

- [ ] **Step 6: Implement segment summaries and hash**

Assign DELTA points by `[start, end)` overlap using their interval end timestamp
and assign GAUGE points by point end timestamp. Record the 60-second alignment
and half-open boundary rule in output metadata.

- [ ] **Step 7: Run tests and commit**

```bash
python3 -m pytest -s backend/tests/test_redis_observability_script.py -q
git diff --check
git add scripts/redis_observability.py \
  backend/tests/test_redis_observability_script.py
git commit -m "feat: summarize Redis Monitoring time series"
```

---

### Task 4: Build the guarded Monitoring exporter CLI

**Files:**
- Create: `scripts/export_redis_monitoring_metrics.py`
- Modify: `backend/tests/test_redis_observability_script.py`

**Interfaces:**
- Consumes Task 3 normalization and summary helpers
- Produces: `MonitoringClient.request_json(path, params) -> dict[str, Any]`
- Produces CLI arguments:
  `--profile`, `--start`, `--end`, repeated
  `--segment NAME,START,END`, `--output`, `--execute`

- [ ] **Step 1: Write failing guard and dry-run tests**

Assert the default is dry-run, profile account/project/region/instance are
required, start/end are timezone-aware UTC, segments are within the export
window, and invalid instance/project values stop before obtaining a token.

- [ ] **Step 2: Run CLI tests and verify RED**

Run:

```bash
python3 -m pytest -s backend/tests/test_redis_observability_script.py -q
```

Expected: FAIL because the exporter module does not exist.

- [ ] **Step 3: Implement guards and bounded HTTP retry**

Use `gcloud auth print-access-token` through `_command_output`-equivalent
subprocess handling, keep the token only in memory, and send it only through
the Authorization header. Retry HTTP 429 and 5xx with delays
`1, 2, 4, 8` seconds; stop after five total attempts. Never include headers,
token, or full URL in public errors.

- [ ] **Step 4: Write failing pagination and retry tests**

Use an injected transport to return:

- two descriptor pages totaling three descriptors;
- one metric with two time-series pages;
- one no-series metric;
- one initial 429 followed by success;
- persistent 429 exhaustion.

Assert available/not-observed/error counts and bounded attempt count.

- [ ] **Step 5: Run tests and verify RED**

Expected: pagination/retry tests fail before client implementation is complete.

- [ ] **Step 6: Implement descriptor scan, time-series export, and artifact**

Query all `redis.googleapis.com/` descriptors. For each descriptor, query:

```text
metric.type="{metric_type}"
AND resource.type="redis_instance"
AND resource.labels.instance_id="{instance_resource_name}"
```

Normalize observed series, preserve no-series separately, calculate named
segment summaries, and write JSON only when `--execute` is present.

- [ ] **Step 7: Run focused tests and safe CLI dry-run**

```bash
python3 -m pytest -s backend/tests/test_redis_observability_script.py -q

test -n "$CLOUDSDK_CONFIG"

python3 scripts/export_redis_monitoring_metrics.py \
  --profile infra/gcp/release-profile.json \
  --start 2026-07-27T06:21:00Z \
  --end 2026-07-27T06:32:00Z \
  --segment idle,2026-07-27T06:21:00Z,2026-07-27T06:24:00Z \
  --segment benchmark,2026-07-27T06:24:00Z,2026-07-27T06:27:00Z \
  --segment recovery,2026-07-27T06:27:00Z,2026-07-27T06:32:00Z \
  --output benchmarks/orchestration/runs/redis-celery-20260727T0626Z-redis-monitoring.json
```

Expected: guards and planned query count print; no file is written.

- [ ] **Step 8: Commit**

```bash
git add scripts/export_redis_monitoring_metrics.py \
  backend/tests/test_redis_observability_script.py
git commit -m "feat: export Redis Cloud Monitoring evidence"
```

---

### Task 5: Recover the existing 39 Redis metrics and publish evidence

**Files:**
- Create ignored:
  `benchmarks/orchestration/runs/redis-celery-20260727T0626Z-redis-monitoring.json`
- Create: `docs/evidence/issue-83-redis-monitoring-backfill.json`
- Modify: `docs/evidence/issue-83-redis-celery-baseline.md`
- Modify: `docs/runbooks/mock-orchestration-benchmark.md`
- Modify: `docs/current-work.md`

**Interfaces:**
- Consumes exporter CLI from Task 4
- Produces SHA-bound committed Redis evidence used by PR #85 and the future A/B

- [ ] **Step 1: Execute the read-only historical export**

Run the Task 4 command with `--execute` and explicit personal
`CLOUDSDK_CONFIG`, project, and account guards.

Expected:

- descriptors scanned: `192`
- available metrics: `39`
- query errors: `0`
- no jobs, provider calls, deployment mutations, or Redis writes

- [ ] **Step 2: Verify raw artifact safety**

Run:

```bash
rg -ni \
  'authorization|bearer|password|private_key|client_secret|redis://|rediss://|access_token' \
  benchmarks/orchestration/runs/redis-celery-20260727T0626Z-redis-monitoring.json
```

Expected: no matches.

Verify the raw file remains ignored:

```bash
git check-ignore \
  benchmarks/orchestration/runs/redis-celery-20260727T0626Z-redis-monitoring.json
```

- [ ] **Step 3: Create the committed summary**

Write `docs/evidence/issue-83-redis-monitoring-backfill.json` with:

- export window and the three named segments;
- raw SHA-256;
- descriptor/available/not-observed/error counts;
- all 39 available metric names;
- segment summaries for CPU, main-thread CPU, memory, clients, commands,
  weighted command latency, network, cache, keyspace, evictions, rejects,
  persistence, and replication;
- explicit `post_hoc_60s_aligned` source and attribution limits.

- [ ] **Step 4: Update human-readable evidence and runbook**

Add a Redis service section to the baseline document. Clearly distinguish:

- original harness direct values;
- Redis Cloud Monitoring post-hoc values;
- idle comparison;
- future live Redis `INFO` contract.

Document the exporter command, ingestion-delay expectation, query quota/backoff,
raw hash verification, and no-secret check in the runbook. Update
`docs/current-work.md` with recovered counts and remaining Issue #84 boundary.

- [ ] **Step 5: Validate JSON/docs and commit**

```bash
python3 -m json.tool \
  docs/evidence/issue-83-redis-monitoring-backfill.json >/dev/null
git diff --check
git status --short --branch
git diff --cached --name-only
```

Commit only committed evidence and docs:

```bash
git add docs/evidence/issue-83-redis-monitoring-backfill.json \
  docs/evidence/issue-83-redis-celery-baseline.md \
  docs/runbooks/mock-orchestration-benchmark.md \
  docs/current-work.md
git commit -m "docs: recover complete Redis baseline metrics"
```

---

### Task 6: Final verification, review, and PR update

**Files:**
- Verify all files changed by Tasks 1-5
- Update PR #85 and Issue #83 comments without changing deployment state

**Interfaces:**
- Produces a clean, pushed branch with artifact-backed Redis baseline evidence

- [ ] **Step 1: Run focused and full verification**

```bash
python3 -m pytest -s \
  backend/tests/test_redis_observability_script.py \
  backend/tests/test_benchmark_mock_orchestration_script.py \
  backend/tests/test_supply_chain_release.py \
  -q

docker run --rm \
  -v "$(git rev-parse --show-toplevel):/repo:ro" \
  -e AI_PROVIDER=mock \
  python:3.11-slim \
  sh -lc "cp -a /repo/backend /tmp/backend-install && \
    cd /tmp/backend-install && \
    python -m pip install --disable-pip-version-check -q '.[dev]' && \
    cd /repo/backend && \
    python -m pytest -p no:cacheprovider -q"

cd frontend && npm run build && cd ..
docker compose --env-file .env.example config --quiet
git diff --check origin/main...HEAD
git status --short --branch
git diff --cached --name-only
```

- [ ] **Step 2: Run GKE read-only dry-run**

Use explicit personal `CLOUDSDK_CONFIG` and `KUBECONFIG`. Pass the restored
rate-limit minimum `5`; do not pass `--execute`.

Expected: exact account/project/context, mock/Celery, idle queue, and safe Redis
snapshot pass; jobs created `0`.

- [ ] **Step 3: Request independent code/evidence review**

Ask the reviewer to verify:

- no connection details or tokens can enter reports;
- live counter/gauge/command aggregation semantics;
- Cloud Monitoring 60-second window attribution;
- all 39 observed metrics and no-series distinction;
- raw SHA and evidence calculations;
- no new deployed load or provider call.

- [ ] **Step 4: Push and update GitHub**

```bash
git push
gh pr checks 85 --repo bbungjun/AI_multimodal_platform
```

Update PR #85 and Issue #83 with the Redis service metrics, source limitations,
verification counts, and review outcome. Keep the PR draft.

- [ ] **Step 5: Final remote read-back**

```bash
git rev-list --left-right --count \
  origin/codex/issue-83-redis-celery-baseline...HEAD
gh pr view 85 \
  --repo bbungjun/AI_multimodal_platform \
  --json state,isDraft,headRefOid,mergeStateStatus,url
```

Expected: branch `0 0`, clean worktree, draft PR open, checks passing.
