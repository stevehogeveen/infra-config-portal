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
