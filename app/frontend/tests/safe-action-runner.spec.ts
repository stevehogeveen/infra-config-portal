import { expect, test, type Page, type Route } from "@playwright/test";

const checkedAt = "2026-06-09T21:00:00Z";

const safeAction = workflowAction({
  action_id: "build-verification.run-full",
  category: "verify",
  current_availability: "available",
  label: "Run Full Verification",
  mode: "read_only",
  provider: "build-verification",
  stage: "build-verification",
  stage_label: "Build Verification",
  ui_run_supported: true
});

const destructiveAction = workflowAction({
  action_id: "raid.apply",
  category: "apply",
  current_availability: "manual_command_required",
  label: "Apply",
  mode: "destructive",
  provider: "raid",
  stage: "raid",
  stage_label: "RAID",
  ui_run_supported: false,
  ui_run_blockers: ["destructive actions require a guarded workflow and cannot be run from this UI pass."]
});

const netappSetupPreviewAction = workflowAction({
  action_id: "netapp.setup-preview",
  category: "plan",
  current_availability: "available",
  label: "Setup Preview",
  mode: "read_only",
  provider: "netapp-ontap",
  stage: "netapp",
  stage_label: "NetApp",
  ui_run_supported: true
});

const netappNfsReadinessAction = workflowAction({
  action_id: "netapp.nfs-vcenter-readiness",
  category: "verify",
  current_availability: "manual_command_required",
  label: "NFS / vCenter Readiness",
  mode: "read_only",
  provider: "netapp-ontap",
  stage: "netapp",
  stage_label: "NetApp",
  ui_run_supported: false
});

const ciscoValidationAction = workflowAction({
  action_id: "cisco.validate-ssh-scp",
  category: "verify",
  current_availability: "blocked",
  label: "Validate SSH/SCP",
  mode: "read_only",
  provider: "cisco",
  stage: "cisco",
  stage_label: "Cisco",
  ui_run_supported: false
});

test.beforeEach(async ({ page }) => {
  await installApiMocks(page);
});

test("renders Run Check control for a safe read-only action and invokes the safe runner", async ({ page }) => {
  await page.goto("/control-center?section=action-catalog&action=build-verification.run-full");

  await expect(page.getByRole("heading", { name: "Control Center" })).toBeVisible();
  const safeRow = page.getByRole("row", { name: /Run Full Verification/ });
  const runButton = safeRow.getByRole("button", { name: "Run Verification" });
  await expect(runButton).toBeVisible();

  const runResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/build-verification.run-full/run")
  );
  await runButton.click();
  await expect((await runResponse).ok()).toBeTruthy();
  await expect(page.getByRole("button", { name: "Run Verification" }).first()).toBeVisible();
});

test("does not render a run button for a destructive action", async ({ page }) => {
  await page.goto("/control-center?section=action-catalog&action=raid.apply");

  const destructiveRow = page.getByRole("row", { name: /Apply Requires guarded workflow/ });
  await expect(destructiveRow.getByText("Requires guarded workflow").first()).toBeVisible();
  await expect(destructiveRow.getByRole("button", { name: /Run Check|Run Verification|Refresh Status/ })).toHaveCount(0);
});

test("uses merged navigation and dashboard lab setup selector", async ({ page }) => {
  await page.goto("/verification");

  await expect(page.getByRole("heading", { name: "Validation & Reports" })).toBeVisible();
  await expect(page.locator("nav .nav-item-label")).toHaveText([
    "Dashboard",
    "Lab Setup",
    "Hardware",
    "Control Center",
    "Firmware Upgrades",
    "Validation & Reports",
    "Settings"
  ]);
  await expect(page.locator("nav .nav-item-label", { hasText: /^Verification$/ })).toHaveCount(0);
  await expect(page.locator("nav .nav-item-label", { hasText: /^Lab Validation$/ })).toHaveCount(0);
  await expect(page.locator("nav .nav-item-label", { hasText: /^Reports$/ })).toHaveCount(0);

  await page.goto("/dashboard");
  await expect(page.getByRole("combobox", { name: "Active lab setup" })).toBeVisible();
  await expect(page.getByText("Runtime Lab").first()).toBeVisible();
  await expect(page.getByText("192.168.1.201").first()).toBeVisible();
});

test("renders standard control layout with collapsed evidence and seeded options", async ({ page }) => {
  await page.goto("/control-center?section=netapp");

  await expect(page.getByRole("heading", { name: "Control Center" })).toBeVisible();
  await expect(page.getByText("ONTAP version is unknown.")).toBeVisible();
  await expect(page.getByText("Access").first()).toBeVisible();
  await expect(page.getByText("Cluster management").first()).toBeVisible();
  await expect(page.getByText("192.168.1.220").first()).toBeVisible();
  await expect(page.getByText("Access Username")).toBeVisible();
  await expect(page.locator("input[value='operator-admin']")).toBeVisible();
  await expect(page.getByText("Actions / Configs")).toBeVisible();
  await expect(page.getByText("artifacts/codex-runs/netapp-live-state-report.md").first()).toBeHidden();
  await expect(page.locator("input[value='topsecret-password-ref']")).toBeHidden();

  await page.locator("details.actions-config-dropdown > summary").click();
  await expect(page.getByText("Configure NetApp NFS")).toBeVisible();
  await expect(page.getByText("Choose Storage Protocol")).toBeVisible();
  await expect(page.getByText("Upgrade Apply", { exact: true })).toBeVisible();

  await page.locator("details.standard-evidence-details > summary").click();
  await expect(page.getByText("artifacts/codex-runs/netapp-live-state-report.md").first()).toBeVisible();
});

test("renders Firmware Upgrades as the global upgrade overview", async ({ page }) => {
  await page.goto("/firmware");

  await expect(page.getByRole("heading", { name: "Firmware Upgrades" })).toBeVisible();
  await expect(page.getByText("iLO").first()).toBeVisible();
  await expect(page.getByText("Cisco").first()).toBeVisible();
  await expect(page.getByText("ONTAP").first()).toBeVisible();
  await expect(page.getByText("ESXi").first()).toBeVisible();
  await expect(page.getByText("Smart Array").first()).toBeVisible();
});

async function installApiMocks(page: Page) {
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/health") {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          app: "infra-config-portal",
          dev_test_banner: null,
          expected_runtime_mode: "local-lab-readwrite",
          operator_runtime_mode: "local-lab-readwrite",
          provider_mode: "local-lab-readwrite",
          status: "ok"
        })
      });
    }
    if (!url.pathname.startsWith("/api/v1/")) {
      return route.continue();
    }
    if (url.pathname === "/api/v1/lab/profiles") {
      return json(route, labProfiles());
    }
    if (url.pathname === "/api/v1/lab/profiles/runtime/activate") {
      return json(route, labProfiles());
    }
    if (url.pathname === "/api/v1/reports/issues") {
      return json(route, reportCenter());
    }
    if (url.pathname === "/api/v1/requests") {
      return json(route, []);
    }
    if (url.pathname === "/api/v1/workflow-runs") {
      return json(route, []);
    }
    if (url.pathname === "/api/v1/workflows/stages") {
      return json(route, workflowStages());
    }
    if (url.pathname === "/api/v1/workflows/actions") {
      return json(route, [safeAction, destructiveAction, netappSetupPreviewAction, netappNfsReadinessAction, ciscoValidationAction]);
    }
    if (url.pathname === "/api/v1/control/actions") {
      return json(route, controlCatalog());
    }
    if (url.pathname === "/api/v1/lab/build-verification") {
      return json(route, buildVerification());
    }
    if (url.pathname === "/api/v1/lab/validation") {
      return json(route, labValidation());
    }
    if (url.pathname === "/api/v1/lab/vcenter-netapp/readiness") {
      return json(route, { status: "not_checked" });
    }
    if (url.pathname === "/api/v1/lab/firmware-inventory") {
      return json(route, firmwareInventory());
    }
    if (url.pathname === "/api/v1/lab/firmware-compliance") {
      return json(route, firmwareCompliance());
    }
    if (url.pathname === "/api/v1/lab/firmware-waiver-check") {
      return json(route, { checked_at: checkedAt, status: "not_checked", warnings: [], blockers: [] });
    }
    if (url.pathname === "/api/v1/workflows/actions/build-verification.run-full/run") {
      return json(route, workflowActionRun());
    }
    if (url.pathname.endsWith("/runs")) {
      return json(route, []);
    }
    return json(route, {});
  });
}

function json(route: Route, body: unknown) {
  return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
}

function workflowStages() {
  return [
    {
      action_count: 1,
      actions: [safeAction],
      blocked_count: 0,
      current_state: "not_checked",
      dependencies: [],
      desired_state: "All required stages are verified before the run is called complete.",
      label: "Build Verification",
      order: 80,
      primary_action: "build-verification.run-full",
      report_count: 0,
      reports: [],
      secondary_actions: [],
      stage_id: "build-verification"
    },
    {
      action_count: 1,
      actions: [destructiveAction],
      blocked_count: 0,
      current_state: "not_checked",
      dependencies: [],
      desired_state: "Storage layout is planned and validated before ESXi install.",
      label: "RAID",
      order: 50,
      primary_action: "raid.apply",
      report_count: 0,
      reports: [],
      secondary_actions: [],
      stage_id: "raid"
    }
  ];
}

function workflowAction(overrides: Record<string, unknown>) {
  const actionId = String(overrides.action_id);
  const mode = String(overrides.mode);
  const uiRunSupported = Boolean(overrides.ui_run_supported);
  return {
    api_endpoint: null,
    api_method: null,
    blockers: [],
    command: actionId === "raid.apply" ? "HPE_RAID_ALLOW_DESTRUCTIVE=true make provider-lab-hpe-raid-apply" : "make provider-lab-build-verification",
    description: "Mocked registry action for safe action runner UI tests.",
    evidence_artifacts: [],
    inputs: [],
    last_run_report: null,
    last_run_status: "not_checked",
    last_run_trace: {
      action_id: actionId,
      blockers: [],
      command: null,
      finished_at: null,
      freshness: "not_checked",
      next_action: "Run Check from the UI to refresh current state.",
      report_artifacts: [],
      run_id: `not-checked:${actionId}`,
      stage_id: String(overrides.stage),
      started_at: null,
      status: "not_checked",
      source_type: "not_checked",
      summary: "No current run trace has been recorded for this action.",
      warnings: []
    },
    next_action: uiRunSupported ? "Run Check from the UI to refresh current state." : "Requires guarded workflow.",
    outputs: [],
    provider: overrides.provider,
    required_confirmations: mode === "destructive" ? ["APPLY HPE RAID PLAN"] : [],
    required_credentials: [],
    required_gates: [],
    required_mode: mode === "destructive" ? "local-lab-readwrite" : "local-readonly or local-lab-readwrite for live checks",
    reports: [],
    run_endpoint: `/api/v1/workflows/actions/${actionId}/run`,
    runs_endpoint: `/api/v1/workflows/actions/${actionId}/runs`,
    safety_notes: [],
    source_type: "make_target",
    stale_after_seconds: 86400,
    ui_run_blockers: overrides.ui_run_blockers ?? [],
    ui_run_supported: uiRunSupported,
    ...overrides
  };
}

function workflowActionRun() {
  return {
    action_id: "build-verification.run-full",
    action_label: "Run Full Verification",
    blockers: [],
    checked_at: checkedAt,
    command: "make provider-lab-build-verification",
    executed: true,
    finished_at: checkedAt,
    freshness: "current",
    mode: "read_only",
    next_action: "Review evidence artifacts, then continue with the next safe stage.",
    not_mock: true,
    report_artifacts: ["artifacts/codex-runs/build-verification-report.md"],
    return_code: 0,
    run_id: "workflow-action:build-verification.run-full:test",
    source_type: "live_probe",
    stage_id: "build-verification",
    stage_label: "Build Verification",
    started_at: checkedAt,
    status: "completed",
    stderr_summary: "",
    stdout_summary: "verification passed",
    summary: "Safe read-only/report-only action completed.",
    trace_artifact: "artifacts/codex-runs/workflow-action-runs/test.json",
    warnings: []
  };
}

function reportCenter() {
  return {
    checked_at: checkedAt,
    classification_counts: { not_configured_yet: 1, stale_config: 0 },
    counts: { critical: 0, info: 1, success: 1, warning: 1 },
    evidence_artifacts: ["artifacts/codex-runs/validation-evidence.md"],
    issues: [
      {
        auto_fix_action_id: null,
        can_auto_fix: false,
        classification: "not_configured_yet",
        details: {},
        evidence_artifacts: ["artifacts/codex-runs/netapp-live-state-report.md"],
        freshness: "not_checked",
        id: "netapp-not-configured",
        is_current: false,
        is_operator_visible: true,
        last_checked: null,
        linked_page: "/control-center?section=netapp",
        next_action: "Run NetApp setup preview after access is ready.",
        problem: "NetApp is not configured yet.",
        recheck_command: "make provider-lab-netapp-live-state",
        severity: "warning",
        source: "netapp",
        source_action_id: "netapp.setup-preview",
        source_action_label: "Setup Preview",
        source_action_link: "/control-center?section=netapp&action=netapp.setup-preview",
        source_report: "artifacts/codex-runs/netapp-live-state-report.md",
        source_stage: "netapp",
        source_stage_id: "netapp",
        source_stage_label: "NetApp",
        source_type: "not_checked",
        stale_after_seconds: null,
        status: "open",
        summary: "NetApp setup has not been validated.",
        title: "NetApp not configured yet",
        ttl_seconds: null
      }
    ],
    last_reports: {},
    overall_status: "warning",
    page_badges: {
      firmware: { count: 1, critical: 0, default_filter: "firmware", label: "Review", not_configured_yet: 0, page: "firmware", sources: ["firmware"], status: "warning", success: 0, warning: 1 },
      reports: { count: 1, critical: 0, default_filter: "netapp", label: "Review", not_configured_yet: 1, page: "reports", sources: ["netapp"], status: "warning", success: 0, warning: 1 }
    },
    sources: [],
    top_issues: []
  };
}

function buildVerification() {
  return {
    artifacts: { report: "artifacts/codex-runs/build-verification-report.md" },
    blockers: [],
    certification_state: "not_checked",
    checked_at: checkedAt,
    message: "Verification has not run in this mocked UI test.",
    next_safe_action: "Run validation after setup steps are ready.",
    status: "not_checked",
    warnings: []
  };
}

function labValidation() {
  return {
    freshness: "not_checked",
    generated_at: checkedAt,
    handoff_report: "artifacts/codex-runs/lab-validation-handoff-report.md",
    next_action: "Run validation after setup steps are ready.",
    overall_status: "not_checked",
    progress_counts: { blocked: 0, not_configured: 1, partial: 0, ready: 0 },
    proof_links: [
      {
        component_id: "netapp",
        component_label: "NetApp",
        path: "artifacts/codex-runs/netapp-live-state-report.md"
      }
    ],
    source_type: "not_checked",
    top_blocker: null,
    validation_items: [
      {
        blockers: [],
        category: "storage",
        current_state: "Not checked",
        desired_state: "NetApp setup validated",
        evidence_artifacts: ["artifacts/codex-runs/netapp-live-state-report.md"],
        evidence_collapsed_by_default: true,
        freshness: "not_checked",
        id: "netapp",
        label: "NetApp",
        last_checked: null,
        linked_workflow_action: null,
        login_hint: "Use NETAPP_USERNAME with the cluster management URL.",
        management_url: "https://192.168.1.220",
        next_action: "Run setup preview.",
        proof_points: [],
        recheck_command: "make provider-lab-netapp-live-state",
        setup_summary: "NetApp setup is not validated yet.",
        source_type: "not_checked",
        ssh_target: "<username>@192.168.1.220",
        stage: "netapp",
        status: "not_configured",
        warnings: []
      }
    ],
    warnings: []
  };
}

function firmwareInventory() {
  return {
    checked_at: checkedAt,
    firmware_packages: [],
    media_candidates: [],
    packages: [],
    status: "not_checked"
  };
}

function firmwareCompliance() {
  return {
    blockers: [],
    checked_at: checkedAt,
    components: [
      { current_version: "Unknown", device: "iLO", id: "hpe_ilo_firmware", label: "iLO firmware", status: "unknown" },
      { current_version: "Unknown", device: "Cisco", id: "cisco_ios_xe_version", label: "Cisco IOS XE", status: "unknown" },
      { current_version: "Unknown", device: "NetApp", id: "netapp_ontap_version", label: "ONTAP", status: "unknown" },
      { current_version: "Unknown", device: "ESXi", id: "esxi_version", label: "ESXi", status: "unknown" },
      { current_version: "Unknown", device: "HPE", id: "hpe_bios_version", label: "BIOS", status: "unknown" },
      { current_version: "Unknown", device: "HPE", id: "hpe_smart_array_firmware", label: "Smart Array", status: "unknown" }
    ],
    devices: { cisco: { status: "unknown" }, ilo: { status: "unknown" }, netapp: { status: "unknown" } },
    message: "Firmware versions are not checked in this mocked UI test.",
    next_safe_action: "Check firmware inventory.",
    status: "warning",
    warnings: ["Firmware versions unknown."]
  };
}

function labProfiles() {
  const profile = {
    active: true,
    address_plan: {
      ansible_control_host: "192.168.1.205",
      cisco_management: "192.168.1.204",
      esxi_management: "192.168.1.203",
      ilo: "192.168.1.201",
      netapp_cluster_mgmt: "192.168.1.220",
      netapp_controller_a_sp: "192.168.1.210",
      netapp_controller_b_sp: "192.168.1.211",
      netapp_iscsi_lifs: [],
      netapp_nfs_lifs: ["192.168.1.230", "192.168.1.231"],
      netapp_node_a_mgmt: "192.168.1.221",
      netapp_node_b_mgmt: "192.168.1.222",
      netapp_svm_mgmt: "192.168.1.223",
      server_embedded_nic: "192.168.1.202",
      subnet: "192.168.1.0/24"
    },
    created_at: checkedAt,
    description: "Test lab setup",
    global_settings: {
      dns_servers: [],
      domain_name: null,
      gateway: null,
      netapp_disabled_reason: null,
      netapp_enabled: true,
      ntp_servers: [],
      subnet_prefix: 24,
      timezone: null,
      vcenter_enabled: false,
      vlan_id: null,
      mtu: null
    },
    profile_topology: "high_address_lab",
    subnet_cidr: "192.168.1.0/24",
    gateway: null,
    dns: [],
    ntp: [],
    vlan_id: null,
    mtu: null,
    devices: {
      cisco: "192.168.1.204",
      esxi: "192.168.1.203",
      gateway: null,
      ilo: "192.168.1.201",
      netapp: {
        cluster_mgmt: "192.168.1.220",
        nfs_lifs: ["192.168.1.230", "192.168.1.231"]
      },
      utility_vm: "192.168.1.205",
      vcenter: null
    },
    features: {
      build_verification_enabled: true,
      block_legacy_protocols: true,
      disable_ipv6: true,
      enable_dns: true,
      enable_ntp: true,
      enable_snmp: false,
      firmware_gate_enabled: true,
      netapp_disabled_reason: null,
      netapp_enabled: true,
      storage_protocol: "nfs",
      vcenter_disabled_reason: "vCenter is disabled by the active lab setup.",
      vcenter_enabled: false
    },
    resolved_address_plan: {
      ansible_control_host: "192.168.1.205",
      cisco_management: "192.168.1.204",
      esxi_management: "192.168.1.203",
      ilo: "192.168.1.201",
      netapp_cluster_mgmt: "192.168.1.220",
      netapp_controller_a_sp: "192.168.1.210",
      netapp_controller_b_sp: "192.168.1.211",
      netapp_iscsi_lifs: [],
      netapp_nfs_lifs: ["192.168.1.230", "192.168.1.231"],
      netapp_node_a_mgmt: "192.168.1.221",
      netapp_node_b_mgmt: "192.168.1.222",
      netapp_svm_mgmt: "192.168.1.223",
      server_embedded_nic: "192.168.1.202",
      subnet: "192.168.1.0/24"
    },
    not_in_scope_stages: ["vcenter", "vcenter-netapp"],
    mismatch_warnings: [],
    fix_guidance: [],
    history: [],
    id: "runtime",
    last_selected_at: checkedAt,
    name: "Runtime Lab",
    source: "runtime_env",
    updated_at: checkedAt,
    version: 1
  };
  return {
    active_profile: profile,
    active_context: {
      active_profile: profile,
      disabled_features: { vcenter: "vCenter is disabled by the active lab setup." },
      enabled_features: profile.features,
      fix_guidance: [],
      mismatch_warnings: [],
      not_in_scope_stages: ["vcenter", "vcenter-netapp"],
      resolved_address_plan: profile.resolved_address_plan,
      topology: "high_address_lab"
    },
    mock_only: false,
    next_safe_action: "Run Check.",
    profiles: [],
    runtime_profile: profile,
    store_path: ".local/lab-profiles.json",
    subnet_options: []
  };
}

function controlCatalog() {
  const profile = labProfiles().active_profile;
  return {
    actions: [],
    generated_at: checkedAt,
    lab_profile: {
      active_profile_name: "Runtime Lab",
      address_plan: profile.address_plan,
      configured_flags: {},
      edit_profile_path: "/lab-profiles",
      env_update_command: "",
      features: profile.features,
      global_settings: profile.global_settings,
      fix_guidance: [],
      known_lab_profile: {},
      mismatch_warnings: [],
      network: { dns: "192.168.1.1", gateway: "192.168.1.1", mtu: "1500", ntp: "192.168.1.1", vlan_ids: { cisco_management: "10" } },
      not_in_scope_stages: ["vcenter", "vcenter-netapp"],
      source: "runtime_env",
      stale_or_invalid_values: [],
      topology: "high_address_lab",
      version: 1
    },
    provider_mode: "local-lab-readwrite",
    sections: [
      controlSection({
        access_config: {
          blockers: [],
          desired_address_label: "Cluster management",
          desired_management_ip: "192.168.1.220",
          editable_fields: [],
          first_time_configuring: false,
          first_time_note: "First-time setup path.",
          original_dhcp_ip: null,
          password_configured: true,
          password_reference_label: "topsecret-password-ref",
          section_id: "netapp",
          title: "NetApp access",
          access_method: "REST / SSH",
          updated_at: checkedAt,
          username_reference: "operator-admin"
        },
        actions: [],
        current_state: [
          { detail: null, label: "Provider status", status: "not_checked", value: "not_checked" },
          { detail: null, label: "Cluster management", status: null, value: "192.168.1.220" },
          { detail: null, label: "ONTAP", status: "unknown", value: "Unknown" }
        ],
        description: "Minimal NetApp control section.",
        id: "netapp",
        last_result: {
          checked_at: checkedAt,
          label: "Read NetApp State",
          report: "artifacts/codex-runs/netapp-live-state-report.md",
          status: "report_available"
        },
        report_links: [
          {
            label: "NetApp live state",
            path: "artifacts/codex-runs/netapp-live-state-report.md",
            status: "report_available"
          }
        ],
        stage: "NetApp Control",
        status: "ready",
        title: "NetApp Control"
      }),
      controlSection({
        current_state: [
          { detail: null, label: "Status", status: "unknown", value: "not_checked" },
          { detail: null, label: "Cisco IOS XE", status: "unknown", value: "Unknown" }
        ],
        description: "Minimal Cisco control section.",
        id: "cisco",
        stage: "Cisco Control",
        title: "Cisco Control"
      })
    ],
    summary: {}
  };
}

function controlSection(overrides: Record<string, unknown>) {
  return {
    access_config: null,
    actions: [],
    advanced_diagnostics: {},
    current_state: [],
    description: "Mock control section.",
    desired_state: [],
    destructive_actions: [],
    id: "mock",
    last_result: { checked_at: null, label: null, report: null, status: "not_run" },
    plan_diff: [],
    primary_actions: [],
    report_links: [],
    stage: "Mock",
    status: "not_checked",
    title: "Mock",
    upgrade_actions: [],
    ...overrides
  };
}
