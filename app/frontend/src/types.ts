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

export type CiscoSetupReadiness = {
  provider_id: string;
  phase: string;
  planned_management_ip: string | null;
  management_configured: boolean;
  state_boundaries: Record<string, unknown>;
  console: {
    status: string;
    effective_path: string | null;
    recommended_path: string | null;
    selected_path: string | null;
    selection_source: string | null;
    baud: number | null;
    read_timing: Record<string, unknown>;
    candidate_count: number;
    stable_candidate_count: number;
    fallback_candidate_count: number;
    safe_next_action: string;
    last_prompt_readiness: Record<string, unknown>;
  };
  bootstrap_preview: {
    apply_enabled: boolean;
    commands_redacted: boolean;
    serial_writes_attempted: boolean;
    missing_requirements: string[];
    redacted_command_summary: string[];
    summary: string[];
  };
  ssh_scp_readiness: {
    planned_only: boolean;
    apply_enabled: boolean;
    summary: string;
  };
  ansible: {
    status: string;
    enabled: boolean;
    reason: string;
  };
  backup_report: {
    backup_enabled: boolean;
    report_placeholder_enabled: boolean;
    summary: string;
  };
  setup_wizard_plan: {
    available: boolean;
    detected: boolean;
    detected_prompt_state: string;
    apply_enabled: boolean;
    next_safe_action: string;
    summary: string;
  } | null;
  blockers: string[];
  warnings: string[];
  disabled_actions: string[];
  next_safe_action: string;
};

export type CiscoSetupWizardPlan = {
  provider_id: string;
  status: string;
  apply_enabled: boolean;
  planned_management_ip: string | null;
  detected_prompt_state: string;
  setup_wizard_detected: boolean;
  message: string;
  why_blocked: string[];
  future_guarded_plan_preview: string[];
  not_attempted: string[];
  disabled_actions: string[];
  blockers: string[];
  warnings: string[];
  next_safe_action: string;
};

export type CiscoBootstrapRequirements = {
  provider_id: string;
  status: string;
  apply_enabled: boolean;
  management_configured: boolean;
  requirements: Record<string, unknown>;
  blockers: string[];
  warnings: string[];
  disabled_actions: string[];
  not_attempted: string[];
  next_safe_action: string;
};

export type CiscoConsoleBootstrapPlan = {
  provider_id: string;
  status: string;
  target: Record<string, unknown>;
  apply_enabled: boolean;
  execution_supported: boolean;
  serial_writes_attempted: boolean;
  flow: string;
  prompt_state: string;
  prompt_detail: string;
  prompt_checked_at: string | null;
  summary: string[];
  intended_steps: string[];
  command_preview: string[];
  redacted_command_summary: string[];
  commands_redacted: boolean;
  blocker_summary: Record<string, unknown>;
  artifact_preview: Record<string, unknown>;
  destructive_actions_disabled: string[];
  blockers: string[];
  warnings: string[];
  confirmation_phrase: string;
  next_safe_action: string;
};

export type CiscoBootstrapRequirementsUpdate = {
  planned_management_ip: string;
  subnet_prefix: string;
  gateway: string;
  management_vlan: string | null;
  management_interface: string | null;
  management_strategy: string;
  hostname: string;
  domain_name: string;
  dns_servers: string[];
  local_admin_username_configured: boolean;
  local_admin_username_reference: string | null;
  operator_notes: string | null;
};

export type NetAppPlanPreview = {
  provider_id: string;
  mode: string;
  apply_enabled: boolean;
  netapp_configured: boolean;
  planned_targets: Record<string, unknown>;
  current_discovered_targets: Record<string, unknown> | null;
  readiness_summary: Record<string, unknown>;
  setup_readiness: Record<string, unknown> | null;
  upgrade_readiness: Record<string, unknown> | null;
  readiness_buckets: Record<string, unknown>;
  cluster_intent_preview: Record<string, unknown>;
  svm_intent_preview: Record<string, unknown>;
  lif_intent_preview: Record<string, unknown>;
  storage_iscsi_plan_preview: Record<string, unknown>;
  readiness_comparison_preview: Record<string, unknown> | null;
  upgrade_readiness_preview: Record<string, unknown>;
  blockers: string[];
  warnings: string[];
  removable_warnings: string[];
  disabled_actions: ProviderAction[];
  artifact_placeholders: string[];
  next_safe_action: string;
};

export type NetAppProviderArtifact = {
  id: string;
  provider_id: string;
  kind: string;
  title: string;
  description: string;
  status: string;
  mock_only: boolean;
  redacted: boolean;
  downloadable: boolean;
  download_url: string | null;
  generated_at: string;
  metadata: Record<string, unknown>;
};

export type NetAppUpgradeCandidate = {
  id: string;
  category: string;
  product_hint: string | null;
  version: string | null;
  source: string;
  redacted_label: string;
  match_confidence: string;
  warnings: string[];
};

export type NetAppUpgradeReadiness = {
  provider_id: string;
  mode: string;
  apply_enabled: boolean;
  upgrade_enabled: boolean;
  setup_ready: boolean;
  readiness_scope: string;
  current_version_source: string;
  current_version: string | null;
  current_version_confidence: string;
  media_inventory_mode: string;
  candidates: NetAppUpgradeCandidate[];
  recommended_target: string | null;
  required_intermediate_versions: string[];
  upgrade_chain: NetAppUpgradeCandidate[];
  blockers: string[];
  warnings: string[];
  removable_warnings: string[];
  next_safe_action: string;
  disabled_actions: ProviderAction[];
};

export type NetAppConsoleState =
  | "unknown"
  | "loader_prompt"
  | "boot_menu"
  | "cluster_setup_prompt"
  | "existing_cluster_login"
  | "other";

export type NetAppObservationUpdate = {
  observed_console_state: NetAppConsoleState;
  controller_a_console_seen: boolean;
  controller_b_console_seen: boolean;
  controller_a_sp_cabled: boolean;
  controller_b_sp_cabled: boolean;
  management_network_reviewed: boolean;
  planned_targets_reviewed: boolean;
  existing_data_risk_acknowledged: boolean;
  operator_notes: string;
};

export type NetAppObservations = NetAppObservationUpdate & {
  provider_id: string;
  updated_at: string;
  updated_by: string;
  mock_only: boolean;
  sent_to_netapp: boolean;
};

export type NetAppConsoleReadiness = {
  provider_id: string;
  mode: string;
  bootstrap_enabled: boolean;
  console_probe_enabled: boolean;
  apply_enabled: boolean;
  netapp_configured: boolean;
  planned_targets: Record<string, unknown>;
  current_discovered_targets: Record<string, unknown> | null;
  prerequisites: Array<Record<string, unknown>>;
  manual_steps: string[];
  expected_prompts_or_states: Array<Record<string, unknown>>;
  readiness_buckets: Record<string, unknown>;
  observations: NetAppObservations | null;
  observation_summary: Record<string, unknown> | null;
  observation_blockers: string[];
  blockers: string[];
  warnings: string[];
  removable_warnings: string[];
  disabled_actions: ProviderAction[];
  next_safe_action: string;
};

export type NetAppReadinessComparisonItem = {
  id: string;
  label: string;
  planned: string;
  observed: string;
  status: "matched" | "unknown" | "blocker" | "warning" | string;
  next_action: string;
  source: string;
};

export type NetAppReadinessComparison = {
  provider_id: string;
  mode: string;
  comparison_enabled: boolean;
  apply_enabled: boolean;
  discovery_enabled: boolean;
  planned_targets: Record<string, unknown>;
  current_discovered_targets: Record<string, unknown> | null;
  observations: NetAppObservations;
  comparison_items: NetAppReadinessComparisonItem[];
  matched_items: NetAppReadinessComparisonItem[];
  unknown_items: NetAppReadinessComparisonItem[];
  warning_items: NetAppReadinessComparisonItem[];
  blocker_items: NetAppReadinessComparisonItem[];
  blockers: string[];
  warnings: string[];
  removable_warnings: string[];
  next_safe_action: string;
  disabled_actions: ProviderAction[];
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
