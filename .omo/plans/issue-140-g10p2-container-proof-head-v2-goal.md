# Issue140 v2 packaged-layout correction

Preserve original SHA-256
`5d802bcc10bb4a002614b3dd548b3d7eb209f0f5e8a0826074ac3cb0c0e4ae85`.
First real schema run failed before the additive proof's guarded entrypoint,
cleanup PASS. Dockerfile installs app under site-packages while migrations live
under WORKDIR. The source-relative resolver was valid on host but not in the
packaged image. No constraint failure or timeout; no result counts accepted.

Stop v1. Under the user's overall design-and-execute authorization, add only
backend/app/schema_revision.py, making20 non-document paths. Follow the existing
schema_control source-root/working-directory lookup contract. Test packaged
layout, absent directories and malformed source with no fallback. Re-run Todo2–8
and F1–F4. All other budgets, tests, privacy and cleanup requirements unchanged.
