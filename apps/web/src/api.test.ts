import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { fetchHealth } from "./api.ts";

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
