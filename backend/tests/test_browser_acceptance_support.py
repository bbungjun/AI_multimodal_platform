import pytest
from pathlib import Path
import socket
import sys

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import browser_acceptance_support as support
from browser_acceptance_support import (
    HarnessError, parse_emergency_receipt, parse_node_message, port_available,
)


def test_emergency_receipt_is_count_only_and_consistent():
    assert parse_emergency_receipt(
        "PASS: emergency_session_revocation mode=execute reason=operator_drill active_before=3 revoked=3 active_after=0"
    )["revoked"] == 3
    with pytest.raises(HarnessError, match="emergency_receipt_invalid"):
        parse_emergency_receipt("PASS: token=secret")


def test_node_protocol_is_closed_and_typed():
    value = '{"type":"complete","groups":8,"checks":80,"external_requests":0}'
    assert parse_node_message(value, "complete")["groups"] == 8
    with pytest.raises(HarnessError, match="browser_protocol_invalid"):
        parse_node_message('{"type":"complete","groups":8,"checks":80,"external_requests":0,"secret":"x"}', "complete")


def test_reserved_port_probe_returns_boolean():
    assert type(port_available()) is bool


def test_port_probe_is_posix_compatible_and_refuses_listener(monkeypatch):
    monkeypatch.delattr(support.socket, "SO_EXCLUSIVEADDRUSE", raising=False)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        assert port_available(listener.getsockname()[1]) is False
