from __future__ import annotations

import math
import re
import hashlib
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


REDIS_GAUGE_FIELDS = (
    "connected_clients",
    "blocked_clients",
    "used_memory",
    "used_memory_peak",
    "maxmemory",
    "instantaneous_ops_per_sec",
    "instantaneous_input_kbps",
    "instantaneous_output_kbps",
    "pubsub_channels",
    "pubsub_patterns",
    "key_count",
    "expiration_key_count",
    "average_ttl",
)

REDIS_COUNTER_FIELDS = (
    "total_connections_received",
    "total_commands_processed",
    "total_net_input_bytes",
    "total_net_output_bytes",
    "keyspace_hits",
    "keyspace_misses",
    "expired_keys",
    "evicted_keys",
    "rejected_connections",
    "cpu_user_seconds",
    "cpu_sys_seconds",
    "main_thread_cpu_user_seconds",
    "main_thread_cpu_sys_seconds",
)

REDIS_STATE_FIELDS = (
    "role",
    "rdb_last_bgsave_status",
    "aof_last_bgrewrite_status",
    "aof_last_write_status",
    "aof_enabled",
    "rdb_bgsave_in_progress",
    "aof_rewrite_in_progress",
    "loading",
    "uptime_in_seconds",
)

REDIS_COMMAND_FIELDS = (
    "calls",
    "usec",
    "usec_per_call",
    "rejected",
    "failed",
)

REDIS_KEYSPACE_FIELDS = ("keys", "expires", "avg_ttl")

_COMMAND_NAME_RE = re.compile(r"^[a-z0-9_|-]{1,64}$")
_KEYSPACE_NAME_RE = re.compile(r"^db[0-9]+$")
_STATE_STRING_VALUES = {
    "role": {"master", "slave", "replica", "sentinel"},
    "rdb_last_bgsave_status": {"ok", "err"},
    "aof_last_bgrewrite_status": {"ok", "err"},
    "aof_last_write_status": {"ok", "err"},
}


def _finite_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _safe_state_value(name: str, value: Any) -> int | float | str | None:
    number = _finite_number(value)
    if number is not None:
        return number
    if isinstance(value, str) and value in _STATE_STRING_VALUES.get(name, set()):
        return value
    return None


def validate_redis_snapshot(value: Any) -> dict[str, Any]:
    """Return a fresh snapshot containing only the public Redis metric contract."""

    if not isinstance(value, Mapping):
        raise ValueError("Redis snapshot must be an object")

    queue_depth = _finite_number(value.get("queue_depth"))
    if queue_depth is None or queue_depth < 0:
        raise ValueError("Redis queue depth must be a non-negative number")

    normalized: dict[str, Any] = {
        "queue_depth": queue_depth,
        "gauges": {},
        "counters": {},
        "states": {},
        "keyspace": {},
        "commands": {},
    }

    for section, fields in (
        ("gauges", REDIS_GAUGE_FIELDS),
        ("counters", REDIS_COUNTER_FIELDS),
    ):
        source = value.get(section)
        if not isinstance(source, Mapping):
            continue
        for name in fields:
            number = _finite_number(source.get(name))
            if number is not None and number >= 0:
                normalized[section][name] = number

    states = value.get("states")
    if isinstance(states, Mapping):
        for name in REDIS_STATE_FIELDS:
            safe_value = _safe_state_value(name, states.get(name))
            if safe_value is not None:
                normalized["states"][name] = safe_value

    keyspace = value.get("keyspace")
    if isinstance(keyspace, Mapping):
        for database, database_values in keyspace.items():
            if not isinstance(database, str) or not _KEYSPACE_NAME_RE.fullmatch(database):
                continue
            if not isinstance(database_values, Mapping):
                continue
            safe_values: dict[str, int | float] = {}
            for name in REDIS_KEYSPACE_FIELDS:
                number = _finite_number(database_values.get(name))
                if number is not None and number >= 0:
                    safe_values[name] = number
            if safe_values:
                normalized["keyspace"][database] = safe_values

    commands = value.get("commands")
    if isinstance(commands, Mapping):
        for command_name, command_values in commands.items():
            if not isinstance(command_name, str) or not _COMMAND_NAME_RE.fullmatch(command_name):
                continue
            if not isinstance(command_values, Mapping):
                continue
            safe_values: dict[str, int | float] = {}
            for name in REDIS_COMMAND_FIELDS:
                number = _finite_number(command_values.get(name))
                if number is not None and number >= 0:
                    safe_values[name] = number
            if safe_values:
                normalized["commands"][command_name] = safe_values

    return normalized


def _parse_sample_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Redis sample timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Redis sample timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _series_stats(values: list[float]) -> dict[str, float | None]:
    return {
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": max(values) if values else None,
        "last": values[-1] if values else None,
    }


def _counter_delta(
    samples: list[dict[str, Any]],
    name: str,
) -> dict[str, int | float | bool | None]:
    values = [
        sample["redis"]["counters"][name]
        for sample in samples
        if name in sample["redis"]["counters"]
    ]
    if not values:
        return {"delta": None, "counter_reset": False}
    first = values[0]
    last = values[-1]
    if last < first:
        return {"delta": None, "counter_reset": True}
    return {"delta": last - first, "counter_reset": False}


def _delta_value(
    counters: dict[str, dict[str, int | float | bool | None]],
    name: str,
) -> int | float | None:
    result = counters.get(name)
    if not result or result.get("counter_reset"):
        return None
    delta = result.get("delta")
    return delta if isinstance(delta, (int, float)) else None


def summarize_redis_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate safe Redis samples using their timezone-aware sample timestamps."""

    if not samples:
        return {
            "sample_count": 0,
            "queue_depth": _series_stats([]),
            "gauges": {},
            "counters": {},
            "cpu": {
                "parent_utilization_ratio": None,
                "main_thread_utilization_ratio": None,
            },
            "cache_hit_ratio": None,
            "commands": {},
        }

    prepared = []
    for sample in samples:
        if not isinstance(sample, Mapping):
            raise ValueError("Redis sample must be an object")
        at = _parse_sample_time(sample.get("at"))
        prepared.append({"at": at, "redis": validate_redis_snapshot(sample.get("redis"))})
    prepared.sort(key=lambda item: item["at"])

    elapsed_seconds = (prepared[-1]["at"] - prepared[0]["at"]).total_seconds()
    queue_values = [float(item["redis"]["queue_depth"]) for item in prepared]
    gauge_names = sorted(
        {
            name
            for item in prepared
            for name in item["redis"]["gauges"]
        }
    )
    gauge_summary = {
        name: _series_stats(
            [float(item["redis"]["gauges"][name]) for item in prepared if name in item["redis"]["gauges"]]
        )
        for name in gauge_names
    }

    counter_names = sorted(
        {
            name
            for item in prepared
            for name in item["redis"]["counters"]
        }
    )
    counter_summary = {
        name: _counter_delta(prepared, name)
        for name in counter_names
    }

    parent_user = _delta_value(counter_summary, "cpu_user_seconds")
    parent_sys = _delta_value(counter_summary, "cpu_sys_seconds")
    main_user = _delta_value(counter_summary, "main_thread_cpu_user_seconds")
    main_sys = _delta_value(counter_summary, "main_thread_cpu_sys_seconds")
    parent_cpu_delta = (
        parent_user + parent_sys
        if parent_user is not None and parent_sys is not None
        else None
    )
    main_cpu_delta = (
        main_user + main_sys
        if main_user is not None and main_sys is not None
        else None
    )
    parent_ratio = (
        parent_cpu_delta / elapsed_seconds
        if parent_cpu_delta is not None and elapsed_seconds > 0
        else None
    )
    main_ratio = (
        main_cpu_delta / elapsed_seconds
        if main_cpu_delta is not None and elapsed_seconds > 0
        else None
    )

    hit_delta = _delta_value(counter_summary, "keyspace_hits")
    miss_delta = _delta_value(counter_summary, "keyspace_misses")
    cache_total = (
        hit_delta + miss_delta
        if hit_delta is not None and miss_delta is not None
        else None
    )
    cache_hit_ratio = hit_delta / cache_total if cache_total else None

    command_names = sorted(
        {
            name
            for item in prepared
            for name in item["redis"]["commands"]
        }
    )
    command_summary: dict[str, Any] = {}
    for command_name in command_names:
        command_values = [
            item["redis"]["commands"].get(command_name, {})
            for item in prepared
        ]
        calls = [value["calls"] for value in command_values if "calls" in value]
        usec = [value["usec"] for value in command_values if "usec" in value]
        calls_delta = (calls[-1] - calls[0]) if calls else None
        usec_delta = (usec[-1] - usec[0]) if usec else None
        reset = (
            (calls and calls[-1] < calls[0])
            or (usec and usec[-1] < usec[0])
        )
        if reset:
            calls_delta = None
            usec_delta = None
        command_summary[command_name] = {
            "calls_delta": calls_delta,
            "total_usec_delta": usec_delta,
            "weighted_usec_per_call": (
                usec_delta / calls_delta
                if calls_delta not in (None, 0) and usec_delta is not None
                else None
            ),
            "counter_reset": bool(reset),
        }
        for field in ("rejected", "failed"):
            field_values = [value[field] for value in command_values if field in value]
            if field_values:
                delta = field_values[-1] - field_values[0]
                command_summary[command_name][f"{field}_delta"] = (
                    None if delta < 0 else delta
                )

    return {
        "sample_count": len(prepared),
        "start": prepared[0]["at"].isoformat().replace("+00:00", "Z"),
        "end": prepared[-1]["at"].isoformat().replace("+00:00", "Z"),
        "elapsed_seconds": elapsed_seconds,
        "queue_depth": _series_stats(queue_values),
        "gauges": gauge_summary,
        "counters": counter_summary,
        "cpu": {
            "parent_cpu_seconds_delta": parent_cpu_delta,
            "parent_utilization_ratio": parent_ratio,
            "main_thread_cpu_seconds_delta": main_cpu_delta,
            "main_thread_utilization_ratio": main_ratio,
        },
        "cache_hit_ratio": cache_hit_ratio,
        "commands": command_summary,
    }


_MONITORING_RESOURCE_LABELS = ("project_id", "region", "instance_id", "node_id")
_MONITORING_FORBIDDEN_LABELS = {
    "authorization",
    "bearer",
    "credential",
    "host",
    "password",
    "port",
    "secret",
    "token",
    "url",
}


def _canonical_monitoring_time(value: Any) -> str:
    parsed = _parse_sample_time(value)
    return parsed.isoformat().replace("+00:00", "Z")


def _monitoring_value(value: Any) -> int | float | bool | None:
    if not isinstance(value, Mapping):
        return None
    if "int64Value" in value:
        try:
            return int(value["int64Value"])
        except (TypeError, ValueError):
            return None
    if "uint64Value" in value:
        try:
            parsed = int(value["uint64Value"])
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None
    if "doubleValue" in value:
        try:
            parsed = float(value["doubleValue"])
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None
    if "boolValue" in value and isinstance(value["boolValue"], bool):
        return value["boolValue"]
    return None


def _safe_monitoring_labels(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    labels: dict[str, str] = {}
    for name, label_value in value.items():
        if not isinstance(name, str) or not isinstance(label_value, str):
            continue
        if name.lower() in _MONITORING_FORBIDDEN_LABELS:
            continue
        if len(name) <= 128 and len(label_value) <= 256:
            labels[name] = label_value
    return dict(sorted(labels.items()))


def normalize_monitoring_series(
    descriptor: Mapping[str, Any],
    series: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize one Monitoring time series without copying request metadata."""

    metric_type = descriptor.get("type")
    metric_kind = descriptor.get("metricKind")
    value_type = descriptor.get("valueType")
    if not isinstance(metric_type, str) or not metric_type.startswith("redis.googleapis.com/"):
        raise ValueError("Monitoring descriptor is not a Redis metric")
    if metric_kind not in {"GAUGE", "DELTA", "CUMULATIVE"}:
        raise ValueError("Monitoring descriptor has an unsupported metric kind")
    if value_type not in {"INT64", "UINT64", "DOUBLE", "BOOL"}:
        raise ValueError("Monitoring descriptor has an unsupported value type")
    if not isinstance(series, Mapping):
        raise ValueError("Monitoring series must be an object")

    resource = series.get("resource")
    resource_labels = resource.get("labels") if isinstance(resource, Mapping) else {}
    normalized_resource = {
        name: resource_labels[name]
        for name in _MONITORING_RESOURCE_LABELS
        if isinstance(resource_labels, Mapping)
        and isinstance(resource_labels.get(name), str)
        and len(resource_labels[name]) <= 256
    }
    points: list[dict[str, Any]] = []
    raw_points = series.get("points")
    if isinstance(raw_points, list):
        for point in raw_points:
            if not isinstance(point, Mapping):
                continue
            interval = point.get("interval")
            if not isinstance(interval, Mapping):
                continue
            end = interval.get("endTime")
            if not isinstance(end, str):
                continue
            value = _monitoring_value(point.get("value"))
            if value is None:
                continue
            start = interval.get("startTime")
            points.append(
                {
                    "start": _canonical_monitoring_time(start) if start else None,
                    "end": _canonical_monitoring_time(end),
                    "value": value,
                }
            )
    points.sort(key=lambda point: point["end"])
    metric = series.get("metric")
    metric_labels = metric.get("labels") if isinstance(metric, Mapping) else {}
    return {
        "metric_type": metric_type,
        "metric_kind": metric_kind,
        "value_type": value_type,
        "unit": descriptor.get("unit", "")
        if isinstance(descriptor.get("unit", ""), str)
        else "",
        "metric_labels": _safe_monitoring_labels(metric_labels),
        "resource": {
            "type": "redis_instance",
            "labels": dict(sorted(normalized_resource.items())),
        },
        "points": points,
    }


def _monitoring_point_in_segment(point: Mapping[str, Any], start: datetime, end: datetime) -> bool:
    point_end = _parse_sample_time(point["end"])
    return start <= point_end < end


def summarize_monitoring_segments(
    series: list[dict[str, Any]],
    segments: list[dict[str, str]],
) -> dict[str, Any]:
    """Summarize normalized Redis Monitoring series by named half-open segments."""

    segment_output: dict[str, Any] = {}
    all_metric_names = {
        item.get("metric_type")
        for item in series
        if isinstance(item, Mapping) and isinstance(item.get("metric_type"), str)
    }
    observed_any: set[str] = set()
    for segment in segments:
        name = segment.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Monitoring segment name is required")
        if name in segment_output:
            raise ValueError(f"Duplicate Monitoring segment: {name}")
        start = _parse_sample_time(segment.get("start"))
        end = _parse_sample_time(segment.get("end"))
        if end <= start:
            raise ValueError(f"Monitoring segment must have positive duration: {name}")
        metrics: dict[str, Any] = {}
        observed: set[str] = set()
        for item in series:
            metric_name = item.get("metric_type")
            if not isinstance(metric_name, str):
                continue
            points = [
                point
                for point in item.get("points", [])
                if isinstance(point, Mapping)
                and _monitoring_point_in_segment(point, start, end)
            ]
            if not points:
                continue
            observed.add(metric_name)
            observed_any.add(metric_name)
            metric = metrics.setdefault(
                metric_name,
                {
                    "metric_kind": item.get("metric_kind"),
                    "value_type": item.get("value_type"),
                    "unit": item.get("unit", ""),
                    "point_count": 0,
                    "series_count": 0,
                    "values": [],
                },
            )
            metric["point_count"] += len(points)
            metric["series_count"] += 1
            metric["values"].extend(point["value"] for point in points)

        for metric_name, metric in metrics.items():
            values = [float(value) for value in metric.pop("values")]
            if metric["metric_kind"] == "DELTA":
                delta_sum = sum(values)
                metric["delta_sum"] = delta_sum
                metric["observed_zero"] = delta_sum == 0
            else:
                metric["gauge"] = _series_stats(values)
        segment_output[name] = {
            "start": _canonical_monitoring_time(segment.get("start")),
            "end": _canonical_monitoring_time(segment.get("end")),
            "metrics": metrics,
            "observed_metric_names": sorted(observed),
            "not_observed_metric_names": sorted(all_metric_names - observed),
        }

    return {
        "alignment": "60s",
        "boundary_rule": "[start,end)",
        "point_assignment": "point end timestamp",
        "segments": segment_output,
        "observed_metric_names": sorted(observed_any),
        "not_observed_metric_names": sorted(all_metric_names - observed_any),
    }


def sha256_file(path: Any) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
