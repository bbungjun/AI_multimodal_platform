# Storage And Assets

CreativeOps Studio stores generated media as local files and tracks metadata in
Postgres.

## Asset Metadata

Assets are linked to jobs and returned in job detail/list responses. The
frontend relies on the asset DTO, especially:

- asset id
- job id
- media kind
- MIME type
- size
- generated URL

Changing the asset response shape requires updating frontend previews and API
tests together.

## File Storage

Generated media bytes are written under `DATA_DIR`. The storage helper owns
file writes, reads, deletion, and path validation.

User-provided filenames must never be used directly as trusted filesystem
paths. All file serving should resolve through storage helpers and reject paths
outside the asset root.

## File Serving

Files are served through `/files/...`. The endpoint supports streaming and byte
ranges so image previews and video playback work in the browser.

Serving requires a valid Session. `OwnershipAccess.file_asset(local_path)` performs
an exact Asset path/Job owner lookup before storage resolution, stat/open or Range
parsing. Ordinary Users read their own files; Master may read another owner's file
but receives no mutation/use bypass. Foreign, missing, orphaned or inconsistent
Asset/Job paths return404 `content_not_found`; invalid Sessions retain401.

Canonical UUID/filename binding rejects encoded/traversal/duplicate aliases and
pre-existing in-root symlink redirection to a different file. It does not claim
atomic protection against a trusted concurrent filesystem replacement or DBA edit.
Authorized full200 and Range206/400/416 keep existing bytes/header semantics.
Denied ranges expose no file bytes, size or Content-Range. HEAD remains405, not a
new feature. A newly requested Range after logout is401; sent bytes are not recalled.

File, metadata and operations responses use `Cache-Control: private, no-store`,
including errors; response-start handling does not buffer streaming bodies.
`/api/ops/health`, `/api/ops/metrics`, `/metrics` require Master (User403/anonymous401).
Public health probes remain public; machine-scraper authentication is a separate gate.
See [Issue112 proof and delivery](portfolio/issue-112-file-ops-access.md).

Important behavior to preserve:

- path containment validation
- not-found handling
- range request support
- safe content headers
- media preview compatibility

## Current Trade-Off

Local storage is intentionally simple for a personal app. It is fast to run with
Docker Compose, easy to test, and avoids introducing object storage before the
product needs it.

File deletion followed by DB commit is not atomic. A safe rollback stops public
exposure before reverting B code, because the predecessor lacks file/ops protection.
Do not use an auth-off toggle as rollback or imply that a schema downgrade is needed.

## Future Storage Work

Production hardening can add:

- retention policy
- checksums
- deduplication
- backup/restore scripts
- object-storage adapter
- signed asset URLs
- storage usage dashboard
