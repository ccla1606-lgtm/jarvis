export type HealthStatus = "ok" | "not_ready";

export interface HealthResponse {
  status: HealthStatus;
  service: string;
  detail: string | null;
}

export async function fetchHealth(
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<HealthResponse> {
  const response = await fetcher("/api/health/ready", {
    headers: { Accept: "application/json" },
    signal,
  });
  const payload = (await response.json()) as HealthResponse;
  if (!response.ok) {
    throw new Error(payload.detail ?? `Readiness failed with ${response.status}`);
  }
  return payload;
}

