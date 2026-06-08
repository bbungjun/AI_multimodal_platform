# ADR 0004: Review-First Prompt Enhancement

## Status

Accepted.

## Decision

Prompt enhancement produces an editable draft. It does not automatically replace
the user's final generation prompt.

## Rationale

Creative work benefits from review and control. The source of truth for a
generation job is the prompt submitted in the generation payload, not an
unreviewed LLM rewrite.

## Consequences

Benefits:

- user keeps creative control
- prompt enhancement can be audited and linked to jobs
- tests can validate enhancement linkage without changing final prompt semantics

Trade-offs:

- the UI needs a clear accept/edit flow
- users may need one extra interaction before generation

## Follow-Up

Expose prompt enhancement history and accepted draft linkage in the product UI.
