import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mock_auth_support as support


@pytest.mark.parametrize("project", ["", "default", "creativeops-login-preview", "ownership-verify-../",
                                    "ownership-verify-abcdef", "ownership-verify-AAAAAAAAAAAA"])
def test_project_refuses_unowned_names(project):
    with pytest.raises(support.HarnessError, match="invalid_project"):
        support.validate_project(project)


def test_project_accepts_only_fresh_namespace():
    assert support.validate_project("ownership-verify-012345abcdef") == "ownership-verify-012345abcdef"
