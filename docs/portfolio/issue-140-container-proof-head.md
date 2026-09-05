# Issue140 — packaged proof revision compatibility

## Problem, cause and failed attempt

G10P1 consolidated host revision selection. Container proof programs must use
the same contract before Audit changes schema. Initial focused143 passed, but
the real schema run failed before additive proof entry. Runtime Docker installs
the Python package under site-packages and copies migrations into WORKDIR;
the host-only source-relative resolver could not find those files. That failure
is preserved in `.omo/evidence/schema/migration-schema-verify-61a993eea9c7.json`
(82.625s work/1.875s cleanup, no accepted checks, cleanup PASS).

## Solution and rationale

v1 stops at19 paths. v2 adds only the shared resolver, reaching20. Use the same
source/working-directory layout contract as schema_control. Malformed existing
source fails closed and never silently falls back. Two layout-specific tests
cover installed package discovery, absent directories and invalid-source refusal.
No migration, runtime business behavior, schema acceptance or budget changed.

## Verification

- Baseline focused143 PASS; after packaged correction focused145 PASS.
- Initial full Windows1602 PASS/3 guarded skips; only established Bash path
  exception. Corrected full regression and actual proofs pending.
- Frontend lint/build, Session60/Chromium47 and Compose PASS.
- Final acceptance requires stable-commit schema and personal-usage proof,
  cleanup0 and final-head Linux verify/both Scan/SBOM.

## Result and remaining work

20 paths including shared resolver, no migration. No Master/Audit implementation
or live claims. Historical migration assertions remain explicit; G10A adds the
Audit schema and audited administration once this compatibility slice merges.
