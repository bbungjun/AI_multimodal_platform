from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCRIPTS_DIR = Path(__file__).resolve().parent
import sys

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from redis_observability import (  # noqa: E402
    normalize_monitoring_series,
    summarize_monitoring_segments,
)


EXPECTED_ACCOUNT = "youngjun3108@gmail.com"
EXPECTED_PROJECT = "krafton-vertex-live-3108"
EXPECTED_REGION = "asia-northeast3"
EXPECTED_INSTANCE = "creativeops-portfolio-redis"
MONITORING_BASE_URL = "https://monitoring.googleapis.com/v3/"
RETRYABLE_STATUS_CODES = {429, *range(500, 600)}


class ExportError(RuntimeError):
    """Expected exporter failure with a public, secret-free message."""


class MonitoringHttpError(RuntimeError):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"Monitoring HTTP status {status_code}")


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ExportError("Monitoring time must be an ISO timestamp.")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ExportError("Monitoring time is not a valid ISO timestamp.") from exc
    if parsed.tzinfo is None:
        raise ExportError("Monitoring time must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _canonical_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_profile(path: Path) -> dict[str, Any]:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError("Could not read the release profile.") from exc
    if not isinstance(profile, dict):
        raise ExportError("Release profile must be a JSON object.")
    required = {"account", "project_id", "region", "redis_instance_name"}
    missing = sorted(required - set(profile))
    if missing:
        raise ExportError("Release profile is missing required Redis guard fields.")
    expected = {
        "account": EXPECTED_ACCOUNT,
        "project_id": EXPECTED_PROJECT,
        "region": EXPECTED_REGION,
        "redis_instance_name": EXPECTED_INSTANCE,
    }
    for name, expected_value in expected.items():
        if profile.get(name) != expected_value:
            raise ExportError(f"Release profile {name} does not match the personal target.")
    return profile


def _parse_segment(value: str) -> dict[str, str]:
    parts = value.split(",")
    if len(parts) != 3 or not parts[0]:
        raise ExportError("Monitoring segment must be NAME,START,END.")
    name, start_value, end_value = parts
    start = _parse_utc(start_value)
    end = _parse_utc(end_value)
    if end <= start:
        raise ExportError(f"Monitoring segment {name!r} must have positive duration.")
    return {"name": name, "start": _canonical_time(start), "end": _canonical_time(end)}


def validate_export_request(args: argparse.Namespace) -> dict[str, Any]:
    profile = _load_profile(Path(args.profile))
    start = _parse_utc(args.start)
    end = _parse_utc(args.end)
    if end <= start:
        raise ExportError("Monitoring export end must be after start.")
    segments = [_parse_segment(value) for value in (args.segment or [])]
    for segment in segments:
        segment_start = _parse_utc(segment["start"])
        segment_end = _parse_utc(segment["end"])
        if segment_start < start or segment_end > end:
            raise ExportError(f"Monitoring segment {segment['name']!r} is outside the export window.")
    resource_name = (
        f"projects/{profile['project_id']}/locations/{profile['region']}"
        f"/instances/{profile['redis_instance_name']}"
    )
    return {
        "account": profile["account"],
        "project_id": profile["project_id"],
        "region": profile["region"],
        "redis_instance_name": profile["redis_instance_name"],
        "resource_name": resource_name,
        "start": _canonical_time(start),
        "end": _canonical_time(end),
        "segments": segments,
    }


def _access_token() -> str:
    try:
        completed = subprocess.run(
            ["gcloud", "auth", "print-access-token", "--account", EXPECTED_ACCOUNT],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExportError("Could not obtain the Cloud Monitoring credential.") from exc
    if completed.returncode != 0 or not completed.stdout.strip():
        raise ExportError("Could not obtain the Cloud Monitoring credential.")
    return completed.stdout.strip()


def _urlopen_transport(path: str, params: dict[str, str], token: str) -> dict[str, Any]:
    query = urlencode(params)
    url = MONITORING_BASE_URL + path.lstrip("/")
    if query:
        url += "?" + query
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=60) as response:
            body = response.read()
    except HTTPError as exc:
        raise MonitoringHttpError(exc.code) from exc
    except URLError as exc:
        raise ExportError("Cloud Monitoring request transport failed.") from exc
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExportError("Cloud Monitoring returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise ExportError("Cloud Monitoring returned an unexpected response.")
    return result


class MonitoringClient:
    def __init__(
        self,
        *,
        token_provider: Callable[[], str] | None = None,
        transport: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        max_attempts: int = 5,
    ) -> None:
        self.token_provider = token_provider or _access_token
        self.transport = transport
        self.sleep_fn = sleep_fn
        self.max_attempts = max_attempts
        self._token: str | None = None

    def request_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        for attempt in range(self.max_attempts):
            try:
                if self.transport is not None:
                    result = self.transport(path, dict(params))
                else:
                    if self._token is None:
                        self._token = self.token_provider()
                    if not isinstance(self._token, str) or not self._token:
                        raise ExportError("Cloud Monitoring credential was empty.")
                    result = _urlopen_transport(path, params, self._token)
                if not isinstance(result, dict):
                    raise ExportError("Cloud Monitoring returned an unexpected response.")
                return result
            except MonitoringHttpError as exc:
                if exc.status_code not in RETRYABLE_STATUS_CODES:
                    raise ExportError(
                        f"Cloud Monitoring request failed with HTTP {exc.status_code}."
                    ) from exc
                if attempt == self.max_attempts - 1:
                    raise ExportError(
                        f"Cloud Monitoring request exhausted bounded retries for HTTP {exc.status_code}."
                    ) from exc
                self.sleep_fn(2**attempt)
        raise ExportError("Cloud Monitoring request failed.")


def _paged(
    client: MonitoringClient,
    path: str,
    params: dict[str, str],
    response_key: str,
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        page_params = dict(params)
        if page_token:
            page_params["pageToken"] = page_token
        response = client.request_json(path, page_params)
        page_values = response.get(response_key, [])
        if not isinstance(page_values, list):
            raise ExportError("Cloud Monitoring returned an unexpected page.")
        values.extend(item for item in page_values if isinstance(item, dict))
        page_token = response.get("nextPageToken")
        if not isinstance(page_token, str) or not page_token:
            return values


def _list_descriptors(client: MonitoringClient, project_id: str) -> list[dict[str, Any]]:
    descriptors = _paged(
        client,
        f"projects/{project_id}/metricDescriptors",
        {
            "filter": 'metric.type = starts_with("redis.googleapis.com/")',
            "pageSize": "1000",
        },
        "metricDescriptors",
    )
    return [
        descriptor
        for descriptor in descriptors
        if isinstance(descriptor.get("type"), str)
        and descriptor["type"].startswith("redis.googleapis.com/")
    ]


def _list_time_series(
    client: MonitoringClient,
    request: dict[str, Any],
    metric_type: str,
) -> list[dict[str, Any]]:
    metric_filter = (
        f'metric.type = "{metric_type}" AND resource.type = "redis_instance" '
        f'AND resource.labels.instance_id = "{request["resource_name"]}"'
    )
    return _paged(
        client,
        f"projects/{request['project_id']}/timeSeries",
        {
            "filter": metric_filter,
            "interval.startTime": request["start"],
            "interval.endTime": request["end"],
            "view": "FULL",
            "pageSize": "1000",
        },
        "timeSeries",
    )


def collect_redis_monitoring(
    request: dict[str, Any],
    client: MonitoringClient,
) -> dict[str, Any]:
    descriptors = _list_descriptors(client, request["project_id"])
    normalized_series: list[dict[str, Any]] = []
    query_errors: list[dict[str, str]] = []
    for descriptor in descriptors:
        metric_type = descriptor["type"]
        try:
            raw_series = _list_time_series(client, request, metric_type)
        except ExportError as exc:
            query_errors.append(
                {"metric_type": metric_type, "error_type": type(exc).__name__}
            )
            continue
        if not raw_series:
            raw_series = [
                {
                    "metric": {"labels": {}},
                    "resource": {"type": "redis_instance", "labels": {}},
                    "points": [],
                }
            ]
        for raw in raw_series:
            try:
                normalized_series.append(normalize_monitoring_series(descriptor, raw))
            except ValueError:
                query_errors.append(
                    {"metric_type": metric_type, "error_type": "normalization_error"}
                )

    segment_summary = summarize_monitoring_segments(
        normalized_series,
        request["segments"],
    )
    return {
        "schema_version": 1,
        "source": "Cloud Monitoring post-hoc, 60s-aligned",
        "project_id": request["project_id"],
        "region": request["region"],
        "redis_instance_name": request["redis_instance_name"],
        "resource_name": request["resource_name"],
        "window": {"start": request["start"], "end": request["end"]},
        "segments": request["segments"],
        "descriptor_count": len(descriptors),
        "available_metric_count": len(segment_summary["observed_metric_names"]),
        "not_observed_metric_count": len(segment_summary["not_observed_metric_names"]),
        "query_error_count": len(query_errors),
        "query_errors": query_errors,
        "series": normalized_series,
        "segment_summary": segment_summary,
    }


def _write_artifact(path: Path, artifact: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export secret-safe Redis Cloud Monitoring evidence.")
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--segment", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    return parser


def run_export(args: argparse.Namespace) -> dict[str, Any] | None:
    request = validate_export_request(args)
    if not args.execute:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "project_id": request["project_id"],
                    "region": request["region"],
                    "redis_instance_name": request["redis_instance_name"],
                    "window": {"start": request["start"], "end": request["end"]},
                    "segment_count": len(request["segments"]),
                    "descriptor_query_count": 1,
                    "time_series_query_count": "one per Redis descriptor",
                    "output_written": False,
                },
                sort_keys=True,
            )
        )
        return None
    if args.output is None:
        raise ExportError("--output is required with --execute.")
    client = MonitoringClient()
    artifact = collect_redis_monitoring(request, client)
    _write_artifact(args.output, artifact)
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run_export(args)
    except ExportError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
