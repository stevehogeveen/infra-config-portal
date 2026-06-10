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

test.beforeEach(async ({ page }) => {
  await installApiMocks(page);
});

test("renders Run Check control for a safe read-only action and shows the result", async ({ page }) => {
  await page.goto("/lab-setup?stage=build-verification");

  await expect(page.getByRole("heading", { name: "Lab Setup" })).toBeVisible();
  const safeRow = page.locator(".workflow-action-row", { hasText: "build-verification.run-full" });
  await expect(safeRow.getByRole("button", { name: "Run Verification" })).toBeVisible();

  await safeRow.getByRole("button", { name: "Run Verification" }).click();
  await expect(page.getByText("verify / read_only / live_probe / current")).toBeVisible();
});

test("does not render a run button for a destructive action", async ({ page }) => {
  await page.goto("/control-center?section=action-catalog&action=raid.apply");

  const destructiveRow = page.locator("tr", { hasText: "raid.apply" });
  await expect(destructiveRow.locator(".guarded-workflow-label")).toBeVisible();
  await expect(destructiveRow.getByRole("button", { name: /Run Check|Run Verification|Refresh Status/ })).toHaveCount(0);
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
    if (url.pathname === "/api/v1/reports/issues") {
      return json(route, reportCenter());
    }
    if (url.pathname === "/api/v1/workflows/stages") {
      return json(route, workflowStages());
    }
    if (url.pathname === "/api/v1/workflows/actions") {
      return json(route, [safeAction, destructiveAction]);
    }
    if (url.pathname === "/api/v1/control/actions") {
      return json(route, controlCatalog());
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
    classification_counts: {},
    counts: { critical: 0, info: 0, success: 0, warning: 0 },
    evidence_artifacts: [],
    issues: [],
    last_reports: {},
    overall_status: "success",
    page_badges: {},
    sources: [],
    top_issues: []
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
      netapp_node_a_mgmt: "192.168.1.221",
      netapp_node_b_mgmt: "192.168.1.222",
      netapp_svm_mgmt: "192.168.1.223",
      server_embedded_nic: "192.168.1.202",
      subnet: "192.168.1.0/24"
    },
    created_at: checkedAt,
    description: "Mocked lab profile",
    global_settings: {
      dns_servers: [],
      domain_name: null,
      gateway: null,
      netapp_disabled_reason: null,
      netapp_enabled: true,
      ntp_servers: [],
      subnet_prefix: 24,
      timezone: null
    },
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
    mock_only: false,
    next_safe_action: "Run Check.",
    profiles: [],
    runtime_profile: profile,
    store_path: ".local/lab-profiles.json",
    subnet_options: []
  };
}

function controlCatalog() {
  return {
    actions: [],
    generated_at: checkedAt,
    lab_profile: {
      active_profile_name: "Runtime Lab",
      address_plan: labProfiles().active_profile.address_plan,
      configured_flags: {},
      edit_profile_path: "/lab-profiles",
      env_update_command: "",
      global_settings: labProfiles().active_profile.global_settings,
      known_lab_profile: {},
      network: {},
      source: "runtime_env",
      stale_or_invalid_values: [],
      version: 1
    },
    provider_mode: "local-lab-readwrite",
    sections: [],
    summary: {}
  };
}
