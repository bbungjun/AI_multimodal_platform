from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from google import genai
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account

from app.config import Settings, get_settings
from app.services.vertex.errors import (
    VertexCredentialsInvalidError,
    VertexCredentialsMissingError,
    VertexLocationMissingError,
    VertexProjectMissingError,
    VertexServiceError,
    map_vertex_error,
)

VERTEX_AUTH_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


@dataclass(frozen=True)
class VertexReadiness:
    ready: bool
    status: str
    credentials: str
    project: str
    location: str

    def to_public_dict(self) -> dict[str, bool | str]:
        return {
            "ready": self.ready,
            "status": self.status,
            "credentials": self.credentials,
            "project": self.project,
            "location": self.location,
        }


@lru_cache
def get_vertex_client() -> genai.Client:
    settings = get_settings()
    credentials = load_service_account_credentials(settings)
    project_id = resolve_project_id(settings, credentials)
    location = resolve_location(settings)
    return genai.Client(
        vertexai=True,
        credentials=credentials,
        project=project_id,
        location=location,
    )


def get_vertex_readiness() -> VertexReadiness:
    settings = get_settings()

    try:
        get_vertex_client()
    except VertexServiceError as exc:
        return _readiness_from_error(settings, exc)
    except Exception as exc:
        return _readiness_from_error(settings, map_vertex_error(exc))

    return VertexReadiness(
        ready=True,
        status="ready",
        credentials="available",
        project="configured",
        location=resolve_location(settings),
    )


def load_service_account_credentials(
    settings: Settings,
) -> service_account.Credentials:
    credentials_path = _resolve_credentials_path(settings.google_application_credentials)

    try:
        return service_account.Credentials.from_service_account_file(
            str(credentials_path),
            scopes=[VERTEX_AUTH_SCOPE],
        )
    except (GoogleAuthError, OSError, ValueError) as exc:
        raise VertexCredentialsInvalidError() from exc


def resolve_project_id(
    settings: Settings,
    credentials: service_account.Credentials,
) -> str:
    project_id = settings.gcp_project_id or getattr(credentials, "project_id", None)
    if not project_id:
        raise VertexProjectMissingError()
    return project_id


def resolve_location(settings: Settings) -> str:
    location = settings.gcp_location.strip()
    if not location:
        raise VertexLocationMissingError()
    return location


def _resolve_credentials_path(path: Path | None) -> Path:
    if path is None:
        raise VertexCredentialsMissingError()

    try:
        resolved = path.expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise VertexCredentialsMissingError() from exc
    except OSError as exc:
        raise VertexCredentialsInvalidError() from exc

    if not resolved.is_file():
        raise VertexCredentialsInvalidError()

    return resolved


def _readiness_from_error(
    settings: Settings,
    exc: VertexServiceError,
) -> VertexReadiness:
    return VertexReadiness(
        ready=False,
        status=exc.code,
        credentials=_credential_status(exc),
        project=_project_status(settings, exc),
        location=_location_status(settings, exc),
    )


def _credential_status(exc: VertexServiceError) -> str:
    if isinstance(exc, VertexCredentialsMissingError):
        return "missing"
    if isinstance(exc, VertexCredentialsInvalidError):
        return "invalid"
    return "unknown"


def _project_status(settings: Settings, exc: VertexServiceError) -> str:
    if isinstance(exc, VertexProjectMissingError):
        return "missing"
    if settings.gcp_project_id:
        return "configured"
    return "unknown"


def _location_status(settings: Settings, exc: VertexServiceError) -> str:
    if isinstance(exc, VertexLocationMissingError):
        return "missing"
    return settings.gcp_location or "missing"
