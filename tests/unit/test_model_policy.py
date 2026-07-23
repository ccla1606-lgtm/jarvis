import pytest

from jarvis.models.contracts import (
    MessageRole,
    ModelMessage,
    ModelProfile,
    ModelRequest,
    OutputSchema,
)
from jarvis.models.errors import ModelErrorCategory, ModelGatewayError
from jarvis.models.policy import (
    ModelCandidate,
    ModelCapabilities,
    ModelRouter,
    StructuredOutputMode,
    default_router,
)


def test_default_router_keeps_raw_model_names_inside_model_layer() -> None:
    router = default_router(
        openai_fast_model="openai-fast",
        deepseek_fast_model="deepseek-fast",
    )
    request = ModelRequest(
        ModelProfile.FAST,
        (ModelMessage(MessageRole.USER, "hello"),),
    )

    candidates = router.candidates(request)

    assert [candidate.provider for candidate in candidates] == ["openai", "deepseek"]
    assert [candidate.model for candidate in candidates] == [
        "openai-fast",
        "deepseek-fast",
    ]


def test_capability_mismatch_is_explicit() -> None:
    capabilities = ModelCapabilities(
        StructuredOutputMode.NONE,
        tool_calls=False,
        streaming=False,
        cancellation=False,
        reasoning_controls=False,
        context_window_tokens=100,
        max_output_tokens=10,
    )
    candidate = ModelCandidate(
        ModelProfile.FAST,
        "limited",
        "limited-model",
        capabilities,
    )
    router = ModelRouter({profile: (candidate,) for profile in ModelProfile})
    request = ModelRequest(
        ModelProfile.FAST,
        (ModelMessage(MessageRole.USER, "json"),),
        output_schema=OutputSchema(
            "answer",
            {"type": "object", "properties": {}},
        ),
    )

    with pytest.raises(ModelGatewayError) as captured:
        router.candidates(request)

    assert captured.value.category is ModelErrorCategory.CAPABILITY_MISMATCH


def test_router_rejects_missing_profile_routes() -> None:
    with pytest.raises(ValueError, match="missing model routes"):
        ModelRouter({})
