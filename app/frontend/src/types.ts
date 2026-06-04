export type RequestStatus =
  | "draft"
  | "submitted"
  | "validating"
  | "needs_approval"
  | "approved"
  | "planned"
  | "executing"
  | "completed"
  | "failed"
  | "cancelled"
  | "rejected";

export type WorkflowRunStatus = "planned" | "executing" | "completed" | "failed" | "cancelled";

export type VMDeployment = {
  cluster: string;
  vm_name: string;
  template: string;
  cpu: number;
  memory_gb: number;
  disk_gb: number;
  network: string;
  datastore: string | null;
  storage_tier: string | null;
};

export type RequestRecord = {
  id: string;
  request_type: string;
  status: RequestStatus;
  requester: string;
  owner: string;
  environment: "dev" | "test" | "prod";
  site: string;
  expiry_date: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  vm_deploy: VMDeployment;
};

export type WorkflowRun = {
  id: string;
  request_id: string;
  workflow_id: string | null;
  workflow_slug: string;
  status: WorkflowRunStatus;
  provider: string;
  plan_json: Record<string, unknown>;
  result_json: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type AuditEvent = {
  id: string;
  request_id: string | null;
  workflow_run_id: string | null;
  actor: string;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  message: string;
  data_json: Record<string, unknown>;
  created_at: string;
};

export type ArtifactRecord = {
  id: string;
  request_id: string;
  workflow_run_id: string | null;
  kind: string;
  title: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
  mock_only: boolean;
  redacted: boolean;
  downloadable: boolean;
  download_url: string | null;
  metadata: Record<string, unknown>;
};

export type ReadinessIssue = {
  code: string;
  message: string;
  severity: "blocking" | "warning" | string;
  action: string;
};

export type RequestReadiness = {
  request_id: string;
  current_status: RequestStatus;
  ready_for_submit: boolean;
  ready_for_approval: boolean;
  ready_for_plan: boolean;
  ready_for_execute: boolean;
  next_action: string;
  blockers: ReadinessIssue[];
  warnings: ReadinessIssue[];
  summary: string;
};

export type ProviderAction = {
  id: string;
  label: string;
  enabled: boolean;
  read_only: boolean;
  reason: string;
  method: string | null;
  endpoint: string | null;
};

export type ConsoleCandidate = {
  path: string;
  stable_path: boolean;
  exists: boolean;
  readable: boolean | null;
  writable: boolean | null;
  label: string | null;
  target_path: string | null;
  recommendation: string;
};

export type ProviderStatus = {
  id: string;
  name: string;
  kind: string;
  mode: string;
  status: string;
  capabilities: string[];
  message: string;
  configuration: Record<string, unknown>;
  discovery: Record<string, unknown> | null;
  blockers: string[];
  warnings: string[];
  safe_actions: ProviderAction[];
  disabled_actions: ProviderAction[];
  last_probe_result: Record<string, unknown> | null;
  last_probe_time: string | null;
};

export type ProviderProbeResult = {
  provider_id: string;
  status: string;
  message: string;
  warnings: string[];
  blockers: string[];
  checked_at: string | null;
  [key: string]: unknown;
};

export type MediaInventoryItem = {
  placeholder_name: string;
  extension: string;
  size_bytes: number;
  category: string;
  source: string;
  actual_name_redacted: boolean;
  product_hints: string[];
  generation_hints: string[];
  version_hint: string | null;
};

export type MediaInventory = {
  mode: string;
  configured_directories: string[];
  items: MediaInventoryItem[];
  warnings: string[];
};

export type UpgradeSubject = {
  provider_type: string;
  product: string | null;
  generation: string | null;
  model: string | null;
  serial: string | null;
  current_version: string | null;
  discovery_confidence: string;
};

export type UpgradeCandidate = {
  id: string;
  category: string;
  product_hint: string | null;
  generation_hint: string | null;
  version: string | null;
  source: string;
  redacted_label: string;
  match_confidence: string;
  warnings: string[];
};

export type UpgradeDecision = {
  status: string;
  current_version: string | null;
  recommended_target: string | null;
  required_intermediate_versions: string[];
  candidate_chain: UpgradeCandidate[];
  blockers: string[];
  warnings: string[];
  removable_warnings: string[];
  next_safe_action: string;
  apply_enabled: boolean;
};

export type IloUpgradeReadiness = {
  provider_id: string;
  subject: UpgradeSubject;
  candidates: UpgradeCandidate[];
  decision: UpgradeDecision;
  blockers: string[];
  warnings: string[];
  removable_warnings: string[];
  upgrade_chain: UpgradeCandidate[];
  apply_enabled: boolean;
};

export type IloConnectionReadiness = {
  provider_mode: string;
  provider_status: string;
  host_configured: boolean;
  username_configured: boolean;
  password_configured: boolean;
  tls_verify: boolean;
  timeout_seconds: number;
  missing_fields: string[];
  redfish_probe_available: boolean;
  safety_flags: Record<string, unknown>;
};

export type IloEndpointCheck = {
  name?: string | null;
  path: string | null;
  status_code: number | null;
  content_type: string | null;
  error_class: string | null;
  classification: string | null;
};

export type IloEndpointDetection = {
  classification: string;
  message: string;
  redfish_status: string;
  legacy_status: string;
  web_status: string;
  inventory_collection_status: string;
  inventory_collection_classification: string;
  inventory_collection_checks: IloEndpointCheck[];
  auth_failure_classification: string;
  auth_recovery_hint: string;
  next_safe_action: string;
  diagnostic_hints: string[];
  checks: IloEndpointCheck[];
};

export type IloCurrentState = {
  last_probe_status: string;
  last_probe_time: string | null;
  model: string | null;
  serial: string | null;
  current_firmware: string | null;
  ilo_generation: string | null;
  endpoint_classification: string;
  endpoint_next_safe_action: string;
  redfish_root_status: string;
  redfish_endpoint_detected: string;
  legacy_endpoint_status: string;
  legacy_endpoint_message: string;
  web_endpoint_status: string;
  endpoint_detection: IloEndpointDetection;
  media_inventory_mode: string;
};

export type IloDesiredSetupSection = {
  id: string;
  title: string;
  status: string;
  apply_enabled: boolean;
  note: string;
};

export type IloReportArtifactPlaceholder = {
  kind: string;
  title: string;
  status: string;
  note: string;
};

export type IloReadinessSummary = {
  provider_id: string;
  connection: IloConnectionReadiness;
  current_state: IloCurrentState;
  desired_setup_sections: IloDesiredSetupSection[];
  firmware_readiness: IloUpgradeReadiness;
  upgrade_decision_status: string;
  blockers: string[];
  warnings: string[];
  removable_warnings: string[];
  disabled_dangerous_actions: ProviderAction[];
  reports_artifacts: IloReportArtifactPlaceholder[];
};

export type IloSetupPlanSection = {
  id: string;
  title: string;
  status: string;
  apply_enabled: boolean;
  source: string;
  current_observation: string;
  planned_preview: string;
  notes: string[];
  blockers: string[];
  warnings: string[];
};

export type IloSetupPlanPreview = {
  provider_id: string;
  mode: string;
  plan_only: boolean;
  apply_enabled: boolean;
  generated_from: string;
  sections: IloSetupPlanSection[];
  firmware_readiness_handoff: Record<string, unknown>;
  reports_artifacts: IloReportArtifactPlaceholder[];
  disabled_dangerous_actions: ProviderAction[];
  blockers: string[];
  warnings: string[];
  removable_warnings: string[];
};

export type IloSetupIntent = {
  provider_id?: string;
  network: {
    hostname: string | null;
    management_ip: string | null;
    subnet_mask_or_prefix: string | null;
    gateway: string | null;
    vlan: string | null;
  };
  users: Array<{
    username_label: string;
    role: string;
  }>;
  snmp: {
    enabled: boolean;
    destinations: string[];
    community_or_user_ref_labels: string[];
  };
  time: {
    timezone: string | null;
    ntp_servers: string[];
  };
  dns_domain: {
    domain_name: string | null;
    dns_servers: string[];
  };
  notes: string | null;
  apply_enabled?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export type IloSetupCompareRow = {
  section: string;
  field: string;
  label: string;
  desired: string;
  discovered: string;
  status: string;
  next_safe_action: string;
  apply_enabled: boolean;
};

export type IloSetupCompareSection = {
  id: string;
  title: string;
  status: string;
  apply_enabled: boolean;
  next_safe_action: string;
  rows: IloSetupCompareRow[];
};

export type IloSetupCompareReport = {
  provider_id: string;
  mode: string;
  source: string;
  apply_enabled: boolean;
  sections: IloSetupCompareSection[];
  disabled_dangerous_actions: ProviderAction[];
  blockers: string[];
  warnings: string[];
  removable_warnings: string[];
};

export type IloDestructiveRebuildRequirement = {
  id: string;
  label: string;
  status: string;
  detail: string;
};

export type IloRealChangeLane = {
  id: string;
  label: string;
  status: string;
  execution_enabled: boolean;
  next_safe_action: string;
  required_gates: string[];
  blocked_actions: string[];
};

export type IloDestructiveRebuildPreview = {
  provider_id: string;
  provider_mode: string;
  status: string;
  destructive_enabled: boolean;
  apply_enabled: boolean;
  safe_next_action: string;
  target_identity: Record<string, unknown>;
  discovered_state: Record<string, unknown>;
  intended_scope: string[];
  required_capabilities: IloDestructiveRebuildRequirement[];
  real_change_lanes: IloRealChangeLane[];
  blockers: string[];
  warnings: string[];
  future_workflow_handoff: Record<string, unknown>;
  confirmation_requirements: Record<string, unknown>;
  artifact_requirements: string[];
};

export type IloReportPreview = {
  provider_id: string;
  provider_mode: string;
  generated_at: string;
  source: string;
  apply_enabled: boolean;
  readiness_summary: Record<string, unknown>;
  desired_setup_intent: Record<string, unknown>;
  setup_compare_report: IloSetupCompareReport;
  setup_plan_preview: Record<string, unknown>;
  destructive_rebuild_preview: Record<string, unknown>;
  firmware_readiness: Record<string, unknown>;
  media_inventory_summary: Record<string, unknown>;
  disabled_dangerous_actions: ProviderAction[];
  blockers: string[];
  warnings: string[];
  removable_warnings: string[];
};

export type Catalog = {
  environments: string[];
  sites: string[];
  clusters_by_site: Record<string, string[]>;
  templates: string[];
  networks: Array<{ name: string; vlan_id: number; environments: string[] }>;
  datastores: string[];
  storage_tiers: string[];
};

export type VMDeploymentCreate = {
  requester: string;
  environment: "dev" | "test" | "prod";
  site: string;
  cluster: string;
  vm_name: string;
  template: string;
  cpu: number;
  memory_gb: number;
  disk_gb: number;
  network: string;
  datastore?: string | null;
  storage_tier?: string | null;
  owner: string;
  expiry_date: string;
  notes?: string | null;
};

export type VMDeploymentUpdate = Partial<VMDeploymentCreate>;
