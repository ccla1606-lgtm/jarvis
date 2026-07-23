"""Sanitized, provider-neutral model error taxonomy."""

from enum import StrEnum


class ModelErrorCategory(StrEnum):
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    CONTEXT_OVERFLOW = "context_overflow"
    INVALID_REQUEST = "invalid_request"
    INVALID_RESPONSE = "invalid_response"
    CAPABILITY_MISMATCH = "capability_mismatch"
    PARTIAL_OUTPUT = "partial_output"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


RETRYABLE_CATEGORIES = frozenset(
    {
        ModelErrorCategory.TIMEOUT,
        ModelErrorCategory.RATE_LIMIT,
        ModelErrorCategory.PROVIDER_UNAVAILABLE,
    }
)


class ModelGatewayError(RuntimeError):
    """An error safe to expose outside a provider adapter."""

    def __init__(
        self,
        category: ModelErrorCategory,
        message: str,
        *,
        provider: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        self.category = category
        self.provider = provider
        self.retryable = category in RETRYABLE_CATEGORIES if retryable is None else retryable
        super().__init__(message)


def classify_http_error(
    *,
    provider: str,
    status_code: int,
    response_text: str = "",
) -> ModelGatewayError:
    """Classify an HTTP failure without copying provider payloads into messages."""

    lowered = response_text[:4096].lower()
    if status_code == 401:
        category = ModelErrorCategory.AUTHENTICATION
        message = "model provider authentication failed"
    elif status_code == 429:
        category = ModelErrorCategory.RATE_LIMIT
        message = "model provider rate limit reached"
    elif status_code >= 500:
        category = ModelErrorCategory.PROVIDER_UNAVAILABLE
        message = "model provider is unavailable"
    elif status_code in {400, 413, 422} and any(
        marker in lowered
        for marker in (
            "context length",
            "context_length",
            "maximum context",
            "too many tokens",
            "token limit",
        )
    ):
        category = ModelErrorCategory.CONTEXT_OVERFLOW
        message = "model request exceeds the provider context limit"
    elif status_code in {400, 402, 403, 404, 413, 422}:
        category = ModelErrorCategory.INVALID_REQUEST
        message = "model provider rejected the request"
    else:
        category = ModelErrorCategory.UNKNOWN
        message = "unexpected model provider response"
    return ModelGatewayError(category, message, provider=provider)
