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
  guarded_run_supported: true,
  label: "Apply",
  mode: "destructive",
  provider: "raid",
  required_confirmations: ["APPLY HPE RAID PLAN"],
  required_gates: ["HPE_RAID_ALLOW_DESTRUCTIVE=true"],
  stage: "raid",
  stage_label: "RAID",
  ui_run_supported: false,
  ui_run_blockers: ["guarded workflow requires exact confirmation phrase: APPLY HPE RAID PLAN"]
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

const ciscoFirmwareAction = workflowAction({
  action_id: "cisco.firmware-inventory",
  category: "inventory",
  current_availability: "available",
  label: "Cisco Firmware Inventory",
  mode: "read_only",
  provider: "cisco",
  stage: "cisco",
  stage_label: "Cisco",
  ui_run_supported: true
});

const ciscoBootstrapAction = workflowAction({
  action_id: "cisco.apply-bootstrap",
  category: "apply",
  current_availability: "manual_command_required",
  guarded_run_supported: true,
  label: "Apply Bootstrap",
  mode: "write",
  provider: "cisco",
  required_confirmations: ["APPLY CISCO CONSOLE BOOTSTRAP 192.168.1.204"],
  required_gates: ["CISCO_CONSOLE_APPLY_ENABLED=true", "LAB_APPLY_ACK=YES", "LAB_TARGET_ACK=192.168.1.204"],
  stage: "cisco",
  stage_label: "Cisco Control",
  ui_run_supported: false,
  ui_run_blockers: ["guarded workflow requires exact confirmation phrase: APPLY CISCO CONSOLE BOOTSTRAP 192.168.1.204"]
});

const iloVirtualMediaAction = workflowAction({
  action_id: "ilo.virtual-media-insert",
  category: "install",
  current_availability: "manual_command_required",
  guarded_run_supported: true,
  label: "Virtual Media Insert",
  mode: "write",
  provider: "ilo-redfish",
  required_confirmations: ["INSERT ESXI VIRTUAL MEDIA"],
  stage: "ilo",
  stage_label: "HPE / iLO Control",
  ui_run_supported: false,
  ui_run_blockers: ["guarded workflow requires exact confirmation phrase: INSERT ESXI VIRTUAL MEDIA"]
});

const esxiRebuildAction = workflowAction({
  action_id: "esxi.rebuild-install",
  category: "install",
  current_availability: "manual_command_required",
  guarded_run_supported: true,
  label: "Rebuild / Install",
  mode: "destructive",
  provider: "esxi",
  required_confirmations: ["REBUILD ESXI HOST"],
  required_gates: ["LAB_ALLOW_POWER_ACTIONS=true"],
  stage: "esxi",
  stage_label: "ESXi Control",
  ui_run_supported: false,
  ui_run_blockers: ["guarded workflow requires exact confirmation phrase: REBUILD ESXI HOST"]
});

const netappFirmwareAction = workflowAction({
  action_id: "netapp.ontap-upgrade-inventory",
  blockers: ["not configured yet"],
  category: "inventory",
  current_availability: "blocked",
  label: "ONTAP Upgrade Inventory",
  mode: "read_only",
  provider: "netapp-ontap",
  stage: "netapp",
  stage_label: "NetApp",
  ui_run_supported: false,
  ui_run_blockers: ["not configured yet"]
});

const netappSetupApplyAction = workflowAction({
  action_id: "netapp.setup-apply",
  category: "apply",
  current_availability: "manual_command_required",
  guarded_run_supported: true,
  label: "Apply Setup",
  mode: "write",
  provider: "netapp-ontap",
  required_confirmations: ["APPLY NETAPP CLUSTER SETUP"],
  required_gates: ["NETAPP_SETUP_APPLY=true"],
  stage: "netapp",
  stage_label: "NetApp",
  ui_run_supported: false,
  ui_run_blockers: ["guarded workflow requires exact confirmation phrase: APPLY NETAPP CLUSTER SETUP"]
});

const firmwareUpgradePlanAction = workflowAction({
  action_id: "firmware.upgrade-plan",
  category: "plan",
  current_availability: "available",
  label: "Plan Upgrade",
  mode: "read_only",
  provider: "firmware",
  stage: "firmware-upgrade",
  stage_label: "Firmware / Upgrade Center",
  ui_run_supported: true
});

const firmwareUpgradeApplyPlaceholderAction = workflowAction({
  action_id: "firmware.upgrade-apply-placeholder",
  blockers: ["requires guarded firmware update workflow"],
  category: "upgrade",
  current_availability: "manual_command_required",
  label: "Run Upgrade Placeholder",
  mode: "upgrade",
  provider: "firmware",
  guarded_run_blockers: ["No guarded UI runner allowlist entry exists for this action yet."],
  guarded_run_supported: false,
  required_confirmations: ["RUN FIRMWARE UPGRADE"],
  required_gates: ["LAB_ALLOW_FIRMWARE_UPDATES=true"],
  stage: "firmware-upgrade",
  stage_label: "Firmware / Upgrade Center",
  ui_run_supported: false,
  ui_run_blockers: ["requires guarded firmware update workflow"]
});

const netappOntapUpgradeApplyAction = workflowAction({
  action_id: "netapp.ontap-upgrade-apply",
  category: "upgrade",
  current_availability: "manual_command_required",
  guarded_run_supported: true,
  label: "Upgrade ONTAP",
  mode: "upgrade",
  provider: "netapp-ontap",
  required_confirmations: ["UPGRADE ONTAP"],
  required_gates: ["NETAPP_ONTAP_UPGRADE_APPLY=true"],
  stage: "netapp",
  stage_label: "NetApp",
  ui_run_supported: false,
  ui_run_blockers: ["guarded workflow requires exact confirmation phrase: UPGRADE ONTAP"]
});

test.beforeEach(async ({ page }) => {
  await installApiMocks(page);
});

test("renders the new top-level navigation and pages", async ({ page }) => {
  await page.goto("/overview");

  await expect(page.locator("nav .nav-item-label")).toHaveText([
    "Overview",
    "Network",
    "Server",
    "Storage",
    "Virtualization",
    "Firmware Upgrades",
    "Validation",
    "Settings"
  ]);

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.goto("/lab-setup");
  await expect(page).toHaveURL(/\/overview/);
  await page.goto("/network");
  await expect(page.getByRole("heading", { name: "Network" })).toBeVisible();
  await page.goto("/server");
  await expect(page.getByRole("heading", { name: "Server" })).toBeVisible();
  await page.goto("/storage");
  await expect(page.getByRole("heading", { name: "Storage" })).toBeVisible();
  await page.goto("/virtualization");
  await expect(page.getByRole("heading", { name: "Virtualization" })).toBeVisible();
  await page.goto("/firmware-upgrades");
  await expect(page.getByRole("heading", { name: "Firmware Upgrades" })).toBeVisible();
  await page.goto("/validation");
  await expect(page.getByRole("heading", { name: "Validation", exact: true })).toBeVisible();
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

  await page.goto("/control-center");
  await expect(page).toHaveURL(/\/overview/);
});

test("overview shows active setup, lab values, and access without dashboard clutter", async ({ page }) => {
  await page.goto("/overview");

  await expect(page.getByRole("heading", { name: "Active lab setup" })).toBeVisible();
  await expect(page.getByText("Runtime Lab").first()).toBeVisible();
  await expect(page.getByText("192.168.1.0/24").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit Config" }).first()).toBeVisible();

  await expect(page.getByRole("heading", { name: "Lab Values" })).toBeVisible();
  await expect(page.getByText("Cisco IP").first()).toBeVisible();
  await expect(page.getByText("192.168.1.204").first()).toBeVisible();
  await expect(page.getByText("iLO IP").first()).toBeVisible();
  await expect(page.getByText("192.168.1.201").first()).toBeVisible();
  await expect(page.getByText("ESXi IP").first()).toBeVisible();
  await expect(page.getByText("192.168.1.203").first()).toBeVisible();
  await expect(page.getByText("NetApp cluster IP").first()).toBeVisible();
  await expect(page.getByText("192.168.1.220").first()).toBeVisible();
  await expect(page.getByText("vCenter IP").first()).toBeVisible();
  await expect(page.getByText("192.168.1.206").first()).toBeVisible();
  await expect(page.getByText("netapp_nfs_ds01").first()).toBeVisible();

  await expect(page.getByRole("heading", { name: "Currently Accessible" })).toBeVisible();
  await expect(page.getByRole("row", { name: /Cisco/ })).toContainText(/Accessible|Needs credentials|Needs console/);
  await expect(page.getByRole("row", { name: /iLO/ })).toContainText(/Accessible|Needs credentials/);
  await expect(page.getByRole("row", { name: /NetApp/ })).toContainText(/Accessible|Need NetApp API reachable|Needs credentials/);
  await expect(page.getByText(/what is healthy/i)).toHaveCount(0);
  await expect(page.getByText(/what is next/i)).toHaveCount(0);
  await expect(page.getByText("Artifact")).toHaveCount(0);
});

test("each domain page exposes relevant run test or apply buttons", async ({ page }) => {
  const pages = [
    ["/overview", /Refresh Access|Edit Config/],
    ["/network", /Test Switch|Save Config|Scan Firmware/],
    ["/server", /Test iLO|Test ESXi|Recover ESXi|Validate RAID/],
    ["/storage", /Test NetApp|Validate NFS|Mount Datastore/],
    ["/virtualization", /Test vCenter|Deploy VM|Validate Inventory/],
    ["/firmware-upgrades", /Rescan Files|Scan Firmware|Validate Upgrade Path|Upgrade/],
    ["/validation", /Run Validation|Generate Handoff/],
    ["/settings", /Save Setup|Test Credentials|Refresh Consoles/]
  ] as const;

  for (const [path, buttonName] of pages) {
    await page.goto(path);
    await expect(page.getByRole("button", { name: buttonName }).first()).toBeVisible();
  }
});

test("advanced proof is collapsed and operator labels hide raw statuses", async ({ page }) => {
  await page.goto("/validation");

  const advanced = page.locator("details.advanced-drawer").first();
  await expect(advanced).not.toHaveAttribute("open", "");
  await expect(page.getByText("Golden State", { exact: true })).toBeVisible();
  await expect(page.getByText("Expected working lab state.").first()).toBeVisible();
  await expect(page.getByText("Different from expected")).toBeVisible();
  await expect(page.getByText("Artifact")).toHaveCount(0);
  await expect(page.getByText("manual_review")).toHaveCount(0);
  await expect(page.getByText("not_configured_yet")).toHaveCount(0);

  await page.goto("/settings");
  await expect(page.getByText("Real lab").first()).toBeVisible();
  await expect(page.getByText("local-lab-readwrite")).toHaveCount(0);
});

test("firmware table renders upgrade path states", async ({ page }) => {
  await page.goto("/firmware-upgrades");

  await expect(page.getByRole("heading", { name: "Firmware Files" })).toBeVisible();
  await expect(page.getByText("/home/administrator/infra-config-portal/artifacts/Media")).toBeVisible();
  await expect(page.getByRole("button", { name: "Rescan Files" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Media Inventory" })).toBeVisible();

  const ciscoRow = page.getByRole("row", { name: /Cisco Switch.*IOS XE/ });
  await expect(ciscoRow).toHaveCount(1);
  await expect(ciscoRow).toContainText("17.15.05");
  await expect(ciscoRow).toContainText("Needs review");
  await expect(ciscoRow).toContainText("cat9k_iosxe.17.15.05.SPA.bin");
  await expect(ciscoRow).toContainText("Auto-selected");
  await ciscoRow.getByRole("combobox").selectOption("cat9k_iosxe.17.12.01.SPA.bin");
  await expect(ciscoRow).toContainText("cat9k_iosxe.17.12.01.SPA.bin");
  await expect(ciscoRow).toContainText("Selected by user");
  await expect(ciscoRow.getByRole("button", { name: "Scan" })).toBeVisible();
  await expect(ciscoRow.getByRole("button", { name: "Validate Path" })).toBeVisible();
  await expect(ciscoRow.getByRole("button", { name: "Upgrade" })).toBeDisabled();

  await expect(page.getByRole("row", { name: /HPE Server.*Service Pack \/ Smart Array/ })).toContainText("SPP2024.03.00.iso");
  await expect(page.getByRole("row", { name: /NetApp.*ONTAP/ })).toHaveCount(1);
  const advanced = page.locator("details.advanced-drawer").first();
  await expect(advanced).not.toHaveAttribute("open", "");
  await expect(page.getByText("artifacts/codex-runs/cisco-firmware-inventory-report.md")).toHaveCount(0);
});

test("settings uses active lab setup values and never renders secret material", async ({ page }) => {
  await page.goto("/settings");

  await expect(page.getByText("Runtime Lab").first()).toBeVisible();
  await expect(page.getByText("192.168.1.201").first()).toBeVisible();
  await expect(page.getByText("192.168.1.204").first()).toBeVisible();
  await expect(page.getByText("192.168.1.203").first()).toBeVisible();
  await expect(page.getByText("192.168.1.220").first()).toBeVisible();
  await expect(page.getByText("Configured or missing only")).toBeVisible();
  await expect(page.getByText("Secret values are hidden")).toHaveCount(0);
  await expect(page.locator("input[type='password']")).toHaveCount(0);
});

test("safe read-only page action still invokes the workflow runner", async ({ page }) => {
  await page.goto("/validation");

  const runResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/build-verification.run-full/run")
  );
  await page.getByRole("button", { name: "Run Validation" }).click();
  await expect((await runResponse).ok()).toBeTruthy();
  await expect(page.getByText(/Run Full Verification:/)).toBeVisible();
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
      return json(route, workflowActions());
    }
    if (url.pathname === "/api/v1/control/actions") {
      return json(route, controlCatalog());
    }
    if (url.pathname === "/api/v1/providers/status") {
      return json(route, providerStatuses());
    }
    if (url.pathname === "/api/v1/providers/cisco/setup-readiness") {
      return json(route, ciscoSetupReadiness());
    }
    if (url.pathname === "/api/v1/providers/ilo-redfish/hpe-raid-plan-preview") {
      return json(route, hpeRaidPlanPreview());
    }
    if (url.pathname === "/api/v1/providers/ilo-redfish/esxi-install-readiness") {
      return json(route, esxiInstallReadiness());
    }
    if (url.pathname === "/api/v1/providers/netapp-ontap/plan-preview") {
      return json(route, netappPlanPreview());
    }
    if (url.pathname === "/api/v1/providers/netapp-ontap/console-readiness") {
      return json(route, netappConsoleReadiness());
    }
    if (url.pathname === "/api/v1/providers/netapp-ontap/nfs-vcenter-readiness") {
      return json(route, netappNfsVcenterReadiness());
    }
    if (url.pathname === "/api/v1/lab/build-verification") {
      return json(route, buildVerification());
    }
    if (url.pathname === "/api/v1/lab/validation") {
      return json(route, labValidation());
    }
    if (url.pathname === "/api/v1/lab/validation/handoff") {
      return json(route, labValidation());
    }
    if (url.pathname === "/api/v1/lab/vcenter-netapp/readiness") {
      return json(route, vcenterNetappReadiness());
    }
    if (url.pathname === "/api/v1/lab/vcenter/install-readiness") {
      return json(route, vcenterInstallReadiness());
    }
    if (url.pathname === "/api/v1/lab/vcenter/post-attach-validation") {
      return json(route, vcenterPostAttachValidation());
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
    if (url.pathname === "/api/v1/firmware/summary") {
      return json(route, firmwareSummaries());
    }
    if (url.pathname === "/api/v1/media-inventory") {
      return json(route, mediaInventory());
    }
    if (url.pathname === "/api/v1/workflows/actions/build-verification.run-full/run") {
      return json(route, workflowActionRun());
    }
    if (url.pathname.endsWith("/run")) {
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
    guarded_run_blockers: overrides.guarded_run_blockers ?? [],
    guarded_run_supported: Boolean(overrides.guarded_run_supported),
    ui_run_blockers: overrides.ui_run_blockers ?? [],
    ui_run_supported: uiRunSupported,
    ...overrides
  };
}

function workflowActions() {
  return [
    safeAction,
    destructiveAction,
    netappSetupPreviewAction,
    netappNfsReadinessAction,
    ciscoValidationAction,
    ciscoFirmwareAction,
    ciscoBootstrapAction,
    iloVirtualMediaAction,
    esxiRebuildAction,
    netappFirmwareAction,
    netappSetupApplyAction,
    firmwareUpgradePlanAction,
    firmwareUpgradeApplyPlaceholderAction,
    netappOntapUpgradeApplyAction,
    readAction("cisco.setup-readiness", "Test Cisco Access", "cisco", "cisco"),
    readAction("cisco.discover-console", "Refresh Cisco Console", "cisco", "cisco"),
    readAction("ilo.reachability", "Test iLO", "ilo", "ilo-redfish"),
    readAction("ilo.auth", "Test iLO Auth", "ilo", "ilo-redfish"),
    readAction("esxi.management-validation", "Test ESXi", "esxi", "esxi"),
    readAction("esxi.ssh-api-check", "Test ESXi SSH/API", "esxi", "esxi"),
    readAction("raid.validate", "Validate RAID", "raid", "ilo-redfish"),
    readAction("netapp.live-state", "Test NetApp", "netapp", "netapp-ontap"),
    readAction("netapp.nfs-setup-validate", "Validate NFS", "netapp", "netapp-ontap"),
    readAction("netapp.console-autodiscovery", "Refresh NetApp Consoles", "netapp", "netapp-ontap"),
    readAction("netapp.component-firmware-inventory", "Refresh ONTAP", "netapp", "netapp-ontap"),
    readAction("vcenter-netapp.readiness", "Test vCenter", "vcenter", "vcenter"),
    readAction("vcenter.post-attach-validation", "Validate Datastore", "vcenter", "vcenter"),
    readAction("esxi.vm-deploy-validate", "Validate VM Inventory", "esxi", "esxi"),
    readAction("firmware.inventory", "Scan All Firmware", "firmware-upgrade", "firmware"),
    readAction("lab-validation.summary", "Refresh Evidence", "validation", "lab-validation"),
    writeAction("cisco.save-config", "Save Config", "cisco", "cisco"),
    writeAction("esxi.recover-management", "Recover ESXi", "esxi", "esxi"),
    writeAction("esxi.netapp-datastore-apply", "Mount Datastore", "esxi", "esxi"),
    writeAction("vcenter.attach-esxi-apply", "Attach ESXi", "vcenter", "vcenter"),
    writeAction("esxi.vm-deploy-apply", "Deploy VM", "esxi", "esxi")
  ];
}

function readAction(action_id: string, label: string, stage: string, provider: string) {
  return workflowAction({
    action_id,
    category: "verify",
    current_availability: "available",
    label,
    mode: "read_only",
    provider,
    stage,
    stage_label: label,
    ui_run_supported: true
  });
}

function writeAction(action_id: string, label: string, stage: string, provider: string) {
  return workflowAction({
    action_id,
    category: "apply",
    current_availability: "manual_command_required",
    guarded_run_supported: true,
    label,
    mode: "write",
    provider,
    required_confirmations: [`CONFIRM ${label.toUpperCase()}`],
    stage,
    stage_label: label,
    ui_run_supported: false,
    ui_run_blockers: ["guarded workflow requires confirmation"]
  });
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
    certification_state: "ready",
    checked_at: checkedAt,
    message: "Build verification is ready in this mocked UI test.",
    next_safe_action: "Generate handoff.",
    status: "ready",
    warnings: []
  };
}

function providerStatuses() {
  return [
    providerStatus("cisco-console", "Cisco", "network", "ready"),
    providerStatus("ilo-redfish", "HPE iLO", "server", "ready"),
    providerStatus("esxi-readonly", "ESXi", "virtualization", "ready"),
    providerStatus("netapp-ontap", "NetApp ONTAP", "storage", "ready")
  ];
}

function providerStatus(id: string, name: string, kind: string, status: string) {
  return {
    blockers: [],
    capabilities: [],
    checked_at: checkedAt,
    configuration: {},
    disabled_actions: [],
    discovery: null,
    evidence_artifacts: [],
    freshness: "live",
    id,
    is_current: true,
    is_operator_visible: true,
    kind,
    last_probe_result: null,
    last_probe_time: checkedAt,
    message: `${name} is ready.`,
    mode: "local-lab-readwrite",
    name,
    recheck_command: null,
    safe_actions: [],
    source_type: "live_cached",
    stale_after_seconds: 86400,
    status,
    ttl_seconds: null,
    warnings: []
  };
}

function ciscoSetupReadiness() {
  return {
    blockers: [],
    bootstrap_preview: { apply_enabled: false, commands_redacted: true, missing_requirements: [], redacted_command_summary: [], serial_writes_attempted: false, summary: [] },
    console: {
      baud: 9600,
      candidate_count: 1,
      effective_path: "/dev/ttyUSB0",
      fallback_candidate_count: 0,
      last_prompt_readiness: {},
      read_timing: {},
      recommended_path: "/dev/ttyUSB0",
      safe_next_action: "Test Cisco access.",
      selected_path: "/dev/ttyUSB0",
      selection_source: "discovered",
      stable_candidate_count: 1,
      status: "ready"
    },
    disabled_actions: [],
    ethernet_readiness: {},
    management_configured: true,
    next_safe_action: "Cisco access is ready.",
    password_recovery: {},
    phase: "ready",
    planned_management_ip: "192.168.1.204",
    provider_id: "cisco",
    real_lab_run: { prompt_state: "privileged-exec" },
    setup_wizard_plan: null,
    ssh_scp_readiness: { apply_enabled: false, planned_only: false, summary: "SSH and SCP are ready." },
    state_boundaries: {},
    warnings: []
  };
}

function hpeRaidPlanPreview() {
  return {
    apply_enabled: false,
    blockers: [],
    checked_at: checkedAt,
    current_layout: {
      controllers: [{ Model: "HPE Smart Array P408i-a SR Gen10" }]
    },
    desired_intent: { volumes: [{ name: "esxi-os", purpose: "ESXi boot", raid_level: "RAID1" }, { name: "datastore", purpose: "VM datastore", raid_level: "RAID6" }] },
    destructive_actions_enabled: false,
    destructive_actions_requested: false,
    message: "RAID layout is ready.",
    planned_layout: {},
    provider_id: "ilo-redfish",
    status: "ready",
    warnings: []
  };
}

function esxiInstallReadiness() {
  return {
    blockers: [],
    checked_at: checkedAt,
    message: "ESXi target is ready.",
    next_safe_action: "Validate ESXi after any server change.",
    provider_id: "esxi",
    status: "ready",
    warnings: []
  };
}

function netappPlanPreview() {
  return {
    apply_enabled: false,
    blockers: [],
    checked_at: checkedAt,
    message: "NetApp and NFS are ready.",
    next_safe_action: "Validate NFS handoff.",
    provider_id: "netapp-ontap",
    status: "ready",
    warnings: []
  };
}

function netappConsoleReadiness() {
  return {
    blockers: [],
    checked_at: checkedAt,
    message: "NetApp console is ready.",
    provider_id: "netapp-ontap",
    runtime_state: { console: "/dev/ttyUSB1" },
    status: "ready",
    warnings: []
  };
}

function netappNfsVcenterReadiness() {
  return {
    apply_enabled: false,
    blockers: [],
    checked_at: checkedAt,
    message: "NetApp NFS datastore is ready.",
    next_safe_action: "Mount datastore only through guarded apply.",
    planned_nfs: {
      datastore_name: "netapp_nfs_ds01",
      export_policy: "esxi_ro_rw",
      volume: "esxi_datastore_01"
    },
    provider_id: "netapp-ontap",
    status: "ready",
    warnings: []
  };
}

function vcenterNetappReadiness() {
  return {
    action: "vcenter-netapp-readiness",
    apply_enabled: false,
    blockers: [],
    checked_at: checkedAt,
    checks: {
      datastore_mounted: { status: "ready", visible: true },
      netapp_datastore_visible: { status: "ready", visible: true },
      vm_inventory_visible: { status: "ready", visible: true }
    },
    credential_state: {
      netapp_credentials_configured: true,
      vcenter_credentials_configured: true,
      vcenter_host_configured: true
    },
    current_state: { vcenter_version: "8.0.3" },
    freshness: "live",
    message: "vCenter is deployed, ESXi is attached, and netapp_nfs_ds01 is visible through vCenter.",
    next_safe_action: "No vCenter-NetApp datastore action required.",
    provider_id: "vcenter-netapp",
    source_type: "live_cached",
    status: "ready",
    targets: {
      datastore_name: "netapp_nfs_ds01",
      esxi_management: "192.168.1.203",
      netapp_cluster_management: "192.168.1.220",
      netapp_nfs_lif: "192.168.1.230",
      vcenter: "https://192.168.1.206/sdk",
      vcenter_management_ip: "192.168.1.206"
    },
    warnings: []
  };
}

function vcenterInstallReadiness() {
  return {
    blockers: [],
    checked_at: checkedAt,
    credential_state: {
      deployment_credentials_configured: true,
      esxi_credentials_configured: true
    },
    deployment_values: {
      complete: true,
      datastore_target: "netapp_nfs_ds01",
      management_ip: "192.168.1.206"
    },
    message: "vCenter install values are complete.",
    provider_id: "vcenter",
    status: "ready",
    warnings: []
  };
}

function vcenterPostAttachValidation() {
  return {
    blockers: [],
    checked_at: checkedAt,
    checks: {
      netapp_datastore_visible: { status: "ready", visible: true },
      vm_inventory_visible: { status: "ready", visible: true }
    },
    message: "vCenter post-attach validation is ready.",
    post_attach_state: { ready: true },
    provider_id: "vcenter",
    status: "ready",
    warnings: []
  };
}

function labValidation() {
  return {
    freshness: "live",
    generated_at: checkedAt,
    handoff_report: "artifacts/codex-runs/lab-validation-handoff-report.md",
    next_action: "Review the firmware manual baseline, then generate handoff.",
    overall_status: "ready",
    progress_counts: { blocked: 0, not_configured: 0, partial: 0, ready: 5 },
    proof_links: [
      { component_id: "cisco", component_label: "Cisco", path: "artifacts/codex-runs/cisco-validation-report.md" },
      { component_id: "ilo", component_label: "iLO", path: "artifacts/codex-runs/ilo-validation-report.md" },
      { component_id: "esxi", component_label: "ESXi", path: "artifacts/codex-runs/esxi-validation-report.md" },
      { component_id: "netapp", component_label: "NetApp", path: "artifacts/codex-runs/netapp-live-state-report.md" },
      { component_id: "vcenter", component_label: "vCenter", path: "artifacts/codex-runs/vcenter-post-attach-validation-report.md" }
    ],
    source_type: "live_cached",
    top_blocker: null,
    validation_items: [
      validationItem("cisco", "Cisco", "network", "Switch access is ready.", "https://192.168.1.204"),
      validationItem("ilo", "HPE iLO", "server", "iLO access is ready.", "https://192.168.1.201"),
      validationItem("esxi", "ESXi host", "virtualization", "ESXi management is ready.", "https://192.168.1.203"),
      validationItem("netapp", "NetApp", "storage", "NetApp NFS datastore is ready.", "https://192.168.1.220"),
      validationItem("vcenter-netapp-datastore", "vCenter", "virtualization", "vCenter sees netapp_nfs_ds01.", "https://192.168.1.206/sdk")
    ],
    warnings: []
  };
}

function validationItem(id: string, label: string, category: string, summary: string, managementUrl: string) {
  return {
    blockers: [],
    category,
    current_state: "Ready",
    desired_state: "Ready",
    evidence_artifacts: [`artifacts/codex-runs/${id}-proof.md`],
    evidence_collapsed_by_default: true,
    freshness: "live",
    id,
    label,
    last_checked: checkedAt,
    linked_workflow_action: null,
    login_hint: `Use configured ${label} credentials.`,
    management_url: managementUrl,
    next_action: "No action required.",
    proof_points: [summary],
    recheck_command: "make provider-lab-build-verification",
    setup_summary: summary,
    source_type: "live_cached",
    ssh_target: null,
    stage: id,
    status: "ready",
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

function mediaInventory() {
  return {
    configured_directories: ["/home/administrator/infra-config-portal/artifacts/Media"],
    items: [
      {
        actual_name_redacted: false,
        category: "firmware",
        confidence: "high",
        detected_product: "cisco-ios-xe",
        detected_vendor: "Cisco",
        detected_version: "17.15.05",
        extension: ".bin",
        file_name: "cat9k_iosxe.17.15.05.SPA.bin",
        file_path: "/home/administrator/infra-config-portal/artifacts/Media/cat9k_iosxe.17.15.05.SPA.bin",
        generation_hints: ["9300"],
        placeholder_name: "cisco-ios-xe-firmware.bin",
        product_hints: ["cisco", "ios-xe"],
        size_bytes: 1024,
        source: "local",
        version_hint: "17.15.05"
      }
    ],
    mode: "configured",
    warnings: []
  };
}

function firmwareCompliance() {
  return {
    blockers: [],
    checked_at: checkedAt,
    components: [
      { current_version: "Unknown", device: "iLO", id: "hpe_ilo_firmware", label: "iLO firmware", status: "unknown" },
      { current_version: "17.15.05", device: "Cisco", id: "cisco_ios_xe_version", label: "Cisco IOS XE", status: "passed" },
      { current_version: "Unknown", device: "NetApp", id: "netapp_ontap_version", label: "ONTAP", status: "unknown" },
      { current_version: "Unknown", device: "ESXi", id: "esxi_version", label: "ESXi", status: "unknown" },
      { current_version: "Unknown", device: "HPE", id: "hpe_bios_version", label: "BIOS", status: "unknown" },
      { current_version: "Unknown", device: "HPE", id: "hpe_smart_array_firmware", label: "Smart Array", status: "unknown" }
    ],
    devices: { cisco: { status: "unknown" }, ilo: { status: "unknown" }, netapp: { status: "unknown" } },
    inventory: {
      media_inventory: {
        candidate_count: 3,
        candidates: [
          {
            file_name: "cat9k_iosxe.17.15.05.SPA.bin",
            file_path: "/home/administrator/infra-config-portal/artifacts/Media/cat9k_iosxe.17.15.05.SPA.bin",
            detected_vendor: "Cisco",
            detected_product: "cisco-ios-xe",
            detected_version: "17.15.05",
            confidence: "high"
          },
          {
            file_name: "cat9k_iosxe.17.12.01.SPA.bin",
            file_path: "/home/administrator/infra-config-portal/artifacts/Media/cat9k_iosxe.17.12.01.SPA.bin",
            detected_vendor: "Cisco",
            detected_product: "cisco-ios-xe",
            detected_version: "17.12.01",
            confidence: "medium"
          },
          {
            file_name: "ontap-9.14.1.tgz",
            file_path: "/home/administrator/infra-config-portal/artifacts/Media/ontap-9.14.1.tgz",
            detected_vendor: "NetApp",
            detected_product: "netapp-ontap",
            detected_version: "9.14.1",
            confidence: "high"
          }
        ]
      }
    },
    message: "Firmware versions are not checked in this mocked UI test.",
    next_safe_action: "Check firmware inventory.",
    status: "warning",
    warnings: ["Firmware versions unknown."]
  };
}

function firmwareSummaries() {
  return [
    {
      approved_versions: [
        { label: "Cisco IOS XE", status: "minimum", version: ">= 17.9" },
        { label: "ROMMON", status: "manual_review", version: null }
      ],
      blocker: "ROMMON baseline missing/manual review",
      compliance_status: "cannot_verify",
      component_type: "network_os",
      current_versions: [
        { label: "Cisco IOS XE", status: "passed", version: "17.15.05" },
        { label: "ROMMON", status: "warning", version: null }
      ],
      device_id: "cisco",
      evidence_artifacts: ["artifacts/codex-runs/cisco-firmware-inventory-report.md"],
      freshness: "live",
      label: "Cisco",
      last_scanned: checkedAt,
      next_action: "Open Firmware Upgrades and record the manual baseline decision.",
      path_status: "manual_review",
      package_available: true,
      package_name: "cisco-ios-xe-firmware.bin",
      prechecks_required: ["Manual ROMMON baseline review"],
      required_intermediate_versions: [],
      reboot_required: true,
      scan_action_id: "cisco.firmware-inventory",
      severity: "yellow",
      source_type: "cached_live",
      target_version: ">= 17.9",
      upgrade_center_link: "/firmware?device=cisco",
      upgrade_paths: [
        {
          apply_enabled: false,
          baseline_source: "manual",
          candidate_files: [
            {
              confidence: "high",
              detected_product: "cisco-ios-xe",
              detected_vendor: "Cisco",
              detected_version: "17.15.05",
              file_name: "cat9k_iosxe.17.15.05.SPA.bin",
              file_path: "/home/administrator/infra-config-portal/artifacts/Media/cat9k_iosxe.17.15.05.SPA.bin"
            },
            {
              confidence: "medium",
              detected_product: "cisco-ios-xe",
              detected_vendor: "Cisco",
              detected_version: "17.12.01",
              file_name: "cat9k_iosxe.17.12.01.SPA.bin",
              file_path: "/home/administrator/infra-config-portal/artifacts/Media/cat9k_iosxe.17.12.01.SPA.bin"
            }
          ],
          component_id: "cisco_ios_xe_version",
          component_label: "Cisco IOS XE",
          current_version: "17.15.05",
          device_label: "Cisco",
          disabled_reason: "Manual ROMMON baseline review is still required.",
          equipment_label: "Cisco Switch",
          equipment_type: "network_os",
          estimated_impact: "Switch reload may be required.",
          evidence_artifacts: ["artifacts/codex-runs/cisco-firmware-inventory-report.md"],
          freshness: "live",
          last_checked: checkedAt,
          missing_evidence: ["ROMMON baseline"],
          next_action: "Review manual baseline before applying upgrades.",
          package_available: true,
          package_name: "cisco-ios-xe-firmware.bin",
          package_version: "17.15.05",
          path_status: "manual_review",
          prechecks_required: ["Manual ROMMON baseline review"],
          reboot_required: true,
          required_intermediate_versions: [],
          scan_action_id: "cisco.firmware-inventory",
          selected_file_name: "cat9k_iosxe.17.15.05.SPA.bin",
          selected_file_path: "/home/administrator/infra-config-portal/artifacts/Media/cat9k_iosxe.17.15.05.SPA.bin",
          selection_source: "auto",
          source_type: "cached_live",
          target_version: ">= 17.9"
        }
      ]
    },
    {
      approved_versions: [{ label: "ONTAP", status: "minimum", version: ">= 9.14" }],
      blocker: null,
      compliance_status: "ready",
      component_type: "storage_os_and_component_firmware",
      current_versions: [{ label: "ONTAP", status: "passed", version: "9.14.1" }],
      device_id: "netapp",
      evidence_artifacts: ["artifacts/codex-runs/netapp-upgrade-inventory-report.md"],
      freshness: "live",
      label: "NetApp",
      last_scanned: checkedAt,
      next_action: "No upgrade required.",
      path_status: "current",
      package_available: true,
      package_name: "netapp-ontap-upgrade.tgz",
      prechecks_required: [],
      required_intermediate_versions: [],
      reboot_required: false,
      scan_action_id: "netapp.ontap-upgrade-inventory",
      severity: "green",
      source_type: "cached_live",
      target_version: ">= 9.14",
      upgrade_center_link: "/firmware?device=netapp",
      upgrade_paths: [
        {
          apply_enabled: false,
          baseline_source: "approved",
          candidate_files: [
            {
              confidence: "high",
              detected_product: "netapp-ontap",
              detected_vendor: "NetApp",
              detected_version: "9.14.1",
              file_name: "ontap-9.14.1.tgz",
              file_path: "/home/administrator/infra-config-portal/artifacts/Media/ontap-9.14.1.tgz"
            }
          ],
          component_id: "netapp_ontap_version",
          component_label: "ONTAP",
          current_version: "9.14.1",
          device_label: "NetApp",
          disabled_reason: "Already current.",
          equipment_label: "NetApp",
          equipment_type: "storage_os",
          estimated_impact: "None",
          evidence_artifacts: ["artifacts/codex-runs/netapp-upgrade-inventory-report.md"],
          freshness: "live",
          last_checked: checkedAt,
          missing_evidence: [],
          next_action: "No upgrade required.",
          package_available: true,
          package_name: "netapp-ontap-upgrade.tgz",
          package_version: "9.14.1",
          path_status: "current",
          prechecks_required: [],
          reboot_required: false,
          required_intermediate_versions: [],
          scan_action_id: "netapp.ontap-upgrade-inventory",
          selected_file_name: "ontap-9.14.1.tgz",
          selected_file_path: "/home/administrator/infra-config-portal/artifacts/Media/ontap-9.14.1.tgz",
          selection_source: "auto",
          source_type: "cached_live",
          target_version: ">= 9.14"
        }
      ]
    },
    {
      approved_versions: [{ label: "HPE Service Pack", status: "manual_review", version: null }],
      blocker: "Smart Array baseline missing/manual review",
      compliance_status: "cannot_verify",
      component_type: "storage_controller_firmware",
      current_versions: [{ label: "Smart Array", status: "warning", version: "52.26.3-5379" }],
      device_id: "raid",
      evidence_artifacts: ["artifacts/codex-runs/firmware-inventory-report.md"],
      freshness: "live",
      label: "HPE Storage",
      last_scanned: checkedAt,
      next_action: "Use the HPE Service Pack for Smart Array firmware review.",
      path_status: "manual_review",
      package_available: true,
      package_name: "SPP2024.03.00.iso",
      prechecks_required: ["Review HPE Service Pack release notes"],
      required_intermediate_versions: [],
      reboot_required: true,
      scan_action_id: "ilo.firmware-inventory",
      severity: "yellow",
      source_type: "cached_live",
      target_version: null,
      upgrade_center_link: "/firmware?device=raid",
      upgrade_paths: [
        {
          apply_enabled: false,
          baseline_source: "manual",
          candidate_files: [
            {
              confidence: "high",
              detected_product: "hpe-spp",
              detected_vendor: "HPE",
              detected_version: "2024.3.0",
              file_name: "SPP2024.03.00.iso",
              file_path: "/home/administrator/infra-config-portal/artifacts/Media/SPP2024.03.00.iso"
            }
          ],
          component_id: "hpe_smart_array_firmware",
          component_label: "Smart Array",
          current_version: "52.26.3-5379",
          device_label: "HPE Storage",
          disabled_reason: "Manual review required: missing approved HPE baseline.",
          equipment_label: "HPE Server",
          equipment_type: "storage_controller_firmware",
          estimated_impact: "Host reboot may be required.",
          evidence_artifacts: ["artifacts/codex-runs/firmware-inventory-report.md"],
          freshness: "live",
          last_checked: checkedAt,
          missing_evidence: ["approved HPE baseline"],
          next_action: "Review HPE Service Pack release notes before applying upgrades.",
          package_available: true,
          package_name: "SPP2024.03.00.iso",
          package_version: "2024.3.0",
          path_status: "manual_review",
          prechecks_required: ["Review HPE Service Pack release notes"],
          reboot_required: true,
          required_intermediate_versions: [],
          scan_action_id: "ilo.firmware-inventory",
          selected_file_name: "SPP2024.03.00.iso",
          selected_file_path: "/home/administrator/infra-config-portal/artifacts/Media/SPP2024.03.00.iso",
          selection_source: "auto",
          source_type: "cached_live",
          target_version: null
        }
      ]
    }
  ];
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
      dns_servers: ["192.168.1.1"],
      domain_name: "lab.local",
      gateway: "192.168.1.1",
      netapp_disabled_reason: null,
      netapp_enabled: true,
      ntp_servers: ["192.168.1.1"],
      subnet_prefix: 24,
      timezone: "America/Toronto",
      vcenter_enabled: true,
      vlan_id: "10",
      mtu: 1500
    },
    profile_topology: "high_address_lab",
    subnet_cidr: "192.168.1.0/24",
    gateway: "192.168.1.1",
    dns: ["192.168.1.1"],
    ntp: ["192.168.1.1"],
    vlan_id: "10",
    mtu: 1500,
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
      vcenter: "https://192.168.1.206/sdk"
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
      vcenter_disabled_reason: null,
      vcenter_enabled: true
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
    not_in_scope_stages: [],
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
      disabled_features: {},
      enabled_features: profile.features,
      fix_guidance: [],
      mismatch_warnings: [],
      not_in_scope_stages: [],
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
        firmware_summary: firmwareSummaries()[1],
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
        firmware_summary: firmwareSummaries()[0],
        id: "cisco",
        stage: "Cisco Control",
        title: "Cisco Control"
      }),
      controlSection({
        current_state: [
          { detail: null, label: "Cisco IOS XE", status: "cannot_verify", value: "17.15.05" },
          { detail: null, label: "ONTAP", status: "not_configured", value: "Unknown" }
        ],
        description: "Firmware and upgrade controls.",
        id: "firmware-upgrade",
        stage: "Firmware / Upgrade Center",
        status: "warning",
        title: "Firmware / Upgrade"
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
    firmware_summary: null,
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
