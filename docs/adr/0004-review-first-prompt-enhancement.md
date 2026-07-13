# ADR 0004: Review-First Prompt Enhancement

## Status

Accepted.

## Decision

Prompt enhancement produces an editable draft. It does not automatically replace
the user's final generation prompt.

The `prompt` submitted in the generation payload is the exact execution prompt
passed to Imagen or Veo. An `enhancement_id` links provenance only and must not
replace that prompt with hidden provider-specific text.

## Rationale

Creative work benefits from review and control. The source of truth for a
generation job is the prompt submitted in the generation payload, not an
unreviewed LLM rewrite.

This also makes Raw/Enhanced evaluation auditable: every job exposes a stable
SHA-256 hash of the execution prompt, while enhancement provenance records the
linked draft, enhancer model, template version, target, creativity preset, and
whether the user edited the draft before generation.

## Consequences

Benefits:

- user keeps creative control
- prompt enhancement can be audited and linked to jobs
- user edits cannot be bypassed by stale hidden provider prompt metadata
- tests can validate enhancement linkage without changing final prompt semantics

Trade-offs:

- the UI needs a clear accept/edit flow
- users may need one extra interaction before generation

## Follow-Up

Expose prompt enhancement history and accepted draft linkage in the product UI.
