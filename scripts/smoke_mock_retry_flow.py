from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from smoke_mock_golden_path import (  # noqa: E402
    HttpClient,
    SmokeError,
    assert_health,
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
    from verify_ownership import main as verify_main
    return verify_main(argv)


def run_smoke(args: argparse.Namespace, *, client: HttpClient) -> None:
    deadline = time.monotonic() + args.timeout_sec
    source_id: str | None = None
    retry_id: str | None = None
    body_error: BaseException | None = None

    try:
        step("Health")
        health = wait_for_health(client, deadline, args.poll_interval_sec)
        assert_health(health)

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
    raise SmokeError("isolated_coordinator_required")


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
            "Retry job expected retry_of_job_id to match source job id."
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
