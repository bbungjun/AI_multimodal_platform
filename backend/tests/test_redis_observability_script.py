from __future__ import annotations

import importlib.util
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
