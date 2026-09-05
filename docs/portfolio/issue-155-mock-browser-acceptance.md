# Issue155 G11B mock browser acceptance

## Background and problem

G11A proved the authenticated generation/accounting/administration chain through
real HTTP, while existing frontend tests supplied response fixtures. Neither
proved that the built React application, a local frontend proxy, real auth
dependencies, PostgreSQL/Redis, dispatcher/worker and file response operated as
one browser flow. Actual Google OAuth and deployed TLS were intentionally outside
the user's mock-first authorization.

The accepted solution is one deep, test-only Interface:
`python scripts/verify_browser_acceptance.py`. Astra designed its boundary;
Sol/medium implemented it sequentially. Exactly eight new test/harness paths were
used, with no migration, product code, dependency, frontend UX or CI change.

## Observations and failed approaches

The first two runs reached the fixed command boundary but left two isolated
projects because the temporary Compose override was deleted before `down` could
consume it. The projects were positively identified by their random project name
and verifier nonce, then only those containers/volumes/networks were removed.
Cleanup now runs while the override still exists and independently checks Node,
Chromium, port and Docker ownership.

Subsequent bounded receipts exposed four test-contract mistakes rather than
product defects: the Usage payload uses `usage` and scalar `plan`; one-image
results render `img.asset-media`; auth responses require `no-store` while content
responses require `private, no-store`; and browser back navigation can reach
`about:blank`, so authentication is rechecked after returning to the app origin.
Audit uniqueness is asserted from the real API while matching real UI table rows,
avoiding ambiguous localized text selectors. No timeout was raised and no
response was fulfilled or stubbed.

The first final-head Linux CI then failed one new unit test because
`SO_EXCLUSIVEADDRUSE` exists on Windows but not POSIX. The port guard now applies
that option only when the platform exposes it; POSIX retains an ordinary bind
without `SO_REUSEADDR`, so an occupied port is still refused. Both Scan/SBOM jobs
had already passed. The fix remains inside the original eight-path boundary and
requires a fresh final-head verify plus both scans before merge.

## Solution and safety decisions

- Reuse the established owned runtime with a random
  `ownership-verify-<nonce>` project, exact `.env.example`, mock provider and
  label-guarded cleanup. Port18155 collisions are refused, never adopted.
- Start Vite programmatically with dotenv/config loading disabled and proxy only
  `/api` and `/files` to a validated loopback backend. Browser interception aborts
  every non-local request; external count must remain zero.
- Keep three isolated browser contexts for User A, User B and Master. Session
  secrets remain in memory/stdin, never argv, environment, disk or evidence.
- Exercise real UI commands for Plan, bonus, suspension, reactivation and logout;
  use the existing guarded emergency CLI for preview, execute and replay.
- Recovery appends new hash-only A/Master Sessions only after old sessions are
  revoked and Users are active. It does not rewrite or resurrect old rows and is
  explicitly not a Google re-login.

Rollback is removal of the eight test-only paths; there is no schema or user-data
rollback. A verifier failure always attempts owned cleanup and emits only fixed
phase/assertion codes.

## Verification and result

Final PR head: `0994c5bad8882c1b48ad026af970a54a325abdf9`.

| Verification | Result |
| --- | --- |
| Focused Python | 11 passed |
| Node protocol unit tests | 2 passed |
| Browser acceptance | 2 independent cycles; each8 groups/109 assertions; aggregate218; external0; cleanup0 |
| Emergency Session verifier | 2 runs PASS; each8 groups/80+ checks/1+ race contract |
| G11A integrated verifier | 2 cycles; each8 scenarios/108 checks; cleanup0 |
| Auth PostgreSQL/Redis | PASS including outage/recovery;50 auth requests |
| Master suspension | PASS |
| Backend Windows | 1799 passed,3 guarded skips,1 documented Bash path127 failure |
| Frontend | lint/build, Session70, Chromium61 PASS |
| Compose | `.env.example` config PASS |
| Final GitHub CI | Linux backend1801/3 guarded skips; frontend70+61; verify and both Scan/SBOM SUCCESS |

The browser confirmed login-disabled503/no-store, Free Usage with seven meters,
mock PNG completion and file bytes, foreign404, Pro/bonus persistence, Audit
uniqueness, suspension/logout revocation, emergency active-after-zero/replay-zero,
old-cookie refusal and fresh mock recovery with prior Usage/Audit intact.

## Impact and remaining risk

This closes the missing local browser-to-worker acceptance seam and demonstrates
FDE-style integration, AI Full Stack workflow verification and platform-grade
cleanup/security boundaries without paid services. [PR156](https://github.com/bbungjun/AI_multimodal_platform/pull/156)
was protected-auto-merged as squash `eda7c68fec41edb9d039a363217aee1a27f71889`;
Issue155 is closed. It is Mock Verified only. Parent Issue152 remains open for
actual Google callback/relogin, HTTPS/Secure-cookie transport, deployed
proxy/ingress, a live operator revocation drill and any real provider/cloud
verification. No local timing is presented as provider latency or throughput.
