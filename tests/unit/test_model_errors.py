import pytest

from jarvis.models.errors import ModelErrorCategory, classify_http_error


@pytest.mark.parametrize(
    ("status_code", "body", "category", "retryable"),
    (
        (401, "credential-secret", ModelErrorCategory.AUTHENTICATION, False),
        (429, "slow down", ModelErrorCategory.RATE_LIMIT, True),
        (500, "server failed", ModelErrorCategory.PROVIDER_UNAVAILABLE, True),
        (503, "overloaded", ModelErrorCategory.PROVIDER_UNAVAILABLE, True),
        (
            400,
            "maximum context length exceeded",
            ModelErrorCategory.CONTEXT_OVERFLOW,
            False,
        ),
        (422, "invalid field", ModelErrorCategory.INVALID_REQUEST, False),
    ),
)
def test_http_error_classification_matrix(
    status_code: int,
    body: str,
    category: ModelErrorCategory,
    retryable: bool,
) -> None:
    error = classify_http_error(
        provider="provider",
        status_code=status_code,
        response_text=body,
    )

    assert error.category is category
    assert error.retryable is retryable
    assert body not in str(error)
    assert "credential-secret" not in str(error)
