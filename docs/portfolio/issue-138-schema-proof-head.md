# Issue138 — code-derived verification head

## Problem and cause

G10 needs an additive Audit migration. Host verifiers previously embedded the
current0006 revision independently, making a legitimate next migration require
many unrelated literal edits. Some tests checked script source text rather than
the revision actually used, concealing that coupling.

## Approach and rejected attempts

One dependency-free Module parses literal migration metadata with AST. It refuses
missing/duplicate/disconnected/cyclic/branched chains and returns the unique head.
It does not execute migration files or import application settings. Standalone
host scripts load the trusted helper through stdlib runpy, without a backend
package installation requirement. Database revision still must equal code head;
this is not accepting arbitrary schema or weakening stale-revision refusal.

Initial RED: missing Module prevented collection. Resolver then passed14 tests.
First host focused run:207 PASS/1 source-literal assertion failure; after adapting
the named tests:208 PASS. First full Windows run:1601 PASS/2 FAIL/3 guarded skips.
One new failure was the additional ownership parity source-text assertion; the
other was the pre-existing Bash Windows-path exception. v1 stopped before the
extra path. v2 freezes19 paths (within repository20), preserving v1 and both
failures; runtime value comparisons replace that assertion. No budget or test
was skipped or relaxed.

## Verification

- Resolver plus ownership focused:52 PASS.
- Latest Windows `AI_PROVIDER=mock python -m pytest -q`:1602 PASS,3 existing
  isolated-environment skips,1 existing Bash path exception (exit127).
- Frontend lint/build PASS; Session60 and Chromium47 PASS.
- Compose public-template config PASS from repository root. An initial command
  from backend failed because the relative public template was absent; corrected
  working directory without reading local environment files.
- Stable `45eabec` isolated schema verifier PASS: public-template mock PostgreSQL,
  round-trip, constraints, stale-revision refusal,90 credit checks and42 accounting
  checks/four downgrade cases. Disposable container/volume/network cleanup PASS.
  Receipt: `.omo/evidence/schema/migration-schema-verify-8b1c06cca1b2.json`.
  Final-head Linux/CI results pending at PR submission.

The first schema run started before the v2 parity-test correction commit. Its
end-of-run revision guard correctly rejected `code_changed_during_proof`;
cleanup passed and the unsuccessful receipt is preserved. The final run above
used a stable committed revision without concurrent repository edits/commits.

F1 scope APPROVE (19 paths, migration0); F2 Interface/security APPROVE;
F3 local reproducibility APPROVE with Linux CI required before merge;
F4 documentation APPROVE with protected delivery pending. No whole-G10 closure.

## Outcome and risks

No product behavior, migration, data or provider call changed. Host current-head
contracts are consolidated; container proof consumers remain G10P2. Audit,
Master mutations, suspension and console are not implemented by this slice.
Historical migration assertions remain exact. Next migration must still prove
additive safety, metadata parity and upgrade/downgrade/re-upgrade.
