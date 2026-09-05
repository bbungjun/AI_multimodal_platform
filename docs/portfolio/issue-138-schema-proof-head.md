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
- Isolated schema and final-head Linux/CI results: pending.

The first schema run started before the v2 parity-test correction commit. Its
end-of-run revision guard must reject that changing checkout; it cannot serve
as final evidence. Preserve that run and perform the final proof only against
a stable committed revision, without concurrent repository edits/commits.

## Outcome and risks

No product behavior, migration, data or provider call changed. Host current-head
contracts are consolidated; container proof consumers remain G10P2. Audit,
Master mutations, suspension and console are not implemented by this slice.
Historical migration assertions remain exact. Next migration must still prove
additive safety, metadata parity and upgrade/downgrade/re-upgrade.
