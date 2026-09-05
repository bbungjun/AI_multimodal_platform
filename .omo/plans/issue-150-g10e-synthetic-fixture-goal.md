# Issue150 G10E Goal

Read AGENTS,current-work,canonical Synthetic Data/G10 status,G10 design and
docs/initiatives/g10e-synthetic-fixture-spec.md. Sequential/no subagents.
Branch codex/issue-150-synthetic-operations-fixture. Local Docker/mock only.

## Exact8 code paths; migration0

1. backend/app/synthetic_seed.py
2. backend/app/synthetic_seed_cli.py
3. backend/tests/test_synthetic_seed.py
4. backend/tests/test_synthetic_seed_cli.py
5. backend/tests/synthetic_seed_support.py
6. backend/tests/test_synthetic_seed_support.py
7. scripts/verify_synthetic_seed.py
8. backend/tests/test_verify_synthetic_seed_script.py

No existing writer/model/migration/frontend/provider change. Preserve developer/
preview DBs, user changes and .omo history. No raw IDs/PII/SQL/prompt/credentials
in evidence. No provider calls, asset creation, Outbox publication or fake login.

## Todo1–8

1. Confirm prior merge/main sync/Goal SHA; baseline focused credit+Master tests,
   current state In Progress. Freeze explicit as-of and deterministic protocol.
2. Pure fixture plan/guard Interface and tests:120 users84/30/6,3000 jobs,90days,
   login-disabled identities and fixed state/model/usage distributions.
3. Atomic seed Module through existing lifecycle/accounting/state_machine,
   advisory serialization, marker-bound replay/partial refusal and dry-run rollback.
4. Guarded CLI Adapter, exact target/confirmation/mock/test/local checks, safe errors.
5. Owned proof/harness8 groups (guards,dryrun,seed,distribution,accounting,replay,
   denials,readmodel),100checks minimum and one observed concurrent seed lock race.
6. Stable committed proof twice, each600s work/60s cleanup. Inherited read/admin
   proofs once, full backend/frontend and public Compose; no edits during proof.
7. Portfolio problem/root cause/failed approach/solution/results/risks, canonical
   and current-work latest state, prior G10D merge evidence; record remaining G11.
8. Ready PR, final-head verify and both Scan/SBOM SUCCESS, protected squash auto-
   merge/actual MERGED. Close Issue150 and parent137 only after all slice evidence;
   sync main. Do not start G11/live verification or claim real provider throughput.

Each Todo focused tests/diff --check/status/staged/cumulative path checks and
small commits, no broad .omo staging. F1 scope8/migration0, F2 atomic fixture/
guards/idempotency/ledger, F3 fresh independent proofs/cleanup0/regressions/CI,
F4 truthful documentation/protected delivery must all APPROVE.
Path/time/schema overrun stops for redesign; no timeout relaxation or bypass.

## Commands and budgets

Backend AI_PROVIDER=mock focused `python -m pytest tests/test_synthetic_seed.py
tests/test_synthetic_seed_cli.py tests/test_synthetic_seed_support.py
tests/test_verify_synthetic_seed_script.py -q`120s (existing subset while building).
Full `python -m pytest -q`300s; known Windows Bash127 exception retained,
fresh Linux CI mandatory. Root `python scripts/verify_synthetic_seed.py --env-file
.env.example` twice, each600/60,8groups/100checks/races1 minimum, cleanup0.
Root verify_master_read.py and verify_master_admin.py --env-file .env.example
once each180/60. Frontend npm run lint/build/test:auth/test:auth:browser each180s.
Public Compose config60s. Verification DB/volume/network owned and removed only.
