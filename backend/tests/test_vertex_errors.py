from __future__ import annotations

from app.services.vertex import errors


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str = "provider failed",
        *,
        status_code: int | None = None,
        code: int | str | None = None,
        status: int | str | None = None,
        error: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status
        if error is not None:
            self.error = error


def test_map_vertex_error_classifies_auth_and_permission_without_raw_message():
    auth_error = errors.map_vertex_error(
        ProviderError(
            "raw credential path C:/secrets/service-account.json",
            status_code=401,
        )
    )
    permission_error = errors.map_vertex_error(ProviderError(status_code=403))

    assert isinstance(auth_error, errors.VertexAuthenticationFailedError)
    assert auth_error.code == "vertex_authentication_failed"
    assert "service-account" not in str(auth_error)
    assert auth_error.to_public_dict()["message"] == "Vertex AI authentication failed."

    assert isinstance(permission_error, errors.VertexPermissionDeniedError)
    assert permission_error.code == "vertex_permission_denied"
    assert permission_error.status_code == 403


def test_map_vertex_error_classifies_google_rpc_status_names():
    quota_error = errors.map_vertex_error(
        ProviderError(error={"status": "RESOURCE_EXHAUSTED"})
    )
    transient_error = errors.map_vertex_error(ProviderError(status="UNAVAILABLE"))
    invalid_error = errors.map_vertex_error(ProviderError(code="INVALID_ARGUMENT"))

    assert isinstance(quota_error, errors.VertexRateLimitedError)
    assert quota_error.code == "vertex_rate_limited"
    assert quota_error.retryable is True

    assert isinstance(transient_error, errors.VertexTransientError)
    assert transient_error.code == "vertex_transient_error"
    assert transient_error.retryable is True

    assert isinstance(invalid_error, errors.VertexRequestInvalidError)
    assert invalid_error.code == "vertex_request_invalid"
    assert invalid_error.retryable is False


def test_map_vertex_error_classifies_google_rpc_numeric_codes():
    assert isinstance(
        errors.map_vertex_error(ProviderError(code=16)),
        errors.VertexAuthenticationFailedError,
    )
    assert isinstance(
        errors.map_vertex_error(ProviderError(code=7)),
        errors.VertexPermissionDeniedError,
    )
    assert isinstance(
        errors.map_vertex_error(ProviderError(code=8)),
        errors.VertexRateLimitedError,
    )
    assert isinstance(
        errors.map_vertex_error(ProviderError(code=14)),
        errors.VertexTransientError,
    )
    assert isinstance(
        errors.map_vertex_error(ProviderError(code=3)),
        errors.VertexRequestInvalidError,
    )
