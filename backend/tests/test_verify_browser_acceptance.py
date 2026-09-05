import pytest
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from browser_acceptance_support import HarnessError
from verify_browser_acceptance import main, validate_results


def rows():
    return [{"cycle": cycle, "groups": 8, "checks": 80, "external_requests": 0,
             "cleanup": 0, "recovered": 2, "seconds": 1.0} for cycle in (1, 2)]


def test_validate_results_requires_two_complete_cycles():
    assert validate_results(rows()) == {"complete": True, "cycles": 2, "groups": 8,
                                        "checks": 160, "cleanup": 0, "external_requests": 0}
    with pytest.raises(HarnessError, match="browser_acceptance_incomplete"):
        validate_results(rows()[:1])


def test_cli_refuses_arguments(capsys):
    assert main(["--cycles", "1"]) == 2
    assert "arguments_refused" in capsys.readouterr().out
