import pytest

from jarvis.models.contracts import (
    MessageRole,
    ModelMessage,
    ModelProfile,
    ModelRequest,
    ModelUsage,
    OutputSchema,
    StreamEvent,
    StreamEventKind,
)


def test_model_request_rejects_empty_messages_and_unbounded_values() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ModelRequest(ModelProfile.FAST, ())
    with pytest.raises(ValueError, match="positive"):
        ModelRequest(
            ModelProfile.FAST,
            (ModelMessage(MessageRole.USER, "hello"),),
            timeout_seconds=0,
        )


def test_output_schema_requires_object_root() -> None:
    with pytest.raises(ValueError, match="root"):
        OutputSchema("items", {"type": "array"})


def test_usage_cannot_hide_token_totals() -> None:
    with pytest.raises(ValueError, match="smaller"):
        ModelUsage(10, 5, 14)


def test_stream_event_requires_payload_for_its_kind() -> None:
    from jarvis.models.contracts import Resolution

    resolution = Resolution(
        ModelProfile.FAST,
        "provider",
        "model",
        None,
        1,
    )
    with pytest.raises(ValueError, match="requires text"):
        StreamEvent(StreamEventKind.TEXT_DELTA, resolution)
