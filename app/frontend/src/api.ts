import type {
  ArtifactRecord,
  AuditEvent,
  Catalog,
  CiscoBootstrapRequirements,
  CiscoBootstrapRequirementsUpdate,
  CiscoConsoleBootstrapPlan,
  CiscoSetupReadiness,
  CiscoSetupWizardPlan,
  HpeRaidIntent,
  HpeRaidIntentWrite,
  HpeRaidPlanPreview,
  HpeStorageDiscovery,
  IloUpgradeReadiness,
  IloSetupIntent,
  IloSetupIntentWrite,
  IloSetupPlanPreview,
  MediaInventory,
  NetAppConsoleReadiness,
  NetAppObservationUpdate,
  NetAppObservations,
  NetAppProviderArtifact,
  NetAppPlanPreview,
  NetAppReadinessComparison,
  NetAppUpgradeReadiness,
  ProviderProbeResult,
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
  requestArtifacts: (id: string) =>
    apiRequest<ArtifactRecord[]>(`/api/v1/requests/${id}/artifacts`),
  workflowRunArtifacts: (id: string) =>
    apiRequest<ArtifactRecord[]>(`/api/v1/workflow-runs/${id}/artifacts`),
  auditEvents: () => apiRequest<AuditEvent[]>("/api/v1/audit-events"),
  mediaInventory: () => apiRequest<MediaInventory>("/api/v1/media-inventory"),
  iloUpgradeReadiness: () =>
    apiRequest<IloUpgradeReadiness>("/api/v1/providers/ilo-redfish/upgrade-readiness"),
  iloSetupIntent: () =>
    apiRequest<IloSetupIntent>("/api/v1/providers/ilo-redfish/setup-intent"),
  saveIloSetupIntent: (payload: IloSetupIntentWrite) =>
    apiRequest<IloSetupIntent>("/api/v1/providers/ilo-redfish/setup-intent", {
      method: "PUT",
      body: payload
    }),
  iloSetupPlanPreview: () =>
    apiRequest<IloSetupPlanPreview>("/api/v1/providers/ilo-redfish/setup-plan-preview"),
  hpeStorageDiscovery: () =>
    apiRequest<HpeStorageDiscovery>("/api/v1/providers/ilo-redfish/hpe-storage-discovery"),
  hpeRaidIntent: () =>
    apiRequest<HpeRaidIntent>("/api/v1/providers/ilo-redfish/hpe-raid-intent"),
  saveHpeRaidIntent: (payload: HpeRaidIntentWrite) =>
    apiRequest<HpeRaidIntent>("/api/v1/providers/ilo-redfish/hpe-raid-intent", {
      method: "PUT",
      body: payload
    }),
  hpeRaidPlanPreview: () =>
    apiRequest<HpeRaidPlanPreview>("/api/v1/providers/ilo-redfish/hpe-raid-plan-preview"),
  hpeRaidApplyPlan: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-apply-plan"),
  applyHpeRaidPlan: (confirmation_phrase: string) =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-apply", {
      method: "POST",
      body: { confirmation_phrase }
    }),
  hpeRaidPending: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-pending"),
  hpeRaidResetPlan: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-reset-plan"),
  resetHpeRaidServer: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-reset", {
      method: "POST"
    }),
  validateHpeRaidAfterReset: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-validate-after-reset", {
      method: "POST"
    }),
  esxiInstallReadiness: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/esxi-install-readiness"),
  ciscoSetupReadiness: () =>
    apiRequest<CiscoSetupReadiness>("/api/v1/providers/cisco/setup-readiness"),
  ciscoSetupWizardPlan: () =>
    apiRequest<CiscoSetupWizardPlan>("/api/v1/providers/cisco/setup-wizard-plan"),
  ciscoBootstrapRequirements: () =>
    apiRequest<CiscoBootstrapRequirements>("/api/v1/providers/cisco/bootstrap-requirements"),
  saveCiscoBootstrapRequirements: (payload: CiscoBootstrapRequirementsUpdate) =>
    apiRequest<CiscoBootstrapRequirements>("/api/v1/providers/cisco/bootstrap-requirements", {
      method: "PUT",
      body: payload
    }),
  ciscoConsoleBootstrapPlan: () =>
    apiRequest<CiscoConsoleBootstrapPlan>("/api/v1/providers/cisco/console-bootstrap/plan"),
  netappPlanPreview: () =>
    apiRequest<NetAppPlanPreview>("/api/v1/providers/netapp-ontap/plan-preview"),
  netappConsoleReadiness: () =>
    apiRequest<NetAppConsoleReadiness>("/api/v1/providers/netapp-ontap/console-readiness"),
  netappObservations: () =>
    apiRequest<NetAppObservations>("/api/v1/providers/netapp-ontap/observations"),
  saveNetappObservations: (payload: NetAppObservationUpdate) =>
    apiRequest<NetAppObservations>("/api/v1/providers/netapp-ontap/observations", {
      method: "PUT",
      body: payload
    }),
  netappReadinessComparison: () =>
    apiRequest<NetAppReadinessComparison>("/api/v1/providers/netapp-ontap/readiness-comparison"),
  netappUpgradeReadiness: () =>
    apiRequest<NetAppUpgradeReadiness>("/api/v1/providers/netapp-ontap/upgrade-readiness"),
  netappArtifacts: () =>
    apiRequest<NetAppProviderArtifact[]>("/api/v1/providers/netapp-ontap/artifacts"),
  providerArtifacts: () =>
    apiRequest<NetAppProviderArtifact[]>("/api/v1/providers/artifacts"),
  providers: () => apiRequest<ProviderStatus[]>("/api/v1/providers/status"),
  firmwareInventory: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/firmware-inventory"),
  firmwareCompliance: (scope = "full") =>
    apiRequest<ProviderProbeResult>(`/api/v1/lab/firmware-compliance?scope=${encodeURIComponent(scope)}`),
  firmwareWaiverCheck: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/firmware-waiver-check"),
  fullRebuildSummary: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/full-rebuild-summary"),
  buildVerification: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/build-verification"),
  ciscoConsolePromptReadiness: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/cisco-console/prompt-readiness", {
      method: "POST"
    }),
  probeProvider: (id: string) =>
    apiRequest<ProviderProbeResult>(`/api/v1/providers/${id}/probe`, { method: "POST" })
};
