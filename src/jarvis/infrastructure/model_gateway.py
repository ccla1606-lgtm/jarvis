"""Application composition for deterministic and live model gateways."""

from jarvis.config import Settings
from jarvis.models.adapters import DeepSeekAdapter, OpenAIResponsesAdapter
from jarvis.models.contracts import ModelProfile
from jarvis.models.development import DeterministicDevelopmentAdapter
from jarvis.models.gateway import ModelGateway
from jarvis.models.policy import OPENAI_CAPABILITIES, ModelCandidate, ModelRouter, default_router


def build_model_gateway(settings: Settings) -> ModelGateway:
    """Build one provider-neutral gateway for the selected runtime mode."""

    if settings.model_mode == "deterministic":
        adapter = DeterministicDevelopmentAdapter()
        candidate_routes = {
            profile: (
                ModelCandidate(
                    profile,
                    adapter.provider,
                    "deterministic-development",
                    OPENAI_CAPABILITIES,
                ),
            )
            for profile in ModelProfile
        }
        return ModelGateway(
            router=ModelRouter(candidate_routes),
            adapters={adapter.provider: adapter},
            max_retries_per_candidate=0,
            max_structured_repairs=0,
        )

    if settings.openai_api_key is None or settings.deepseek_api_key is None:
        raise ValueError("live model mode requires both provider credentials")
    return ModelGateway(
        router=default_router(
            openai_fast_model=settings.openai_fast_model,
            openai_reasoning_model=settings.openai_reasoning_model,
            deepseek_fast_model=settings.deepseek_fast_model,
            deepseek_reasoning_model=settings.deepseek_reasoning_model,
        ),
        adapters={
            "openai": OpenAIResponsesAdapter(settings.openai_api_key),
            "deepseek": DeepSeekAdapter(settings.deepseek_api_key),
        },
    )
