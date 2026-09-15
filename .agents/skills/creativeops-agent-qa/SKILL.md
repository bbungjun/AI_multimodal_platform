---
name: creativeops-agent-qa
description: Operate this repository's Agent QA workflow when asked to verify code changes, run Chrome E2E, inspect QA impact, interpret an aggregate Receipt, or assess PR merge readiness. Use only for AI_multimodal_platform; do not use for generic testing in other repositories.
---

# CreativeOps Agent QA

Use the repository's existing QA interfaces; do not recreate test logic in the prompt or improvise a checklist.

## Scope and authority

- Confirm the repository root contains `qa/contracts/registry.v1.json` and `scripts/agent_qa_all.py`. If not, stop using this skill.
- For an explanation or status request, inspect existing evidence without starting Docker or changing external state.
- Run QA when the user asks to verify, test, assess merge readiness, or complete a development workflow that includes verification.
- Use `AI_PROVIDER=mock`. Never invoke live Google or Vertex APIs through this skill.
- A Receipt decision is evidence, not authorization. Never merge, push, create a PR, or change product code unless the user's request separately authorizes it.
- Preserve unrelated working-tree changes. Never stash, reset, prune Docker, delete volumes, or edit `.env` to make QA pass.

## Orient

Read `AGENTS.md`, then `docs/current-work.md`. Read these only as needed:

- `qa/executor/README.md` for current commands and execution semantics.
- `qa/contracts/registry.v1.json` and the selected files under `qa/contracts/scenarios/` when explaining assertions.
- `docs/evidence/issue-186/aggregate-receipt.json` only as a historical example, never as evidence for a new revision.

Distinguish three facts throughout the work:

1. whether execution completed,
2. whether the product assertions passed,
3. whether the Receipt permits merge.

## Choose the mode

### Existing-result review

Use this for questions about the last recorded QA. Read the named Receipt, validate its revision and make clear that it does not verify newer code. Report scenario counts, assertion counts, failed assertion IDs, cleanup, and verdict.

### Focused diagnosis

Use a focused runner when diagnosing one surface:

```powershell
python scripts/agent_qa_executor.py --base <BASE_SHA> --head <HEAD_SHA> --scenario auth_login
python scripts/devtools_login_qa.py --scenario image --auto
python scripts/devtools_login_qa.py --scenario video --auto
python scripts/devtools_login_qa.py --scenario i2v --auto
python scripts/devtools_login_qa.py --scenario pipeline --auto
python scripts/devtools_login_qa.py --scenario workspace --auto
```

Focused results help diagnosis but do not authorize merge. Use the aggregate gate for a merge-readiness decision.

### Aggregate merge-readiness gate

Require committed, clean tracked source:

```powershell
git status --short --untracked-files=no
$base = git merge-base origin/main HEAD
$head = git rev-parse HEAD
python scripts/agent_qa_all.py --base $base --head $head
```

`base` and `head` must be different immutable 40-character revisions, and `head` must equal the checked-out `HEAD`. Do not invent either revision. If local `origin/main` may be stale, say so; fetch only when allowed by the user's workflow.

If a local runtime interruption occurs after some slices completed, retry once with the same revisions:

```powershell
python scripts/agent_qa_all.py --base $base --head $head --resume
```

Resume may reuse only exact-revision results with `source_unchanged=true`, successful process execution, and cleanup zero. Do not use resume after a new commit or tracked edit.

## Interpret without weakening

- Exit `0`, `complete=true`, `verdict=PASS`, `merge_decision=ALLOW`: QA evidence permits merge consideration.
- Exit `1`, `complete=true`, `verdict=FAIL`, `merge_decision=REJECT`: execution succeeded and found product failures. Do not retry merely to seek PASS.
- Exit `2` or `complete=false`: QA is technically incomplete. Diagnose the first concrete blocker; do not report a product verdict from missing evidence.
- `BLOCKED` is not `FAIL`, and `NOT_APPLICABLE` is not `PASS`.
- Do not turn a known defect into allow-failure or remove an assertion to obtain ALLOW.

Read the `receipt` path emitted by the command. Treat `scenario_results[].assertions[].id` and its declared evidence sources as the explanation surface. Do not copy raw browser logs, request bodies, identities, prompts, cookies, OAuth values, headers, credentials, or machine-specific paths into committed evidence.

## Report the outcome

Always report:

- base and head revision,
- execution completeness and elapsed time,
- selected/total scenarios and assertion PASS/FAIL/BLOCKED counts,
- failed assertion IDs grouped by scenario,
- `source_unchanged` and Browser/MCP/Vite/runtime cleanup,
- Receipt path,
- `ALLOW` or `REJECT`, explicitly separated from any actual merge action,
- the first actionable next step.

When a product assertion fails, trace it through its contract evidence before proposing a fix. When execution is blocked, fix or report the infrastructure/evidence problem before changing product code.
