from __future__ import annotations

from typing import Any


class VertexServiceError(RuntimeError):
    code = "vertex_service_error"
    public_message = "Vertex AI service error."
    retryable = False
    status_code: int | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        status_code: int | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message or self.public_message)
        if status_code is not None:
            self.status_code = status_code
        if retryable is not None:
            self.retryable = retryable

    def to_public_dict(self) -> dict[str, bool | int | str | None]:
        return {
            "code": self.code,
            "message": self.public_message,
            "retryable": self.retryable,
            "status_code": self.status_code,
        }


class VertexCredentialsMissingError(VertexServiceError):
    code = "vertex_credentials_missing"
    public_message = "Vertex credentials are not configured."


class VertexCredentialsInvalidError(VertexServiceError):
    code = "vertex_credentials_invalid"
    public_message = "Vertex credentials could not be loaded."


class VertexProjectMissingError(VertexServiceError):
    code = "vertex_project_missing"
    public_message = "Vertex project is not configured."


class VertexLocationMissingError(VertexServiceError):
    code = "vertex_location_missing"
    public_message = "Vertex location is not configured."


class VertexRateLimitedError(VertexServiceError):
    code = "vertex_rate_limited"
    public_message = "Vertex AI request was rate limited."
    retryable = True


class VertexTransientError(VertexServiceError):
    code = "vertex_transient_error"
    public_message = "Vertex AI service was temporarily unavailable."
    retryable = True


class VertexRequestError(VertexServiceError):
    code = "vertex_request_error"
    public_message = "Vertex AI rejected the request."


class VertexOperationFailedError(VertexServiceError):
    code = "vertex_operation_failed"
    public_message = "Vertex AI operation failed."


class VertexSafetyBlockedError(VertexServiceError):
    code = "vertex_safety_blocked"
    public_message = "Vertex AI blocked the generation for safety reasons."


class VertexOutputUnavailableError(VertexServiceError):
    code = "vertex_output_unavailable"
    public_message = "Vertex AI did not return an output."


class VertexUnknownError(VertexServiceError):
    code = "vertex_unknown_error"
    public_message = "Unexpected Vertex AI service error."


def map_vertex_error(exc: Exception) -> VertexServiceError:
    if isinstance(exc, VertexServiceError):
        return exc

    status_code = _extract_status_code(exc)
    if status_code == 429:
        return VertexRateLimitedError(status_code=status_code)
    if status_code in {408, 500, 502, 503, 504}:
        return VertexTransientError(status_code=status_code)
    if status_code is not None:
        return VertexRequestError(status_code=status_code)

    return VertexUnknownError()


def _extract_status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value

    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status

    error = getattr(exc, "error", None)
    if isinstance(error, dict):
        value: Any = error.get("code") or error.get("status_code")
        if isinstance(value, int):
            return value

    return None
