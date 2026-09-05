from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.master_admin import MasterCommand, MasterError, validate_command, _fingerprint

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)
CMD = MasterCommand(UUID(int=1), UUID(int=2), "plan_change", "entitlement_change", target_plan="pro")


@pytest.mark.parametrize("change", [{"action": "promote"}, {"action": "suspend"},
    {"reason_code": "free form"}, {"target_id": "not uuid"}, {"request_id": None},
    {"target_plan": "admin"}, {"amount_microcredits": 1}, {"expires_at": NOW}])
def test_bad_commands_fail_closed(change):
    with pytest.raises(MasterError, match="master_input_invalid"):
        validate_command(replace(CMD, **change), source="browser", now=NOW)


@pytest.mark.parametrize("amount", [0, -1, True, 1.5, "100", 9_000_000_000_000_001])
def test_bonus_is_positive_bounded_integer(amount):
    command = replace(CMD, action="bonus_grant", target_plan=None, amount_microcredits=amount)
    with pytest.raises(MasterError):
        validate_command(command, source="browser", now=NOW)


def test_fingerprint_binds_authority_payload_and_reason():
    validate_command(CMD, source="browser", now=NOW)
    original = _fingerprint(CMD, UUID(int=3), "browser")
    assert len(original) == 64
    for changed in (replace(CMD, target_plan="max"), replace(CMD, reason_code="support_adjustment"),
                    replace(CMD, target_id=UUID(int=4))):
        assert _fingerprint(changed, UUID(int=3), "browser") != original
    assert _fingerprint(CMD, UUID(int=4), "browser") != original


def test_cli_promote_seam_only_and_time_guard():
    promote = replace(CMD, action="promote", target_plan=None)
    validate_command(promote, source="operator_cli", now=NOW)
    with pytest.raises(MasterError):
        validate_command(promote, source="browser", now=NOW)
    with pytest.raises(MasterError):
        validate_command(CMD, source="browser", now=NOW.replace(tzinfo=None))
