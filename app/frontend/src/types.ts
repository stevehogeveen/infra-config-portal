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

export type ProviderStatus = {
  name: string;
  kind: string;
  mode: string;
  status: string;
  capabilities: string[];
  message: string;
};

export type MediaInventoryItem = {
  placeholder_name: string;
  extension: string;
  size_bytes: number;
  category: string;
  source: string;
  actual_name_redacted: boolean;
};

export type MediaInventory = {
  mode: string;
  configured_directories: string[];
  items: MediaInventoryItem[];
  warnings: string[];
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
