import type { RackPlan } from "./components/RackPlanner";
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
  DeviceInventoryItem,
  DeviceInventoryWrite,
  FirmwareFileSelections,
  FirmwareFileSelectionsWrite,
  FirmwareSummary,
  HpeRaidIntent,
  HpeRaidIntentWrite,
  HpeRaidPlanPreview,
  HpeStorageDiscovery,
  HpeVsanReadiness,
  IloAccessSettings,
  InventoryRun,
  IloAccessSettingsWrite,
  IloBaselinePreview,
  IloBaselineReadiness,
  IloDiscoveredSettings,
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
  if (response.status === 500 && text.trim().toLowerCase() === "internal server error") {
    return "The Lab Builder backend is unavailable. Reconnect it, then try again.";
  }
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

export type KitReport = {
  id: string; name: string; profile_id: string; captured_at: string; rack_revision: number; limitations: string;
  equipment: Array<{name: string; device_id: string | null; model: string; position: number; host: string | null; connection: string; checked_at: string | null; versions: Array<{component: string; version: string}>; firmware_assessment?: FirmwareAssessment}>;
  activity: Array<{id: string; at: string; action: string; from_status: string | null; to_status: string | null}>;
  firmware_package?: FirmwarePackage | null;
  firmware_package_current?: boolean;
};

export type FirmwarePackage = {path:string; file_name:string; size_bytes:number; modified_ns:string; volume_label:string; release_hint:string|null; generation_hints:string[]; manifest_files:string[]; status:string; validation_note:string};
export type FirmwarePackageSource = {root:string; host_root:string|null; folder:string; folders:Array<{name:string;path:string}>; files:Array<{name:string;path:string;size_bytes:number}>; warning:string|null; download_url:string; documentation_url:string; selected:FirmwarePackage|null; selection_current:boolean};

export type FirmwareAssessment = {
  status: string; reason: string; detected_model?: string; planned_model?: string;
  identity_mismatch?: boolean; rom_family?: string; package_release?: string;
  checked_at?: string; limitations?: string;
  health_review?: HardwareHealthReview;
  /** Last read kept for display only when too old to plan from. */
  last_read?: {checked_at:string;drives:DiskPreparation["drives"];volumes:DiskPreparation["volumes"]} | null;
  rows: Array<{component:string;installed:string|null;target:string|null;status:string;reason:string;files:string[];health?:string;group?:string}>;
};

export type HardwareHealthReview = {
  diagnostic_log?: {entries:Array<{Id?:string;Message?:string;Severity?:string;Created?:string;HpeRecommendedAction?:string;HpeSeverity?:string;HpeUpdated?:string;HpeUserAction?:string;Repaired?:boolean}>;message:string;complete:boolean}|null;
  current:boolean; checked_at:string|null; review_token:string; unacknowledged:number;
  message:string; refresh_required:string|null;
  issues:Array<{id:string;title:string;group:string;health:string;location:string;details:string[];next_step:string;
    facts:Record<string,string|number>;reasons:string[];acknowledged_at:string|null}>;
};
export type FirmwareUpgradeReview = {
  review_token:string;server:string;host:string|null;model:string|null;package_file:string|null;
  updates:FirmwareAssessment["rows"];unassessed:number;health_review:HardwareHealthReview;
  blockers:string[];can_save_review:boolean;apply_enabled:false;execution_method:string;vendor_url:string;
};

export type DiskPreparation = {
  name:string;model:string;host:string;current:boolean;checked_at:string;inventory_token:string;
  controllers:Array<{id:string;model:string;health:string;firmware:string}>;
  drives:Array<{id:string;location:string;model:string;capacity_bytes:number;media?:string;health:string;firmware:string;eligible:boolean;presence?:string;label?:string;reported_health?:string;explanation?:string}>;
  volumes:Array<{id:string;name:string;raid:string;capacity_bytes:number;bays?:string[]}>;
  blockers:string[];health_issues:string[];boot_mirror_matches:boolean;saved_intent:{volumes:Array<{drive_bays:string[];spare_bays?:string[];spare_rebuild_mode?:string|null;bootable:boolean;raid_level:string}>;wipe_existing_logical_drives:boolean};cleanup_method:string;
  health_review?: HardwareHealthReview;
  /** Last read kept for display only when too old to plan from. */
  last_read?: {checked_at:string;drives:DiskPreparation["drives"];volumes:DiskPreparation["volumes"]} | null;
};

export type StorageOperation = "clear" | "create" | "reset" | "sanitize";
export type EraseMethod = "SanitizeRestrictedOverwrite" | "SanitizeRestrictedBlockErase" | "OnePass";
export type EraseOptions = {
  models:string[];controllers:string[];current:boolean;
  options:Array<{id:string;label:string;speed:string;protection:string;selectable:boolean;status:string;reason:string}>;
  reset:{label:string;speed:string;protection:string;reason:string};
};
export type EraseDrive = {path?:string;bay:string;identity:string;model:string;firmware?:string;capacity_bytes:number;media:string;erase_pattern?:EraseMethod|null;role?:string;blockers?:string[];status?:string;percent?:number|null;progress_note?:string};
export function eraseMethodLabel(method?:EraseMethod|null):string {
  return method === "SanitizeRestrictedBlockErase" ? "Block erase (device sanitize)" :
    method === "SanitizeRestrictedOverwrite" ? "Overwrite (device sanitize)" :
    method === "OnePass" ? "Controller overwrite (not a purge)" : "Not determined";
}
export type RaidRebuildReview = {
  preview_id:string;operation:StorageOperation;name:string;host:string;controller:string;
  method:string;path:string;payload:Record<string,unknown>;volumes:DiskPreparation["volumes"];
  empty_bays:string[];warnings:string[];blockers:string[];apply_enabled:boolean;confirmation:string;expires_at:string;
  drives?:EraseDrive[];erase_pattern?:EraseMethod|"auto";scope_note?:string;assurance?:string;
  power?:string;arrays_present?:boolean;authorization_expires_at?:string|null;
  preparation?:{raw_bays:string[];assigned_bays:string[];support_review_bays:string[]};
  raw_preparation?:{assignment_verified:boolean;controller_mode?:string|null;blockers:string[];reference:string}|null;
  erase_options?:EraseOptions;
  capability_context?:Record<string,string>;
};

export type RaidOperationStatus = {
  status: "not_started" | "staged" | "waiting" | "uncertain" | "verified" | "needs_attention" | "failed";
  message: string; active: boolean; attempt_id?: string; operation?: StorageOperation;
  sanitization?:{drives:EraseDrive[];checked_at:string;message:string;power?:string;pending_changes?:boolean;controller_errors?:string[]}|null;
  erase_scope?:EraseDrive[]|null;
  erase_recovery?:{rejected_method:string;message:string}|null;
  submitted_at?: string; boot_started_at?: string | null; verified_at?: string | null; boot_blockers?: string[];
};
export type StorageDiagnosis = {
  name:string; checked_at:string; status:string; summary:string; controller:string; controller_health:string;
  backup_power:string; battery_health:string; detected_drives:number; healthy_drives:number; volume_count:number;
  pending_changes:boolean; log_complete:boolean; log_note:string; repair_available:false; raid_verification:string;
  findings:Array<{id:string;title:string;source:string;detail:string;evidence:string[];action:string}>;
  volumes:Array<{raid:string;members:string[];spares:string[]}>; recovery_steps:string[];
};
export type RaidBootReview = {
  preview_id: string; name: string; operation: StorageOperation; confirmation: string;
  pending_payload: Record<string, unknown>; path: string; method: string; payload: Record<string, unknown>;
  blockers: string[]; apply_enabled: boolean; expires_at: string;
};

export type EsxiIso = { path: string; name: string; size_bytes: number; version: string | null; hpe_image: boolean };
export type EsxiMedia = { root_ready: boolean; isos: EsxiIso[]; folder: string;
  selected: { path: string; name: string; size_bytes: number; selected_at: string; present: boolean } | null };
export type EsxiBootVolume = { name: string; bays: string[]; capacity_bytes: number; disk_id: string | null; read_at: string | null };
export type EsxiDataVolume = EsxiBootVolume & { raid: string };
export type WindowsImage = { path: string; name: string; folder?: string; size_bytes: number; kind: "ova" | "ovf"; missing: string[]; windows: boolean };
export type WindowsSetup = { images: WindowsImage[]; image: string | null; vm_name: string | null; datastore: string | null; network: string | null; saved_at: string | null;
  host: { address: string | null; datastores: Array<{ name: string; capacity: number; free: number }>; networks: string[]; problem: string | null; default_datastore: string | null } };
export type WindowsReview = { ready: boolean; blockers: string[]; permission: string[]; image?: string; size_bytes?: number; vm_name?: string; datastore?: string; network?: string; address?: string; free_bytes?: number | null };
export type WindowsStatus = { state: "not_started" | "running" | "needs_attention" | "verified" | "failed"; active: boolean; message: string; run_id?: string; vm_name?: string; datastore?: string;
  network?: string; image?: string; esxi_address?: string; started_at?: string; address?: string | null; hostname?: string | null; guest_os?: string | null;
  last_check?: { checked_at: string; power: string | null; tools: string | null; address: string | null } | null;
  phases: Array<{ phase: "import" | "power" | "verify"; label: string; state: "todo" | "sent" | "ok" | "failed" | "uncertain"; message: string | null }> };
export type AcceptanceCheck = { name: string; ok: boolean; detail?: string | null };
export type AcceptanceStatus = { state: "not_started" | "running" | "needs_attention" | "verified" | "failed"; active: boolean; message: string; run_id?: string; vm?: string; lookup?: string;
  started_at?: string; finished_at?: string; default_lookup?: string | null; signin: { username: string | null; password_saved: boolean };
  phases: Array<{ phase: "outside" | "inside" | "reboot" | "after"; label: string; state: "todo" | "running" | "ok" | "failed" | "uncertain"; message: string | null; checks: AcceptanceCheck[] }> };
const winPath = (id: string, device: string, action: string) => `/api/v1/rack-plans/${encodeURIComponent(id)}/windows/${action}?device_id=${encodeURIComponent(device)}`;
export type SwitchCheck = { status: "ok" | "unreachable" | "sign_in_failed" | "blocked" | "failed"; message: string; host: string | null; hostname: string | null; model: string | null; version: string | null; serial: string | null; port_count: number | null; uptime: string | null; checked_at: string | null };
export type SwitchAccess = { device_id: string; host: string | null; username: string | null; username_configured: boolean; password_configured: boolean; enable_password_configured: boolean; updated_at: string | null; last_check: SwitchCheck | null; console?: { port: string | null; baud: number | null; last: SwitchConsoleRead | null } };
export type SwitchConsolePort = { port: string; candidate_fingerprint: string; description: string; manufacturer: string; usb: boolean; hint: string; recommended: boolean; recommended_bauds: number[] };
export type SwitchConsolePorts = { helper_running: boolean; ports: SwitchConsolePort[]; bauds?: number[]; saved_port: string | null; saved_baud: number | null; problem: string | null };
export type SwitchConsoleRead = { port: string; baud: number; answered: boolean; identity_verified: boolean; prompt_state: string; state_text: string | null; model: string | null; version: string | null; message: string | null; detail?: string | null; checked_at: string };
const swPath = (device: string) => `/api/v1/devices/${encodeURIComponent(device)}/switch-access`;
export type KitJob = { id: string; resource: string; label: string; device_id: string; device_name: string; state: "running" | "needs_attention" | "done" | "stopped"; status: string; started_at: string; updated_at: string; path: string };
export type KitJobs = { running: KitJob[]; attention: KitJob[]; recent: KitJob[]; now: string };
export type DeviceIdentity = { indicator: string | null; serial: string | null; model: string | null; ilo_host?: string | null };
export type DeviceHealth = { overall: string | null; checked_at: string | null; inlet_c?: number | null; hottest?: { name: string; c: number } | null; fans_ok?: number; fans?: number; psu_ok?: number; psus?: number; problems: string[] };
export type PreflightItem = { group: string; name: string; state: "ok" | "warn" | "fail"; detail: string; fix: string | null };
export type PreflightResult = { state: "ok" | "warn" | "fail"; checked_at: string; items: PreflightItem[] };
export type CableRow = { server_id: string; server: string; server_port: string; mac: string; switch_id: string; switch: string; switch_port: string; vlan: string };
export type CableMapResult = { state: string; checked_at?: string; problems?: string[]; message?: string; cables: CableRow[];
  unmatched_server_ports: Array<{ server: string; server_port: string; note: string }>; other_switch_ports: Array<{ switch: string; switch_port: string; vlan: string; note: string }> };
export type Handover = { kit: string; generated_at: string; network: { subnet: string | null; gateway: string | null; dns: string[] | null; domain: string | null };
  servers: Array<{ name: string; model: string; observed_at?: string | null; ilo: { address: string | null; firmware: string | null; bios: string | null; checked_at: string | null }; health: DeviceHealth | null;
    boot_disks: { bays: string[]; capacity_bytes: number } | null; data_disks: { raid: string | null; bays: string[]; capacity_bytes: number } | null;
    esxi: { state: string; host_name: string | null; address: string | null; datastore: { name: string } | null; verified_at: string | null };
    windows: { state: string; vm: string | null; address: string | null; computer: string | null; os: string | null; verified_at?: string | null };
    acceptance?: { state: string; finished_at?: string | null; lookup?: string | null } }>;
  switches: Array<{ name: string; address: string | null; username: string | null; model: string; software: string | null; serial: string | null; checked_at: string | null; check_status: string | null; console: string | null;
    config?: { before: string | null; after: string | null; diff: string[]; at: string; outcome: string | null } | null }>;
  cables: CableMapResult | null; verified: BuildHistoryEntry[] };
export type SwitchResetStatus = { state: "not_started" | "running" | "needs_attention" | "verified" | "failed"; active: boolean; message: string; run_id?: string; name: string;
  console_port?: string; step?: string | null; phases: Array<{ phase: "erase" | "restart"; label: string; state: "todo" | "sent" | "ok" | "failed" | "uncertain"; message: string | null }> };
export type SwitchResetReview = { ready: boolean; blockers: string[]; permission: string[]; name: string; phrase: string; console_port: string | null; baud: number | null;
  model: string | null; serial: string | null; prompt_state: string | null; erases: string[] };
export type KitReset = { enabled: boolean; forget_phrase: string; removed?: string[];
  servers: Array<{ device_id: string; name: string; model: string; erases: string[]; signins: string[] }>;
  switches: Array<{ device_id: string; name: string; model: string; console_port: string | null; erases: string[]; reset: SwitchResetStatus; signins: string[] }> };
const resetPath = (id: string, action: string, device?: string) => `/api/v1/rack-plans/${encodeURIComponent(id)}/${action}${device ? `?device_id=${encodeURIComponent(device)}` : ""}`;
export const resetApi = {
  summary: (id: string) => apiRequest<KitReset>(resetPath(id, "reset")),
  forget: (id: string, confirmation: string) => apiRequest<KitReset>(resetPath(id, "reset/forget-signins"), { method: "POST", body: { confirmation } }),
  switchReview: (id: string, device: string) => apiRequest<SwitchResetReview>(resetPath(id, "switch-reset/review", device), { method: "POST", timeoutMs: 60000 }),
  switchStatus: (id: string, device: string) => apiRequest<SwitchResetStatus>(resetPath(id, "switch-reset/status", device)),
  switchStart: (id: string, device: string, confirmation: string) => apiRequest<SwitchResetStatus>(resetPath(id, "switch-reset/start", device), { method: "POST", body: { confirmation }, timeoutMs: 60000 }),
  switchAdvance: (id: string, device: string) => apiRequest<SwitchResetStatus>(resetPath(id, "switch-reset/advance", device), { method: "POST" }),
  switchClose: (id: string, device: string) => apiRequest<SwitchResetStatus>(resetPath(id, "switch-reset/close", device), { method: "POST" }),
};
export type TraceHop = { name: string; detail: string | null; state: "proven" | "saved" | "unknown"; source: string; at: string | null; prove: string | null };
export type TracePath = { device_id: string; name: string; hops: TraceHop[]; stops_at: number | null };
export type AskRow = { where: string; at: string | null; message: string; outcome?: string | null };
export type AskAnswer = { question: string; terms: string[]; plan: AskRow[]; changes: AskRow[]; checks: AskRow[]; summary: string };
export const insightApi = {
  trace: (id: string) => apiRequest<{ servers: TracePath[]; cables_read_at: string | null }>(`/api/v1/rack-plans/${encodeURIComponent(id)}/trace`),
  ask: (q: string) => apiRequest<AskAnswer>(`/api/v1/ask?q=${encodeURIComponent(q)}`),
};
export const jobsApi = {
  handover: (profileId: string) => apiRequest<Handover>(`/api/v1/rack-plans/${encodeURIComponent(profileId)}/handover`, { timeoutMs: 60000 }),
  recipe: (profileId: string) => apiRequest<Record<string, unknown>>(`/api/v1/rack-plans/${encodeURIComponent(profileId)}/recipe`),
  applyRecipe: (name: string, recipe: Record<string, unknown>) => apiRequest<{ kit: { id: string; name: string }; todo: string[] }>("/api/v1/recipes/apply", { method: "POST", body: { name, recipe }, timeoutMs: 60000 }),
  cableMap: (profileId: string) => apiRequest<CableMapResult>(`/api/v1/rack-plans/${encodeURIComponent(profileId)}/cable-map`),
  readCableMap: (profileId: string) => apiRequest<CableMapResult>(`/api/v1/rack-plans/${encodeURIComponent(profileId)}/cable-map/read`, { method: "POST", timeoutMs: 120000 }),
  preflight: (profileId: string) => apiRequest<PreflightResult>(`/api/v1/rack-plans/${encodeURIComponent(profileId)}/preflight`, { timeoutMs: 120000 }),
  health: (device: string) => apiRequest<DeviceHealth>(`/api/v1/devices/${encodeURIComponent(device)}/health`),
  list: () => apiRequest<KitJobs>("/api/v1/jobs"),
  identity: (device: string) => apiRequest<DeviceIdentity>(`/api/v1/devices/${encodeURIComponent(device)}/identity`, { timeoutMs: 30000 }),
  identify: (device: string, on: boolean) => apiRequest<DeviceIdentity>(`/api/v1/devices/${encodeURIComponent(device)}/identify`, { method: "POST", body: { on }, timeoutMs: 30000 }),
};
export type BuildHistoryEntry = { id: string; at: string; area: string; message: string; outcome: "ok" | "failed" | "attention" | "info"; actor: string };
export type SwitchSetupSettings = { hostname: string; domain: string; vlan: number; mode: "dhcp" | "static"; address: string | null; prefix: number | null; gateway: string | null; save: boolean; uplink?: string; uplink_mode?: "access" | "trunk" };
export type SwitchSetup = { settings: SwitchSetupSettings | null; defaults: SwitchSetupSettings & { username: string }; username: string | null; password_configured: boolean; enable_password_configured: boolean; console: { port: string | null; baud: number | null; last: SwitchConsoleRead | null } };
export type SwitchSetupReview = { ready: boolean; blockers: string[]; permission: string[]; notes?: string[]; replace_needed?: boolean; console_port?: string | null; baud?: number | null; prompt_state?: string | null; hostname?: string; vlan?: number; mode?: string; address?: string | null; prefix?: number | null; gateway?: string | null; username?: string; save?: boolean; preview?: string[] };
export type SwitchSetupStatus = { state: "not_started" | "running" | "needs_attention" | "verified" | "failed"; active: boolean; message: string; run_id?: string; hostname?: string; console_port?: string; address?: string | null; saved?: boolean | null; sent?: string[] | null; step?: string | null; model?: string | null; version?: string | null; phases: Array<{ phase: string; label: string; state: string; message: string | null }> };
const swSetupPath = (id: string, device: string, action: string) => `/api/v1/rack-plans/${encodeURIComponent(id)}/switch-setup/${action}?device_id=${encodeURIComponent(device)}`;
export const switchSetupApi = {
  setup: (id: string, device: string) => apiRequest<SwitchSetup>(swSetupPath(id, device, "setup")),
  save: (id: string, device: string, body: SwitchSetupSettings & { username: string; password?: string; enable_password?: string }) => apiRequest<SwitchSetup>(swSetupPath(id, device, "setup"), { method: "PUT", body }),
  review: (id: string, device: string) => apiRequest<SwitchSetupReview>(swSetupPath(id, device, "review"), { method: "POST", timeoutMs: 60000 }),
  status: (id: string, device: string) => apiRequest<SwitchSetupStatus>(swSetupPath(id, device, "status")),
  start: (id: string, device: string, replaceExisting = false) => apiRequest<SwitchSetupStatus>(swSetupPath(id, device, "start"), { method: "POST", body: { replace_existing: replaceExisting }, timeoutMs: 60000 }),
  advance: (id: string, device: string) => apiRequest<SwitchSetupStatus>(swSetupPath(id, device, "advance"), { method: "POST", timeoutMs: 120000 }),
  close: (id: string, device: string) => apiRequest<SwitchSetupStatus>(swSetupPath(id, device, "close"), { method: "POST" }),
};
export const switchApi = {
  read: (device: string) => apiRequest<SwitchAccess>(swPath(device)),
  save: (device: string, body: { host?: string; username?: string; password?: string; enable_password?: string }) => apiRequest<SwitchAccess>(swPath(device), { method: "PUT", body }),
  check: (device: string) => apiRequest<SwitchCheck>(`${swPath(device)}/check`, { method: "POST", timeoutMs: 120000 }),
  consolePorts: (device: string) => apiRequest<SwitchConsolePorts>(`/api/v1/devices/${encodeURIComponent(device)}/switch-console/ports`, { timeoutMs: 30000 }),
  address: (device: string) => apiRequest<{ state: string; message: string; address: string | null; addresses: Array<{ interface: string; address: string; method: string | null; status: string | null }> }>(`/api/v1/devices/${encodeURIComponent(device)}/switch-console/address`, { method: "POST", timeoutMs: 90000 }),
  identify: (device: string, body: { port: string; baud: number; candidate_fingerprint: string }) => apiRequest<SwitchConsoleRead>(`/api/v1/devices/${encodeURIComponent(device)}/switch-console/identify`, { method: "POST", body, timeoutMs: 120000 }),
};

export const windowsApi = {
  setup: (id: string, device: string) => apiRequest<WindowsSetup>(winPath(id, device, "setup"), { timeoutMs: 60000 }),
  save: (id: string, device: string, body: { image: string; vm_name: string; datastore: string; network: string }) => apiRequest<WindowsSetup>(winPath(id, device, "setup"), { method: "PUT", body, timeoutMs: 60000 }),
  review: (id: string, device: string) => apiRequest<WindowsReview>(winPath(id, device, "review"), { method: "POST", timeoutMs: 120000 }),
  status: (id: string, device: string) => apiRequest<WindowsStatus>(winPath(id, device, "status")),
  start: (id: string, device: string) => apiRequest<WindowsStatus>(winPath(id, device, "start"), { method: "POST", timeoutMs: 120000 }),
  advance: (id: string, device: string) => apiRequest<WindowsStatus>(winPath(id, device, "advance"), { method: "POST", timeoutMs: 120000 }),
  close: (id: string, device: string) => apiRequest<WindowsStatus>(winPath(id, device, "close"), { method: "POST" }),
  signin: (id: string, device: string) => apiRequest<{ username: string | null; password_saved: boolean }>(winPath(id, device, "guest-signin")),
  saveSignin: (id: string, device: string, body: { username: string; password: string }) => apiRequest<{ username: string | null; password_saved: boolean }>(winPath(id, device, "guest-signin"), { method: "PUT", body }),
  test: (id: string, device: string) => apiRequest<AcceptanceStatus>(winPath(id, device, "acceptance")),
  testStart: (id: string, device: string, name: string) => apiRequest<AcceptanceStatus>(winPath(id, device, "acceptance/start"), { method: "POST", body: { name: name || null }, timeoutMs: 60000 }),
  testAdvance: (id: string, device: string) => apiRequest<AcceptanceStatus>(winPath(id, device, "acceptance/advance"), { method: "POST", timeoutMs: 180000 }),
  testClose: (id: string, device: string) => apiRequest<AcceptanceStatus>(winPath(id, device, "acceptance/close"), { method: "POST" }),
};
export type PartsUpdatePart = { id: string; component: string; item?: string; from: string; to: string; file: string; method: "ilo" | "bios"; reset?: boolean; minutes?: number; rom?: boolean; state?: "waiting" | "installing" | "installed" | "done" | "failed" };
export type PartsUpdatePlan = { review_id: string; digest: string; package: string; parts: PartsUpdatePart[]; elsewhere: Array<{ component: string; from: string; to: string; reason: string }>;
  phases: Array<{ kind: string; part?: string }>; restarts: number; minutes: number; power: string | null; blockers: string[]; expires_at: string };
export type PartsUpdateStatus = { state: "not_started" | "running" | "needs_attention" | "verified" | "failed"; active: boolean; run_id?: string; message: string; started_at?: string;
  parts: PartsUpdatePart[]; phases: Array<{ index: number; kind: string; label: string; state: "todo" | "sent" | "ok" | "failed" | "uncertain"; message: string | null }> };
const partsPath = (id: string, device: string, action: string) => `/api/v1/rack-plans/${encodeURIComponent(id)}/parts-update/${action}?device_id=${encodeURIComponent(device)}`;
export const partsUpdateApi = {
  status: (id: string, device: string) => apiRequest<PartsUpdateStatus>(partsPath(id, device, "status")),
  review: (id: string, device: string) => apiRequest<PartsUpdatePlan>(partsPath(id, device, "review"), { method: "POST", timeoutMs: 180000 }),
  start: (id: string, device: string, reviewId: string) => apiRequest<PartsUpdateStatus>(partsPath(id, device, "start"), { method: "POST", body: { review_id: reviewId }, timeoutMs: 1200000 }),
  advance: (id: string, device: string) => apiRequest<PartsUpdateStatus>(partsPath(id, device, "advance"), { method: "POST", timeoutMs: 1200000 }),
  close: (id: string, device: string) => apiRequest<PartsUpdateStatus>(partsPath(id, device, "close"), { method: "POST" }),
};
export type EsxiNetworkPort = { mac: string; adapter: string; location: string; port: number; link: boolean; speed_mbps: number | null; vmnic: string | null };
export type EsxiNetworkPorts = { available: boolean; ports: EsxiNetworkPort[]; suggested: string | null; message: string | null };
export type EsxiSettings = {
  hostname: string | null; addressing: "static" | "dhcp"; management_ip: string | null; vlan_id: number; management_nic: string | null;
  datastore_name: string; password_set: boolean; signin_ready: boolean; saved_at: string | null; data_volume: EsxiDataVolume | null;
  kit: { profile_id: string; profile_version: number; saved_profile: boolean; subnet: string | null; gateway: string | null; dns: string[];
    ntp_enabled: boolean; ntp: string[]; domain_name: string | null; esxi_management: string | null; single_server_local: boolean };
  boot_volume: EsxiBootVolume | null;
};
export type EsxiInstallerBuild = { status: "blocked" | "not_built" | "ready" | "stale"; blockers: string[];
  built: { iso_name: string; iso_sha256: string; size_bytes: number; built_at: string; install_disk_id: string; hostname: string; management_ip: string } | null };
export type EsxiInstallStatus = {
  state: "not_started" | "starting" | "installing" | "needs_attention" | "reachable" | "verified" | "closed"; active: boolean; message: string;
  phases: Record<string, string>; phase?: string; run_id?: string; started_at?: string; verified_at?: string; ejected?: boolean | null; late?: boolean; can_check_installed?: boolean;
  management_ip?: string | null; addressing?: "static" | "dhcp"; hostname?: string; iso_name?: string; datastore_name?: string | null;
  last_check?: { answering: boolean; detail: string; checked_at: string; address?: string | null } | null;
  verification?: { passed: boolean; address: string; checked_at: string; problem?: string;
    checks: Array<{ name: string; ok: boolean; expected: string; found: string }> } | null;
  datastore?: { name: string; disk: string } | null;
};

export const api = {
  eraseOptions: (id:string,device:string) => apiRequest<EraseOptions>(`/api/v1/rack-plans/${encodeURIComponent(id)}/raid-rebuild/erase-options?device_id=${encodeURIComponent(device)}`),
  sanitizationReport: (id:string,device:string) => apiRequest<{status:string;message:string;[key:string]:unknown}>(`/api/v1/rack-plans/${encodeURIComponent(id)}/raid-rebuild/sanitization-report?device_id=${encodeURIComponent(device)}`),
  resetPowerState: (profile:string,device:string) => apiRequest<{power:string;pending_changes:boolean}>(`/api/v1/rack-plans/${encodeURIComponent(profile)}/raid-rebuild/power-state?device_id=${encodeURIComponent(device)}`,{timeoutMs:180000}),
  previewResetShutdown: (profile:string,device:string,force:boolean) => apiRequest<{preview_id:string;name:string;force:boolean;confirmation:string;blockers:string[];apply_enabled:boolean;payload:{ResetType:string}}>(`/api/v1/rack-plans/${encodeURIComponent(profile)}/raid-rebuild/shutdown-preview?device_id=${encodeURIComponent(device)}`,{method:'POST',body:{force},timeoutMs:180000}),
  applyResetShutdown: (profile:string,device:string,preview_id:string,confirmation:string) => apiRequest<{message:string}>(`/api/v1/rack-plans/${encodeURIComponent(profile)}/raid-rebuild/shutdown?device_id=${encodeURIComponent(device)}`,{method:'POST',body:{preview_id,confirmation,downtime_confirmed:true,data_loss_confirmed:true},timeoutMs:180000}),
  startSsaDiagnostic: (device:string) => apiRequest<{job_id:string}>(`/api/v1/devices/${encodeURIComponent(device)}/maintenance-diagnostics`, {method:'POST'}),
  readSsaDiagnostic: (device:string, job:string) => apiRequest<{status:string;result?:{status:string;message:string;checked_at:string;reports:string[]}}>(`/api/v1/devices/${encodeURIComponent(device)}/maintenance-diagnostics/${encodeURIComponent(job)}`),
  diagnoseStorage: (id:string,device:string) => apiRequest<StorageDiagnosis>(`/api/v1/rack-plans/${encodeURIComponent(id)}/raid-rebuild/diagnose?device_id=${encodeURIComponent(device)}`, {method:"POST",timeoutMs:180000}),
  raidOperationStatus: (id:string,device:string) => apiRequest<RaidOperationStatus>(`/api/v1/rack-plans/${encodeURIComponent(id)}/raid-rebuild/status?device_id=${encodeURIComponent(device)}`),
  previewRaidBoot: (id:string,device:string) => apiRequest<RaidBootReview>(`/api/v1/rack-plans/${encodeURIComponent(id)}/raid-rebuild/boot-preview?device_id=${encodeURIComponent(device)}`, {method:"POST",timeoutMs:120000}),
  startRaidBoot: (id:string,device:string,body:{preview_id:string;confirmation:string;pending_changes_reviewed:true;data_loss_confirmed:true;maintenance_confirmed:true}) => apiRequest<{status:string;message:string}>(`/api/v1/rack-plans/${encodeURIComponent(id)}/raid-rebuild/boot?device_id=${encodeURIComponent(device)}`, {method:"POST",body,timeoutMs:120000}),
  verifyRaidRebuild: (id:string,device:string) => apiRequest<{status:string;message:string;verified:boolean}>(`/api/v1/rack-plans/${encodeURIComponent(id)}/raid-rebuild/verify?device_id=${encodeURIComponent(device)}`, {method:"POST",timeoutMs:120000}),
  previewRaidRebuild: (id:string,device:string,operation:StorageOperation,erase_pattern?:EraseMethod|"auto") => apiRequest<RaidRebuildReview>(`/api/v1/rack-plans/${encodeURIComponent(id)}/raid-rebuild/preview?device_id=${encodeURIComponent(device)}`, {method:"POST",body:{operation,...(erase_pattern?{erase_pattern}:{})},timeoutMs:180000}),
  authorizeSanitization: (id:string,device:string,body:{preview_id:string;confirmation:string;vendor_support_reviewed:true;sources:Record<string,string>}) =>
    apiRequest<{expires_at:string;message:string}>(`/api/v1/rack-plans/${encodeURIComponent(id)}/raid-rebuild/sanitize-authorization?device_id=${encodeURIComponent(device)}`, {method:"POST",body,timeoutMs:180000}),
  applyRaidRebuild: (id:string,device:string,body:{preview_id:string;confirmation:string;data_loss_confirmed:true;backups_confirmed:true;health_reviewed:true;firmware_reviewed:true;empty_bays_confirmed:string[];physical_erase_confirmed?:boolean}) => apiRequest<{status:string;message:string;verified:false}>(`/api/v1/rack-plans/${encodeURIComponent(id)}/raid-rebuild/apply?device_id=${encodeURIComponent(device)}`, {method:"POST",body,timeoutMs:180000}),
  acknowledgeHealth: (id:string,device:string,reviewToken:string,issueId:string) => apiRequest<HardwareHealthReview>(`/api/v1/rack-plans/${encodeURIComponent(id)}/health-acknowledgements?device_id=${encodeURIComponent(device)}`, {method:"POST",body:{review_token:reviewToken,issue_id:issueId}}),
  firmwareUpgradeReview: (id:string,device:string) => apiRequest<FirmwareUpgradeReview>(`/api/v1/rack-plans/${encodeURIComponent(id)}/firmware-upgrade-review?device_id=${encodeURIComponent(device)}`),
  saveFirmwareUpgradeReview: (id:string,device:string,reviewToken:string) => apiRequest<{status:string;message:string;apply_enabled:false}>(`/api/v1/rack-plans/${encodeURIComponent(id)}/firmware-upgrade-review?device_id=${encodeURIComponent(device)}`, {method:"POST",body:{review_token:reviewToken}}),
  esxiMedia: (id: string, device: string) => apiRequest<EsxiMedia>(`/api/v1/rack-plans/${encodeURIComponent(id)}/esxi/media?device_id=${encodeURIComponent(device)}`),
  chooseEsxiMedia: (id: string, device: string, path: string) => apiRequest<EsxiMedia>(`/api/v1/rack-plans/${encodeURIComponent(id)}/esxi/media?device_id=${encodeURIComponent(device)}`, { method: "POST", body: { path }, timeoutMs: 120000 }),
  esxiNetworkPorts: (id: string, device: string) => apiRequest<EsxiNetworkPorts>(`/api/v1/rack-plans/${encodeURIComponent(id)}/esxi/network-ports?device_id=${encodeURIComponent(device)}`, { timeoutMs: 60000 }),
  esxiSettings: (id: string, device: string) => apiRequest<EsxiSettings>(`/api/v1/rack-plans/${encodeURIComponent(id)}/esxi/settings?device_id=${encodeURIComponent(device)}`),
  saveEsxiSettings: (id: string, device: string, body: { hostname: string; addressing: "static" | "dhcp"; management_ip: string | null; vlan_id: number; management_nic: string; datastore_name: string; root_password?: string | null }) =>
    apiRequest<EsxiSettings>(`/api/v1/rack-plans/${encodeURIComponent(id)}/esxi/settings?device_id=${encodeURIComponent(device)}`, { method: "PUT", body }),
  esxiInstaller: (id: string, device: string) => apiRequest<EsxiInstallerBuild>(`/api/v1/rack-plans/${encodeURIComponent(id)}/esxi/installer?device_id=${encodeURIComponent(device)}`),
  buildEsxiInstaller: (id: string, device: string) => apiRequest<EsxiInstallerBuild>(`/api/v1/rack-plans/${encodeURIComponent(id)}/esxi/installer?device_id=${encodeURIComponent(device)}`, { method: "POST", timeoutMs: 1800000 }),
  esxiInstall: (id: string, device: string) => apiRequest<EsxiInstallStatus>(`/api/v1/rack-plans/${encodeURIComponent(id)}/esxi/install?device_id=${encodeURIComponent(device)}`),
  startEsxiInstall: (id: string, device: string) => apiRequest<EsxiInstallStatus>(`/api/v1/rack-plans/${encodeURIComponent(id)}/esxi/install?device_id=${encodeURIComponent(device)}`, { method: "POST", timeoutMs: 600000 }),
  checkEsxiInstall: (id: string, device: string, address?: string) => apiRequest<EsxiInstallStatus>(`/api/v1/rack-plans/${encodeURIComponent(id)}/esxi/install/check?device_id=${encodeURIComponent(device)}`, { method: "POST", timeoutMs: 600000, ...(address ? { body: { address } } : {}) }),
  resumeEsxiInstall: (id: string, device: string) => apiRequest<EsxiInstallStatus>(`/api/v1/rack-plans/${encodeURIComponent(id)}/esxi/install/resume?device_id=${encodeURIComponent(device)}`, { method: "POST", timeoutMs: 600000 }),
  closeEsxiInstall: (id: string, device: string) => apiRequest<EsxiInstallStatus>(`/api/v1/rack-plans/${encodeURIComponent(id)}/esxi/install/close?device_id=${encodeURIComponent(device)}`, { method: "POST" }),
  diskPreparation: (id:string,device:string) => apiRequest<DiskPreparation>(`/api/v1/rack-plans/${encodeURIComponent(id)}/disk-preparation?device_id=${encodeURIComponent(device)}`),
  saveDiskPreparation: (id:string,device:string,body:{inventory_token:string;boot_drive_ids:string[];remove_existing_volumes:boolean;data_loss_reviewed:boolean;data_drive_ids?:string[];data_raid?:string;spare_drive_ids?:string[];spare_for?:"boot"|"data"}) => apiRequest<{status:string;message:string}>(`/api/v1/rack-plans/${encodeURIComponent(id)}/disk-preparation?device_id=${encodeURIComponent(device)}`, {method:"POST",body}),
  firmwareAssessment: (id:string, deviceId:string) => apiRequest<FirmwareAssessment>(`/api/v1/rack-plans/${encodeURIComponent(id)}/firmware-assessment?device_id=${encodeURIComponent(deviceId)}`, {timeoutMs:120000}),
  uploadMedia: (id:string, folder:string, file:File, progress:(percent:number)=>void, kind:"iso"|"vm"="iso") => {
    const xhr = new XMLHttpRequest();
    const promise = new Promise<{name:string;path:string;size_bytes:number}>((resolve,reject)=>{
      const query = new URLSearchParams({folder,name:file.name,size:String(file.size),kind});
      xhr.open("POST",`${API_BASE}/api/v1/rack-plans/${encodeURIComponent(id)}/media-upload?${query}`);
      xhr.setRequestHeader("Content-Type","application/octet-stream");
      xhr.setRequestHeader("X-Local-User","local-operator");
      xhr.upload.onprogress = event => {if(event.lengthComputable)progress(Math.round(event.loaded/event.total*100));};
      xhr.onerror = ()=>reject(new Error("Upload connection lost. Please retry."));
      xhr.onabort = ()=>reject(new Error("Upload cancelled."));
      xhr.onload = ()=>{
        let body;
        try{body=JSON.parse(xhr.responseText);}catch{reject(new Error("Upload failed: invalid server response."));return;}
        if(xhr.status>=200 && xhr.status<300)resolve(body);
        else reject(new Error(apiErrorMessage(body.detail ?? body)));
      };
      xhr.send(file);
    });
    return {promise,cancel:()=>xhr.abort()};
  },
  firmwarePackageSource: (id:string, folder="") => apiRequest<FirmwarePackageSource>(`/api/v1/rack-plans/${encodeURIComponent(id)}/firmware-package?folder=${encodeURIComponent(folder)}`),
  selectFirmwarePackage: (id:string, path:string) => apiRequest<FirmwarePackage>(`/api/v1/rack-plans/${encodeURIComponent(id)}/firmware-package`, {method:"POST",body:{path}, timeoutMs:120000}),
  saveKitAs: (id: string, name: string) => apiRequest<LabProfile>(`/api/v1/rack-plans/${encodeURIComponent(id)}/save-as`, {method: "POST", body: {name}}),
  renameKit: (id: string, name: string) => apiRequest<LabProfile>(`/api/v1/rack-plans/${encodeURIComponent(id)}/name`, {method: "PATCH", body: {name}}),
  kitReports: (id: string) => apiRequest<KitReport[]>(`/api/v1/rack-plans/${encodeURIComponent(id)}/reports`),
  saveKitReport: (id: string) => apiRequest<KitReport>(`/api/v1/rack-plans/${encodeURIComponent(id)}/reports`, {method: "POST"}),
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
  buildHistory: (limit = 100) => apiRequest<BuildHistoryEntry[]>(`/api/v1/build-history?limit=${limit}`),
  mediaInventory: () => apiRequest<MediaInventory>("/api/v1/media-inventory"),
  iloUpgradeReadiness: (deviceId: string) =>
    apiRequest<IloUpgradeReadiness>(`/api/v1/providers/ilo-redfish/upgrade-readiness?device_id=${encodeURIComponent(deviceId)}`),
  iloBaselinePreview: (deviceId: string) =>
    apiRequest<IloBaselinePreview>(`/api/v1/providers/hpe-ilo/baseline-preview?device_id=${encodeURIComponent(deviceId)}`),
  iloBaselineReadiness: (deviceId: string) =>
    apiRequest<IloBaselineReadiness>(`/api/v1/providers/hpe-ilo/readiness?device_id=${encodeURIComponent(deviceId)}`),
  iloSetupIntent: (deviceId: string) =>
    apiRequest<IloSetupIntent>(`/api/v1/providers/ilo-redfish/setup-intent?device_id=${encodeURIComponent(deviceId)}`),
  iloDiscoveredSettings: (deviceId: string) =>
    apiRequest<IloDiscoveredSettings>(`/api/v1/providers/ilo-redfish/discovered-settings?device_id=${encodeURIComponent(deviceId)}`),
  saveIloSetupIntent: (deviceId: string, payload: IloSetupIntentWrite) =>
    apiRequest<IloSetupIntent>(`/api/v1/providers/ilo-redfish/setup-intent?device_id=${encodeURIComponent(deviceId)}`, {
      method: "PUT",
      body: payload
    }),
  iloAccessSettings: (deviceId: string) =>
    apiRequest<IloAccessSettings>(`/api/v1/providers/ilo-redfish/access-settings?device_id=${encodeURIComponent(deviceId)}`),
  createInventoryJob: (deviceId: string) =>
    apiRequest<InventoryRun>(`/api/v1/devices/${encodeURIComponent(deviceId)}/inventory-jobs`, { method: "POST", body: {} }),
  latestInventoryJob: (deviceId: string) =>
    apiRequest<InventoryRun | null>(`/api/v1/devices/${encodeURIComponent(deviceId)}/inventory-jobs`),
  saveIloAccessSettings: (deviceId: string, payload: IloAccessSettingsWrite) =>
    apiRequest<IloAccessSettings>(`/api/v1/providers/ilo-redfish/access-settings?device_id=${encodeURIComponent(deviceId)}`, {
      method: "PUT",
      body: payload
    }),
  iloSetupPlanPreview: (deviceId: string) =>
    apiRequest<IloSetupPlanPreview>(`/api/v1/providers/ilo-redfish/setup-plan-preview?device_id=${encodeURIComponent(deviceId)}`),
  hpeStorageDiscovery: (deviceId: string) =>
    apiRequest<HpeStorageDiscovery>(`/api/v1/providers/ilo-redfish/hpe-storage-discovery?device_id=${encodeURIComponent(deviceId)}`),
  hpeVsanReadiness: (deviceId: string) =>
    apiRequest<HpeVsanReadiness>(`/api/v1/providers/ilo-redfish/vsan-readiness?device_id=${encodeURIComponent(deviceId)}`),
  hpeRaidIntent: (deviceId: string) =>
    apiRequest<HpeRaidIntent>(`/api/v1/providers/ilo-redfish/hpe-raid-intent?device_id=${encodeURIComponent(deviceId)}`),
  saveHpeRaidIntent: (deviceId: string, payload: HpeRaidIntentWrite) =>
    apiRequest<HpeRaidIntent>(`/api/v1/providers/ilo-redfish/hpe-raid-intent?device_id=${encodeURIComponent(deviceId)}`, {
      method: "PUT",
      body: payload
    }),
  hpeRaidPlanPreview: (deviceId: string) =>
    apiRequest<HpeRaidPlanPreview>(`/api/v1/providers/ilo-redfish/hpe-raid-plan-preview?device_id=${encodeURIComponent(deviceId)}`),
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
  rackPlan: (profileId: string) => apiRequest<RackPlan>(`/api/v1/rack-plans/${encodeURIComponent(profileId)}`),
  saveRackPlan: (profileId: string, payload: RackPlan) => apiRequest<RackPlan>(`/api/v1/rack-plans/${encodeURIComponent(profileId)}`, { method: "PUT", body: payload }),
  deviceInventory: () => apiRequest<DeviceInventoryItem[]>("/api/v1/device-inventory"),
  createDevice: (payload: DeviceInventoryWrite) =>
    apiRequest<DeviceInventoryItem>("/api/v1/device-inventory", { method: "POST", body: payload }),
  updateDevice: (id: string, payload: Partial<DeviceInventoryWrite>) =>
    apiRequest<DeviceInventoryItem>(`/api/v1/device-inventory/${id}`, { method: "PATCH", body: payload }),
  deleteDevice: (id: string) =>
    apiRequest<void>(`/api/v1/device-inventory/${id}`, { method: "DELETE" }),
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
  probeProvider: (id: string, deviceId?: string | null) => {
    const params = id === "ilo-redfish" && deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : "";
      return apiRequest<ProviderProbeResult>(`/api/v1/providers/${id}/probe${params}`, { method: "POST", timeoutMs:180000 });
  }
};

/* ---------- guarded execution: /firmware-execution and /drive-return-to-service ----------
 * Shapes follow backend/app/services/guarded_execution.py and guarded_operation_ledger.recorded_result. */
export type GuardedStatusName = "not_started" | "blocked" | "submitting" | "accepted" | "running" | "uncertain" | "failed" | "verified";
export type GuardedStage = { name: string; status: string; at?: string | null; detail?: string | null };
export type GuardedOperationStatus = {
  status: GuardedStatusName; operation_id?: string | null; evidence_at?: string | null;
  stages?: GuardedStage[]; next_action?: string | null; message?: string | null; blockers?: string[]; blocker_details?: BlockerDetail[];
  profile_id?: string; device_id?: string; resource?: GuardedResource;
  /** The idempotency key recorded on the operation row. Null when no row exists. */
  idempotency_key?: string | null;
  record_found?: boolean; safe_to_retry?: boolean; execution_available?: boolean;
  /** Set only when reconcile-unsent durably fenced this attempt before any dispatch. */
  dispatch_prevented?: boolean;
  resolution?: "operator_closed_unverified";
  transport?: { stage: string; upload_started: boolean; reason: string; http_status?: number; content_type?: string; json_error_present?: boolean | null };
  recorded_at?: string | null; reviewed_at?: string | null;
};
/** GET reconcile. requested_idempotency_key is only an echo of the lookup and proves nothing. */
export type GuardedReconcile = GuardedOperationStatus & { requested_idempotency_key?: string | null };
export type GuardedTarget = { device_id?: string; name?: string | null; host?: string | null; model?: string | null; serial?: string | null; controller?: string | null; fingerprint?: string | null };
export type FirmwareExecutionOperation = { order: number; component: string; current_version?: string | null; package_version?: string | null; file?: string | null; action?: string | null; blockers?: string[] };
export type DriveReturnOperation = { order: number; location: string; drive_id?: string | null; model?: string | null; current_status?: string | null; status_reasons?: string[]; action?: string | null; blockers?: string[] };
export type GuardedPreview<Op> = {
  review_token: string; expires_at: string; target: GuardedTarget; target_provenance?: string | null; evidence_at?: string | null;
  warnings?: HealthWarning[];
  component_hash?: string | null; drive_identities?: string[];
  operations: Op[]; blockers: string[]; blocker_details?: BlockerDetail[]; can_apply: boolean; confirmation_phrase: string; message?: string | null;
};
export type GuardedResource = "firmware-execution" | "drive-return-to-service";

/** Backend services/blocker_guidance.py: display-only guidance beside each plain blocker string. */
export type BlockerAction = "read_again" | "prepare_again" | "narrow_scope_firmware" | "open_connection" | "select_package" | "check_status" | "none";
export type BlockerDetail = { code: string; text: string; fix_kind: "app" | "physical" | "wait" | "vendor"; fix: string; action?: BlockerAction };

/** Thrown when the resource does not exist yet (404/501) or the backend cannot be reached. */
export class GuardedUnavailableError extends Error {
  constructor(message: string, readonly httpStatus: number | null) { super(message); this.name = "GuardedUnavailableError"; }
}

/** A known warning bound to the review: disclosed, never a blocker, never a health clearance. */
export type HealthWarning = { group: string; health: string; title: string; details?: string | null };
export type IloUpdateHealth = { scope: string; warnings: HealthWarning[]; blockers: string[]; blocker_details?: BlockerDetail[]; assessment_sha256: string; powered_supplies?: string[] };
export type FirmwareCapabilities = {
  ilo_update_health?: IloUpdateHealth;
  device_id: string; profile_id?: string; checked_at: string; manager_firmware_version?: string | null; system_health?: string | null;
  health_issues?: Array<{ group: string; health: string }>; state?: string | null; errors?: string[]; message?: string;
  inventory?: Array<{ resource_path?: string; name?: string | null; version?: string | null; updateable?: boolean | null; device_class?: string | null }>;
  identity_verified?: boolean; exact_target_only?: boolean; can_apply?: boolean; source?: string;
};
export type BridgePreparation = {
  target_version?: string;
  preparation_id: string | number; profile_id: string; device_id: string; package_selection_id: string | number;
  bridge: { source_kind?: string; path?: string; sha256?: string; size_bytes?: number; payload?: unknown; can_apply?: boolean };
  authentication: { binary_authenticated?: boolean; authentication_method?: string; signing_key_id?: string; rpm_path?: string; rpm_sha256?: string;
    binary?: { sha256?: string; size_bytes?: number }; component_sha256?: string; fwpkg_signature_verified?: boolean; metadata_authenticated?: boolean;
    applicability_verified?: boolean; can_apply?: boolean };
  blockers: string[]; can_apply: boolean;
};
export type FirmwareRecoveryPreview = {
  operation_id: string; profile_id: string; device_id: string; can_close: boolean;
  blockers: string[]; review_token: string | null; expires_at: string | null;
  confirmation_phrase: string | null; message: string; evidence_at: string | null;
};
type GuardedAction = "status" | "preview" | "apply" | "reconcile" | "reconcile-unsent" | "verify" | "capabilities" | "prepare-spp-bridge" | "recovery-preview" | "close-unverified";
async function guardedRequest<T>(profileId: string, resource: GuardedResource, action: GuardedAction, deviceId: string, body?: unknown, extra = ""): Promise<T> {
  const path = `/api/v1/rack-plans/${encodeURIComponent(profileId)}/${resource}/${action}?device_id=${encodeURIComponent(deviceId)}${extra}`;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: action === "status" || action === "reconcile" ? "GET" : "POST",
      headers: { "Content-Type": "application/json", "X-Local-User": "local-operator" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // Unreachable is "not available", never evidence of anything on the server.
    throw new GuardedUnavailableError(`The app could not reach ${path}.`, null);
  }
  if (response.status === 404 || response.status === 501) throw new GuardedUnavailableError(await apiErrorFromResponse(response), response.status);
  if (!response.ok) throw new Error(await apiErrorFromResponse(response));
  return await response.json() as T;
}

export const guardedApi = {
  recoveryPreview: (profileId: string, deviceId: string, operationId: string) =>
    guardedRequest<FirmwareRecoveryPreview>(profileId, "firmware-execution", "recovery-preview", deviceId, { operation_id: operationId }),
  closeUnverified: (profileId: string, deviceId: string, body: { operation_id: string; review_token: string; confirmation_phrase: string }) =>
    guardedRequest<GuardedOperationStatus>(profileId, "firmware-execution", "close-unverified", deviceId, body),
  status: (profileId: string, resource: GuardedResource, deviceId: string) => guardedRequest<GuardedOperationStatus>(profileId, resource, "status", deviceId),
  reconcile: (profileId: string, resource: GuardedResource, deviceId: string, idempotencyKey: string) =>
    guardedRequest<GuardedReconcile>(profileId, resource, "reconcile", deviceId, undefined, `&idempotency_key=${encodeURIComponent(idempotencyKey)}`),
  reconcileUnsent: (profileId: string, deviceId: string, body: { review_token: string; idempotency_key: string }) =>
    guardedRequest<GuardedOperationStatus>(profileId, "firmware-execution", "reconcile-unsent", deviceId, { ...body, prevent_late_dispatch: true }),
  verify: (profileId: string, deviceId: string, operationId: string) =>
    guardedRequest<GuardedOperationStatus>(profileId, "firmware-execution", "verify", deviceId, { operation_id: operationId, confirm_read_only: true }),
  capabilities: (profileId: string, deviceId: string) =>
    guardedRequest<FirmwareCapabilities>(profileId, "firmware-execution", "capabilities", deviceId, { confirm_read_only: true }),
  prepareBridge: (profileId: string, deviceId: string) =>
    guardedRequest<BridgePreparation>(profileId, "firmware-execution", "prepare-spp-bridge", deviceId, {}),
  preview: <Op,>(profileId: string, resource: GuardedResource, deviceId: string) => guardedRequest<GuardedPreview<Op>>(profileId, resource, "preview", deviceId, {}),
  apply: (profileId: string, resource: GuardedResource, deviceId: string, body: { review_token: string; confirmation_phrase: string; idempotency_key: string }) =>
    guardedRequest<GuardedOperationStatus>(profileId, resource, "apply", deviceId, body),
};

/* ---------- whole-SPP firmware update (Claude 2026-09-29 contract; Codex owns the backend) ---------- */
export type SppRestart = "none" | "ilo" | "host";
export type SppUpdateItem = { step_id: string; component: string; from: string; to: string; order: number; restarts: SppRestart; est_minutes?: number | null };
/** Mirrors backend services/spp_update_contract.py UpdatePlan. A blocked plan carries no credentials. */
export type SppUpdatePlan = {
  execution_mode?: "online" | "offline";
  plan_id: string; profile_id: string; device_id: string;
  review_token: string | null; expires_at: string; can_apply: boolean; confirmation_phrase: string | null;
  server: { name: string; model: string; manager_generation: 5 | 6 | 7 };
  package: { file: string; release: string };
  updates: SppUpdateItem[];
  effects: { host_restarts: number | null; ilo_restarts: number | null; est_total_minutes?: number | null; power_on_required: boolean };
  not_included: Array<{ component: string; reason: string }>;
  blockers: string[]; blocker_details?: BlockerDetail[]; warnings: string[];
  details?: unknown;
};
export type SppStepState = "waiting" | "installing" | "restarting" | "verifying" | "done" | "failed" | "not_started" | "uncertain";
/** Mirrors backend UpdateStatus. current_step is a step_id; active is authoritative for locking. */
export type SppUpdateStatus = {
  execution_mode?: "online" | "offline";
  profile_id: string; device_id: string; operation_id: string | null; idempotency_key: string | null;
  status: "not_started" | "running" | "waiting_restart" | "verifying" | "verified" | "failed" | "uncertain";
  steps: Array<SppUpdateItem & { state: SppStepState; started_at?: string | null; finished_at?: string | null; verified_version?: string | null }>;
  current_step: string | null; message: string; next_action: string | null; evidence_at: string | null;
  active: boolean; dispatch_prevented?: boolean;
  observed?: SppObserved | null;
};
/** Latest read-only look at the server while HPE's updater runs; explains progress, never proves it. */
export type SppObserved = {
  checked_at: string; power: string | null; post_state: string | null;
  updater_started: boolean; restarted_after_updater: boolean;
  parts: Array<{ component: string; installed: string | null; target: string; at_target: boolean }>;
  queued: string[]; updater_reported_error: boolean; waiting_for_reboot: boolean; summary: string;
};
async function sppRequest<T>(profileId: string, action: "plan" | "apply" | "status" | "reconcile" | "verify", deviceId: string, body?: unknown, attemptKey?: string): Promise<T> {
  const path = `/api/v1/rack-plans/${encodeURIComponent(profileId)}/firmware-update/${action}?device_id=${encodeURIComponent(deviceId)}${attemptKey ? `&idempotency_key=${encodeURIComponent(attemptKey)}` : ""}`;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: action === "status" ? "GET" : "POST",
      headers: { "Content-Type": "application/json", "X-Local-User": "local-operator" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new GuardedUnavailableError(`The app could not reach ${path}.`, null);
  }
  if (response.status === 404 || response.status === 501) throw new GuardedUnavailableError(await apiErrorFromResponse(response), response.status);
  if (!response.ok) throw new Error(await apiErrorFromResponse(response));
  return await response.json() as T;
}
export const sppUpdateApi = {
  status: (profileId: string, deviceId: string, attemptKey?: string) => sppRequest<SppUpdateStatus>(profileId, "status", deviceId, undefined, attemptKey),
  plan: (profileId: string, deviceId: string) => sppRequest<SppUpdatePlan>(profileId, "plan", deviceId, { device_id: deviceId }),
  apply: (profileId: string, deviceId: string, body: { review_token: string; confirmation_phrase: string; idempotency_key: string }) =>
    sppRequest<SppUpdateStatus>(profileId, "apply", deviceId, body),
  reconcile: (profileId: string, deviceId: string, body: { review_token: string; confirmation_phrase: string; idempotency_key: string }) =>
    sppRequest<SppUpdateStatus>(profileId, "reconcile", deviceId, body),
  verify: (profileId: string, deviceId: string, operationId: string) =>
    sppRequest<SppUpdateStatus>(profileId, "verify", deviceId, { operation_id: operationId }),
};

/* ---------- runtime write scope (Claude 14:32 contract; Codex owns the backend) ---------- */
export type WriteScopeName = "read_only" | "firmware_only" | "storage" | "power" | "mixed" | string;
export type WriteScopeOperation = string | { operation_id?: string | null; name?: string | null; resource?: string | null; device_id?: string | null; status?: string | null; kind?: string | null; description?: string | null };
export type WriteScopeState = { scope: WriteScopeName; source?: string | null; changed_at?: string | null; changed_by?: string | null; active_operations?: WriteScopeOperation[]; blockers?: string[] };
export type WriteScopePreview = { review_token: string; expires_at: string; current_scope: WriteScopeName; target_scope: WriteScopeName; effects?: string[]; blockers?: string[]; blocker_details?: BlockerDetail[]; confirmation_phrase?: string | null };

async function writeScopeRequest<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/runtime/write-scope${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json", "X-Local-User": "local-operator" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new GuardedUnavailableError("The write-scope service could not be reached.", null);
  }
  if (response.status === 404 || response.status === 501) throw new GuardedUnavailableError(await apiErrorFromResponse(response), response.status);
  if (!response.ok) throw new Error(await apiErrorFromResponse(response));
  return await response.json() as T;
}

export const writeScopeApi = {
  get: () => writeScopeRequest<WriteScopeState>(""),
  preview: (targetScope: "firmware_only" | "storage_only" | "esxi_install_only" | "vm_deploy_only" | "switch_setup_only" | "switch_reset_only" | "read_only") => writeScopeRequest<WriteScopePreview>("/preview", { target_scope: targetScope }),
  apply: (body: { review_token: string; confirmation_phrase: string }) => writeScopeRequest<WriteScopeState>("/apply", body),
};
