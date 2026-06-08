# ADR 0005: Job-Centric Pipeline Model

## Status

Accepted.

## Decision

Pipelines are modeled with related jobs instead of a separate pipeline execution
table. A parent T2I job can unblock a child I2V job once a source image asset is
available.

## Rationale

Both single generations and pipelines share the same lifecycle concepts:
request parameters, state transitions, provider calls, assets, and failures. A
job-centric model avoids duplicating lifecycle logic.

## Consequences

Benefits:

- one state machine for single jobs and pipeline steps
- one history/detail response shape
- simple asset linkage through `source_asset_id`
- pipeline failures can reuse public job error codes

Trade-offs:

- pipeline views must assemble parent/child data
- future multi-step workflows may need a richer orchestration model

## Follow-Up

If pipelines grow beyond T2I -> I2V, introduce a workflow graph only after the
job-centric model becomes insufficient.
