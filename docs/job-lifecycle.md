# Job Lifecycle

Generation requests are durable jobs. A request returns quickly, then the
backend runner processes work asynchronously and records state changes.

## Core States

The state machine protects job transitions. All state changes should go through
`transition(...)` in `backend/app/state_machine.py`.

Typical text-to-image path:

```text
pending -> queued -> generating -> completed
```

Typical video path:

```text
pending -> queued -> generating -> polling -> downloading -> completed
```

Failure, cancellation, and deletion rules depend on terminal state. Terminal
jobs can be deleted. Active or dependent jobs are protected.

## Runner

The internal runner:

- starts with the FastAPI app
- claims pending jobs with row locks
- respects concurrency limits
- dispatches mode-specific handlers
- records failures with public error codes
- resumes or sweeps orphaned work on startup

This is appropriate for a personal single-backend deployment. A multi-replica
deployment would need stronger distributed coordination.

## Pipelines

A pipeline is represented by two related jobs rather than a separate pipeline
table.

```text
parent T2I job
  -> image asset
  -> child I2V job
```

The child starts blocked. When the parent completes and has a valid image asset,
pipeline linking attaches that asset to the child and unblocks it. If the parent
fails, the child should fail or stay protected according to the pipeline
contract.

## State History

Job responses include state history so the frontend can show a meaningful
timeline instead of only the latest state. This is also the foundation for a
future Ops Console.

Important fields to preserve:

- current state
- previous state
- transition timestamp
- state detail payload
- provider operation name when available
- public failure code and message

## Production Gaps

The next lifecycle improvements should add:

- structured job event logs
- stuck-job alerts
- job duration metrics
- provider operation audit view
- graceful shutdown visibility
- daily cost or request budget status
