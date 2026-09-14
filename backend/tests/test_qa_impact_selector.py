from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPOSITORY_ROOT / "qa" / "contracts"
IMPACT_ROOT = REPOSITORY_ROOT / "qa" / "impact"
sys.path.insert(0, str(CONTRACT_ROOT))
sys.path.insert(0, str(IMPACT_ROOT))

from registry import load_registry  # noqa: E402
import selector as impact_selector  # noqa: E402
from select_impact import changes_between, main  # noqa: E402
from selector import Change, ImpactError, load_policy, select_impact, validate_manifest  # noqa: E402


BASE = "1" * 40
HEAD = "2" * 40


@pytest.fixture
def registry():
    return load_registry(CONTRACT_ROOT)


@pytest.fixture
def policy(registry):
    return load_policy(scenario_ids=registry.by_id())


def _select(registry, policy, changes: list[Change]) -> dict:
    return select_impact(
        registry,
        policy,
        changes,
        base_revision=BASE,
        head_revision=HEAD,
    )


def _selected(manifest: dict) -> set[str]:
    return {
        decision["scenario_id"]
        for decision in manifest["scenario_decisions"]
        if decision["selected"]
    }


def test_related_path_selects_only_direct_scenario(registry, policy) -> None:
    manifest = _select(
        registry,
        policy,
        [Change("M", "frontend/src/pages/UsagePage.tsx")],
    )

    assert manifest["classification"] == "TARGETED_E2E"
    assert _selected(manifest) == {"usage_credits"}
    usage = next(row for row in manifest["scenario_decisions"] if row["scenario_id"] == "usage_credits")
    assert usage["rule_ids"] == ["registry_related_path", "usage_surface_changed"]
    assert all(row["reason"] == "not_impacted_by_changed_paths"
               for row in manifest["scenario_decisions"] if not row["selected"])


def test_shared_generate_page_selects_all_related_modes(registry, policy) -> None:
    manifest = _select(
        registry,
        policy,
        [Change("M", "frontend/src/pages/GeneratePage.tsx")],
    )

    assert manifest["classification"] == "TARGETED_E2E"
    assert _selected(manifest) == {
        "prompt_review", "t2i_generation", "t2v_generation", "i2v_generation"
    }


@pytest.mark.parametrize(
    "path",
    [
        "frontend/src/api/client.ts",
        "qa/contracts/registry.v1.json",
        "qa/impact/policy.v1.json",
    ],
)
def test_shared_or_contract_change_requires_full_e2e(registry, policy, path: str) -> None:
    manifest = _select(registry, policy, [Change("M", path)])

    assert manifest["classification"] == "FULL_E2E"
    assert len(_selected(manifest)) == 10
    assert manifest["unmatched_paths"] == []


def test_unknown_path_fails_safe_to_full_e2e(registry, policy) -> None:
    manifest = _select(registry, policy, [Change("A", "scripts/new_runtime_driver.py")])

    assert manifest["classification"] == "FULL_E2E"
    assert manifest["unmatched_paths"] == ["scripts/new_runtime_driver.py"]
    assert all("unknown_path_fallback" in row["rule_ids"] for row in manifest["scenario_decisions"])


def test_all_current_product_paths_have_explicit_policy_coverage(registry, policy) -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "backend/app/**", "frontend/src/**"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    manifest = _select(registry, policy, [Change("M", path) for path in tracked])

    assert tracked
    assert manifest["unmatched_paths"] == []


def test_docs_only_change_explicitly_requires_no_browser_e2e(registry, policy) -> None:
    manifest = _select(registry, policy, [Change("M", "docs/testing.md")])

    assert manifest["classification"] == "NO_E2E_REQUIRED"
    assert _selected(manifest) == set()
    assert all(row["reason"] == "no_e2e_required" for row in manifest["scenario_decisions"])
    assert all(row["rule_ids"] == ["documentation_only"] for row in manifest["scenario_decisions"])


def test_product_change_wins_over_docs_only_change(registry, policy) -> None:
    manifest = _select(
        registry,
        policy,
        [Change("M", "docs/testing.md"), Change("M", "frontend/src/pages/UsagePage.tsx")],
    )

    assert manifest["classification"] == "TARGETED_E2E"
    assert _selected(manifest) == {"usage_credits"}


def test_rename_evaluates_old_and_new_paths(registry, policy) -> None:
    safe_rename = _select(
        registry,
        policy,
        [Change("R", "frontend/src/auth/SessionView.tsx", "frontend/src/auth/OldSessionView.tsx")],
    )
    unknown_destination = _select(
        registry,
        policy,
        [Change("R", "frontend/src/new-session.tsx", "frontend/src/auth/SessionView.tsx")],
    )

    assert _selected(safe_rename) == {"auth_login", "role_ops_master"}
    assert unknown_destination["classification"] == "FULL_E2E"
    assert unknown_destination["unmatched_paths"] == ["frontend/src/new-session.tsx"]


def test_deleted_related_path_remains_impacted(registry, policy) -> None:
    manifest = _select(
        registry,
        policy,
        [Change("D", "frontend/src/pages/UsagePage.tsx")],
    )

    assert manifest["classification"] == "TARGETED_E2E"
    assert _selected(manifest) == {"usage_credits"}


@pytest.mark.parametrize(
    "path",
    [
        "C:/private/file.py",
        "../outside.py",
        "backend\\app\\main.py",
        ".env",
        "config/service-account.json",
        "keys/deploy.pem",
    ],
)
def test_unsafe_or_secret_like_path_is_refused(registry, policy, path: str) -> None:
    with pytest.raises(ImpactError, match="impact_change_invalid"):
        _select(registry, policy, [Change("M", path)])


def test_duplicate_path_is_refused(registry, policy) -> None:
    with pytest.raises(ImpactError, match="impact_change_duplicate"):
        _select(
            registry,
            policy,
            [Change("M", "docs/testing.md"), Change("M", "docs/testing.md")],
        )


@pytest.mark.parametrize(
    ("base", "head"),
    [("main", HEAD), (BASE, "head"), (BASE, BASE)],
)
def test_only_distinct_immutable_revisions_are_accepted(registry, policy, base: str, head: str) -> None:
    with pytest.raises(ImpactError, match="impact_revision_invalid"):
        select_impact(
            registry,
            policy,
            [Change("M", "docs/testing.md")],
            base_revision=base,
            head_revision=head,
        )


def test_selection_is_deterministic_for_change_order(registry, policy) -> None:
    changes = [
        Change("M", "frontend/src/pages/UsagePage.tsx"),
        Change("M", "frontend/src/pages/HistoryPage.tsx"),
    ]

    first = _select(registry, policy, changes)
    second = _select(registry, policy, list(reversed(changes)))

    assert first == second
    assert first["selection_sha256"] == second["selection_sha256"]


def test_manifest_validator_rederives_mapping(registry, policy) -> None:
    manifest = _select(registry, policy, [Change("M", "frontend/src/pages/UsagePage.tsx")])
    tampered = copy.deepcopy(manifest)
    t2i = next(row for row in tampered["scenario_decisions"] if row["scenario_id"] == "t2i_generation")
    t2i.update(selected=True, reason="directly_impacted")
    tampered["selection_sha256"] = impact_selector._selection_sha(tampered)

    with pytest.raises(ImpactError, match="impact_manifest_mapping_invalid"):
        validate_manifest(tampered, registry, policy)


def test_policy_sha_covers_manifest_schema(tmp_path: Path, registry) -> None:
    root = tmp_path / "impact"
    shutil.copytree(IMPACT_ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
    before = load_policy(root, scenario_ids=registry.by_id()).sha256
    schema_path = root / "selection.schema.v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["description"] = "contract revision"
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

    assert load_policy(root, scenario_ids=registry.by_id()).sha256 != before


def test_cli_uses_git_diff_adapter_and_outputs_json(tmp_path: Path, capsys) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    commands = [
        ["git", "init"],
        ["git", "config", "user.name", "QA Test"],
        ["git", "config", "user.email", "qa-test@invalid.example"],
        ["git", "commit", "--allow-empty", "-m", "base"],
    ]
    for command in commands:
        subprocess.run(command, cwd=repository, check=True, capture_output=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
    ).stdout.strip()
    docs = repository / "docs"
    docs.mkdir()
    (docs / "note.md").write_text("documentation only\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/note.md"], cwd=repository, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "docs"], cwd=repository, check=True, capture_output=True
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
    ).stdout.strip()

    assert main(["--base", base, "--head", head], repository_root=repository) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["complete"] is True
    assert output["classification"] == "NO_E2E_REQUIRED"
    assert output["changed_files"] == [
        {"status": "A", "path": "docs/note.md", "previous_path": None}
    ]


def test_git_adapter_preserves_rename_paths(tmp_path: Path) -> None:
    repository = tmp_path / "rename-repo"
    source = repository / "frontend" / "src" / "auth" / "OldSession.tsx"
    source.parent.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "QA Test"], cwd=repository, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "qa-test@invalid.example"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    source.write_text("export const session = true\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repository, check=True, capture_output=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
    ).stdout.strip()
    target = source.with_name("Session.tsx")
    subprocess.run(["git", "mv", str(source), str(target)], cwd=repository, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "rename"], cwd=repository, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
    ).stdout.strip()

    assert changes_between(repository, base, head) == [
        Change(
            "R",
            "frontend/src/auth/Session.tsx",
            "frontend/src/auth/OldSession.tsx",
        )
    ]


def test_git_adapter_refuses_mutable_or_same_revision_before_git_call(tmp_path: Path) -> None:
    with pytest.raises(ImpactError, match="impact_revision_invalid"):
        changes_between(tmp_path, "main", HEAD)
    with pytest.raises(ImpactError, match="impact_revision_invalid"):
        changes_between(tmp_path, BASE, BASE)
