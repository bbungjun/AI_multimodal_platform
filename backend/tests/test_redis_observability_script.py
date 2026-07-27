from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "redis_observability.py"
EXPORTER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_redis_monitoring_metrics.py"


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


def load_monitoring_exporter_module():
    spec = importlib.util.spec_from_file_location(
        "export_redis_monitoring_metrics",
        EXPORTER_PATH,
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


def test_command_counter_missing_from_first_sample_uses_zero_baseline():
    module = load_redis_observability_module()

    summary = module.summarize_redis_samples(
        [
            {
                "at": "2026-07-27T00:00:00Z",
                "redis": {"queue_depth": 0, "commands": {}},
            },
            {
                "at": "2026-07-27T00:00:10Z",
                "redis": {
                    "queue_depth": 0,
                    "commands": {"lpush": {"calls": 10, "usec": 40}},
                },
            },
        ]
    )

    assert summary["commands"]["lpush"] == {
        "calls_delta": 10,
        "total_usec_delta": 40,
        "weighted_usec_per_call": pytest.approx(4.0),
        "counter_reset": False,
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


def test_monitoring_export_defaults_to_dry_run_and_plans_only_valid_segments(tmp_path, capsys):
    module = load_monitoring_exporter_module()
    profile = {
        "account": "youngjun3108@gmail.com",
        "project_id": "krafton-vertex-live-3108",
        "region": "asia-northeast3",
        "redis_instance_name": "creativeops-portfolio-redis",
    }
    profile_path = tmp_path / "release-profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    output_path = tmp_path / "raw.json"

    exit_code = module.main(
        [
            "--profile",
            str(profile_path),
            "--start",
            "2026-07-27T06:21:00Z",
            "--end",
            "2026-07-27T06:32:00Z",
            "--segment",
            "idle,2026-07-27T06:21:00Z,2026-07-27T06:24:00Z",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert not output_path.exists()
    planned = json.loads(capsys.readouterr().out)
    assert planned["dry_run"] is True
    assert planned["descriptor_query_count"] == 1
    assert planned["time_series_query_count"] == "one per Redis descriptor"


def test_monitoring_export_rejects_invalid_project_before_token(monkeypatch, tmp_path):
    module = load_monitoring_exporter_module()
    profile = {
        "account": "youngjun3108@gmail.com",
        "project_id": "wrong-project",
        "region": "asia-northeast3",
        "redis_instance_name": "creativeops-portfolio-redis",
    }
    profile_path = tmp_path / "release-profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    args = module.build_parser().parse_args(
        [
            "--profile",
            str(profile_path),
            "--start",
            "2026-07-27T06:21:00Z",
            "--end",
            "2026-07-27T06:32:00Z",
            "--execute",
        ]
    )
    token_calls = []
    monkeypatch.setattr(module, "_access_token", lambda: token_calls.append(True))

    with pytest.raises(module.ExportError, match="project"):
        module.run_export(args)

    assert token_calls == []


def test_monitoring_client_retries_429_with_bounded_backoff():
    module = load_monitoring_exporter_module()
    attempts = 0
    delays = []

    def transport(path, params):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise module.MonitoringHttpError(429)
        return {"ok": True}

    client = module.MonitoringClient(
        token_provider=lambda: "opaque-token",
        transport=transport,
        sleep_fn=delays.append,
    )

    assert client.request_json("projects/p/test", {}) == {"ok": True}
    assert attempts == 2
    assert delays == [1]


def test_monitoring_client_stops_after_five_retryable_responses():
    module = load_monitoring_exporter_module()
    attempts = 0
    delays = []

    def transport(path, params):
        nonlocal attempts
        attempts += 1
        raise module.MonitoringHttpError(500)

    client = module.MonitoringClient(
        token_provider=lambda: "opaque-token",
        transport=transport,
        sleep_fn=delays.append,
    )

    with pytest.raises(module.ExportError, match="bounded retries"):
        client.request_json("projects/p/test", {})
    assert attempts == 5
    assert delays == [1, 2, 4, 8]


def test_monitoring_export_paginates_descriptors_and_time_series():
    module = load_monitoring_exporter_module()
    descriptors = [
        {
            "type": "redis.googleapis.com/instance/observed",
            "metricKind": "GAUGE",
            "valueType": "DOUBLE",
            "unit": "1",
        },
        {
            "type": "redis.googleapis.com/instance/no-series",
            "metricKind": "GAUGE",
            "valueType": "DOUBLE",
            "unit": "1",
        },
        {
            "type": "redis.googleapis.com/instance/second-no-series",
            "metricKind": "DELTA",
            "valueType": "DISTRIBUTION",
            "unit": "1",
            "monitoredResourceTypes": ["redis.googleapis.com/Cluster"],
        },
    ]

    def descriptor_page(page_token):
        if page_token is None:
            return {"metricDescriptors": descriptors[:2], "nextPageToken": "page-2"}
        return {"metricDescriptors": descriptors[2:]}

    def transport(path, params):
        if path.endswith("metricDescriptors"):
            return descriptor_page(params.get("pageToken"))
        metric_type = params["filter"].split('metric.type = "', 1)[1].split('"', 1)[0]
        if metric_type == descriptors[0]["type"]:
            if params.get("pageToken"):
                return {
                    "timeSeries": [
                        {
                            "metric": {"labels": {}},
                            "resource": {"type": "redis_instance", "labels": {}},
                            "points": [
                                {
                                    "interval": {"endTime": "2026-07-27T06:22:30Z"},
                                    "value": {"doubleValue": 2.0},
                                }
                            ],
                        }
                    ]
                }
            return {
                "timeSeries": [
                    {
                        "metric": {"labels": {}},
                        "resource": {"type": "redis_instance", "labels": {}},
                        "points": [
                            {
                                "interval": {"endTime": "2026-07-27T06:21:30Z"},
                                "value": {"doubleValue": 1.0},
                            }
                        ],
                    }
                ],
                "nextPageToken": "series-2",
            }
        if metric_type == descriptors[2]["type"]:
            raise AssertionError("non-instance descriptor must not be queried")
        return {"timeSeries": []}

    client = module.MonitoringClient(
        token_provider=lambda: "opaque-token",
        transport=transport,
        sleep_fn=lambda _: None,
    )
    request = {
        "project_id": "krafton-vertex-live-3108",
        "region": "asia-northeast3",
        "redis_instance_name": "creativeops-portfolio-redis",
        "resource_name": "projects/krafton-vertex-live-3108/locations/asia-northeast3/instances/creativeops-portfolio-redis",
        "start": "2026-07-27T06:21:00Z",
        "end": "2026-07-27T06:24:00Z",
        "segments": [
            {"name": "idle", "start": "2026-07-27T06:21:00Z", "end": "2026-07-27T06:24:00Z"}
        ],
    }

    result = module.collect_redis_monitoring(request, client)

    assert result["descriptor_count"] == 3
    assert result["available_metric_count"] == 1
    assert result["not_observed_metric_count"] == 2
    assert result["query_error_count"] == 0
    assert len(result["series"]) == 4
    assert "authorization" not in repr(result).lower()
    assert "opaque-token" not in repr(result)
