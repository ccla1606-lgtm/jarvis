import assert from "node:assert/strict";
import { describe, it } from "node:test";

import submitFixture from "./fixtures/submit-task-response.json" with { type: "json" };
import {
  ApiRequestError,
  fetchHealth,
  submitTask,
  type SubmitTaskResponse,
} from "./api.ts";

const typedSubmitFixture: SubmitTaskResponse = submitFixture;

void describe("fetchHealth", () => {
  void it("returns the normalized readiness response", async () => {
    const fetcher: typeof fetch = () =>
      Promise.resolve(
        new Response(
        JSON.stringify({
          status: "ok",
          service: "jarvis-api",
          detail: "postgres ready",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    const response = await fetchHealth(fetcher);

    assert.deepEqual(response, {
      status: "ok",
      service: "jarvis-api",
      detail: "postgres ready",
    });
  });

  void it("surfaces a safe readiness failure", async () => {
    const fetcher: typeof fetch = () =>
      Promise.resolve(
        new Response(
        JSON.stringify({
          status: "not_ready",
          service: "jarvis-api",
          detail: "postgres unavailable",
        }),
        { status: 503, headers: { "Content-Type": "application/json" } },
        ),
      );

    await assert.rejects(fetchHealth(fetcher), /postgres unavailable/);
  });
});

void describe("submitTask", () => {
  void it("sends auth and idempotency headers and returns the shared fixture", async () => {
    let captured: RequestInit | undefined;
    const fetcher: typeof fetch = (_input, init) => {
      captured = init;
      return Promise.resolve(
        new Response(JSON.stringify(typedSubmitFixture), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        }),
      );
    };

    const response = await submitTask(
      { objective: "Implement the approved change" },
      {
        token: "test-token",
        idempotencyKey: "task-command-1",
        fetcher,
      },
    );

    assert.deepEqual(response, typedSubmitFixture);
    assert.equal(captured?.method, "POST");
    assert.deepEqual(captured?.headers, {
      Accept: "application/json",
      Authorization: "Bearer test-token",
      "Content-Type": "application/json",
      "Idempotency-Key": "task-command-1",
    });
  });

  void it("preserves the API error code and correlation ID", async () => {
    const fetcher: typeof fetch = () =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            error: {
              code: "STALE_PLAN",
              message: "Plan version is stale",
              correlation_id: "correlation-7",
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      );

    await assert.rejects(
      submitTask(
        { objective: "Invalid" },
        {
          token: "test-token",
          idempotencyKey: "task-command-2",
          fetcher,
        },
      ),
      (error: unknown) =>
        error instanceof ApiRequestError &&
        error.code === "STALE_PLAN" &&
        error.correlationId === "correlation-7" &&
        error.status === 409,
    );
  });
});
