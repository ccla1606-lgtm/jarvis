export type HealthStatus = "ok" | "not_ready";

export interface HealthResponse {
  status: HealthStatus;
  service: string;
  detail: string | null;
}

export interface TaskView {
  id: string;
  objective: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface SubmitTaskRequest {
  objective: string;
  allowed_tools?: string[];
  allowed_repositories?: string[];
  side_effects_allowed?: boolean;
}

export interface SubmitTaskResponse {
  task: TaskView;
  orchestration: {
    route: string | null;
    interrupted: boolean;
  };
}

export interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    correlation_id: string;
  };
}

export interface SubmitTaskOptions {
  token: string;
  idempotencyKey: string;
  fetcher?: typeof fetch;
  signal?: AbortSignal;
}

export class ApiRequestError extends Error {
  readonly code: string;
  readonly correlationId: string;
  readonly status: number;

  constructor(
    code: string,
    message: string,
    correlationId: string,
    status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.correlationId = correlationId;
    this.status = status;
  }
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

export async function submitTask(
  request: SubmitTaskRequest,
  options: SubmitTaskOptions,
): Promise<SubmitTaskResponse> {
  const fetcher = options.fetcher ?? fetch;
  const response = await fetcher("/api/v1/tasks", {
    method: "POST",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${options.token}`,
      "Content-Type": "application/json",
      "Idempotency-Key": options.idempotencyKey,
    },
    body: JSON.stringify(request),
    signal: options.signal,
  });
  const payload = (await response.json()) as SubmitTaskResponse | ApiErrorResponse;
  if (!response.ok) {
    const failure = payload as ApiErrorResponse;
    throw new ApiRequestError(
      failure.error.code,
      failure.error.message,
      failure.error.correlation_id,
      response.status,
    );
  }
  return payload as SubmitTaskResponse;
}
