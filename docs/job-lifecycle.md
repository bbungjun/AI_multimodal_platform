# Job Lifecycle

Generation requests are durable jobs. A request returns quickly, then the
worker process runs the job runner asynchronously and records state changes.

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

## Failed Job Retry

`POST /api/generations/{job_id}/retry` is only valid for failed jobs. A retry
creates a new pending job and links it with `retry_of_job_id`; it never revives
or mutates the original failed job. The new job copies the user-reviewed
generation contract (`mode`, `model`, prompts, enhancement link, parent link,
source asset link, and parameters) while resetting runtime fields such as
attempts, state history, provider operation name, error, charged status, and
assets.

For image-to-video retries, the original source asset must still exist and be an
image. If the asset was detached, deleted, or is not an image, the API returns a
conflict and does not create a retry job.

Deletion treats active retry jobs as dependencies of their failed source job.
Terminal retry jobs are detached from `retry_of_job_id` when the original job is
deleted.

## Runner

The worker runner:

- runs in the standalone `python -m app.worker` process in local Compose
- claims pending jobs with row locks
- respects concurrency limits
- dispatches mode-specific handlers
- records failures with public error codes
- resumes or sweeps orphaned work on startup

FastAPI can still gate runner auto-start through `JOB_RUNNER_AUTO_START`, but
the Phase 1 local default keeps API serving and job execution in separate
processes. A multi-replica deployment would need stronger distributed
coordination.

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
