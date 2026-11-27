import type {
  HealthResponse,
  SimulationRunRequest,
  SimulationRunResultsResponse,
  SimulationRunStatusResponse,
} from "../types/api";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly details: string[];

  constructor(status: number, message: string, details: string[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "Could not reach the simulation API. Check the server and API URL.");
  }

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw toApiError(response.status, body);
  }
  return body as T;
}

function toApiError(status: number, body: unknown): ApiError {
  if (isRecord(body) && Array.isArray(body.detail)) {
    const details = body.detail.map((item) => {
      if (!isRecord(item)) return String(item);
      const location = Array.isArray(item.loc) ? item.loc.slice(1).join(" → ") : "Configuration";
      return `${location || "Configuration"}: ${String(item.msg ?? "Invalid value")}`;
    });
    return new ApiError(status, "The configuration was rejected by the API.", details);
  }
  if (isRecord(body) && isRecord(body.detail)) {
    return new ApiError(status, String(body.detail.message ?? "Request failed."));
  }
  const detail = isRecord(body) ? body.detail : undefined;
  const message = typeof detail === "string" ? detail : `Request failed (${status}).`;
  return new ApiError(status, message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export const simulationApi = {
  health: (signal?: AbortSignal) => request<HealthResponse>("/api/v1/health", { signal }),

  start: (payload: SimulationRunRequest, signal?: AbortSignal) =>
    request<SimulationRunStatusResponse>("/api/v1/simulations", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    }),

  status: (runId: string, signal?: AbortSignal) =>
    request<SimulationRunStatusResponse>(`/api/v1/simulations/${encodeURIComponent(runId)}`, {
      signal,
    }),

  results: (runId: string, signal?: AbortSignal) =>
    request<SimulationRunResultsResponse>(
      `/api/v1/simulations/${encodeURIComponent(runId)}/results`,
      { signal },
    ),

  cancel: (runId: string, signal?: AbortSignal) =>
    request<SimulationRunStatusResponse>(`/api/v1/simulations/${encodeURIComponent(runId)}`, {
      method: "DELETE",
      signal,
    }),
};
