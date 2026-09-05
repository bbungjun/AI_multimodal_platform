# G11A v2 approved resumption

User approved the four-path auth-cache redesign by requesting resumption.
Original plan SHA256:
924e0512e96ed6df0972330e8cf381eb5b1584d110dd656e4d8223c828e3788b.
Read original plan and g11-integrated-acceptance-spec.md. Preserve failures.

Only scope delta: total four non-document paths, original coordinator/test plus
backend/app/main.py and backend/tests/test_auth_api.py. Migration0. Existing outer
response-start wrapper must set no-store for every /api/auth response, including
dependency401/403/503, callback redirects and unhandled500; preserve cookies,
streaming, Origin and existing content private/no-store. No new auth behavior.

Resume Todo2-4 with focused auth/cache tests, stable code commit, then Todo5-8
unchanged. F1 is four paths; F2 also includes all-status auth cache protection.
All original proof counts, time limits, cleanup and F3/F4 remain unchanged.
No live OAuth/provider/cloud or developer DB changes. No subagents.
