# G10D — existing-style Master console

One console delivery slice on merged G10A/B/C. Route /master, Master-only desktop
and mobile navigation; direct URL by normal User refuses before any Master fetch.
Existing Session epoch/QueryClient replacement and API guard remain authoritative.
No new login/profile/provider flow or backend mutation contract.

Existing creative-page/Panel/Button/Badge/usage table CSS; add scoped responsive
master styles only. Overview/users/Audit sections with explicit loading/error/
empty states, refresh, window7/30/90 and origin all/oauth/synthetic, paginated
users/Audit. Existing generation workspace remains default landing page.
Display Plan/status counts, reserved/held/charged/released, seven meter usage,
UTC daily charges, persisted Job model/status/p95/error mix and safe recent
failures. Show measurement caveats, null sample and projected renewal labels.
Decimal-string Credit values format with BigInt, no Number/float conversion.
Never display arbitrary object JSON, raw errors, email or unsupported fields.

Selecting a User opens an accessible in-page command form: Plan change, bonus,
suspend/reactivate; no role promotion. Exact selected ID, reason code, consequence
text and confirmation checkbox before submission. Self suspend disabled; server
remains authority. Bonus entered as decimal Credit (up to6 fractional places),
converted exactly to bounded microcredits, optional future expiry. No free reason.
Synchronous in-flight gate prevents double-click. Freeze UUID+payload before first
send; errors retry the same request, no automatic retries/new UUID. After success,
refresh Master and personal usage queries, show replay status. Pending/uncertain
form does not silently reset or accept edits; navigation/reload warning explains
that receipt must be checked in Audit if abandoned. No persistent sensitive form
storage. Session replacement unmounts the form and rejects late responses.

Response parsing is strict on consumed types/enums/decimal strings, projection
uses explicit fields only. Auth401 follows existing logout/reset;403/503 shows safe
copy and never a raw payload. Stale results hidden on request errors.

Tests extend existing Session and Chromium projects without weakening gates:
model precision/refusal; normal-role direct URL/nav refusal; Master filters/pages;
confirmation, double submit, replay sameUUID, validation,403/503/401, delayed
response after logout, desktop/mobile no horizontal overflow and masked visual
artifacts. Actual external/provider/OAuth request count0. Existing mock frontend
fixtures, not live login. Browser screenshot artifacts contain no identity.
