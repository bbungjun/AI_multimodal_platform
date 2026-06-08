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

## Future Storage Work

Production hardening can add:

- retention policy
- checksums
- deduplication
- backup/restore scripts
- object-storage adapter
- signed asset URLs
- storage usage dashboard
