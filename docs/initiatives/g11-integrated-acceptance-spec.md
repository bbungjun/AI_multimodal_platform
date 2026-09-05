# G11 integrated acceptance

## Scope and status

Parent #152 remains open for the full canonical completion gate. G11A #153 is
the local mock acceptance slice; real Google browser smoke for a Master and a
normal User, real emergency revocation drill and proxy verification need separate
authorization. No live provider/cloud, developer DB mutation or new login seam.

## G11A Interface

One test-only command, `python scripts/verify_integrated_acceptance.py`, reuses
the owned G4 PostgreSQL/Redis/API/dispatcher/worker runtime and ephemeral
hash-only Session fixtures. Two fresh cycles run the same eight ordered groups:
identity, usage, prompt, generation, administration, concurrency, suspension,
audit. Requests use real HTTP routes and real mock worker output, not route stubs.
Evidence contains only fixed group names, counts, revision and cleanup/timing.

- Identity: anonymous/normal/Master authorization and private no-store.
- Usage: initial Free account, seven meters, thirty-day cycle, independent User.
- Prompt: successful enhancement charges; same request replay does not charge again.
- Generation: real worker completes image, Usage changes and foreign read is denied.
- Administration: Master changes Pro entitlement, grants bonus, replays exactly;
  normal User cannot mutate; personal Usage observes the new entitlement.
- Concurrency: stop only owned consumers, admit three Pro jobs and reject fourth;
  personal Usage reports three held slots. No production limit bypass.
- Suspension: Master cancels unpublished jobs, old Session is rejected; Master
  sees canceled jobs; reactivation does not resurrect the revoked Session.
- Audit: exact command receipts occur once, no denied/replayed duplicate Audit.

The Interface does not claim actual Google authentication, real browser/backend
integration or provider billing. Existing browser tests use response fixtures;
keep that distinct from the HTTP/worker proof. Missing live gates stay Planned.

## Frozen limits and acceptance

Exactly two allowed non-document paths: scripts/verify_integrated_acceptance.py
and backend/tests/test_verify_integrated_acceptance.py. No product, migration,
frontend or infrastructure changes. Scope overrun requires redesign, not a hidden
fix. Reuse existing cycle limits: 360s work,90s cleanup,900s aggregate; no retry or
time-limit relaxation after overrun. Two cycles, all eight groups, at least
40 assertions per cycle, cleanup zero. Stable committed code during proofs.

Fresh existing proofs: schema twice; lifecycle/accounting/concurrency/prompt-credit/
generation-credit/personal-usage/auth/Master admin/read/suspension once each;
ownership `--suite all --cycles 2`. Each existing verifier retains its own limits.
Concurrency proof must retain fifty admissions, no overspend/duplicate settlement.
Full backend Windows regression (known Bash path exception separately recorded),
Linux CI, frontend lint/build/Session/Chromium and public Compose config.

No email/identity/session/SQL/prompt/raw provider/error payload in evidence. Existing
local .omo history is preserved. Document problems, failures, fixes, results and
remaining gaps. Ready PR, final-head verify and both Scan/SBOM success, protected
squash auto-merge; close only #153 and sync main. Never close #152 from mock alone.
