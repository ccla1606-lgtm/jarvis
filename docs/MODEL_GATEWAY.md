# Model gateway

## Boundary

Application and graph code select one of five logical profiles:

- `fast`
- `planner`
- `coder`
- `reviewer`
- `summarizer`

Only `jarvis.models` may resolve a profile to a provider, model, account, or
provider capability. Provider credentials and raw HTTP responses stay inside
the adapter.

## Runtime design

`ModelGateway` applies these bounded steps:

1. filter the route by required capabilities;
2. invoke the primary candidate with a timeout;
3. retry only timeout, rate-limit, and provider-unavailable failures;
4. validate structured output locally with JSON Schema;
5. request at most the configured number of repairs;
6. fall back only before any streamed output has escaped;
7. return normalized content, tool calls, usage, and a resolution record.

OpenAI uses the Responses API and native JSON Schema output. DeepSeek uses its
OpenAI-compatible Chat Completions endpoint and JSON Object mode. Jarvis still
validates both providers locally, because transport success is not application
schema success.

The default route is intentionally data, not business logic. Model identifiers
may be overridden in the model composition root without changing application
or agent code.

## Error policy

| Category | Retry same candidate | May fall back |
| --- | --- | --- |
| timeout | yes, bounded | yes |
| authentication | no | yes |
| rate limit | yes, bounded | yes |
| provider unavailable / 5xx | yes, bounded | yes |
| context overflow | no | yes |
| invalid structured response | repair, bounded | yes |
| invalid request | no | no |
| capability mismatch | no | no |
| failure after partial stream output | no | no |

Provider error bodies are used only for local classification. They are not
copied into normalized exception messages.

## Verification lanes

`make verify` runs fake and mocked-transport contract tests. It performs no
network calls and needs no credentials.

`make smoke-models` is an explicit paid/network lane. It requires both
`OPENAI_API_KEY` and `DEEPSEEK_API_KEY`, makes one small call to each provider,
and prints only provider/model metadata, token counts, timestamp, and a digest
of the response content. A missing key reports `BLOCKED` and exits with status
2; mocked tests are never presented as live compatibility evidence.

## Runtime modes

`JARVIS_MODEL_MODE=deterministic` is the development and integration default. It exercises the same router, structured-output validation, graph nodes, and persistence path without network calls or provider cost. It is evidence for orchestration correctness, never evidence of external provider compatibility.

`JARVIS_MODEL_MODE=live` composes the OpenAI and DeepSeek adapters behind the same gateway. Production rejects deterministic mode, the development API token, or missing `JARVIS_OPENAI_API_KEY` / `JARVIS_DEEPSEEK_API_KEY` at settings validation time. Model names remain configurable through the documented environment variables.

`make smoke-models` is the independent release gate for real GPT and DeepSeek compatibility. Both calls must pass with credentials and their redacted evidence must be attached to the milestone; unit mocks and deterministic runs cannot satisfy that gate.

## Wire-contract references

- [OpenAI Responses API migration and item model](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI streaming Responses](https://developers.openai.com/api/docs/guides/streaming-responses)
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
- [DeepSeek error codes](https://api-docs.deepseek.com/quick_start/error_codes/)
