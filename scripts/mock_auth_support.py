"""Test-only local authenticated smoke harness; never imported by the product."""
import re


class HarnessError(RuntimeError):
    """A bounded public failure code, never a raw exception/response."""


def validate_project(project):
    if not re.fullmatch(r"ownership-verify-[0-9a-f]{12}", project):
        raise HarnessError("invalid_project")
    return project
