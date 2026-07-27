from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from uuid import uuid4


TERMINAL_STATES = {"completed", "failed", "cancelled"}
WORKER_ENVIRONMENT_KEYS = (
    "AI_PROVIDER",
    "JOB_DISPATCH_MODE",
    "RATE_LIMIT_IMAGEN_PER_MIN",
    "CELERY_WORKER_CONCURRENCY",
    "CELERY_DEFAULT_QUEUE",
)
WORKLOAD_PREFIXES = (
    "creativeops-api-",
    "creativeops-dispatcher-",
    "creativeops-worker-",
)


class BenchmarkError(RuntimeError):
    """Expected benchmark failure with an operator-facing message."""


def build_phase_specs(
    *,
    warmup_jobs: int = 20,
    steady_jobs: int = 100,
    burst_jobs: int = 200,
    burst_rounds: int = 5,
    steady_concurrency: int = 2,
    burst_concurrency: int = 50,
) -> list[dict[str, Any]]:
    values = {
        "warmup_jobs": warmup_jobs,
        "steady_jobs": steady_jobs,
        "burst_jobs": burst_jobs,
        "burst_rounds": burst_rounds,
        "steady_concurrency": steady_concurrency,
        "burst_concurrency": burst_concurrency,
    }
    invalid = [name for name, value in values.items() if value < 1]
    if invalid:
        raise BenchmarkError(
            "Workload values must be positive: " + ", ".join(sorted(invalid))
        )

    phases: list[dict[str, Any]] = [
        {
            "name": "warmup",
            "jobs": warmup_jobs,
            "submit_concurrency": min(steady_concurrency, warmup_jobs),
            "include_in_aggregate": False,
        },
        {
            "name": "steady",
            "jobs": steady_jobs,
            "submit_concurrency": min(steady_concurrency, steady_jobs),
            "include_in_aggregate": True,
        },
    ]
    phases.extend(
        {
            "name": f"burst-{round_number}",
            "jobs": burst_jobs,
            "submit_concurrency": min(burst_concurrency, burst_jobs),
            "include_in_aggregate": True,
        }
        for round_number in range(1, burst_rounds + 1)
    )
    return phases


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise BenchmarkError("Cannot calculate a percentile from empty values.")
    if not 0 <= quantile <= 1:
        raise BenchmarkError("Percentile quantile must be between 0 and 1.")

    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    weight = position - lower_index
    return ordered[lower_index] * (1 - weight) + ordered[upper_index] * weight


def parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise BenchmarkError(f"Expected an ISO timestamp, got {value!r}.")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BenchmarkError(f"Invalid ISO timestamp: {value!r}.") from exc
    if parsed.tzinfo is None:
        raise BenchmarkError(f"Timestamp is missing timezone information: {value!r}.")
    return parsed.astimezone(timezone.utc)


def _history_entries(job: dict[str, Any], state: str) -> list[dict[str, Any]]:
    history = job.get("state_history")
    if not isinstance(history, list):
        return []
    return [
        entry
        for entry in history
        if isinstance(entry, dict) and entry.get("state") == state
    ]


def _milliseconds_between(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds() * 1000)


def analyze_job(
    job: dict[str, Any],
    *,
    phase: str,
    submit_latency_ms: float,
    include_in_aggregate: bool = True,
) -> dict[str, Any]:
    job_id = job.get("id")
    if not isinstance(job_id, str) or not job_id:
        raise BenchmarkError("Generation response did not contain a job id.")

    created_value = job.get("created_at")
    created_at = parse_timestamp(created_value)
    queued_entries = _history_entries(job, "queued")
    generating_entries = _history_entries(job, "generating")
    completed_entries = _history_entries(job, "completed")
    queued_at = (
        parse_timestamp(queued_entries[0]["at"])
        if queued_entries and isinstance(queued_entries[0].get("at"), str)
        else None
    )
    completed_at = (
        parse_timestamp(completed_entries[-1]["at"])
        if completed_entries and isinstance(completed_entries[-1].get("at"), str)
        else None
    )

    runner = None
    if queued_entries:
        detail = queued_entries[0].get("detail")
        if isinstance(detail, dict) and isinstance(detail.get("runner"), str):
            runner = detail["runner"]

    rate_limit_wait_sec = None
    if generating_entries:
        detail = generating_entries[0].get("detail")
        if isinstance(detail, dict) and isinstance(
            detail.get("rate_limit_wait_sec"),
            int | float,
        ):
            rate_limit_wait_sec = float(detail["rate_limit_wait_sec"])

    attempts = int(job.get("attempts") or 0)
    queued_count = len(queued_entries)
    return {
        "job_id": job_id,
        "phase": phase,
        "include_in_aggregate": bool(include_in_aggregate),
        "state": str(job.get("state") or "unknown"),
        "runner": runner,
        "attempts": attempts,
        "queued_transition_count": queued_count,
        "duplicate_execution": attempts > 1 or queued_count > 1,
        "rate_limit_wait_sec": rate_limit_wait_sec,
        "submit_latency_ms": float(submit_latency_ms),
        "claim_latency_ms": (
            None
            if queued_at is None
            else _milliseconds_between(created_at, queued_at)
        ),
        "execution_latency_ms": (
            None
            if queued_at is None or completed_at is None
            else _milliseconds_between(queued_at, completed_at)
        ),
        "end_to_end_latency_ms": (
            None
            if completed_at is None
            else _milliseconds_between(created_at, completed_at)
        ),
        "created_at": created_at.isoformat(),
        "queued_at": None if queued_at is None else queued_at.isoformat(),
        "completed_at": None if completed_at is None else completed_at.isoformat(),
        "error": job.get("error") if isinstance(job.get("error"), dict) else None,
    }


def _latency_summary(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "p50": round(percentile(values, 0.50), 3),
        "p95": round(percentile(values, 0.95), 3),
        "p99": round(percentile(values, 0.99), 3),
        "max": round(max(values), 3),
    }


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    included = [
        record for record in records if record.get("include_in_aggregate") is True
    ]
    completed = [record for record in included if record.get("state") == "completed"]
    latency_fields = {
        "submit": "submit_latency_ms",
        "claim": "claim_latency_ms",
        "execution": "execution_latency_ms",
        "end_to_end": "end_to_end_latency_ms",
    }
    latencies: dict[str, dict[str, float] | None] = {}
    for label, field in latency_fields.items():
        values = [
            float(record[field])
            for record in completed
            if isinstance(record.get(field), int | float)
        ]
        latencies[label] = _latency_summary(values)

    throughput = 0.0
    created_values = [
        parse_timestamp(record["created_at"])
        for record in completed
        if isinstance(record.get("created_at"), str)
    ]
    completed_values = [
        parse_timestamp(record["completed_at"])
        for record in completed
        if isinstance(record.get("completed_at"), str)
    ]
    if created_values and completed_values:
        duration_sec = (max(completed_values) - min(created_values)).total_seconds()
        if duration_sec > 0:
            throughput = len(completed) / duration_sec

    rate_limit_wait_values = [
        float(record["rate_limit_wait_sec"])
        for record in completed
        if isinstance(record.get("rate_limit_wait_sec"), int | float)
        and float(record["rate_limit_wait_sec"]) > 0
    ]
    return {
        "jobs": len(included),
        "completed": len(completed),
        "failed": sum(record.get("state") != "completed" for record in included),
        "duplicate_execution": sum(
            record.get("duplicate_execution") is True for record in included
        ),
        "rate_limit_wait": {
            "jobs": len(rate_limit_wait_values),
            "max_sec": round(max(rate_limit_wait_values), 6)
            if rate_limit_wait_values
            else 0.0,
        },
        "throughput_jobs_sec": round(throughput, 6),
        "latency_ms": latencies,
    }


def validate_preflight(
    health: dict[str, Any],
    ops: dict[str, Any],
    worker_env: dict[str, str] | None,
    *,
    expected_dispatch: str,
    minimum_imagen_rate_limit: int,
    require_idle: bool = False,
) -> None:
    vertex = health.get("vertex")
    if not (
        health.get("ok") is True
        and health.get("ready") is True
        and health.get("db") == "up"
        and isinstance(vertex, dict)
        and vertex.get("status") == "mock_provider"
        and vertex.get("credentials") == "not_required"
    ):
        raise BenchmarkError(
            "Health preflight requires ready mock_provider with credentials not_required."
        )

    dispatch = ops.get("dispatch")
    observed_dispatch = dispatch.get("mode") if isinstance(dispatch, dict) else None
    if ops.get("ok") is not True or ops.get("db") != "up":
        raise BenchmarkError("Ops preflight requires an available database.")
    if observed_dispatch != expected_dispatch:
        raise BenchmarkError(
            f"Expected dispatch mode {expected_dispatch!r}, got {observed_dispatch!r}."
        )

    if require_idle:
        jobs = ops.get("jobs")
        outbox = ops.get("outbox")
        active_jobs = jobs.get("active") if isinstance(jobs, dict) else None
        pending_outbox = outbox.get("pending") if isinstance(outbox, dict) else None
        if active_jobs != 0 or pending_outbox != 0:
            raise BenchmarkError(
                "Deployed benchmark requires idle jobs and outbox before execution: "
                f"active_jobs={active_jobs!r}, outbox_pending={pending_outbox!r}."
            )

    if worker_env is None:
        return
    safe_env = whitelist_worker_environment(worker_env)
    if safe_env.get("AI_PROVIDER") != "mock":
        raise BenchmarkError("Worker AI_PROVIDER must be mock.")
    if safe_env.get("JOB_DISPATCH_MODE") != expected_dispatch:
        raise BenchmarkError(
            "Worker dispatch mode does not match the requested comparison mode."
        )
    try:
        observed_rate_limit = int(safe_env.get("RATE_LIMIT_IMAGEN_PER_MIN", ""))
    except ValueError as exc:
        raise BenchmarkError("Worker Imagen rate limit was not an integer.") from exc
    if observed_rate_limit < minimum_imagen_rate_limit:
        raise BenchmarkError(
            "Worker Imagen rate limit is below the benchmark minimum: "
            f"{observed_rate_limit} < {minimum_imagen_rate_limit}."
        )


def whitelist_worker_environment(values: dict[str, Any]) -> dict[str, str]:
    return {
        key: value
        for key in WORKER_ENVIRONMENT_KEYS
        if isinstance((value := values.get(key)), str)
    }


def _cpu_millicores(value: str) -> float:
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000


def _memory_bytes(value: str) -> int:
    units = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
    }
    for suffix, multiplier in units.items():
        if value.endswith(suffix):
            return int(float(value[: -len(suffix)]) * multiplier)
    return int(value)


def parse_kubectl_top(
    output: str,
    *,
    workload_prefixes: tuple[str, ...] = WORKLOAD_PREFIXES,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for raw_line in output.splitlines():
        fields = raw_line.split()
        if len(fields) < 4:
            continue
        pod, container, cpu, memory = fields[:4]
        if not pod.startswith(workload_prefixes):
            continue
        try:
            samples.append(
                {
                    "pod": pod,
                    "container": container,
                    "cpu_millicores": _cpu_millicores(cpu),
                    "memory_bytes": _memory_bytes(memory),
                }
            )
        except ValueError as exc:
            raise BenchmarkError(f"Could not parse kubectl top line: {raw_line!r}.") from exc
    return samples


def join_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


class HttpClient:
    def __init__(self, base_url: str, *, timeout_sec: float = 15.0) -> None:
        self.base_url = base_url
        self.timeout_sec = timeout_sec

    def request_json(
        self,
        method: str,
        path: str,
        *,
        expected_status: int,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        headers: dict[str, str] = {}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            join_url(self.base_url, path),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                body = response.read()
                status = response.status
        except HTTPError as exc:
            body = exc.read()
            snippet = body.decode("utf-8", errors="replace")[:500]
            raise BenchmarkError(
                f"{method} {path} expected HTTP {expected_status}, "
                f"got {exc.code}: {snippet}"
            ) from exc
        except (URLError, RemoteDisconnected, ConnectionResetError) as exc:
            raise BenchmarkError(f"{method} {path} failed: {exc}") from exc

        if status != expected_status:
            snippet = body.decode("utf-8", errors="replace")[:500]
            raise BenchmarkError(
                f"{method} {path} expected HTTP {expected_status}, "
                f"got {status}: {snippet}"
            )
        if not body and expected_status == 204:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise BenchmarkError(f"{method} {path} returned invalid JSON.") from exc


def _command_output(command: list[str], *, timeout_sec: float = 30) -> str:
    completed = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout_sec,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise BenchmarkError(f"Command failed ({' '.join(command[:3])}): {detail[:500]}")
    return completed.stdout.strip()


def _load_release_profile(path: Path) -> dict[str, Any]:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"Could not read release profile {path}: {exc}") from exc
    required = {
        "account",
        "project_id",
        "cluster_name",
        "cluster_zone",
        "namespace",
        "expected_vertex_status",
    }
    missing = sorted(required - set(profile))
    if missing:
        raise BenchmarkError(
            "Release profile is missing required keys: " + ", ".join(missing)
        )
    if profile["expected_vertex_status"] != "mock_provider":
        raise BenchmarkError("Release profile must expect mock_provider.")
    return profile


def _deployment_metadata(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deployments: list[dict[str, Any]] = []
    for item in items:
        metadata = item.get("metadata") or {}
        spec = item.get("spec") or {}
        status = item.get("status") or {}
        template = (spec.get("template") or {}).get("spec") or {}
        containers = []
        for container in template.get("containers") or []:
            resources = container.get("resources") or {}
            containers.append(
                {
                    "name": container.get("name"),
                    "image": container.get("image"),
                    "requests": resources.get("requests") or {},
                    "limits": resources.get("limits") or {},
                }
            )
        deployments.append(
            {
                "name": metadata.get("name"),
                "replicas": int(spec.get("replicas") or 0),
                "ready_replicas": int(status.get("readyReplicas") or 0),
                "containers": containers,
                "runtime_config_hash": (
                    ((spec.get("template") or {}).get("metadata") or {})
                    .get("annotations", {})
                    .get("creativeops.io/runtime-config-hash")
                ),
            }
        )
    return deployments


def collect_gke_preflight(
    profile_path: Path,
    *,
    kubectl: str = "kubectl",
    gcloud: str = "gcloud",
) -> tuple[dict[str, Any], dict[str, str], str]:
    profile = _load_release_profile(profile_path)
    account = _command_output(
        [gcloud, "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"]
    )
    project = _command_output([gcloud, "config", "get-value", "project"])
    if account != profile["account"]:
        raise BenchmarkError(
            f"GCP account guard failed: expected {profile['account']!r}, got {account!r}."
        )
    if project != profile["project_id"]:
        raise BenchmarkError(
            f"GCP project guard failed: expected {profile['project_id']!r}, got {project!r}."
        )

    cluster_status = _command_output(
        [
            gcloud,
            "container",
            "clusters",
            "describe",
            profile["cluster_name"],
            "--zone",
            profile["cluster_zone"],
            "--project",
            profile["project_id"],
            "--format=value(status)",
        ]
    )
    if cluster_status != "RUNNING":
        raise BenchmarkError(f"Expected RUNNING GKE cluster, got {cluster_status!r}.")

    namespace = profile["namespace"]
    deployments_body = _command_output(
        [
            kubectl,
            "get",
            "deployment",
            "creativeops-api",
            "creativeops-dispatcher",
            "creativeops-worker",
            "-n",
            namespace,
            "-o",
            "json",
        ]
    )
    deployments_json = json.loads(deployments_body)
    deployments = _deployment_metadata(deployments_json.get("items") or [])
    not_ready = [
        item["name"]
        for item in deployments
        if item["replicas"] < 1 or item["ready_replicas"] != item["replicas"]
    ]
    if not_ready:
        raise BenchmarkError(
            "GKE deployments are not fully ready: " + ", ".join(not_ready)
        )

    worker_pod = _command_output(
        [
            kubectl,
            "get",
            "pod",
            "-n",
            namespace,
            "-l",
            "app=creativeops-worker",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ]
    )
    if not worker_pod:
        raise BenchmarkError("Could not resolve the worker pod.")

    env_probe = (
        "import json,os;"
        f"keys={list(WORKER_ENVIRONMENT_KEYS)!r};"
        "print(json.dumps({key:os.environ.get(key) for key in keys}))"
    )
    worker_env_raw = _command_output(
        [kubectl, "exec", "-n", namespace, worker_pod, "--", "python", "-c", env_probe]
    )
    worker_env = whitelist_worker_environment(json.loads(worker_env_raw))

    top_output = _command_output(
        [kubectl, "top", "pod", "-n", namespace, "--containers", "--no-headers"]
    )
    initial_resources = parse_kubectl_top(top_output)
    if not initial_resources:
        raise BenchmarkError("kubectl top did not return CreativeOps workload samples.")

    queue_depth = _redis_queue_depth(
        kubectl=kubectl,
        namespace=namespace,
        worker_pod=worker_pod,
    )
    if queue_depth != 0:
        raise BenchmarkError(
            f"Deployed benchmark requires an empty Celery queue, got {queue_depth}."
        )
    evidence = {
        "account": account,
        "project_id": project,
        "cluster_name": profile["cluster_name"],
        "cluster_zone": profile["cluster_zone"],
        "namespace": namespace,
        "cluster_status": cluster_status,
        "deployments": deployments,
        "initial_resources": initial_resources,
        "initial_celery_queue_depth": queue_depth,
    }
    return evidence, worker_env, worker_pod


def _redis_queue_depth(*, kubectl: str, namespace: str, worker_pod: str) -> int:
    probe = (
        "from app.config import get_settings;"
        "from redis import Redis;"
        "s=get_settings();"
        "r=Redis.from_url(s.celery_broker_url,socket_timeout=2);"
        "print(r.llen(s.celery_default_queue));"
        "r.close()"
    )
    output = _command_output(
        [kubectl, "exec", "-n", namespace, worker_pod, "--", "python", "-c", probe],
        timeout_sec=15,
    )
    try:
        return int(output)
    except ValueError as exc:
        raise BenchmarkError(f"Redis queue depth was not an integer: {output!r}.") from exc


class GkeSampler:
    def __init__(
        self,
        *,
        client: HttpClient,
        kubectl: str,
        namespace: str,
        worker_pod: str,
        interval_sec: float,
    ) -> None:
        self.client = client
        self.kubectl = kubectl
        self.namespace = namespace
        self.worker_pod = worker_pod
        self.interval_sec = interval_sec
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> list[dict[str, Any]]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(5.0, self.interval_sec * 2))
        return list(self.samples)

    def _run(self) -> None:
        while not self._stop.is_set():
            sample: dict[str, Any] = {"at": _utc_now()}
            try:
                top_output = _command_output(
                    [
                        self.kubectl,
                        "top",
                        "pod",
                        "-n",
                        self.namespace,
                        "--containers",
                        "--no-headers",
                    ],
                    timeout_sec=15,
                )
                sample["resources"] = parse_kubectl_top(top_output)
                sample["celery_queue_depth"] = _redis_queue_depth(
                    kubectl=self.kubectl,
                    namespace=self.namespace,
                    worker_pod=self.worker_pod,
                )
                ops = self.client.request_json(
                    "GET",
                    "/api/ops/health",
                    expected_status=200,
                )
                if isinstance(ops, dict):
                    sample["active_jobs"] = (ops.get("jobs") or {}).get("active")
                    sample["outbox_pending"] = (ops.get("outbox") or {}).get("pending")
            except (BenchmarkError, TypeError, AttributeError) as exc:
                sample["sample_error"] = str(exc)
            self.samples.append(sample)
            self._stop.wait(self.interval_sec)


def _submit_one(
    client: HttpClient,
    *,
    run_id: str,
    phase_name: str,
    index: int,
) -> tuple[dict[str, Any], float]:
    payload = {
        "prompt": f"benchmark {run_id} {phase_name} {index:04d}",
        "mode": "t2i",
        "model": "imagen-4.0-fast-generate-001",
        "aspect_ratio": "1:1",
        "number_of_images": 1,
        "auto_enhance": False,
    }
    started = time.perf_counter()
    response = client.request_json(
        "POST",
        "/api/generations",
        expected_status=201,
        payload=payload,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    if not isinstance(response, dict):
        raise BenchmarkError("Generation submit expected a JSON object.")
    return response, latency_ms


def submit_phase(
    client: HttpClient,
    *,
    run_id: str,
    phase: dict[str, Any],
) -> dict[str, tuple[dict[str, Any], float]]:
    submitted: dict[str, tuple[dict[str, Any], float]] = {}
    with ThreadPoolExecutor(max_workers=int(phase["submit_concurrency"])) as executor:
        futures = [
            executor.submit(
                _submit_one,
                client,
                run_id=run_id,
                phase_name=str(phase["name"]),
                index=index,
            )
            for index in range(1, int(phase["jobs"]) + 1)
        ]
        for future in as_completed(futures):
            response, latency_ms = future.result()
            job_id = response.get("id")
            if not isinstance(job_id, str) or not job_id:
                raise BenchmarkError("Generation submit response did not include id.")
            submitted[job_id] = (response, latency_ms)
    return submitted


def poll_jobs(
    client: HttpClient,
    *,
    job_ids: set[str],
    timeout_sec: float,
    interval_sec: float,
) -> dict[str, dict[str, Any]]:
    deadline = time.monotonic() + timeout_sec
    terminal: dict[str, dict[str, Any]] = {}
    max_pages = max(5, math.ceil(len(job_ids) / 100) + 5)

    while time.monotonic() <= deadline:
        observed: dict[str, dict[str, Any]] = {}
        for page in range(max_pages):
            body = client.request_json(
                "GET",
                f"/api/generations?limit=100&offset={page * 100}",
                expected_status=200,
            )
            if not isinstance(body, list):
                raise BenchmarkError("Generation list expected a JSON array.")
            for item in body:
                if (
                    isinstance(item, dict)
                    and isinstance(item.get("id"), str)
                    and item["id"] in job_ids
                ):
                    observed[item["id"]] = item
            if len(body) < 100 or len(observed) == len(job_ids):
                break

        for job_id, item in observed.items():
            if item.get("state") in TERMINAL_STATES:
                terminal[job_id] = item
        if len(terminal) == len(job_ids):
            return terminal
        time.sleep(interval_sec)

    missing = sorted(job_ids - set(terminal))
    raise BenchmarkError(
        f"Timed out waiting for {len(missing)} jobs; example ids: {missing[:5]}."
    )


def cleanup_jobs(
    client: HttpClient,
    job_ids: list[str],
    *,
    concurrency: int = 20,
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []

    def delete(job_id: str) -> None:
        client.request_json(
            "DELETE",
            f"/api/generations/{job_id}",
            expected_status=204,
        )

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        futures = {executor.submit(delete, job_id): job_id for job_id in job_ids}
        for future in as_completed(futures):
            job_id = futures[future]
            try:
                future.result()
            except BenchmarkError as exc:
                failures.append({"job_id": job_id, "error": str(exc)})
    return failures


def _phase_summary(records: list[dict[str, Any]], phase_name: str) -> dict[str, Any]:
    phase_records = [record for record in records if record.get("phase") == phase_name]
    adjusted = [
        {**record, "include_in_aggregate": True}
        for record in phase_records
    ]
    return summarize_records(adjusted)


def _resource_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    queue_values = [
        int(sample["celery_queue_depth"])
        for sample in samples
        if isinstance(sample.get("celery_queue_depth"), int)
    ]
    active_values = [
        int(sample["active_jobs"])
        for sample in samples
        if isinstance(sample.get("active_jobs"), int)
    ]
    outbox_values = [
        int(sample["outbox_pending"])
        for sample in samples
        if isinstance(sample.get("outbox_pending"), int)
    ]
    peaks: dict[str, dict[str, float | int]] = {}
    for sample in samples:
        sample_totals: dict[str, dict[str, float | int]] = {}
        for resource in sample.get("resources") or []:
            container = resource.get("container")
            if not isinstance(container, str):
                continue
            total = sample_totals.setdefault(
                container,
                {"cpu_millicores": 0.0, "memory_bytes": 0},
            )
            total["cpu_millicores"] = (
                float(total["cpu_millicores"])
                + float(resource.get("cpu_millicores") or 0)
            )
            total["memory_bytes"] = (
                int(total["memory_bytes"])
                + int(resource.get("memory_bytes") or 0)
            )
        for container, total in sample_totals.items():
            peak = peaks.setdefault(
                container,
                {"cpu_millicores": 0.0, "memory_bytes": 0},
            )
            peak["cpu_millicores"] = max(
                float(peak["cpu_millicores"]),
                float(total["cpu_millicores"]),
            )
            peak["memory_bytes"] = max(
                int(peak["memory_bytes"]),
                int(total["memory_bytes"]),
            )
    return {
        "samples": len(samples),
        "sample_errors": sum("sample_error" in sample for sample in samples),
        "peak_celery_queue_depth": max(queue_values, default=None),
        "peak_active_jobs": max(active_values, default=None),
        "peak_outbox_pending": max(outbox_values, default=None),
        "peak_by_container": peaks,
    }


def _git_metadata() -> dict[str, Any]:
    try:
        commit = _command_output(["git", "rev-parse", "HEAD"])
        dirty = bool(_command_output(["git", "status", "--porcelain"]))
    except BenchmarkError:
        return {"commit": None, "dirty": None}
    return {"commit": commit, "dirty": dirty}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    phases = build_phase_specs(
        warmup_jobs=args.warmup_jobs,
        steady_jobs=args.steady_jobs,
        burst_jobs=args.burst_jobs,
        burst_rounds=args.burst_rounds,
        steady_concurrency=args.steady_concurrency,
        burst_concurrency=args.burst_concurrency,
    )
    client = HttpClient(args.base_url, timeout_sec=args.request_timeout_sec)
    health = client.request_json("GET", "/api/health", expected_status=200)
    ops_before = client.request_json("GET", "/api/ops/health", expected_status=200)
    if not isinstance(health, dict) or not isinstance(ops_before, dict):
        raise BenchmarkError("Preflight endpoints returned unexpected JSON.")

    gke_evidence = None
    worker_env = None
    worker_pod = None
    if args.gke_profile is not None:
        gke_evidence, worker_env, worker_pod = collect_gke_preflight(
            Path(args.gke_profile),
            kubectl=args.kubectl,
            gcloud=args.gcloud,
        )
    validate_preflight(
        health,
        ops_before,
        worker_env,
        expected_dispatch=args.expected_dispatch,
        minimum_imagen_rate_limit=args.minimum_imagen_rate_limit,
        require_idle=gke_evidence is not None,
    )

    run_id = args.run_id or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    report: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "evidence_scope": "mock_orchestration_only",
        "started_at": _utc_now(),
        "completed_at": None,
        "git": _git_metadata(),
        "base_url": args.base_url,
        "expected_dispatch": args.expected_dispatch,
        "workload": {
            "phases": phases,
            "total_jobs": sum(int(phase["jobs"]) for phase in phases),
        },
        "preflight": {
            "health": health,
            "ops": ops_before,
            "worker_environment": worker_env,
            "gke": gke_evidence,
        },
        "records": [],
        "samples": [],
        "cleanup": {"requested": bool(args.cleanup), "failures": []},
    }
    if not args.execute:
        report["dry_run"] = True
        return report

    sampler = None
    if gke_evidence is not None and worker_pod is not None:
        sampler = GkeSampler(
            client=client,
            kubectl=args.kubectl,
            namespace=gke_evidence["namespace"],
            worker_pod=worker_pod,
            interval_sec=args.sample_interval_sec,
        )
        sampler.start()

    all_job_ids: list[str] = []
    run_failure: BaseException | None = None
    try:
        for phase in phases:
            print(
                f"[benchmark] submit {phase['name']}: "
                f"{phase['jobs']} jobs @ concurrency {phase['submit_concurrency']}",
                flush=True,
            )
            submitted = submit_phase(client, run_id=run_id, phase=phase)
            all_job_ids.extend(submitted)
            terminal = poll_jobs(
                client,
                job_ids=set(submitted),
                timeout_sec=args.phase_timeout_sec,
                interval_sec=args.poll_interval_sec,
            )
            phase_records = []
            for job_id, (_, submit_latency_ms) in submitted.items():
                record = analyze_job(
                    terminal[job_id],
                    phase=str(phase["name"]),
                    submit_latency_ms=submit_latency_ms,
                    include_in_aggregate=bool(phase["include_in_aggregate"]),
                )
                phase_records.append(record)
            report["records"].extend(phase_records)
            phase_result = _phase_summary(report["records"], str(phase["name"]))
            print(
                f"[benchmark] completed {phase['name']}: "
                f"{phase_result['completed']}/{phase_result['jobs']}",
                flush=True,
            )
            if (
                phase_result["failed"]
                or phase_result["duplicate_execution"]
                or phase_result["rate_limit_wait"]["jobs"]
            ):
                raise BenchmarkError(
                    f"Phase {phase['name']} observed failures, duplicate execution, "
                    "or rate-limit wait."
                )
    except BaseException as exc:
        run_failure = exc
    finally:
        if sampler is not None:
            report["samples"] = sampler.stop()
        if args.cleanup and all_job_ids:
            print(f"[benchmark] cleanup {len(all_job_ids)} terminal jobs", flush=True)
            report["cleanup"]["failures"] = cleanup_jobs(
                client,
                all_job_ids,
                concurrency=args.cleanup_concurrency,
            )
        try:
            ops_after = client.request_json(
                "GET",
                "/api/ops/health",
                expected_status=200,
            )
            if isinstance(ops_after, dict):
                report["ops_after"] = ops_after
        except BenchmarkError as exc:
            report["ops_after_error"] = str(exc)
        report["summary"] = summarize_records(report["records"])
        report["phase_summaries"] = {
            str(phase["name"]): _phase_summary(report["records"], str(phase["name"]))
            for phase in phases
        }
        report["resource_summary"] = _resource_summary(report["samples"])
        report["completed_at"] = _utc_now()
        report["dry_run"] = False
        if run_failure is not None:
            report["run_error"] = str(run_failure)
        if args.output is not None:
            _write_report(Path(args.output), report)

    if run_failure is not None:
        raise run_failure
    if report["cleanup"]["failures"]:
        raise BenchmarkError(
            f"Cleanup failed for {len(report['cleanup']['failures'])} jobs."
        )
    return report


def _default_output_path() -> Path:
    run_name = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    return Path("benchmarks/orchestration/runs") / f"{run_name}.json"


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark mock-only generation orchestration through public APIs."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--gke-profile")
    parser.add_argument("--expected-dispatch", default="celery")
    parser.add_argument("--minimum-imagen-rate-limit", type=int, default=5000)
    parser.add_argument("--warmup-jobs", type=int, default=20)
    parser.add_argument("--steady-jobs", type=int, default=100)
    parser.add_argument("--burst-jobs", type=int, default=200)
    parser.add_argument("--burst-rounds", type=int, default=5)
    parser.add_argument("--steady-concurrency", type=int, default=2)
    parser.add_argument("--burst-concurrency", type=int, default=50)
    parser.add_argument("--poll-interval-sec", type=float, default=0.5)
    parser.add_argument("--phase-timeout-sec", type=float, default=900)
    parser.add_argument("--request-timeout-sec", type=float, default=20)
    parser.add_argument("--sample-interval-sec", type=float, default=2)
    parser.add_argument("--cleanup-concurrency", type=int, default=20)
    parser.add_argument("--run-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--kubectl", default="kubectl")
    parser.add_argument("--gcloud", default="gcloud")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Create the planned jobs. Without this flag, only preflight runs.",
    )
    parser.add_argument(
        "--no-cleanup",
        dest="cleanup",
        action="store_false",
        help="Keep benchmark jobs and assets after the run.",
    )
    parser.set_defaults(cleanup=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_path = args.output or _default_output_path()
    args.output = output_path
    report: dict[str, Any] | None = None
    try:
        report = run_benchmark(args)
        if args.execute:
            _write_report(output_path, report)
            print(f"[benchmark] report: {output_path}", flush=True)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            print("[benchmark] dry-run only; pass --execute to create jobs.", flush=True)
    except BenchmarkError as exc:
        if report is not None and args.execute:
            _write_report(output_path, report)
        print(f"BENCHMARK FAILED: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("BENCHMARK FAILED: interrupted", file=sys.stderr)
        return 130
    print("BENCHMARK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
