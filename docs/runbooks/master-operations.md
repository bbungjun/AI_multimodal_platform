# Local mock Master operations

G10 is implemented and mock-verified. Do not treat this runbook as authorization
for real OAuth/provider/cloud calls or arbitrary developer DB changes. The studio
still opens at /generate. A signed-in active Master additionally sees /master;
ordinary Users cannot fetch its reads or commands by entering the URL directly.

## Promotion

Google signup always creates an ordinary User. Promotion is operator CLI only,
never a browser role selector. Resolve the exact existing User UUID and intended
database through an approved operational workflow; do not guess the first user
or print account/session/credential values in evidence.

From backend, with the intended local mock configuration, replace placeholders:

```text
python -m app.master_cli --user-id USER_UUID --request-id REQUEST_UUID --reason operator_bootstrap --expected-database DB_NAME
```

Default is a full dry-run rollback. After checking target/preview, applying the
same command requires `--execute --confirm PROMOTE:USER_UUID`. The CLI refuses
nonlocal/live/system DB targets; Master gets Max Credit/concurrency5, no bypass.
This work did not promote an actual user. Role demotion is not implemented.

## Console and commands

- Overview separates real/synthetic cohorts, current persisted Plan attribution,
  reservation/charge/release/held and observed meter units. Model p95 is queue-
  inclusive Job timestamp duration. Null means no samples, not measured zero.
- Users show exact30-day signup-based renewal, Plan/pending Plan and balances;
  projected lazy renewal is marked and GET does not initialize accounts.
- Select an exact target, action, fixed reason and confirmation. Self/final active
  Master suspension is refused. Suspend revokes all Sessions and cancels pending
  unpublished work; dispatched work finishes accounting normally. Reactivation
  does not restore old Sessions/Jobs.
- On uncertain response retry the same frozen request. Never issue a new bonus
  request merely because the response was lost. After navigation/reload, inspect
  Audit before a new request; the form is intentionally not persisted.
- A403 may mean lost authority;503 may be contention or unavailable state. Do not
  bypass checks, use raw SQL or edit Audit to recover. Identify the safe failure
  code and follow up with a bounded diagnostic task.

## Synthetic verification

From repository root:

```text
python scripts/verify_synthetic_seed.py --env-file .env.example
```

This owns a new local Docker project, exercises full preview/apply/replay and
removes its containers/volumes/network. It does not populate the development DB.
Inside an explicitly owned disposable target, the CLI is:

```text
python -m app.synthetic_seed_cli --as-of 2026-09-05T00:00:00+00:00 --expected-database OWNED_DATABASE
```

Apply additionally requires `--execute --confirm SEED`. Only mock/test/local
`master_seed_verify_<12hex>` database names are accepted. Use the same as-of to
replay; mismatched/partial fixtures refuse rather than reset. No generated media,
fake login, provider call or queue publication occurs. A separately selected
persistent demo target requires its own guard/design, not changing this verifier.

## Recovery and evidence

Use Issue-linked safe counts, checks and public failure codes. Never attach raw
SQL, prompt/provider payload, email or Session/OAuth values. Disabling console/
command routes is a reversible rollback; retain Audit. Populated0007 downgrade
refuses instead of deleting history. Do not restore cancelled jobs/revoked
sessions or force schema downgrades. See [G10 closeout](../portfolio/issue-137-g10-closeout.md).
