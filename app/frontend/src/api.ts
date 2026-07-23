import type {
  ArtifactRecord,
  AuditEvent,
  AiChangeRequest,
  AiChangeRequestCreate,
  Catalog,
  CiscoBootstrapRequirements,
  CiscoBootstrapRequirementsUpdate,
  CiscoConsoleBootstrapPlan,
  CiscoConsoleIdentityCandidates,
  CiscoConsoleIdentityResult,
  CiscoConsoleIdentityVerifyRequest,
  CiscoSetupReadiness,
  CiscoSetupWizardPlan,
  ControlAccessConfig,
  ControlAccessConfigWrite,
  ControlActionCatalog,
  ControlActionPlan,
  ControlActionRun,
  FirmwareFileSelections,
  FirmwareFileSelectionsWrite,
  FirmwareSummary,
  HpeRaidIntent,
  HpeRaidIntentWrite,
  HpeRaidPlanPreview,
  HpeStorageDiscovery,
  IloAccessSettings,
  IloAccessSettingsWrite,
  IloBaselinePreview,
  IloBaselineReadiness,
  IloSetupIntent,
  IloSetupIntentWrite,
  IloSetupPlanPreview,
  IloUpgradeReadiness,
  LabCredentials,
  LabCredentialsWrite,
  LabSafetySettings,
  LabSafetySettingsWrite,
  LabBuildPlan,
  LabBuildRun,
  LabBuildResumeRequest,
  LabValidationSummary,
  LabProfile,
  LabProfileList,
  LabProfileRuntimeApply,
  LabProfileWrite,
  TopologyDesignDraft,
  TopologyDesignDraftWrite,
  MediaInventory,
  NetAppConsoleReadiness,
  NetAppObservationUpdate,
  NetAppObservations,
  NetAppProviderArtifact,
  NetAppPlanPreview,
  NetAppReadinessComparison,
  NetAppUpgradeReadiness,
  OperatorIssuePacket,
  OperatorIssuePacketCreate,
  ProviderModeSettings,
  ProviderModeSettingsWrite,
  ProviderProbeResult,
  ProviderStatus,
  ReportCenter,
  RequestReadiness,
  RequestRecord,
  UiIntentRequest,
  UiIntentResponse,
  VMDeploymentCreate,
  VMDeploymentUpdate,
  WorkflowAction,
  WorkflowActionDiagnosis,
  WorkflowActionRunRequest,
  WorkflowActionRun,
  WorkflowRun,
  WorkflowStage
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const VM_DEPLOY_APPLY_TIMEOUT_MS = 20 * 60 * 1000;

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  timeoutMs?: number;
};

async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response: Response;
  const { timeoutMs = 30000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...fetchOptions,
      headers: {
        "Content-Type": "application/json",
        "X-Local-User": "local-operator",
        ...(options.headers ?? {})
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal ?? controller.signal
    });
  } catch (err) {
    const timedOut = err instanceof DOMException && err.name === "AbortError";
    throw new Error(timedOut ? `Request timed out while requesting ${path}.` : `Network error while requesting ${path}.`);
  } finally {
    window.clearTimeout(timeout);
  }

  if (!response.ok) {
    throw new Error(await apiErrorFromResponse(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  if (!text.trim()) {
    return undefined as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(`Invalid JSON response from ${path}.`);
  }
}

async function apiErrorFromResponse(response: Response): Promise<string> {
  const text = await response.text().catch(() => "");
  if (!text.trim()) {
    return response.statusText || `Request failed with HTTP ${response.status}`;
  }
  try {
    const payload = JSON.parse(text) as { detail?: unknown };
    return apiErrorMessage(payload.detail ?? payload);
  } catch {
    return text.trim();
  }
}

export function apiErrorMessage(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (typeof item === "number" || typeof item === "boolean") {
          return String(item);
        }
        if (!item || typeof item !== "object") {
          return "";
        }
        const record = item as Record<string, unknown>;
        const location = Array.isArray(record.loc)
          ? record.loc.filter((part) => part !== "body").join(".")
          : "";
        const message = typeof record.msg === "string" ? record.msg : "Invalid value";
        return location ? `${location}: ${message}` : message;
      })
      .filter(Boolean);
    return messages.length ? messages.join("; ") : "Request failed.";
  }
  if (detail === null || detail === undefined) {
    return "Request failed.";
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

export const api = {
  health: () => apiRequest<{
    status: string;
    app: string;
    provider_mode: string;
    operator_runtime_mode: string;
    expected_runtime_mode: string;
    lab_subnet_cidr?: string | null;
    host_ipv4_addresses?: string[];
    dev_test_banner: string | null;
  }>("/health"),
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
  workflowStages: () => apiRequest<WorkflowStage[]>("/api/v1/workflows/stages"),
  workflowStage: (id: string) =>
    apiRequest<WorkflowStage>(`/api/v1/workflows/stages/${encodeURIComponent(id)}`),
  workflowActions: () => apiRequest<WorkflowAction[]>("/api/v1/workflows/actions", { timeoutMs: 90000 }),
  workflowAction: (id: string) =>
    apiRequest<WorkflowAction>(`/api/v1/workflows/actions/${encodeURIComponent(id)}`),
  runWorkflowAction: (id: string, payload?: WorkflowActionRunRequest) =>
    apiRequest<WorkflowActionRun>(`/api/v1/workflows/actions/${encodeURIComponent(id)}/run`, {
      method: "POST",
      body: payload,
      timeoutMs: id === "esxi.vm-deploy-apply" ? VM_DEPLOY_APPLY_TIMEOUT_MS : 120000
    }),
  workflowActionRuns: (id: string) =>
    apiRequest<WorkflowActionRun[]>(`/api/v1/workflows/actions/${encodeURIComponent(id)}/runs`),
  workflowActionDiagnosis: (id: string) =>
    apiRequest<WorkflowActionDiagnosis>(`/api/v1/workflows/actions/${encodeURIComponent(id)}/diagnosis`),
  labBuildPlan: () => apiRequest<LabBuildPlan>("/api/v1/lab-build/plan"),
  latestLabBuildRun: (kitId: string) =>
    apiRequest<LabBuildRun | null>(`/api/v1/lab-build/runs/latest?kit_id=${encodeURIComponent(kitId)}`),
  startLabBuild: () =>
    apiRequest<LabBuildRun>("/api/v1/lab-build/runs", {
      method: "POST",
      timeoutMs: 120000
    }),
  labBuildRun: (id: string) =>
    apiRequest<LabBuildRun>(`/api/v1/lab-build/runs/${encodeURIComponent(id)}`),
  resumeLabBuild: (id: string, payload: LabBuildResumeRequest) =>
    apiRequest<LabBuildRun>(`/api/v1/lab-build/runs/${encodeURIComponent(id)}/resume`, {
      method: "POST",
      body: payload,
      timeoutMs: 120000
    }),
  retryLabBuildStep: (runId: string, stepId: string) =>
    apiRequest<LabBuildRun>(
      `/api/v1/lab-build/runs/${encodeURIComponent(runId)}/steps/${encodeURIComponent(stepId)}/retry`,
      { method: "POST" }
    ),
  createOperatorIssuePacket: (payload: OperatorIssuePacketCreate) =>
    apiRequest<OperatorIssuePacket>("/api/v1/operator-issue-packets", {
      method: "POST",
      body: payload
    }),
  resolveUiIntent: (payload: UiIntentRequest) =>
    apiRequest<UiIntentResponse>("/api/v1/ui-intent", {
      method: "POST",
      body: payload
    }),
  createAiChangeRequest: (payload: AiChangeRequestCreate) =>
    apiRequest<AiChangeRequest>("/api/v1/ai-change-requests", {
      method: "POST",
      body: payload
    }),
  requestArtifacts: (id: string) =>
    apiRequest<ArtifactRecord[]>(`/api/v1/requests/${id}/artifacts`),
  workflowRunArtifacts: (id: string) =>
    apiRequest<ArtifactRecord[]>(`/api/v1/workflow-runs/${id}/artifacts`),
  auditEvents: (timeoutMs?: number) => apiRequest<AuditEvent[]>("/api/v1/audit-events", { timeoutMs }),
  mediaInventory: () => apiRequest<MediaInventory>("/api/v1/media-inventory"),
  iloUpgradeReadiness: () =>
    apiRequest<IloUpgradeReadiness>("/api/v1/providers/ilo-redfish/upgrade-readiness"),
  iloBaselinePreview: () =>
    apiRequest<IloBaselinePreview>("/api/v1/providers/hpe-ilo/baseline-preview"),
  iloBaselineReadiness: () =>
    apiRequest<IloBaselineReadiness>("/api/v1/providers/hpe-ilo/readiness"),
  iloSetupIntent: () =>
    apiRequest<IloSetupIntent>("/api/v1/providers/ilo-redfish/setup-intent"),
  saveIloSetupIntent: (payload: IloSetupIntentWrite) =>
    apiRequest<IloSetupIntent>("/api/v1/providers/ilo-redfish/setup-intent", {
      method: "PUT",
      body: payload
    }),
  iloAccessSettings: () =>
    apiRequest<IloAccessSettings>("/api/v1/providers/ilo-redfish/access-settings"),
  saveIloAccessSettings: (payload: IloAccessSettingsWrite) =>
    apiRequest<IloAccessSettings>("/api/v1/providers/ilo-redfish/access-settings", {
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
  applyHpeRaidPlan: (confirmation_phrase: string, ilo_host: string) =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-apply", {
      method: "POST",
      body: { confirmation_phrase, ilo_host }
    }),
  hpeRaidFactoryResetPreview: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-factory-reset-preview"),
  applyHpeRaidFactoryReset: (confirmation_phrase: string) =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-factory-reset-apply", {
      method: "POST",
      body: { confirmation_phrase }
    }),
  hpeRaidPending: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-pending"),
  hpeRaidResetPlan: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-reset-plan"),
  resetHpeRaidServer: (ilo_host: string) =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-reset", {
      method: "POST",
      body: { ilo_host }
    }),
  validateHpeRaidAfterReset: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/hpe-raid-validate-after-reset", {
      method: "POST"
    }),
  esxiInstallReadiness: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/ilo-redfish/esxi-install-readiness"),
  ciscoSetupReadiness: () =>
    apiRequest<CiscoSetupReadiness>("/api/v1/providers/cisco/setup-readiness"),
  ciscoSshProbe: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/cisco-ansible/probe", {
      method: "POST",
      timeoutMs: 70000
    }),
  ciscoCurrentIntentDiff: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/cisco/current-intent-diff", {
      method: "POST",
      timeoutMs: 90000
    }),
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
  ciscoConsoleIdentityCandidates: () =>
    apiRequest<CiscoConsoleIdentityCandidates>("/api/v1/providers/cisco-console/identity-candidates"),
  verifyCiscoConsoleIdentity: (payload: CiscoConsoleIdentityVerifyRequest) =>
    apiRequest<CiscoConsoleIdentityResult>("/api/v1/providers/cisco-console/verify-identity", {
      method: "POST",
      body: payload,
      timeoutMs: 30000
    }),
  netappPlanPreview: () =>
    apiRequest<NetAppPlanPreview>("/api/v1/providers/netapp-ontap/plan-preview"),
  netappConsoleReadiness: () =>
    apiRequest<NetAppConsoleReadiness>("/api/v1/providers/netapp-ontap/console-readiness"),
  netappConsoleDiscovery: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/console-discovery"),
  runNetappConsoleDiscovery: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/console-discovery", {
      method: "POST"
    }),
  netappConsoleReadState: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/console-read-state"),
  runNetappConsoleReadState: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/console-read-state", {
      method: "POST",
      timeoutMs: 70000
    }),
  runNetappConsoleLoginState: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/console-login-state", {
      method: "POST",
      timeoutMs: 70000
    }),
  netappLiveState: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/live-state"),
  runNetappLiveState: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/live-state", {
      method: "POST"
    }),
  validateNetappSetup: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/validate-setup", {
      method: "POST"
    }),
  netappAddressPlan: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/address-plan"),
  runNetappAddressPlan: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/address-plan", {
      method: "POST"
    }),
  netappNfsVcenterReadiness: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/nfs-vcenter-readiness"),
  netappNfsSetupPreview: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/nfs-setup-preview"),
  runNetappNfsSetupApply: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/nfs-setup-apply", {
      method: "POST"
    }),
  validateNetappNfsSetup: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/nfs-setup-validate", {
      method: "POST"
    }),
  netappIscsiSetupPreview: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/iscsi-setup-preview"),
  runNetappIscsiSetupApply: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/iscsi-setup-apply", {
      method: "POST"
    }),
  validateNetappIscsiSetup: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/iscsi-setup-validate", {
      method: "POST"
    }),
  esxiIscsiDatastorePreview: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/esxi-readonly/iscsi-datastore-preview", {
      method: "POST"
    }),
  validateEsxiIscsiDatastore: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/esxi-readonly/iscsi-datastore-validate", {
      method: "POST"
    }),
  esxiVmDeployPreview: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/esxi-readonly/vm-deploy-preview"),
  runEsxiVmDeployApply: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/esxi-readonly/vm-deploy-apply", {
      method: "POST",
      timeoutMs: VM_DEPLOY_APPLY_TIMEOUT_MS
    }),
  validateEsxiVmDeploy: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/esxi-readonly/vm-deploy-validate", {
      method: "POST"
    }),
  netappSetupPreview: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/setup-preview"),
  runNetappSetupApply: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/setup-apply", {
      method: "POST"
    }),
  netappOntapUpgradeInventory: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/ontap-upgrade/inventory"),
  netappOntapUpgradePlan: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/ontap-upgrade/plan"),
  validateNetappOntapUpgrade: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/ontap-upgrade/validate", {
      method: "POST"
    }),
  runNetappOntapUpgradeApply: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/netapp-ontap/ontap-upgrade/apply", {
      method: "POST"
    }),
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
  providerModeSettings: () =>
    apiRequest<ProviderModeSettings>("/api/v1/settings/provider-mode"),
  updateProviderModeSettings: (payload: ProviderModeSettingsWrite) =>
    apiRequest<ProviderModeSettings>("/api/v1/settings/provider-mode", {
      method: "PUT",
      body: payload
    }),
  labSafetySettings: () =>
    apiRequest<LabSafetySettings>("/api/v1/settings/lab-safety"),
  updateLabSafetySettings: (payload: LabSafetySettingsWrite) =>
    apiRequest<LabSafetySettings>("/api/v1/settings/lab-safety", {
      method: "PUT",
      body: payload
    }),
  labCredentials: () => apiRequest<LabCredentials>("/api/v1/lab/credentials"),
  updateLabCredentials: (payload: LabCredentialsWrite) =>
    apiRequest<LabCredentials>("/api/v1/lab/credentials", {
      method: "POST",
      body: payload
    }),
  controlActions: () => apiRequest<ControlActionCatalog>("/api/v1/control/actions"),
  updateControlAccessConfig: (sectionId: string, payload: ControlAccessConfigWrite) =>
    apiRequest<ControlAccessConfig>(`/api/v1/control/access/${encodeURIComponent(sectionId)}`, {
      method: "PUT",
      body: payload
    }),
  planControlAction: (id: string) =>
    apiRequest<ControlActionPlan>(`/api/v1/control/actions/${encodeURIComponent(id)}/plan`, {
      method: "POST"
    }),
  runControlAction: (id: string) =>
    apiRequest<ControlActionRun>(`/api/v1/control/actions/${encodeURIComponent(id)}/run`, {
      method: "POST"
    }),
  firmwareInventory: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/firmware-inventory"),
  firmwareCompliance: (scope = "full") =>
    apiRequest<ProviderProbeResult>(`/api/v1/lab/firmware-compliance?scope=${encodeURIComponent(scope)}`),
  firmwareWaiverCheck: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/firmware-waiver-check"),
  firmwareSummary: () =>
    apiRequest<FirmwareSummary[]>("/api/v1/firmware/summary"),
  firmwareFileSelections: () =>
    apiRequest<FirmwareFileSelections>("/api/v1/firmware/file-selections"),
  saveFirmwareFileSelections: (payload: FirmwareFileSelectionsWrite) =>
    apiRequest<FirmwareFileSelections>("/api/v1/firmware/file-selections", {
      method: "PUT",
      body: payload
    }),
  fullRebuildSummary: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/full-rebuild-summary"),
  buildVerification: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/build-verification"),
  goldenState: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/golden-state"),
  labValidation: () =>
    apiRequest<LabValidationSummary>("/api/v1/lab/validation", { timeoutMs: 120000 }),
  labValidationHandoff: () =>
    apiRequest<LabValidationSummary>("/api/v1/lab/validation/handoff", { timeoutMs: 120000 }),
  vcenterNetappReadiness: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/vcenter-netapp/readiness"),
  vcenterNetappDatastorePlan: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/vcenter-netapp/datastore-plan"),
  vcenterInstallReadiness: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/vcenter/install-readiness"),
  vcenterInstallPlan: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/vcenter/install-plan"),
  vcenterInstallPreview: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/vcenter/install-preview"),
  vcenterInstallApply: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/vcenter/install-apply", {
      method: "POST"
    }),
  vcenterAttachEsxiPreview: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/vcenter/attach-esxi-preview"),
  vcenterAttachEsxiApply: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/vcenter/attach-esxi-apply", {
      method: "POST"
    }),
  vcenterPostAttachValidation: () =>
    apiRequest<ProviderProbeResult>("/api/v1/lab/vcenter/post-attach-validation"),
  reportIssues: () =>
    apiRequest<ReportCenter>("/api/v1/reports/issues"),
  reportSummary: () =>
    apiRequest<ReportCenter>("/api/v1/reports/summary"),
  labProfiles: () => apiRequest<LabProfileList>("/api/v1/lab/profiles"),
  createLabProfile: (payload: LabProfileWrite) =>
    apiRequest<LabProfile>("/api/v1/lab/profiles", {
      method: "POST",
      body: payload
    }),
  updateLabProfile: (id: string, payload: LabProfileWrite) =>
    apiRequest<LabProfile>(`/api/v1/lab/profiles/${id}`, {
      method: "PUT",
      body: payload
    }),
  activateLabProfile: (id: string) =>
    apiRequest<LabProfileList>(`/api/v1/lab/profiles/${id}/activate`, {
      method: "POST"
    }),
  applyActiveLabProfileRuntimeEnv: () =>
    apiRequest<LabProfileRuntimeApply>("/api/v1/lab/profiles/active/apply-runtime-env", {
      method: "POST"
    }),
  topologyDesignDraft: (profileId: string, scenario: string, subnet?: string | null) => {
    const params = new URLSearchParams({ profile_id: profileId, scenario });
    if (subnet) params.set("subnet", subnet);
    return apiRequest<TopologyDesignDraft>(`/api/v1/lab/topology-design-draft?${params.toString()}`);
  },
  saveTopologyDesignDraft: (payload: TopologyDesignDraftWrite) =>
    apiRequest<TopologyDesignDraft>("/api/v1/lab/topology-design-draft", {
      method: "PUT",
      body: payload
    }),
  ciscoConsolePromptReadiness: () =>
    apiRequest<ProviderProbeResult>("/api/v1/providers/cisco-console/prompt-readiness", {
      method: "POST"
    }),
  probeProvider: (id: string) =>
    apiRequest<ProviderProbeResult>(`/api/v1/providers/${id}/probe`, { method: "POST" })
};
