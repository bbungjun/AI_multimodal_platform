from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from mock_auth_support import HarnessError as SmokeError, ScopedClient as HttpClient, safe_url


def parse_env_file(path: Path) -> dict[str, str]:
    env_path = path.expanduser()
    if env_path.name == ".env":
        raise SmokeError(
            "Refusing to read sensitive env file '.env'. Use .env.example or another "
            "non-secret mock-only env file."
        )
    if not env_path.exists():
        raise SmokeError(f"Env file was not found: {env_path}")
    if not env_path.is_file():
        raise SmokeError(f"Env file path is not a file: {env_path}")

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            raise SmokeError(
                f"Env file {env_path} line {line_number} is not KEY=VALUE syntax."
            )
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
            raise SmokeError(f"Env file {env_path} line {line_number} has invalid key.")
        values[key] = _strip_env_quotes(value.strip())

    if values.get("AI_PROVIDER") != "mock":
        raise SmokeError(
            f"Env file {env_path} must contain AI_PROVIDER=mock for this smoke check."
        )
    return values


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def join_url(base_url: str, path: str) -> str:
    return safe_url(base_url, path)


def assert_status(step: str, actual: int, expected: int, body: str | bytes = b"") -> None:
    if actual != expected:
        raise SmokeError(f"{step} expected HTTP {expected}, got {actual}")


def normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def header_value(headers: dict[str, str], name: str, default: str | None = None) -> str | None:
    return normalize_headers(headers).get(name.lower(), default)


def main(argv: list[str] | None = None) -> int:
    # Standalone entrypoints delegate to the sole resource-owning coordinator.
    from verify_ownership import main as verify_main
    return verify_main(argv)


def run_smoke(args: argparse.Namespace, *, client: HttpClient) -> None:
    deadline = time.monotonic() + args.timeout_sec

    step("Health")
    health = wait_for_health(client, deadline, args.poll_interval_sec)
    assert_health(health)

    step("Prompt enhance")
    enhancement = client.request_json(
        "POST",
        "/api/prompts/enhance",
        expected_status=201,
        payload={
            "prompt": "a quiet desk lamp on a walnut desk",
            "target_mode": "t2i",
            "target_model": "imagen-4.0-fast-generate-001",
            "creativity_preset": "faithful",
        },
        step_name="Prompt enhance",
    )
    if enhancement.get("components", {}).get("provider") != "mock":
        raise SmokeError("Prompt enhance expected components.provider to be mock.")
    enhanced_prompt = enhancement.get("enhanced")
    if not isinstance(enhanced_prompt, str) or not enhanced_prompt.strip():
        raise SmokeError("Prompt enhance returned an empty enhanced prompt.")
    enhancement_id = enhancement.get("id")
    if not enhancement_id:
        raise SmokeError("Prompt enhance response did not include id.")

    step("Create generation")
    generation = client.request_json(
        "POST",
        "/api/generations",
        expected_status=201,
        payload={
            "prompt": enhanced_prompt,
            "enhancement_id": enhancement_id,
            "mode": "t2i",
            "model": "imagen-4.0-fast-generate-001",
            "aspect_ratio": "1:1",
            "number_of_images": 1,
            "auto_enhance": False,
        },
        step_name="Create generation",
    )
    job_id = generation.get("id")
    if not job_id:
        raise SmokeError("Generation response did not include job id.")

    try:
        step("Poll generation")
        completed = poll_generation(
            client,
            job_id=str(job_id),
            deadline=deadline,
            interval_sec=args.poll_interval_sec,
        )
        asset = assert_completed_job(completed)

        step("Asset metadata")
        asset_metadata = client.request_json(
            "GET",
            f"/api/assets/{asset['id']}",
            expected_status=200,
            step_name="Asset metadata",
        )
        if asset_metadata.get("id") != asset["id"] or asset_metadata.get("url") != asset["url"]:
            raise SmokeError("Asset metadata response did not match completed job asset.")

        step("Asset bytes")
        asset_body, asset_headers, _ = client.request_bytes(
            "GET",
            asset["url"],
            expected_status=200,
            step_name="Asset bytes",
        )
        content_type = header_value(asset_headers, "Content-Type", "") or ""
        content_length = header_value(asset_headers, "Content-Length")
        if not asset_body.startswith(PNG_SIGNATURE):
            raise SmokeError("Asset bytes did not start with PNG signature.")
        if "image/png" not in content_type:
            raise SmokeError(f"Asset Content-Type expected image/png, got {content_type!r}.")
        if content_length is not None and int(content_length) <= 0:
            raise SmokeError("Asset Content-Length was not positive.")
        if len(asset_body) <= 0:
            raise SmokeError("Asset body was empty.")

        step("Asset range")
        range_body, _, _ = client.request_bytes(
            "GET",
            asset["url"],
            expected_status=206,
            headers={"Range": "bytes=0-7"},
            step_name="Asset range",
        )
        if not range_body.startswith(PNG_SIGNATURE):
            raise SmokeError("Asset byte range did not return the PNG signature prefix.")
    finally:
        if not args.keep_job and job_id:
            step("Cleanup")
            client.request_bytes(
                "DELETE",
                f"/api/generations/{job_id}",
                expected_status=204,
                step_name="Cleanup",
            )


def start_compose(env_file: Path) -> None:
    raise SmokeError("isolated_coordinator_required")


def wait_for_health(client: "HttpClient", deadline: float, interval_sec: float) -> dict[str, Any]:
    last_error = "health was not requested"
    while time.monotonic() <= deadline:
        try:
            return client.request_json("GET", "/api/health", expected_status=200, step_name="Health")
        except SmokeError as exc:
            last_error = str(exc)
            time.sleep(interval_sec)
    raise SmokeError(f"Timed out waiting for backend health: {last_error}")


def assert_health(body: dict[str, Any]) -> None:
    vertex = body.get("vertex") if isinstance(body.get("vertex"), dict) else {}
    checks = {
        "ok": body.get("ok") is True,
        "ready": body.get("ready") is True,
        "db": body.get("db") == "up",
        "vertex.status": vertex.get("status") == "mock_provider",
        "vertex.credentials": vertex.get("credentials") == "not_required",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise SmokeError(f"Health response failed checks: {', '.join(failed)}")


def poll_generation(
    client: "HttpClient",
    *,
    job_id: str,
    deadline: float,
    interval_sec: float,
) -> dict[str, Any]:
    last_body: dict[str, Any] | None = None
    while time.monotonic() <= deadline:
        body = client.request_json(
            "GET",
            f"/api/generations/{job_id}",
            expected_status=200,
            step_name="Poll generation",
        )
        last_body = body
        state = body.get("state")
        if body.get("error") is not None:
            raise SmokeError("Generation failed with error.")
        if state == "completed":
            return body
        if state in {"failed", "cancelled"}:
            raise SmokeError("Generation reached unsuccessful terminal state.")
        time.sleep(interval_sec)
    raise SmokeError(
        f"Timed out waiting for generation completion; last state was "
        f"{None if last_body is None else last_body.get('state')}"
    )


def assert_completed_job(job: dict[str, Any]) -> dict[str, Any]:
    if job.get("error") is not None:
        raise SmokeError("Completed job unexpectedly had error.")
    assets = job.get("assets")
    if not isinstance(assets, list) or len(assets) != 1:
        raise SmokeError(f"Completed job expected exactly one asset, got {len(assets or [])}.")
    asset = assets[0]
    if asset.get("mime") != "image/png":
        raise SmokeError(f"Completed job asset expected image/png, got {asset.get('mime')!r}.")
    if not isinstance(asset.get("url"), str) or not asset["url"].startswith("/files/"):
        raise SmokeError(f"Completed job asset URL expected /files/ path, got {asset.get('url')!r}.")
    states = [
        entry.get("state")
        for entry in job.get("state_history", [])
        if isinstance(entry, dict)
    ]
    expected_states = ["queued", "generating", "downloading", "completed"]
    missing = [state for state in expected_states if state not in states]
    if missing:
        raise SmokeError(
            f"Completed job state_history missing {missing}; observed states were {states}."
        )
    if job.get("vertex_charged") is not True:
        raise SmokeError("Completed job expected vertex_charged true in mock mode.")
    return asset


def step(name: str) -> None:
    print(f"[smoke] {name}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
