from __future__ import annotations

import argparse
import asyncio
import json
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
    poll_generation,
    step,
    wait_for_health,
)


DUPLICATE_DETAIL = "An active I2V generation already exists for this source asset."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run mock-only duplicate I2V smoke.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--env-file", default=".env.example")
    parser.add_argument(
        "--compose",
        action="store_true",
        help="Start db, redis, backend, dispatcher, and worker with docker compose.",
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
    i2v_id: str | None = None

    try:
        step("Health")
        health = wait_for_health(client, deadline, args.poll_interval_sec)
        assert_health(health)

        step("Create source T2I generation")
        source = client.request_json(
            "POST",
            "/api/generations",
            expected_status=201,
            payload={
                "prompt": "a quiet desk lamp for duplicate i2v guard",
                "mode": "t2i",
                "model": "imagen-4.0-fast-generate-001",
                "aspect_ratio": "1:1",
                "number_of_images": 1,
                "auto_enhance": False,
            },
            step_name="Create source T2I generation",
        )
        source_id = require_id(source, "Source generation")

        step("Poll source T2I generation")
        completed_source = poll_generation(
            client,
            job_id=source_id,
            deadline=deadline,
            interval_sec=args.poll_interval_sec,
        )
        source_asset_id = require_image_asset_id(completed_source)

        step("Create duplicate I2V requests")
        responses = asyncio.run(
            create_duplicate_i2v_requests(
                args.base_url,
                source_asset_id=source_asset_id,
            )
        )
        assert_duplicate_i2v_responses(responses)
        i2v_id = created_i2v_id(responses)

        step("Poll created I2V generation")
        poll_generation(
            client,
            job_id=i2v_id,
            deadline=deadline,
            interval_sec=args.poll_interval_sec,
        )
    finally:
        if not args.keep_jobs:
            cleanup_jobs(client, i2v_id=i2v_id, source_id=source_id)


def start_compose(env_file: Path) -> None:
    step("Compose up db redis backend dispatcher worker")
    command = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "up",
        "-d",
        "--build",
        "db",
        "redis",
        "backend",
        "dispatcher",
        "worker",
    ]
    env = os.environ.copy()
    env["AI_PROVIDER"] = "mock"
    completed = subprocess.run(
        command,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise SmokeError(
            "docker compose failed while starting db/redis/backend/dispatcher/worker:\n"
            + completed.stdout.strip()
        )


async def create_duplicate_i2v_requests(
    base_url: str,
    *,
    source_asset_id: str,
) -> list[dict[str, Any]]:
    payload = {
        "prompt": "animate the source image once",
        "mode": "i2v",
        "model": "veo-3.0-fast-generate-001",
        "aspect_ratio": "16:9",
        "duration_sec": 4,
        "source_asset_id": source_asset_id,
        "auto_enhance": False,
    }
    first, second = await asyncio.gather(
        asyncio.to_thread(post_generation_status, base_url, payload),
        asyncio.to_thread(post_generation_status, base_url, payload),
    )
    return [first, second]


def post_generation_status(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        join_url(base_url, "/api/generations"),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read()
            return {"status": response.status, "body": decode_json(body)}
    except HTTPError as exc:
        body = exc.read()
        return {"status": exc.code, "body": decode_json(body)}
    except URLError as exc:
        raise SmokeError(f"Duplicate I2V request failed: {exc}") from exc
    except RemoteDisconnected as exc:
        raise SmokeError(f"Duplicate I2V request disconnected: {exc}") from exc


def assert_duplicate_i2v_responses(responses: list[dict[str, Any]]) -> None:
    status_codes = sorted(int(response.get("status", 0)) for response in responses)
    if status_codes != [201, 409]:
        raise SmokeError(
            f"Expected one created I2V and one conflict, got {status_codes}."
        )

    conflicts = [response for response in responses if response.get("status") == 409]
    conflict_body = conflicts[0].get("body") if conflicts else {}
    if not isinstance(conflict_body, dict) or conflict_body.get("detail") != DUPLICATE_DETAIL:
        raise SmokeError(
            "Duplicate I2V conflict response did not include the expected detail."
        )

    created = [response for response in responses if response.get("status") == 201]
    created_body = created[0].get("body") if created else {}
    if not isinstance(created_body, dict) or not created_body.get("id"):
        raise SmokeError("Created I2V response did not include a job id.")


def created_i2v_id(responses: list[dict[str, Any]]) -> str:
    for response in responses:
        if response.get("status") != 201:
            continue
        body = response.get("body")
        if isinstance(body, dict) and body.get("id"):
            return str(body["id"])
    raise SmokeError("Created I2V response did not include a job id.")


def require_image_asset_id(job: dict[str, Any]) -> str:
    assets = job.get("assets")
    if not isinstance(assets, list) or len(assets) != 1:
        raise SmokeError("Source T2I job expected exactly one image asset.")
    asset = assets[0]
    if not isinstance(asset, dict) or asset.get("kind") != "image":
        raise SmokeError("Source T2I job asset expected kind image.")
    asset_id = asset.get("id")
    if not asset_id:
        raise SmokeError("Source T2I asset response did not include id.")
    return str(asset_id)


def require_id(body: dict[str, Any], label: str) -> str:
    job_id = body.get("id")
    if not job_id:
        raise SmokeError(f"{label} response did not include job id.")
    return str(job_id)


def cleanup_jobs(client: HttpClient, *, i2v_id: str | None, source_id: str | None) -> None:
    if i2v_id is not None:
        step("Cleanup I2V")
        client.request_bytes(
            "DELETE",
            f"/api/generations/{i2v_id}",
            expected_status=204,
            step_name="Cleanup I2V",
        )
    if source_id is not None:
        step("Cleanup source")
        client.request_bytes(
            "DELETE",
            f"/api/generations/{source_id}",
            expected_status=204,
            step_name="Cleanup source",
        )


def decode_json(body: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SmokeError(f"Response returned invalid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise SmokeError("Response expected a JSON object.")
    return decoded


if __name__ == "__main__":
    raise SystemExit(main())
