from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from smoke_mock_golden_path import (  # noqa: E402
    HttpClient,
    SmokeError,
    assert_health,
    assert_status,
    join_url,
    parse_env_file,
    step,
    wait_for_health,
)


TERMINAL_STATES = {"completed", "failed", "cancelled"}
RETRY_IN_PROGRESS_STATES = {
    "enhancing",
    "queued",
    "generating",
    "polling",
    "downloading",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run mock-only retry smoke flow.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend-url", default="http://127.0.0.1:5173")
    parser.add_argument("--env-file", default=".env.example")
    parser.add_argument(
        "--compose",
        action="store_true",
        help="Start db, backend, worker, and frontend with docker compose.",
    )
    parser.add_argument("--timeout-sec", type=float, default=60)
    parser.add_argument("--poll-interval-sec", type=float, default=1)
    parser.add_argument("--keep-jobs", action="store_true", help="Skip deleting created jobs.")
    args = parser.parse_args(argv)

    try:
        run_smoke(args)
    except SmokeError as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("SMOKE FAILED: interrupted", file=sys.stderr)
        return 130
    print("SMOKE PASSED")
    return 0


def run_smoke(args: argparse.Namespace) -> None:
    env_file = Path(args.env_file)
    parse_env_file(env_file)

    if args.compose:
        start_compose(env_file)

    deadline = time.monotonic() + args.timeout_sec
    client = HttpClient(args.base_url)
    source_id: str | None = None
    retry_id: str | None = None
    body_error: BaseException | None = None

    try:
        step("Health")
        health = wait_for_health(client, deadline, args.poll_interval_sec)
        assert_health(health)

        step("Frontend /history")
        wait_for_frontend(args.frontend_url, deadline, args.poll_interval_sec)

        step("Create failed generation")
        source = client.request_json(
            "POST",
            "/api/generations",
            expected_status=201,
            payload={
                "prompt": "a quiet desk lamp [[mock-fail:imagen]]",
                "mode": "t2i",
                "model": "imagen-4.0-fast-generate-001",
                "aspect_ratio": "1:1",
                "number_of_images": 1,
                "auto_enhance": False,
            },
            step_name="Create failed generation",
        )
        source_id = _require_id(source, "Source generation")

        step("Poll failed generation")
        failed_source = poll_generation_terminal(
            client,
            job_id=source_id,
            deadline=deadline,
            interval_sec=args.poll_interval_sec,
        )
        assert_failed_source_job(failed_source)

        step("Retry failed generation")
        retry = client.request_json(
            "POST",
            f"/api/generations/{source_id}/retry",
            expected_status=201,
            step_name="Retry failed generation",
        )
        retry_id = _require_id(retry, "Retry generation")
        assert_retry_job(retry, source_id=source_id)

        step("Frontend retry detail")
        assert_frontend_route(
            args.frontend_url,
            f"/jobs/{retry_id}",
            step_name="Frontend retry detail",
        )
    except BaseException as exc:
        body_error = exc
        raise
    finally:
        if not args.keep_jobs:
            cleanup_error = cleanup_jobs(
                client,
                retry_id=retry_id,
                source_id=source_id,
                deadline=deadline,
                interval_sec=args.poll_interval_sec,
            )
            if body_error is None and cleanup_error is not None:
                raise cleanup_error


def cleanup_jobs(
    client: HttpClient,
    *,
    retry_id: str | None,
    source_id: str | None,
    deadline: float,
    interval_sec: float,
) -> SmokeError | None:
    first_error: SmokeError | None = None

    if retry_id is not None:
        step("Cleanup retry")
        try:
            terminal_retry = poll_generation_terminal(
                client,
                job_id=retry_id,
                deadline=deadline,
                interval_sec=interval_sec,
            )
            if source_id is not None:
                assert_retry_job(terminal_retry, source_id=source_id)
        except SmokeError as exc:
            if first_error is None:
                first_error = exc

        try:
            client.request_bytes(
                "DELETE",
                f"/api/generations/{retry_id}",
                expected_status=204,
                step_name="Cleanup retry",
            )
        except SmokeError as exc:
            if first_error is None:
                first_error = exc

    if source_id is not None:
        step("Cleanup source")
        try:
            client.request_bytes(
                "DELETE",
                f"/api/generations/{source_id}",
                expected_status=204,
                step_name="Cleanup source",
            )
        except SmokeError as exc:
            if first_error is None:
                first_error = exc

    return first_error


def start_compose(env_file: Path) -> None:
    step("Compose up db backend worker frontend")
    command = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "up",
        "-d",
        "--build",
        "db",
        "backend",
        "worker",
        "frontend",
    ]
    env = os.environ.copy()
    env["AI_PROVIDER"] = "mock"
    completed = subprocess.run(
        command,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise SmokeError(
            "docker compose failed while starting db/backend/worker/frontend:\n"
            + completed.stdout.strip()
        )


def wait_for_frontend(frontend_url: str, deadline: float, interval_sec: float) -> None:
    last_error = "frontend was not requested"
    first_attempt = True
    while first_attempt or time.monotonic() <= deadline:
        first_attempt = False
        try:
            _request_frontend_route(frontend_url, "/history", step_name="Frontend /history")
            return
        except SmokeError as exc:
            last_error = str(exc)
        if time.monotonic() > deadline:
            break
        time.sleep(interval_sec)
    raise SmokeError(f"Timed out waiting for frontend /history: {last_error}")


def assert_frontend_route(frontend_url: str, path: str, *, step_name: str) -> None:
    _request_frontend_route(frontend_url, path, step_name=step_name)


def _request_frontend_route(frontend_url: str, path: str, *, step_name: str) -> None:
    request = Request(join_url(frontend_url, path), method="GET")
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read()
            status = response.status
    except HTTPError as exc:
        body = exc.read()
        assert_status(step_name, exc.code, 200, body)
        raise
    except URLError as exc:
        raise SmokeError(f"{step_name} request failed: {exc}") from exc
    except RemoteDisconnected as exc:
        raise SmokeError(f"{step_name} request disconnected: {exc}") from exc

    assert_status(step_name, status, 200, body)
    if not body.strip():
        raise SmokeError(f"{step_name} returned an empty body.")


def poll_generation_terminal(
    client: HttpClient,
    *,
    job_id: str,
    deadline: float,
    interval_sec: float,
) -> dict[str, Any]:
    last_body: dict[str, Any] | None = None
    first_attempt = True
    while first_attempt or time.monotonic() <= deadline:
        first_attempt = False
        body = client.request_json(
            "GET",
            f"/api/generations/{job_id}",
            expected_status=200,
            step_name="Poll generation",
        )
        last_body = body
        state = body.get("state")
        if state in TERMINAL_STATES:
            return body
        if time.monotonic() > deadline:
            break
        time.sleep(interval_sec)
    raise SmokeError(
        f"Timed out waiting for generation terminal state; last state was "
        f"{None if last_body is None else last_body.get('state')}"
    )


def assert_failed_source_job(source: dict[str, Any]) -> None:
    if source.get("state") != "failed":
        raise SmokeError(f"Source job expected state failed, got {source.get('state')!r}.")
    _assert_no_assets(source, "Source job")
    if source.get("vertex_charged") is not False:
        raise SmokeError("Source job expected vertex_charged false.")
    error = source.get("error")
    if not isinstance(error, dict) or error.get("code") != "mock_provider_failure":
        raise SmokeError(
            "Source job expected error.code mock_provider_failure, "
            f"got {None if not isinstance(error, dict) else error.get('code')!r}."
        )


def assert_retry_job(retry: dict[str, Any], *, source_id: str) -> None:
    retry_id = retry.get("id")
    if not retry_id:
        raise SmokeError("Retry job response did not include id.")
    if str(retry_id) == str(source_id):
        raise SmokeError("Retry job expected a new job id, but reused the source id.")
    if str(retry.get("retry_of_job_id")) != str(source_id):
        raise SmokeError(
            "Retry job expected retry_of_job_id to match source job id, "
            f"got {retry.get('retry_of_job_id')!r}."
        )
    _assert_no_assets(retry, "Retry job")
    if retry.get("vertex_charged") is not False:
        raise SmokeError("Retry job expected vertex_charged false.")

    state = retry.get("state")
    attempts = retry.get("attempts")
    error = retry.get("error")
    if not isinstance(attempts, int):
        raise SmokeError(f"Retry job expected integer attempts, got {attempts!r}.")

    if state == "pending":
        if attempts != 0 or error is not None:
            raise SmokeError("Pending retry job expected attempts 0 and no error.")
        return

    if state in RETRY_IN_PROGRESS_STATES:
        if attempts < 0 or error is not None:
            raise SmokeError("In-progress retry job expected non-negative attempts and no error.")
        return

    if state == "failed":
        if attempts < 1:
            raise SmokeError("Failed retry job expected attempts >= 1.")
        if not isinstance(error, dict) or error.get("code") != "mock_provider_failure":
            raise SmokeError("Failed retry job expected error.code mock_provider_failure.")
        return

    raise SmokeError(f"Retry job reached unsupported state {state!r}.")


def _assert_no_assets(job: dict[str, Any], label: str) -> None:
    assets = job.get("assets")
    if not isinstance(assets, list) or assets:
        raise SmokeError(f"{label} expected no assets, got {len(assets or [])}.")


def _require_id(body: dict[str, Any], label: str) -> str:
    job_id = body.get("id")
    if not job_id:
        raise SmokeError(f"{label} response did not include job id.")
    return str(job_id)


if __name__ == "__main__":
    raise SystemExit(main())
