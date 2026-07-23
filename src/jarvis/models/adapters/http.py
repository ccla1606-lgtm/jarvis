"""Shared HTTP behavior that does not assume one provider wire format."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import SecretStr

from jarvis.models.errors import (
    ModelErrorCategory,
    ModelGatewayError,
    classify_http_error,
)
from jarvis.models.policy import ModelCapabilities
from jarvis.models.ports import ProviderStreamEvent


class HttpModelAdapter:
    """Base for adapters that own credentials and return normalized values."""

    def __init__(
        self,
        *,
        provider: str,
        api_key: SecretStr | str,
        base_url: str,
        capabilities: ModelCapabilities,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._provider = provider
        self._api_key = api_key if isinstance(api_key, SecretStr) else SecretStr(api_key)
        self._base_url = base_url.rstrip("/")
        self._capabilities = capabilities
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient()

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

    async def _post_json(
        self,
        path: str,
        *,
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        try:
            response = await self._client.post(
                f"{self._base_url}{path}",
                headers=self._headers,
                json=payload,
                timeout=timeout,
            )
        except httpx.TimeoutException as error:
            raise ModelGatewayError(
                ModelErrorCategory.TIMEOUT,
                "model provider request timed out",
                provider=self.provider,
            ) from error
        except httpx.RequestError as error:
            raise ModelGatewayError(
                ModelErrorCategory.PROVIDER_UNAVAILABLE,
                "model provider connection failed",
                provider=self.provider,
            ) from error

        if not response.is_success:
            raise classify_http_error(
                provider=self.provider,
                status_code=response.status_code,
                response_text=response.text,
            )
        try:
            result = response.json()
        except ValueError as error:
            raise ModelGatewayError(
                ModelErrorCategory.INVALID_RESPONSE,
                "model provider returned invalid JSON",
                provider=self.provider,
                retryable=False,
            ) from error
        if not isinstance(result, dict):
            raise ModelGatewayError(
                ModelErrorCategory.INVALID_RESPONSE,
                "model provider returned a non-object response",
                provider=self.provider,
                retryable=False,
            )
        return result

    async def _stream_sse(
        self,
        path: str,
        *,
        payload: dict[str, Any],
        timeout: float,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield decoded SSE data objects; context exit closes on cancellation."""

        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url}{path}",
                headers=self._headers,
                json=payload,
                timeout=timeout,
            ) as response:
                if not response.is_success:
                    body = (await response.aread()).decode(errors="replace")
                    raise classify_http_error(
                        provider=self.provider,
                        status_code=response.status_code,
                        response_text=body,
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        decoded = json.loads(data)
                    except ValueError as error:
                        raise ModelGatewayError(
                            ModelErrorCategory.INVALID_RESPONSE,
                            "model provider returned an invalid stream event",
                            provider=self.provider,
                            retryable=False,
                        ) from error
                    if not isinstance(decoded, dict):
                        raise ModelGatewayError(
                            ModelErrorCategory.INVALID_RESPONSE,
                            "model provider returned a non-object stream event",
                            provider=self.provider,
                            retryable=False,
                        )
                    yield decoded
        except httpx.TimeoutException as error:
            raise ModelGatewayError(
                ModelErrorCategory.TIMEOUT,
                "model provider stream timed out",
                provider=self.provider,
            ) from error
        except httpx.RequestError as error:
            raise ModelGatewayError(
                ModelErrorCategory.PROVIDER_UNAVAILABLE,
                "model provider stream connection failed",
                provider=self.provider,
            ) from error

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def invalid_provider_response(provider: str, detail: str) -> ModelGatewayError:
    return ModelGatewayError(
        ModelErrorCategory.INVALID_RESPONSE,
        f"model provider response is invalid: {detail}",
        provider=provider,
        retryable=False,
    )


def stream_done() -> ProviderStreamEvent:
    return ProviderStreamEvent(kind="done")
