from types import SimpleNamespace
from uuid import UUID

import pytest

from app.master_cli import validate_target
from app.master_admin import MasterError


@pytest.mark.parametrize("change", [dict(database_url="postgresql://remote/test"),
    dict(database_url="sqlite:///test"), dict(database_url="postgresql://db/postgres"),
    dict(ai_provider="vertex"), dict(app_env="production")])
def test_guard_refuses_nonlocal_or_paid_targets(change):
    values = dict(database_url="postgresql://db/test", ai_provider="mock", app_env="test")
    values.update(change)
    with pytest.raises(MasterError, match="master_cli_target_refused"):
        validate_target(SimpleNamespace(**values), "test", UUID(int=1), False, None)


def test_apply_requires_exact_confirmation_and_preview_does_not():
    settings = SimpleNamespace(database_url="postgresql://db/test", ai_provider="mock", app_env="local")
    user = UUID(int=1)
    validate_target(settings, "test", user, False, None)
    validate_target(settings, "test", user, True, f"PROMOTE:{user}")
    for expected, confirmation in (("other", f"PROMOTE:{user}"), ("test", None), ("test", "PROMOTE:other")):
        with pytest.raises(MasterError):
            validate_target(settings, expected, user, True, confirmation)
