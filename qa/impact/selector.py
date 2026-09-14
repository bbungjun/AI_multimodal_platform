"""Deterministic, fail-safe mapping from Git changes to Agent QA scenarios."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
REVISION = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{2,95}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_STATUSES = {"A", "C", "D", "M", "R", "T"}
POLICY_KEYS = {"schema_version", "policy_id", "rules"}
RULE_KEYS = {"id", "effect", "scenarios", "paths", "prefixes", "reason"}
MANIFEST_KEYS = {
    "schema_version", "base_revision", "head_revision", "registry_sha256",
    "policy_sha256", "classification", "changed_files", "unmatched_paths",
    "scenario_decisions", "selection_sha256",
}
CHANGE_KEYS = {"status", "path", "previous_path"}
DECISION_KEYS = {"scenario_id", "selected", "reason", "rule_ids"}
CLASSIFICATIONS = {"FULL_E2E", "TARGETED_E2E", "NO_E2E_REQUIRED"}
DECISION_REASONS = {
    "full_e2e_required", "directly_impacted", "not_impacted_by_changed_paths",
    "no_e2e_required",
}


class ImpactError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class Change:
    status: str
    path: str
    previous_path: str | None = None


@dataclass(frozen=True)
class Policy:
    metadata: dict[str, Any]
    sha256: str


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as error:
        raise ImpactError("impact_json_invalid") from error
    if type(value) is not dict:
        raise ImpactError("impact_object_required")
    return value


def _closed(value: dict[str, Any], keys: set[str], code: str) -> None:
    if set(value) != keys:
        raise ImpactError(code)


def _unique_strings(value: Any, code: str, *, allow_empty: bool = False) -> list[str]:
    if (type(value) is not list or (not value and not allow_empty)
            or any(type(item) is not str for item in value)
            or len(value) != len(set(value))):
        raise ImpactError(code)
    return value


def _secret_like_path(value: str) -> bool:
    lowered = value.lower()
    name = PurePosixPath(lowered).name
    if name == ".env.example":
        return False
    if name == ".env" or name.startswith(".env."):
        return True
    if name in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}:
        return True
    if name.endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    return any(token in name for token in ("credential", "service-account", "private-key"))


def _safe_path(value: Any) -> bool:
    if type(value) is not str or not value or "\\" in value or any(ord(char) < 32 for char in value):
        return False
    path = PurePosixPath(value)
    return (not value.startswith(("/", "~")) and not re.match(r"^[A-Za-z]:", value)
            and ".." not in path.parts and all(part not in {"", "."} for part in path.parts)
            and not _secret_like_path(value))


def _safe_prefix(value: Any) -> bool:
    return type(value) is str and value.endswith("/") and _safe_path(value + "sentinel")


def load_policy(root: Path = HERE, *, scenario_ids: Iterable[str]) -> Policy:
    metadata = _read_json(root / "policy.v1.json")
    _closed(metadata, POLICY_KEYS, "impact_policy_fields_invalid")
    if metadata["schema_version"] != 1 or metadata["policy_id"] != "creativeops-agent-qa-impact":
        raise ImpactError("impact_policy_identity_invalid")
    allowed_scenarios = set(scenario_ids)
    rules = metadata["rules"]
    if type(rules) is not list or not rules:
        raise ImpactError("impact_policy_rules_invalid")
    rule_ids: list[str] = []
    for rule in rules:
        if type(rule) is not dict:
            raise ImpactError("impact_policy_rule_invalid")
        _closed(rule, RULE_KEYS, "impact_policy_rule_invalid")
        paths = _unique_strings(rule["paths"], "impact_policy_paths_invalid", allow_empty=True)
        prefixes = _unique_strings(rule["prefixes"], "impact_policy_prefixes_invalid", allow_empty=True)
        scenarios = _unique_strings(rule["scenarios"], "impact_policy_scenarios_invalid", allow_empty=True)
        if (not IDENTIFIER.fullmatch(rule["id"]) or rule["effect"] not in {"all", "scenario", "no_e2e"}
                or not IDENTIFIER.fullmatch(rule["reason"]) or not paths and not prefixes
                or not all(_safe_path(path) for path in paths)
                or not all(_safe_prefix(prefix) for prefix in prefixes)):
            raise ImpactError("impact_policy_rule_invalid")
        if rule["effect"] == "scenario":
            if not scenarios or not set(scenarios) <= allowed_scenarios:
                raise ImpactError("impact_policy_scenarios_invalid")
        elif scenarios:
            raise ImpactError("impact_policy_scenarios_invalid")
        rule_ids.append(rule["id"])
    if len(rule_ids) != len(set(rule_ids)):
        raise ImpactError("impact_policy_rule_duplicate")
    digest = hashlib.sha256()
    for name in ("policy.v1.json", "selection.schema.v1.json"):
        try:
            data = (root / name).read_bytes()
        except OSError as error:
            raise ImpactError("impact_contract_missing") from error
        digest.update(name.encode("utf-8") + b"\0" + data)
    return Policy(metadata=metadata, sha256=digest.hexdigest())


def _canonical_changes(changes: Iterable[Change]) -> list[Change]:
    values = list(changes)
    if not values:
        raise ImpactError("impact_changes_required")
    occupied_paths: set[str] = set()
    canonical: set[Change] = set()
    for change in values:
        if not isinstance(change, Change) or change.status not in ALLOWED_STATUSES or not _safe_path(change.path):
            raise ImpactError("impact_change_invalid")
        needs_previous = change.status in {"C", "R"}
        if needs_previous != (change.previous_path is not None):
            raise ImpactError("impact_change_invalid")
        paths = [change.path]
        if change.previous_path is not None:
            if not _safe_path(change.previous_path) or change.previous_path == change.path:
                raise ImpactError("impact_change_invalid")
            paths.append(change.previous_path)
        if any(path in occupied_paths for path in paths):
            raise ImpactError("impact_change_duplicate")
        occupied_paths.update(paths)
        canonical.add(change)
    if len(canonical) != len(values):
        raise ImpactError("impact_change_duplicate")
    return sorted(canonical, key=lambda item: (item.path, item.previous_path or "", item.status))


def _rule_matches(rule: dict[str, Any], path: str) -> bool:
    return path in rule["paths"] or any(path.startswith(prefix) for prefix in rule["prefixes"])


def _selection_sha(manifest: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in manifest.items() if key != "selection_sha256"}
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _derive_manifest(
    registry: Any,
    policy: Policy,
    changes: Iterable[Change],
    *,
    base_revision: str,
    head_revision: str,
) -> dict[str, Any]:
    if (not REVISION.fullmatch(base_revision) or not REVISION.fullmatch(head_revision)
            or base_revision == head_revision):
        raise ImpactError("impact_revision_invalid")
    canonical_changes = _canonical_changes(changes)
    scenario_ids = [scenario["id"] for scenario in registry.scenarios]
    direct_paths: dict[str, set[str]] = {}
    for scenario in registry.scenarios:
        for path in scenario["related_paths"]:
            direct_paths.setdefault(path, set()).add(scenario["id"])

    scenario_hits = {scenario_id: set() for scenario_id in scenario_ids}
    full_rule_ids: set[str] = set()
    no_e2e_rule_ids: set[str] = set()
    unmatched_paths: set[str] = set()
    for change in canonical_changes:
        evaluated_paths = [change.path] + ([change.previous_path] if change.previous_path else [])
        for path in evaluated_paths:
            matched = False
            for scenario_id in direct_paths.get(path, set()):
                scenario_hits[scenario_id].add("registry_related_path")
                matched = True
            for rule in policy.metadata["rules"]:
                if not _rule_matches(rule, path):
                    continue
                matched = True
                if rule["effect"] == "all":
                    full_rule_ids.add(rule["id"])
                elif rule["effect"] == "scenario":
                    for scenario_id in rule["scenarios"]:
                        scenario_hits[scenario_id].add(rule["id"])
                else:
                    no_e2e_rule_ids.add(rule["id"])
            if not matched:
                unmatched_paths.add(path)

    selected_ids = {scenario_id for scenario_id, hits in scenario_hits.items() if hits}
    if unmatched_paths:
        full_rule_ids.add("unknown_path_fallback")
    if full_rule_ids or selected_ids == set(scenario_ids):
        classification = "FULL_E2E"
        selected_ids = set(scenario_ids)
    elif selected_ids:
        classification = "TARGETED_E2E"
    else:
        classification = "NO_E2E_REQUIRED"

    decisions = []
    for scenario_id in scenario_ids:
        selected = scenario_id in selected_ids
        if classification == "FULL_E2E":
            reason = "full_e2e_required"
            rule_ids = sorted(full_rule_ids | scenario_hits[scenario_id])
        elif selected:
            reason = "directly_impacted"
            rule_ids = sorted(scenario_hits[scenario_id])
        elif classification == "NO_E2E_REQUIRED":
            reason = "no_e2e_required"
            rule_ids = sorted(no_e2e_rule_ids)
        else:
            reason = "not_impacted_by_changed_paths"
            rule_ids = []
        decisions.append({
            "scenario_id": scenario_id,
            "selected": selected,
            "reason": reason,
            "rule_ids": rule_ids,
        })

    manifest = {
        "schema_version": 1,
        "base_revision": base_revision,
        "head_revision": head_revision,
        "registry_sha256": registry.sha256,
        "policy_sha256": policy.sha256,
        "classification": classification,
        "changed_files": [
            {"status": change.status, "path": change.path, "previous_path": change.previous_path}
            for change in canonical_changes
        ],
        "unmatched_paths": sorted(unmatched_paths),
        "scenario_decisions": decisions,
        "selection_sha256": "",
    }
    manifest["selection_sha256"] = _selection_sha(manifest)
    return manifest


def _validate_manifest_structure(manifest: dict[str, Any], registry: Any, policy: Policy) -> None:
    if type(manifest) is not dict:
        raise ImpactError("impact_manifest_invalid")
    _closed(manifest, MANIFEST_KEYS, "impact_manifest_fields_invalid")
    if (manifest["schema_version"] != 1 or manifest["registry_sha256"] != registry.sha256
            or manifest["policy_sha256"] != policy.sha256
            or manifest["classification"] not in CLASSIFICATIONS
            or not SHA256.fullmatch(manifest["selection_sha256"])):
        raise ImpactError("impact_manifest_identity_invalid")
    if (not REVISION.fullmatch(manifest["base_revision"])
            or not REVISION.fullmatch(manifest["head_revision"])
            or manifest["base_revision"] == manifest["head_revision"]):
        raise ImpactError("impact_manifest_revision_invalid")
    changes = manifest["changed_files"]
    if type(changes) is not list:
        raise ImpactError("impact_manifest_changes_invalid")
    parsed_changes = []
    for change in changes:
        if type(change) is not dict:
            raise ImpactError("impact_manifest_change_invalid")
        _closed(change, CHANGE_KEYS, "impact_manifest_change_invalid")
        parsed_changes.append(Change(**change))
    canonical = _canonical_changes(parsed_changes)
    if parsed_changes != canonical:
        raise ImpactError("impact_manifest_change_order_invalid")

    all_paths = {change.path for change in canonical}
    all_paths.update(change.previous_path for change in canonical if change.previous_path)
    unmatched = _unique_strings(manifest["unmatched_paths"], "impact_manifest_unmatched_invalid", allow_empty=True)
    if unmatched != sorted(unmatched) or not set(unmatched) <= all_paths:
        raise ImpactError("impact_manifest_unmatched_invalid")
    decisions = manifest["scenario_decisions"]
    if type(decisions) is not list:
        raise ImpactError("impact_manifest_decisions_invalid")
    expected_ids = [scenario["id"] for scenario in registry.scenarios]
    actual_ids = []
    selected_count = 0
    classification = manifest["classification"]
    allowed_rule_ids = {rule["id"] for rule in policy.metadata["rules"]}
    allowed_rule_ids.update({"registry_related_path", "unknown_path_fallback"})
    for decision in decisions:
        if type(decision) is not dict:
            raise ImpactError("impact_manifest_decision_invalid")
        _closed(decision, DECISION_KEYS, "impact_manifest_decision_invalid")
        rule_ids = _unique_strings(decision["rule_ids"], "impact_manifest_rules_invalid", allow_empty=True)
        if (type(decision["selected"]) is not bool or decision["reason"] not in DECISION_REASONS
                or rule_ids != sorted(rule_ids) or not set(rule_ids) <= allowed_rule_ids):
            raise ImpactError("impact_manifest_decision_invalid")
        if ((classification == "NO_E2E_REQUIRED" and decision["reason"] != "no_e2e_required")
                or (classification == "FULL_E2E" and decision["reason"] != "full_e2e_required")
                or (classification == "TARGETED_E2E" and decision["selected"]
                    and decision["reason"] != "directly_impacted")
                or (classification == "TARGETED_E2E" and not decision["selected"]
                    and decision["reason"] != "not_impacted_by_changed_paths")):
            raise ImpactError("impact_manifest_decision_invalid")
        actual_ids.append(decision["scenario_id"])
        selected_count += int(decision["selected"])
    if actual_ids != expected_ids:
        raise ImpactError("impact_manifest_scenario_coverage_invalid")
    if ((classification == "FULL_E2E" and selected_count != len(expected_ids))
            or (classification == "TARGETED_E2E" and not 0 < selected_count < len(expected_ids))
            or (classification == "NO_E2E_REQUIRED" and selected_count != 0)):
        raise ImpactError("impact_manifest_classification_invalid")
    if manifest["selection_sha256"] != _selection_sha(manifest):
        raise ImpactError("impact_manifest_sha_invalid")


def select_impact(
    registry: Any,
    policy: Policy,
    changes: Iterable[Change],
    *,
    base_revision: str,
    head_revision: str,
) -> dict[str, Any]:
    manifest = _derive_manifest(
        registry,
        policy,
        changes,
        base_revision=base_revision,
        head_revision=head_revision,
    )
    _validate_manifest_structure(manifest, registry, policy)
    return manifest


def validate_manifest(manifest: dict[str, Any], registry: Any, policy: Policy) -> None:
    _validate_manifest_structure(manifest, registry, policy)
    changes = [Change(**change) for change in manifest["changed_files"]]
    expected = _derive_manifest(
        registry,
        policy,
        changes,
        base_revision=manifest["base_revision"],
        head_revision=manifest["head_revision"],
    )
    if manifest != expected:
        raise ImpactError("impact_manifest_mapping_invalid")
