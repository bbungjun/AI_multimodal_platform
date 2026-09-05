# Issue138 G10P1 v2 overlay

Original Goal SHA-256:
`0b44e1246d6ad3f7965b00daacba4622a3496f26f8a282012797f08dfb64a2cf`.

Preserve original plan and failed full-regression evidence. Todo6 found
`test_ownership_persistence::test_schema_harness_and_verifier_head_parity`
asserting the literal head appears in script source. That is incompatible with
code-derived head discovery. Stop v1 before editing this additional path.

Design correction under the user's design-and-execute authorization: add only
`backend/tests/test_ownership_persistence.py` to the exact path allowlist, making
19 non-document paths, still within the repository20-path cap. Replace the
source-string assertion with a runtime exported-value comparison for host
scripts; preserve the container proof literal until G10P2. No budget, migration,
acceptance, cleanup, privacy or CI relaxation. Resume Todo4–8 and F1–F4.
