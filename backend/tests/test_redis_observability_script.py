from __future__ import annotations

import importlib.util
import hashlib
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "redis_observability.py"


def load_redis_observability_module():
    spec = importlib.util.spec_from_file_location(
        "redis_observability",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_snapshot_validation_keeps_only_safe_whitelisted_fields():
    module = load_redis_observability_module()

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
    assert normalized["counters"] == {
        "total_commands_processed": 100,
        "total_net_input_bytes": 200,
    }
    assert normalized["states"] == {"role": "master", "aof_enabled": 0}
    assert normalized["keyspace"] == {
        "db0": {"keys": 3, "expires": 1, "avg_ttl": 500}
    }
    assert normalized["commands"]["lpush"] == {
        "calls": 10,
        "usec": 50,
        "usec_per_call": 5.0,
    }
    assert "password" not in repr(normalized).lower()
    assert "redis://" not in repr(normalized)


def test_redis_sample_summary_calculates_runtime_deltas_and_percentiles():
    module = load_redis_observability_module()

    samples = [
        {
            "at": "2026-07-27T00:00:00Z",
            "redis": {
                "queue_depth": 2,
                "gauges": {"connected_clients": 4, "used_memory": 100},
                "counters": {
                    "total_commands_processed": 100,
                    "keyspace_hits": 20,
                    "keyspace_misses": 10,
                    "cpu_user_seconds": 1.0,
                    "cpu_sys_seconds": 0.5,
                },
                "commands": {"lpush": {"calls": 2, "usec": 4}},
            },
        },
        {
            "at": "2026-07-27T00:00:10Z",
            "redis": {
                "queue_depth": 9,
                "gauges": {"connected_clients": 8, "used_memory": 140},
                "counters": {
                    "total_commands_processed": 140,
                    "keyspace_hits": 50,
                    "keyspace_misses": 20,
                    "cpu_user_seconds": 2.0,
                    "cpu_sys_seconds": 0.7,
                },
                "commands": {"lpush": {"calls": 10, "usec": 36}},
            },
        },
    ]

    summary = module.summarize_redis_samples(samples)

    assert summary["queue_depth"]["max"] == 9
    assert summary["gauges"]["connected_clients"]["p50"] == pytest.approx(6)
    assert summary["gauges"]["connected_clients"]["last"] == 8
    assert summary["counters"]["total_commands_processed"]["delta"] == 40
    assert summary["cpu"]["parent_utilization_ratio"] == pytest.approx(0.12)
    assert summary["cache_hit_ratio"] == pytest.approx(0.75)
    assert summary["commands"]["lpush"]["calls_delta"] == 8
    assert summary["commands"]["lpush"]["weighted_usec_per_call"] == pytest.approx(4.0)


def test_redis_sample_summary_marks_decreased_counter_as_reset():
    module = load_redis_observability_module()

    samples = [
        {
            "at": "2026-07-27T00:00:00Z",
            "redis": {
                "queue_depth": 0,
                "counters": {"total_commands_processed": 100},
            },
        },
        {
            "at": "2026-07-27T00:00:10Z",
            "redis": {
                "queue_depth": 0,
                "counters": {"total_commands_processed": 40},
            },
        },
    ]

    summary = module.summarize_redis_samples(samples)

    assert summary["counters"]["total_commands_processed"] == {
        "delta": None,
        "counter_reset": True,
    }


def test_monitoring_series_normalization_is_secret_safe_and_time_ordered():
    module = load_redis_observability_module()

    normalized = module.normalize_monitoring_series(
        {
            "type": "redis.googleapis.com/instance/clients/connected",
            "metricKind": "GAUGE",
            "valueType": "DOUBLE",
            "unit": "1",
        },
        {
            "metric": {
                "type": "redis.googleapis.com/instance/clients/connected",
                "labels": {"node_id": "node-1", "shard": "primary"},
            },
            "resource": {
                "type": "redis_instance",
                "labels": {
                    "project_id": "krafton-vertex-live-3108",
                    "region": "asia-northeast3",
                    "instance_id": "creativeops-portfolio-redis",
                    "node_id": "node-1",
                    "host": "must-not-survive",
                },
            },
            "points": [
                {
                    "interval": {
                        "endTime": "2026-07-27T00:00:20Z",
                    },
                    "value": {"doubleValue": 3.5},
                },
                {
                    "interval": {
                        "endTime": "2026-07-27T00:00:10Z",
                    },
                    "value": {"int64Value": "2"},
                },
                {
                    "interval": {
                        "endTime": "2026-07-27T00:00:30Z",
                    },
                    "value": {"boolValue": True},
                },
            ],
            "request": "https://monitoring.googleapis.com/v3/secret",
            "authorization": "Bearer secret",
        },
    )

    assert normalized["metric_type"] == "redis.googleapis.com/instance/clients/connected"
    assert normalized["metric_kind"] == "GAUGE"
    assert normalized["value_type"] == "DOUBLE"
    assert normalized["metric_labels"] == {"node_id": "node-1", "shard": "primary"}
    assert normalized["resource"] == {
        "type": "redis_instance",
        "labels": {
            "project_id": "krafton-vertex-live-3108",
            "region": "asia-northeast3",
            "instance_id": "creativeops-portfolio-redis",
            "node_id": "node-1",
        },
    }
    assert normalized["points"] == [
        {"start": None, "end": "2026-07-27T00:00:10Z", "value": 2},
        {"start": None, "end": "2026-07-27T00:00:20Z", "value": 3.5},
        {"start": None, "end": "2026-07-27T00:00:30Z", "value": True},
    ]
    assert "authorization" not in repr(normalized).lower()
    assert "bearer" not in repr(normalized).lower()
    assert "monitoring.googleapis.com" not in repr(normalized)
    assert "host" not in repr(normalized)


def test_monitoring_series_normalization_preserves_empty_series_metadata():
    module = load_redis_observability_module()

    normalized = module.normalize_monitoring_series(
        {
            "type": "redis.googleapis.com/instance/never-observed",
            "metricKind": "DELTA",
            "valueType": "INT64",
        },
        {
            "metric": {"labels": {}},
            "resource": {"type": "redis_instance", "labels": {}},
            "points": [],
        },
    )

    assert normalized["metric_type"] == "redis.googleapis.com/instance/never-observed"
    assert normalized["metric_kind"] == "DELTA"
    assert normalized["points"] == []


def test_monitoring_segments_use_half_open_boundaries_and_preserve_observed_zero(tmp_path):
    module = load_redis_observability_module()
    series = [
        {
            "metric_type": "redis.googleapis.com/instance/commands/total",
            "metric_kind": "DELTA",
            "value_type": "INT64",
            "unit": "1",
            "metric_labels": {},
            "resource": {"type": "redis_instance", "labels": {}},
            "points": [
                {"start": "2026-07-27T00:00:00Z", "end": "2026-07-27T00:00:30Z", "value": 0},
                {"start": "2026-07-27T00:00:30Z", "end": "2026-07-27T00:01:00Z", "value": 5},
                {"start": "2026-07-27T00:01:00Z", "end": "2026-07-27T00:01:30Z", "value": 7},
            ],
        },
        {
            "metric_type": "redis.googleapis.com/instance/memory/usage_ratio",
            "metric_kind": "GAUGE",
            "value_type": "DOUBLE",
            "unit": "1",
            "metric_labels": {},
            "resource": {"type": "redis_instance", "labels": {}},
            "points": [
                {"start": None, "end": "2026-07-27T00:00:30Z", "value": 1.0},
                {"start": None, "end": "2026-07-27T00:01:00Z", "value": 3.0},
            ],
        },
        {
            "metric_type": "redis.googleapis.com/instance/never-observed",
            "metric_kind": "GAUGE",
            "value_type": "DOUBLE",
            "unit": "1",
            "metric_labels": {},
            "resource": {"type": "redis_instance", "labels": {}},
            "points": [],
        },
    ]
    segments = [
        {"name": "idle", "start": "2026-07-27T00:00:00Z", "end": "2026-07-27T00:01:00Z"},
        {"name": "benchmark", "start": "2026-07-27T00:01:00Z", "end": "2026-07-27T00:02:00Z"},
        {"name": "recovery", "start": "2026-07-27T00:02:00Z", "end": "2026-07-27T00:03:00Z"},
    ]

    summary = module.summarize_monitoring_segments(series, segments)

    idle_delta = summary["segments"]["idle"]["metrics"][
        "redis.googleapis.com/instance/commands/total"
    ]
    assert idle_delta["delta_sum"] == 0
    assert idle_delta["observed_zero"] is True
    assert summary["segments"]["benchmark"]["metrics"][
        "redis.googleapis.com/instance/commands/total"
    ]["delta_sum"] == 12
    assert summary["segments"]["idle"]["metrics"][
        "redis.googleapis.com/instance/memory/usage_ratio"
    ]["gauge"]["p50"] == pytest.approx(1.0)
    assert summary["segments"]["idle"]["metrics"][
        "redis.googleapis.com/instance/memory/usage_ratio"
    ]["gauge"]["p95"] == pytest.approx(1.0)
    assert summary["segments"]["idle"]["metrics"][
        "redis.googleapis.com/instance/memory/usage_ratio"
    ]["gauge"]["max"] == pytest.approx(1.0)
    assert "redis.googleapis.com/instance/never-observed" in summary["segments"][
        "recovery"
    ]["not_observed_metric_names"]

    artifact = tmp_path / "monitoring.json"
    artifact.write_text('{"safe": true}\n', encoding="utf-8")
    assert module.sha256_file(artifact) == hashlib.sha256(
        b'{"safe": true}\n'
    ).hexdigest()
