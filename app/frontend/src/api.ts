import type {
  AuditEvent,
  Catalog,
  ProviderStatus,
  RequestReadiness,
  RequestRecord,
  VMDeploymentCreate,
  VMDeploymentUpdate,
  WorkflowRun
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Mock-User": "local-dev-user",
      ...(options.headers ?? {})
    },
    body: options.body ? JSON.stringify(options.body) : undefined
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail));
  }

  return response.json() as Promise<T>;
}

export const api = {
  health: () => apiRequest<{ status: string; app: string; provider_mode: string }>("/health"),
  catalog: () => apiRequest<Catalog>("/api/v1/catalog"),
  requests: () => apiRequest<RequestRecord[]>("/api/v1/requests"),
  request: (id: string) => apiRequest<RequestRecord>(`/api/v1/requests/${id}`),
  readiness: (id: string) => apiRequest<RequestReadiness>(`/api/v1/requests/${id}/readiness`),
  createVmRequest: (payload: VMDeploymentCreate) =>
    apiRequest<RequestRecord>("/api/v1/requests/vm-deploy", {
      method: "POST",
      body: payload
    }),
  updateVmRequest: (id: string, payload: VMDeploymentUpdate) =>
    apiRequest<RequestRecord>(`/api/v1/requests/${id}`, {
      method: "PATCH",
      body: payload
    }),
  submit: (id: string) =>
    apiRequest<RequestRecord>(`/api/v1/requests/${id}/submit`, { method: "POST" }),
  approve: (id: string, approver: string, notes: string) =>
    apiRequest<RequestRecord>(`/api/v1/requests/${id}/approve`, {
      method: "POST",
      body: { approver, notes }
    }),
  plan: (id: string) =>
    apiRequest<WorkflowRun>(`/api/v1/requests/${id}/plan`, { method: "POST" }),
  cancel: (id: string) =>
    apiRequest<RequestRecord>(`/api/v1/requests/${id}/cancel`, { method: "POST" }),
  execute: (id: string) =>
    apiRequest<WorkflowRun>(`/api/v1/requests/${id}/execute`, { method: "POST" }),
  workflowRuns: () => apiRequest<WorkflowRun[]>("/api/v1/workflow-runs"),
  workflowRun: (id: string) => apiRequest<WorkflowRun>(`/api/v1/workflow-runs/${id}`),
  auditEvents: () => apiRequest<AuditEvent[]>("/api/v1/audit-events"),
  providers: () => apiRequest<ProviderStatus[]>("/api/v1/providers/status")
};
