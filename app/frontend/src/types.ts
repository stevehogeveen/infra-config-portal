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

export type UiDisplayMode = "simple" | "advanced";

export type MinimalStageSummary = {
  label: string;
  status: string;
  one_line_summary: string;
  next_action: string;
  primary_button_label: string;
  primary_button_enabled: boolean;
  secondary_action_label?: string;
  blocker_count: number;
  proof_count: number;
  last_checked: string | null;
  advanced_available: boolean;
};

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
  in_use: boolean;
  rank: number;
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
  source_type: string;
  checked_at: string | null;
  freshness: string;
  ttl_seconds: number | null;
  stale_after_seconds: number | null;
  is_current: boolean;
  is_operator_visible: boolean;
  recheck_command: string | null;
  evidence_artifacts: string[];
  configuration: Record<string, unknown>;
  discovery: Record<string, unknown> | null;
  blockers: string[];
  warnings: string[];
  safe_actions: ProviderAction[];
  disabled_actions: ProviderAction[];
  last_probe_result: Record<string, unknown> | null;
  last_probe_time: string | null;
};

export type ProviderModeOption = {
  mode: "local-readonly" | "local-lab-readwrite";
  label: string;
  status: string;
  description: string;
  restart_command: string;
  requirements: string[];
};

export type ProviderModeSettings = {
  current_mode: string;
  desired_mode: ProviderModeOption["mode"];
  pending_restart: boolean;
  options: ProviderModeOption[];
  restart_command: string;
  expected_runtime_mode: string;
  dev_test_banner: string | null;
  mode_env_path: string;
  store_path: string;
  updated_at: string | null;
  next_safe_action: string;
};

export type ProviderModeSettingsWrite = {
  desired_mode: ProviderModeOption["mode"];
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

export type LabValidationBlocker = {
  problem: string;
  source: string;
  current_value: string;
  expected_value: string;
  where_to_fix: string;
  recommended_action: string;
  copyable_command: string;
  recheck_command: string;
  evidence_links: string[];
  [key: string]: unknown;
};

export type LabValidationItem = {
  id: string;
  label: string;
  category: string;
  stage: string;
  status: "ready" | "partial" | "blocked" | "not_configured" | "not_checked" | "warning" | "not_in_scope";
  current_state: string;
  desired_state: string;
  setup_summary: string;
  next_action: string;
  login_hint: string;
  management_url: string | null;
  ssh_target: string | null;
  proof_points: string[];
  evidence_artifacts: string[];
  evidence_collapsed_by_default: boolean;
  last_checked: string | null;
  source_type: "live_probe" | "live_cached" | "historical_artifact" | "not_checked";
  freshness: string;
  blockers: LabValidationBlocker[];
  warnings: string[];
  recheck_command: string;
  linked_workflow_action: {
    action_id: string;
    label: string | null;
    stage: string | null;
    command: string | null;
    run_endpoint: string | null;
    ui_run_supported: boolean | null;
  } | null;
};

export type LabValidationProofLink = {
  component_id: string;
  component_label: string;
  path: string;
};

export type LabValidationSummary = {
  overall_status: string;
  progress_counts: Record<string, number>;
  top_blocker: LabValidationBlocker | null;
  validation_items: LabValidationItem[];
  proof_links: LabValidationProofLink[];
  generated_at: string;
  next_action: string;
  source_type: string;
  freshness: string;
  handoff_report: string;
  warnings: string[];
};

export type ReportIssueSeverity = "critical" | "warning" | "info" | "success" | string;

export type ReportIssueClassification =
  | "hard_fail"
  | "stale_config"
  | "operator_action_required"
  | "blocked_by_prior_stage"
  | "not_configured_yet"
  | "warning"
  | "passed"
  | string;

export type ReportIssueStatus = "open" | "blocked" | "stale" | "reviewed" | "resolved" | string;

export type ReportIssue = {
  id: string;
  source: string;
  source_stage: string;
  source_stage_id: string | null;
  source_stage_label: string | null;
  source_action_id: string | null;
  source_action_label: string | null;
  source_action_link: string | null;
  severity: ReportIssueSeverity;
  classification: ReportIssueClassification;
  status: ReportIssueStatus;
  source_type: string;
  freshness: string;
  ttl_seconds: number | null;
  stale_after_seconds: number | null;
  is_current: boolean;
  is_operator_visible: boolean;
  title: string;
  summary: string;
  problem: string;
  next_action: string;
  recheck_command: string;
  source_report: string | null;
  evidence_artifacts: string[];
  linked_page: string;
  last_checked: string | null;
  can_auto_fix: boolean;
  auto_fix_action_id: string | null;
  details: Record<string, unknown>;
};

export type ReportSourceSummary = {
  id: string;
  label: string;
  status: string;
  critical: number;
  warning: number;
  info: number;
  success: number;
  issue_count: number;
  source_type: string;
  freshness: string;
  checked_at: string | null;
  is_current: boolean;
  is_operator_visible: boolean;
  linked_page: string;
  recheck_command: string | null;
  last_report: string | null;
};

export type ReportPageBadge = {
  page: string;
  status: string;
  label: string;
  count: number;
  critical: number;
  warning: number;
  not_configured_yet: number;
  success: number;
  sources: string[];
  default_filter: string;
};

export type ReportCenter = {
  checked_at: string;
  overall_status: string;
  counts: Record<string, number>;
  classification_counts: Record<string, number>;
  top_issues: ReportIssue[];
  issues: ReportIssue[];
  sources: ReportSourceSummary[];
  evidence_artifacts: string[];
  last_reports: Record<string, string | null>;
  page_badges: Record<string, ReportPageBadge>;
};

export type LabAddressPlan = {
  subnet: string | null;
  ilo: string | null;
  ilo_initial: string | null;
  server_embedded_nic: string | null;
  esxi_management: string | null;
  cisco_management: string | null;
  ansible_control_host: string | null;
  netapp_controller_a_sp: string | null;
  netapp_controller_b_sp: string | null;
  netapp_cluster_mgmt: string | null;
  netapp_node_a_mgmt: string | null;
  netapp_node_b_mgmt: string | null;
  netapp_svm_mgmt: string | null;
  netapp_nfs_lifs: string[];
  netapp_iscsi_lifs: string[];
};

export type LabGlobalSettings = {
  subnet_prefix: number;
  gateway: string | null;
  support_unit?: string | null;
  domain_name: string | null;
  dom_dc?: string | null;
  dns_servers: string[];
  ntp_servers: string[];
  timezone: string | null;
  netapp_enabled: boolean;
  netapp_disabled_reason: string | null;
  vcenter_enabled: boolean;
  vlan_id: string | null;
  mtu: number | null;
};

export type LabSubnetOption = {
  prefix: number;
  cidr_suffix: string;
  label: string;
  usable_hosts: number;
  netapp_supported: boolean;
  netapp_disabled_reason: string | null;
  default_topology?: string | null;
};

export type LabProfileDevices = {
  gateway?: string | null;
  switch_primary?: string | null;
  switch_secondary?: string | null;
  reserved?: string[];
  ups?: string | null;
  backup_storage?: string | null;
  utility_vm?: string | null;
  esxi?: string | null;
  ilo?: string | null;
  cisco?: string | null;
  netapp?: Record<string, unknown> | null;
  vcenter?: string | null;
};

export type LabProfileFeatures = {
  netapp_enabled: boolean;
  vcenter_enabled: boolean;
  firmware_gate_enabled: boolean;
  build_verification_enabled: boolean;
  storage_protocol: string;
  disable_ipv6: boolean;
  block_legacy_protocols: boolean;
  enable_snmp: boolean;
  enable_ntp: boolean;
  enable_dns: boolean;
  netapp_disabled_reason: string | null;
  vcenter_disabled_reason: string | null;
};

export type LabProfileRevision = {
  version: number;
  saved_at: string;
  name: string;
  description: string;
  profile_topology: string;
  subnet_cidr: string | null;
  gateway: string | null;
  dns: string[];
  ntp: string[];
  vlan_id: string | null;
  mtu: number | null;
  devices: LabProfileDevices;
  features: LabProfileFeatures;
  global_settings: LabGlobalSettings;
  address_plan: LabAddressPlan;
};

export type LabProfile = {
  id: string;
  name: string;
  description: string;
  profile_topology: string;
  subnet_cidr: string | null;
  gateway: string | null;
  dns: string[];
  ntp: string[];
  vlan_id: string | null;
  mtu: number | null;
  devices: LabProfileDevices;
  features: LabProfileFeatures;
  global_settings: LabGlobalSettings;
  address_plan: LabAddressPlan;
  resolved_address_plan: LabAddressPlan;
  not_in_scope_stages: string[];
  mismatch_warnings: Array<Record<string, unknown>>;
  fix_guidance: Array<Record<string, unknown>>;
  source: string;
  version: number;
  active: boolean;
  created_at: string;
  updated_at: string;
  last_selected_at: string | null;
  history: LabProfileRevision[];
};

export type LabProfileWrite = {
  name: string;
  description?: string | null;
  profile_topology?: string | null;
  subnet_cidr?: string | null;
  gateway?: string | null;
  dns?: string[];
  ntp?: string[];
  vlan_id?: string | null;
  mtu?: number | null;
  devices?: LabProfileDevices;
  features?: LabProfileFeatures;
  global_settings: LabGlobalSettings;
  address_plan: LabAddressPlan;
};

export type LabProfileContext = {
  active_profile: LabProfile;
  topology: string;
  resolved_address_plan: LabAddressPlan;
  enabled_features: LabProfileFeatures;
  disabled_features: Record<string, string>;
  not_in_scope_stages: string[];
  mismatch_warnings: Array<Record<string, unknown>>;
  fix_guidance: Array<Record<string, unknown>>;
  control_host_network: Record<string, unknown>;
};

export type LabProfileList = {
  active_profile: LabProfile;
  active_context: LabProfileContext;
  runtime_profile: LabProfile;
  profiles: LabProfile[];
  subnet_options: LabSubnetOption[];
  store_path: string;
  mock_only: boolean;
  next_safe_action: string;
};

export type LabProfileRuntimeApply = {
  applied: boolean;
  env_path: string;
  updated_keys: string[];
  removed_keys: string[];
  restart_required: boolean;
  message: string;
  next_action: string;
  lab_profiles: LabProfileList;
};

export type ControlActionClassification = "read-only" | "write" | "destructive" | "upgrade";

export type ControlActionInput = {
  name: string;
  label: string;
  required: boolean;
  secret: boolean;
  description: string;
};

export type ControlStateItem = {
  label: string;
  value: string;
  status: string | null;
  detail: string | null;
};

export type ControlPlanDiffItem = {
  label: string;
  current: string;
  desired: string;
  status: string;
  note: string | null;
};

export type ControlReportLink = {
  label: string;
  path: string;
  status: string;
};

export type ControlEditableConfigField = {
  label: string;
  value: string;
  source: string;
};

export type ControlEditableConfigFieldWrite = {
  label: string;
  value: string | null;
};

export type ControlAccessConfig = {
  section_id: string;
  title: string;
  access_method: string;
  first_time_configuring: boolean;
  first_time_note: string;
  original_dhcp_ip: string | null;
  desired_management_ip: string | null;
  desired_address_label: string;
  username_reference: string | null;
  password_configured: boolean;
  password_reference_label: string | null;
  editable_fields: ControlEditableConfigField[];
  blockers: string[];
  updated_at: string | null;
};

export type ControlAccessConfigWrite = {
  first_time_configuring: boolean;
  original_dhcp_ip: string | null;
  username_reference: string | null;
  password_configured: boolean;
  password_reference_label: string | null;
  editable_fields?: ControlEditableConfigFieldWrite[];
};

export type ControlAction = {
  id: string;
  label: string;
  section_id: string;
  device_stage: string;
  description: string;
  classification: ControlActionClassification;
  required_inputs: ControlActionInput[];
  required_flags: string[];
  required_confirmations: string[];
  availability: string;
  blocker: string | null;
  last_run_status: string;
  last_run_at: string | null;
  last_report: string | null;
  suggested_command: string | null;
  method: string | null;
  api_endpoint: string | null;
  plan_endpoint: string;
  run_endpoint: string;
  direct_run_supported: boolean;
  diagnostics: string[];
};

export type FirmwareVersionSummary = {
  label: string;
  version: string | null;
  status: string | null;
};

export type FirmwareFileCandidate = {
  file_name: string;
  file_path: string | null;
  detected_vendor: string | null;
  detected_product: string | null;
  detected_version: string | null;
  confidence: string;
};

export type FirmwareFileSelections = {
  provider_id: string;
  status: string;
  message: string;
  source_type: string;
  freshness: string;
  checked_at: string | null;
  updated_at: string | null;
  store_path: string;
  selected_files: Record<string, string>;
  apply_enabled: boolean;
  blockers: string[];
  warnings: string[];
  next_safe_action: string;
};

export type FirmwareFileSelectionsWrite = {
  selected_files: Record<string, string>;
};

export type FirmwareUpgradePath = {
  component_id: string;
  component_label: string;
  device_label: string;
  equipment_label?: string | null;
  equipment_type: string;
  current_version: string | null;
  target_version: string | null;
  baseline_source: string | null;
  package_available: boolean;
  package_name: string | null;
  package_version: string | null;
  selected_file_name?: string | null;
  selected_file_path?: string | null;
  selection_source?: string | null;
  candidate_files?: FirmwareFileCandidate[];
  path_status: "current" | "direct" | "staged" | "blocked" | "unknown" | "manual_review" | string;
  required_intermediate_versions: string[];
  prechecks_required: string[];
  reboot_required: boolean;
  estimated_impact: string;
  apply_enabled: boolean;
  disabled_reason: string;
  next_action: string;
  evidence_artifacts: string[];
  missing_evidence: string[];
  scan_action_id: string | null;
  last_checked: string | null;
  source_type: string;
  freshness: string;
};

export type FirmwareSummary = {
  device_id: string;
  label: string;
  component_type: string;
  current_versions: FirmwareVersionSummary[];
  approved_versions: FirmwareVersionSummary[];
  compliance_status: string;
  severity: string;
  last_scanned: string | null;
  source_type: string;
  freshness: string;
  blocker: string | null;
  next_action: string;
  scan_action_id: string | null;
  upgrade_center_link: string;
  evidence_artifacts: string[];
  upgrade_paths: FirmwareUpgradePath[];
  path_status: string;
  target_version: string | null;
  package_available: boolean;
  package_name: string | null;
  required_intermediate_versions: string[];
  prechecks_required: string[];
  reboot_required: boolean;
  estimated_impact: string;
  apply_enabled: boolean;
  disabled_reason: string;
};

export type ControlSectionRecord = {
  id: string;
  title: string;
  stage: string;
  description: string;
  status: string;
  firmware_summary: FirmwareSummary | null;
  current_state: ControlStateItem[];
  desired_state: ControlStateItem[];
  plan_diff: ControlPlanDiffItem[];
  access_config: ControlAccessConfig | null;
  actions: ControlAction[];
  primary_actions: ControlAction[];
  destructive_actions: ControlAction[];
  upgrade_actions: ControlAction[];
  last_result: Record<string, unknown>;
  report_links: ControlReportLink[];
  advanced_diagnostics: Record<string, unknown>;
};

export type ControlLabProfile = {
  active_profile_name: string;
  source: string;
  version: number;
  topology: string | null;
  features: Record<string, unknown>;
  not_in_scope_stages: string[];
  mismatch_warnings: Array<Record<string, unknown>>;
  fix_guidance: Array<Record<string, unknown>>;
  global_settings: LabGlobalSettings;
  address_plan: LabAddressPlan;
  known_lab_profile: Record<string, unknown>;
  network: Record<string, unknown>;
  configured_flags: Record<string, boolean>;
  edit_profile_path: string;
  env_update_command: string;
  stale_or_invalid_values: string[];
};

export type ControlActionCatalog = {
  generated_at: string;
  provider_mode: string;
  summary: Record<string, unknown>;
  lab_profile: ControlLabProfile;
  sections: ControlSectionRecord[];
  actions: ControlAction[];
};

export type ControlActionPlanStep = {
  label: string;
  status: string;
  detail: string;
};

export type ControlActionPlan = {
  action: ControlAction;
  status: string;
  message: string;
  plan_steps: ControlActionPlanStep[];
  suggested_command: string | null;
  api_endpoint: string | null;
  method: string | null;
  direct_run_enabled: boolean;
  warnings: string[];
  blockers: string[];
};

export type ControlActionRun = {
  action: ControlAction;
  status: string;
  message: string;
  executed: boolean;
  suggested_command: string | null;
  api_endpoint: string | null;
  method: string | null;
  warnings: string[];
  blockers: string[];
};

export type WorkflowActionCategory =
  | "discover"
  | "inventory"
  | "plan"
  | "apply"
  | "verify"
  | "report"
  | "reset"
  | "upgrade"
  | "waive"
  | "reclaim";

export type WorkflowActionMode = "read_only" | "write" | "destructive" | "upgrade" | "report_only";

export type WorkflowActionSourceType = "make_target" | "backend_script" | "api_endpoint" | "manual_guidance";

export type WorkflowActionInput = {
  name: string;
  label: string;
  required: boolean;
  secret: boolean;
  description: string;
};

export type WorkflowRunTrace = {
  run_id: string;
  action_id: string;
  stage_id: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  source_type: "live_probe" | "live_cached" | "historical_artifact" | "test_fixture" | "not_checked" | string;
  freshness: string;
  command: string | null;
  report_artifacts: string[];
  summary: string;
  blockers: string[];
  warnings: string[];
  next_action: string;
};

export type WorkflowActionRun = {
  run_id: string;
  action_id: string;
  action_label: string;
  stage_id: string;
  stage_label: string;
  mode: WorkflowActionMode | string;
  started_at: string;
  finished_at: string;
  checked_at: string;
  status: string;
  source_type: "live_probe" | "live_cached" | "historical_artifact" | "test_fixture" | "not_checked" | string;
  freshness: string;
  not_mock: boolean;
  command: string | null;
  executed: boolean;
  return_code: number | null;
  stdout_summary: string;
  stderr_summary: string;
  report_artifacts: string[];
  trace_artifact: string | null;
  summary: string;
  blockers: string[];
  warnings: string[];
  next_action: string;
};

export type WorkflowAction = {
  action_id: string;
  label: string;
  stage: string;
  stage_label: string;
  provider: string;
  category: WorkflowActionCategory;
  mode: WorkflowActionMode;
  description: string;
  source_type: WorkflowActionSourceType;
  command: string | null;
  api_endpoint: string | null;
  api_method: string | null;
  required_mode: string;
  required_gates: string[];
  required_confirmations: string[];
  required_credentials: string[];
  safety_notes: string[];
  inputs: WorkflowActionInput[];
  outputs: string[];
  reports: string[];
  last_run_report: string | null;
  last_run_status: string;
  current_availability: string;
  blockers: string[];
  next_action: string;
  evidence_artifacts: string[];
  stale_after_seconds: number;
  last_run_trace: WorkflowRunTrace;
  ui_run_supported: boolean;
  ui_run_blockers: string[];
  guarded_run_supported: boolean;
  guarded_run_blockers: string[];
  run_endpoint: string;
  runs_endpoint: string;
};

export type WorkflowActionRunRequest = {
  confirmation_phrase?: string;
  confirmed_gates?: string[];
};

export type WorkflowStage = {
  stage_id: string;
  label: string;
  order: number;
  current_state: string;
  desired_state: string;
  primary_action: string | null;
  secondary_actions: string[];
  dependencies: string[];
  reports: string[];
  action_count: number;
  blocked_count: number;
  report_count: number;
  actions: WorkflowAction[];
};

export type CiscoSetupReadiness = {
  provider_id: string;
  status: string;
  source_type: string;
  freshness: string;
  checked_at: string | null;
  phase: string;
  planned_management_ip: string | null;
  management_configured: boolean;
  control_host_network: Record<string, unknown>;
  state_boundaries: Record<string, unknown>;
  console: {
    status: string;
    serial_candidate_status?: string;
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
  ethernet_readiness: Record<string, unknown>;
  real_lab_run: Record<string, unknown>;
  password_recovery: Record<string, unknown>;
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
  netapp_configured_source: string | null;
  manual_env_flag_required: boolean;
  runtime_state: Record<string, unknown> | null;
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
  storage_nfs_vcenter_preview: Record<string, unknown> | null;
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
  netapp_configured_source: string | null;
  legacy_netapp_configured_env: boolean | null;
  manual_env_flag_required: boolean;
  runtime_state: Record<string, unknown> | null;
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
  file_name?: string | null;
  file_path?: string | null;
  detected_vendor?: string | null;
  detected_product?: string | null;
  detected_version?: string | null;
  confidence?: string | null;
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

export type IloSetupIntent = {
  provider_id?: string;
  apply_enabled?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
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
};

export type IloSetupIntentWrite = Omit<
  IloSetupIntent,
  "provider_id" | "apply_enabled" | "created_at" | "updated_at"
>;

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
  blockers: string[];
  warnings: string[];
  removable_warnings: string[];
};

export type IloBaselineKitProfile = {
  kit_id: string;
  support_unit: string;
  subnet_mask: string;
  gateway: string;
  dom_dc: string;
  derived_subnet: string;
  source_type: string;
  checked_at: string | null;
  freshness: string;
  recheck_command: string;
};

export type IloBaselineDiscoveryRange = {
  source_subnet: string;
  default_start_host: string;
  default_end_host: string;
  addresses: string[];
  override_supported: boolean;
  override_active: boolean;
  source_type: string;
  checked_at: string | null;
  freshness: string;
  recheck_command: string;
};

export type IloBaselineReadinessCheck = {
  name: string;
  status: string;
  current: string;
  desired: string;
  source_type: string;
  checked_at: string | null;
  freshness: string;
  message: string;
  next_action: string;
};

export type IloBaselineSection = {
  id: string;
  title: string;
  status: string;
  items: Record<string, unknown>;
  secret_refs: string[];
  notes: string[];
};

export type IloBaselinePlanRow = {
  section: string;
  item: string;
  current: unknown;
  desired: unknown;
  action: string;
  severity: string;
  message: string;
};

export type IloBaselineBlocker = {
  problem: string;
  source: string;
  current_value: string;
  expected_value: string;
  where_to_fix: string;
  recommended_action: string;
  copyable_command: string | null;
  recheck_command: string;
  evidence_links: string[];
};

export type IloBaselineReadiness = {
  provider_id: string;
  source_provider_id: string;
  provider_mode: string;
  generated_at: string;
  source_type: string;
  checked_at: string | null;
  freshness: string;
  kit_profile: IloBaselineKitProfile;
  discovery_range: IloBaselineDiscoveryRange;
  connection_readiness: IloBaselineReadinessCheck[];
  current_state: Record<string, unknown>;
  comparison_rows: IloBaselinePlanRow[];
  reset_required: boolean;
  apply_enabled: boolean;
  apply_reason: string;
  blockers: IloBaselineBlocker[];
  warnings: string[];
  next_action: string;
};

export type IloBaselinePreview = IloBaselineReadiness & {
  expected_baseline_sections: IloBaselineSection[];
  reports_artifacts: Array<{
    kind: string;
    title: string;
    status: string;
    note: string;
  }>;
};

export type HpeRaidVolumeIntent = {
  name: string;
  purpose: string;
  raid_level: string;
  drive_bays: string[];
  spare_bays: string[];
  spare_rebuild_mode: string | null;
  size_policy: string;
  bootable: boolean;
};

export type HpeRaidIntent = {
  provider_id?: string;
  apply_enabled?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  controller_ref: string | null;
  wipe_existing_logical_drives: boolean;
  volumes: HpeRaidVolumeIntent[];
  notes: string | null;
};

export type HpeRaidIntentWrite = Omit<
  HpeRaidIntent,
  "provider_id" | "apply_enabled" | "created_at" | "updated_at"
>;

export type HpeStorageDiscovery = {
  provider_id: string;
  source: string;
  last_probe_time: string | null;
  storage_inventory_available: boolean;
  server: Record<string, unknown>;
  controllers: Array<Record<string, unknown>>;
  physical_drives: Array<Record<string, unknown>>;
  logical_drives: Array<Record<string, unknown>>;
  warnings: string[];
  blockers: string[];
  next_safe_action: string;
};

export type HpeRaidPlanPreview = {
  provider_id: string;
  status: string;
  apply_enabled: boolean;
  destructive_actions_requested: boolean;
  destructive_actions_enabled: boolean;
  current_layout: HpeStorageDiscovery;
  desired_intent: HpeRaidIntent;
  planned_layout: Record<string, unknown>;
  impact: Record<string, unknown>;
  blockers: string[];
  warnings: string[];
  disabled_actions: string[];
  next_safe_action: string;
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
