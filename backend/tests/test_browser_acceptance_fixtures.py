from uuid import NAMESPACE_URL, uuid5

import pytest

from tests.browser_acceptance_fixtures import expected_user_id, validate_payload


def payload():
    return {"project": "ownership-verify-0123456789ab", "hashes": {"a": "a" * 64, "master": "b" * 64}}


def test_validate_payload_accepts_only_owned_mock_database():
    assert validate_payload(payload(), database_host="db", database_name="ownership_verify_0123456789ab",
                            provider="mock", app_env="local") == payload()["hashes"]
    assert expected_user_id("a") == uuid5(NAMESPACE_URL, "ownership-fixture/a")


@pytest.mark.parametrize("change", [
    {"database_host": "localhost"}, {"database_name": "preview"}, {"provider": "vertex"},
    {"app_env": "production"},
])
def test_validate_payload_refuses_unsafe_target(change):
    kwargs = dict(database_host="db", database_name="ownership_verify_0123456789ab",
                  provider="mock", app_env="local")
    kwargs.update(change)
    with pytest.raises(ValueError, match="recovery_input_refused"):
        validate_payload(payload(), **kwargs)


def test_validate_payload_refuses_unknown_or_reused_hashes():
    unsafe = payload()
    unsafe["hashes"]["master"] = "a" * 64
    with pytest.raises(ValueError, match="recovery_input_refused"):
        validate_payload(unsafe, database_host="db", database_name="ownership_verify_0123456789ab",
                         provider="mock", app_env="local")
    with pytest.raises(ValueError, match="recovery_case_refused"):
        expected_user_id("b")
