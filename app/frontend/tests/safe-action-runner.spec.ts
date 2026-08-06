import { expect, test, type Page, type Route } from "@playwright/test";

const checkedAt = "2026-06-09T21:00:00Z";
let labProfileScenario: "none" | "shared" | "single" = "shared";
let healthHostIpv4Addresses = ["192.168.1.99"];
let workflowActionsOverride: Record<string, unknown>[] | null = null;

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
  label: "Boot ESXi Installer",
  mode: "destructive",
  provider: "esxi",
  required_confirmations: ["BOOT ESXI INSTALLER"],
  required_gates: ["LAB_ALLOW_POWER_ACTIONS=true"],
  stage: "esxi",
  stage_label: "ESXi Control",
  ui_run_supported: false,
  ui_run_blockers: ["guarded workflow requires exact confirmation phrase: BOOT ESXI INSTALLER"]
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
  labProfileScenario = "shared";
  healthHostIpv4Addresses = ["192.168.1.99"];
  workflowActionsOverride = null;
  await installApiMocks(page);
});

async function openWorkspaceAdvanced(page: Page, workspaceName: string) {
  const workspace = page.locator(`section[aria-label='${workspaceName} workspace']`);
  const details = workspace.getByLabel(`${workspaceName} details`);
  if (await details.isVisible()) {
    const isOpen = await details.evaluate((node) => (node as HTMLDetailsElement).open);
    if (!isOpen) {
      await details.locator(":scope > summary").click();
    }
  }
  const proofDoor = workspace.getByLabel(`${workspaceName} proof and diagnostics`);
  if (await proofDoor.count()) {
    const isProofDoorOpen = await proofDoor.evaluate((node) => (node as HTMLDetailsElement).open);
    if (!isProofDoorOpen) {
      await proofDoor.locator(":scope > summary").click();
    }
  }
  const advanced = workspace.getByLabel(`${workspaceName} advanced checks and proof`);
  await advanced.locator(":scope > summary").click();
  return advanced;
}

async function openWorkspaceEditGroup(page: Page, workspaceName: string, groupName: string) {
  const workspace = page.locator(`section[aria-label='${workspaceName} workspace']`);
  const details = workspace.getByLabel(`${workspaceName} details`);
  if (await details.isVisible()) {
    const isDetailsOpen = await details.evaluate((node) => (node as HTMLDetailsElement).open);
    if (!isDetailsOpen) {
      await details.locator(":scope > summary").click();
    }
  }
  const editSettings = workspace.getByLabel(`${workspaceName} edit settings`);
  if (await editSettings.count()) {
    const isEditSettingsOpen = await editSettings.evaluate((node) => (node as HTMLDetailsElement).open);
    if (!isEditSettingsOpen) {
      await editSettings.locator(":scope > summary").click();
    }
  }
  const moreSetupFields = workspace.getByLabel(`${workspaceName} more setup fields`);
  const groupHost = await moreSetupFields.count() ? moreSetupFields : workspace;
  if (await moreSetupFields.count()) {
    const isMoreOpen = await moreSetupFields.evaluate((node) => (node as HTMLDetailsElement).open);
    if (!isMoreOpen) {
      await moreSetupFields.locator(":scope > summary").click();
    }
  }
  const groupButton = groupHost.locator(".design-device-edit-group-button").filter({ hasText: groupName }).first();
  if (await groupButton.getAttribute("aria-pressed") !== "true") {
    await groupButton.click();
  }
  const panel = workspace.getByLabel(`${workspaceName} ${groupName}`);
  await expect(panel).toBeVisible();
  return panel;
}

async function openCredentialReferences(page: Page, workspaceName: string, expectedReferences: string[]) {
  const workspace = page.locator(`section[aria-label='${workspaceName} workspace']`);
  const credentialSetup = workspace.getByLabel(`${workspaceName} credential setup`);
  await expect(credentialSetup).toBeVisible();
  await expect(credentialSetup).toContainText("Reference only");
  await expect.poll(
    () => credentialSetup.evaluate((node) => (node as HTMLDetailsElement).open),
    { message: `${workspaceName} credential references start collapsed` }
  ).toBe(false);

  const references = workspace.getByLabel(`${workspaceName} credential references`);
  await expect(references).not.toBeVisible();
  await credentialSetup.locator(":scope > summary").click();
  await expect(references).toBeVisible();
  for (const reference of expectedReferences) {
    await expect(references).toContainText(reference);
  }
  return references;
}

async function visibleMainText(page: Page) {
  return page.locator("main.content").evaluate((root) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const chunks: string[] = [];
    let node = walker.nextNode();
    while (node) {
      const parent = node.parentElement;
      if (parent) {
        const closedDetails = parent.closest("details:not([open])");
        const insideClosedDetailsBody = closedDetails && !parent.closest("summary");
        let visible = !insideClosedDetailsBody;
        for (let element: Element | null = parent; visible && element && element !== root; element = element.parentElement) {
          const style = window.getComputedStyle(element);
          visible = style.display !== "none" && style.visibility !== "hidden";
        }
        if (visible) chunks.push(node.textContent || "");
      }
      node = walker.nextNode();
    }
    return chunks.join(" ").replace(/\s+/g, " ").trim();
  });
}

async function expectResponsiveShell(page: Page, path: string, viewport: { width: number; height: number }) {
  await page.setViewportSize(viewport);
  await page.goto(path);
  await expect(page.locator("main.content")).toBeVisible();
  const metrics = await page.evaluate(() => {
    const header = document.querySelector("header[aria-label='Application header']");
    const primaryNavigation = document.querySelector("nav[aria-label='Primary navigation']");
    const navRect = primaryNavigation?.getBoundingClientRect();
    return {
      bodyWidth: document.body.scrollWidth,
      headerHeight: header?.getBoundingClientRect().height ?? 0,
      innerWidth: window.innerWidth,
      navClientWidth: primaryNavigation?.clientWidth ?? 0,
      navLeft: navRect?.left ?? 0,
      navLinkCount: primaryNavigation?.querySelectorAll("a").length ?? 0,
      navOverflowX: primaryNavigation ? getComputedStyle(primaryNavigation).overflowX : "",
      navRight: navRect?.right ?? 0,
      navScrollWidth: primaryNavigation?.scrollWidth ?? 0,
      viewportHeight: window.innerHeight,
      width: document.documentElement.scrollWidth
    };
  });
  expect(metrics.width, `${path} document overflow at ${viewport.width}px`).toBeLessThanOrEqual(metrics.innerWidth + 1);
  expect(metrics.bodyWidth, `${path} body overflow at ${viewport.width}px`).toBeLessThanOrEqual(metrics.innerWidth + 1);
  expect(metrics.navLinkCount, `${path} keeps all primary destinations at ${viewport.width}px`).toBe(5);
  expect(metrics.navLeft, `${path} primary nav starts inside the viewport at ${viewport.width}px`).toBeGreaterThanOrEqual(-1);
  expect(metrics.navRight, `${path} primary nav ends inside the viewport at ${viewport.width}px`).toBeLessThanOrEqual(metrics.innerWidth + 1);
  if (viewport.width >= 1280) {
    expect(metrics.navScrollWidth, `${path} primary nav fits without desktop clipping`).toBeLessThanOrEqual(metrics.navClientWidth + 1);
  }
  if (viewport.width <= 390) {
    expect(metrics.navOverflowX, `${path} contains mobile nav overflow`).toBe("auto");
    expect(metrics.headerHeight, `${path} mobile header consumes too much vertical space`).toBeLessThanOrEqual(
      Math.min(220, metrics.viewportHeight * 0.25)
    );
  }
}

test("renders the map-first operator header and pages", async ({ page }) => {
  await page.goto("/overview");

  await expect(page.locator("aside[aria-label='Lab Builder navigation']")).toHaveCount(0);
  const header = page.locator("header[aria-label='Application header']");
  await expect(header).toBeVisible();
  await expect(header.getByRole("link", { name: "Lab Builder overview" })).toHaveAttribute("href", "/overview");
  await expect(header.getByRole("link", { name: "Lab Builder overview" })).toContainText("Lab Builder");
  await expect(header.getByRole("link", { name: "Lab Builder overview" })).toContainText("Operator");
  const primaryNavigation = header.getByRole("navigation", { name: "Primary navigation" });
  await expect(primaryNavigation.locator("a")).toHaveText(["Overview", "Lab Defaults", "Firmware", "Run Center", "Reports"]);
  await expect(primaryNavigation.getByRole("link", { name: "Overview" })).toHaveAttribute("href", "/overview");
  await expect(primaryNavigation.getByRole("link", { name: "Lab Defaults" })).toHaveAttribute("href", "/setup/defaults");
  await expect(primaryNavigation.getByRole("link", { name: "Firmware" })).toHaveAttribute("href", "/firmware-upgrades");
  await expect(primaryNavigation.getByRole("link", { name: "Run Center" })).toHaveAttribute("href", "/run");
  await expect(primaryNavigation.getByRole("link", { name: "Reports" })).toHaveAttribute("href", "/reports");
  await expect(primaryNavigation).not.toContainText(/Compute|Storage|Virtualization|Cisco/);
  await expect(page.getByRole("navigation", { name: "Quick navigation" })).toHaveCount(0);
  const headerActions = header.locator(".shell-topbar-actions");
  await expect(headerActions.getByRole("link", { name: "Create or change kit" })).toHaveAttribute("href", "/lab-profiles#new");
  await expect(headerActions).toHaveText("Create or change kit");
  await expect(header.getByLabel("Lab provider mode")).toHaveCount(0);
  await expect(header.locator("#active-kit-picker")).toHaveCount(0);
  await expect(header.getByRole("group", { name: "Display mode" })).toHaveCount(0);
  await expect(headerActions).not.toContainText(/Test Mode|Local lab setup|New kit|Operator|Advanced/);
  await expect(header).not.toContainText(/Windows|OVF|Global/);

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.goto("/lab-setup");
  await expect(page).toHaveURL(/\/overview/);
  for (const setupPath of ["/network", "/server", "/storage", "/virtualization"]) {
    await page.goto(setupPath);
    await expect(page).toHaveURL(new RegExp(`${setupPath}$`));
    await expect(page.locator("main")).toBeVisible();
  }
  for (const [setupPath, heading] of [
    ["/setup/cisco", "Cisco Switch"],
    ["/setup/ilo", "Compute & iLO"],
    ["/setup/server", "Compute & iLO"],
    ["/setup/storage", "Storage & NetApp"],
    ["/setup/netapp", "Storage & NetApp"],
    ["/setup/esxi", "Virtualization"],
    ["/setup/windows", "Virtualization"],
    ["/setup/media", "Software Media"],
    ["/setup/ovf", "Software Media"]
  ] as const) {
    await page.goto(setupPath);
    await expect(page).toHaveURL(new RegExp(`${setupPath}$`));
    await expect(page.locator("main h1").filter({ hasText: heading })).toBeVisible();
  }
  await page.goto("/setup/defaults");
  await expect(page.getByRole("heading", { name: "Lab Defaults", exact: true })).toBeVisible();
  await page.goto("/setup/global");
  await expect(page).toHaveURL(/\/setup\/defaults$/);
  await expect(page.getByRole("heading", { name: "Lab Defaults", exact: true })).toBeVisible();
  await page.goto("/lab-defaults");
  await expect(page).toHaveURL(/\/setup\/defaults$/);
  await expect(page.getByRole("heading", { name: "Lab Defaults", exact: true })).toBeVisible();
  await page.goto("/firmware-upgrades");
  await expect(page.getByRole("heading", { name: "Keep every device on the expected version.", exact: true })).toBeVisible();
  await page.goto("/setup/firmware");
  await expect(page.getByRole("heading", { name: "Keep every device on the expected version.", exact: true })).toBeVisible();
  await page.goto("/run-center");
  await expect(page.getByRole("heading", { name: "Run Center", exact: true })).toBeVisible();
  await expect(page.getByTestId("lab-build-journey")).toBeVisible();
  await page.goto("/run");
  await expect(page.getByRole("heading", { name: "Run Center", exact: true })).toBeVisible();
  await expect(page.getByTestId("lab-build-journey")).toBeVisible();
  await expect(page.getByLabel("Build Plan")).toBeVisible();
  await expect(page.getByText("Readiness Workflow")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Lab Setup", exact: true })).toHaveCount(0);
  await page.goto("/validation");
  await expect(page.getByRole("heading", { name: "Validation", exact: true })).toBeVisible();
  await page.goto("/config");
  await expect(page).toHaveURL(/\/overview/);
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/overview/);
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();

  await page.goto("/control-center");
  await expect(page).toHaveURL(/\/overview/);
});

test("advanced-only audit and workflow proof routes stay off the operator surface", async ({ page }) => {
  await page.goto("/audit-events");
  await expect(page).toHaveURL(/\/validation$/);
  await expect(page.getByRole("heading", { name: "Validation", exact: true })).toBeVisible();
  await expect(page.getByText("Audit Filters")).toHaveCount(0);

  await page.goto("/workflow-runs/advanced-run-1");
  await expect(page).toHaveURL(/\/validation$/);
  await expect(page.getByRole("heading", { name: "Validation", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Workflow Run", exact: true })).toHaveCount(0);

  for (const path of ["/reports", "/validation-reports", "/artifacts"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/validation$/);
    await expect(page.getByRole("heading", { name: "Validation", exact: true })).toBeVisible();
  }
});

test("advanced mode can still inspect audit events and workflow run proof", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("infra-config-operator-ui-mode", "advanced");
  });

  await page.goto("/audit-events");
  await expect(page).toHaveURL(/\/audit-events$/);
  await expect(page.getByRole("heading", { name: "Audit Events", exact: true })).toBeVisible();
  await expect(page.getByText("Audit Filters")).toBeVisible();

  await page.goto("/workflow-runs/advanced-run-1");
  await expect(page).toHaveURL(/\/workflow-runs\/advanced-run-1$/);
  await expect(page.getByRole("heading", { name: "Workflow Run", exact: true })).toBeVisible();
  await expect(page.getByText("advanced-run-1")).toBeVisible();
  await expect(page.getByText("Local Preview Safety")).toBeVisible();
  await expect(page.getByText("Plan Summary")).toBeVisible();
});

test("lab defaults keeps every shared network service visible and repeatable", async ({ page }) => {
  await page.goto("/setup/defaults");

  await expect(page.getByRole("heading", { name: "Lab Defaults", exact: true })).toBeVisible();
  const network = page.getByLabel("Network defaults");
  await expect(network.getByRole("heading", { name: "Network & services" })).toBeVisible();
  await expect(network.getByRole("textbox", { name: "Subnet" })).toBeVisible();
  await expect(network.getByRole("textbox", { name: "Gateway" })).toBeVisible();
  await expect(network.getByRole("textbox", { name: "Subnet" })).toHaveValue("192.168.1.0/24");
  await expect(network.getByLabel("Storage protocol")).toBeVisible();
  await expect(network.getByRole("textbox", { name: "VLAN" })).toBeVisible();
  await expect(network.getByRole("textbox", { name: "MTU" })).toBeVisible();

  const sharedServices = network.getByLabel("Shared service defaults");
  await expect(sharedServices.getByLabel("DNS defaults")).toBeVisible();
  await expect(sharedServices.getByLabel("NTP defaults")).toBeVisible();
  await expect(sharedServices.getByLabel("SNMP defaults")).toBeVisible();
  await expect(sharedServices.getByRole("checkbox", { name: "Enable DNS" })).toBeChecked();
  await expect(sharedServices.getByRole("checkbox", { name: "Enable NTP" })).toBeChecked();
  await expect(sharedServices.getByRole("checkbox", { name: "Enable SNMP" })).not.toBeChecked();
  await expect(sharedServices.getByRole("textbox", { name: "DNS server 1", exact: true })).toHaveValue("192.168.1.1");
  await expect(sharedServices.getByRole("textbox", { name: "NTP server 1", exact: true })).toHaveValue("192.168.1.1");
  await expect(sharedServices.getByRole("textbox", { name: "SNMP manager 1", exact: true })).toHaveValue("");
  await expect(sharedServices.getByLabel("SNMP version")).toBeVisible();
  await expect(sharedServices.getByLabel("SNMP version").locator("option")).toHaveText(["v1 (legacy)", "v2c", "v3"]);

  await sharedServices.getByRole("button", { name: "Add DNS server" }).click();
  await sharedServices.getByRole("button", { name: "Add NTP server" }).click();
  await sharedServices.getByRole("button", { name: "Add SNMP manager" }).click();
  await expect(sharedServices.getByRole("textbox", { name: /^DNS server / })).toHaveCount(2);
  await expect(sharedServices.getByRole("textbox", { name: /^NTP server / })).toHaveCount(2);
  await expect(sharedServices.getByRole("textbox", { name: /^SNMP manager / })).toHaveCount(2);

  const signIn = page.getByLabel("Shared sign-in");
  await expect(signIn.getByRole("heading", { name: "Shared sign-in" })).toBeVisible();
  await expect(signIn).toContainText("Password location");
  await expect(signIn).toContainText("Secrets are not stored in kit defaults.");
  await expect(signIn).toContainText("Click a device on Overview to set its own sign-in");
  await expect(signIn).toContainText("Set per device");
  await expect(signIn).toContainText("Default username");
  await expect(signIn.getByText("More service defaults")).toHaveCount(0);
  await expect(signIn.getByLabel("Shared service defaults")).toHaveCount(0);
  await expect(signIn.getByLabel("SNMP version")).toHaveCount(0);
  await expect(signIn).not.toContainText("P@ssw0rd");
  await expect(signIn.locator("input[type='password']")).toHaveCount(0);

  await expect(page.locator(".lab-defaults-actions .operator-primary-button")).toHaveCount(1);
  await expect(page.locator(".lab-defaults-actions .operator-primary-button")).toContainText("Save defaults");
  await expect(page.getByRole("heading", { name: "Shared profile policy" })).toHaveCount(0);
  await expect(page.getByText("Setup name")).toHaveCount(0);
  await expect(page.getByText("Allow IPv6")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Expected devices" })).toHaveCount(0);
  await expect(page.locator(".lab-defaults-advanced")).toHaveCount(0);
  await expect(page.getByLabel("Advanced lab default fields")).toHaveCount(0);
  await expect(page.getByLabel("Global profile feature toggles")).toHaveCount(0);
});

test("lab defaults saves editable network and service defaults without secrets or workflows", async ({ page }) => {
  let workflowRunAttempted = false;
  await page.route("**/api/v1/workflows/actions/*/run", async (route) => {
    workflowRunAttempted = true;
    await route.continue();
  });

  await page.goto("/setup/defaults");

  const network = page.getByLabel("Network defaults");
  await network.getByRole("textbox", { name: "Subnet" }).fill("192.168.210.0/24");
  await network.getByRole("textbox", { name: "Gateway" }).fill("192.168.210.1");
  await network.getByRole("textbox", { name: "DNS server 1", exact: true }).fill("192.168.210.1");
  await network.getByRole("button", { name: "Add DNS server" }).click();
  await network.getByRole("textbox", { name: "DNS server 2", exact: true }).fill("1.1.1.1");
  await network.getByRole("textbox", { name: "NTP server 1", exact: true }).fill("192.168.210.1");
  await network.getByRole("button", { name: "Add NTP server" }).click();
  await network.getByRole("textbox", { name: "NTP server 2", exact: true }).fill("192.168.210.2");
  await network.getByRole("textbox", { name: "SNMP manager 1", exact: true }).fill("192.168.210.31");
  await network.getByRole("button", { name: "Add SNMP manager" }).click();
  await network.getByRole("textbox", { name: "SNMP manager 2", exact: true }).fill("192.168.210.32");
  await network.getByRole("textbox", { name: "VLAN" }).fill("120");
  await network.getByRole("textbox", { name: "MTU" }).fill("9000");
  await network.getByLabel("Storage protocol").selectOption("iscsi");

  await network.getByRole("checkbox", { name: "Enable SNMP" }).check();
  await network.getByLabel("SNMP version").selectOption("v3");

  const createProfileRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "POST" && url.pathname === "/api/v1/lab/profiles";
  });
  await page.locator(".lab-defaults-actions .operator-primary-button").click();
  const request = await createProfileRequest;
  const payload = request.postDataJSON() as Record<string, any>;

  expect(payload.address_plan.subnet).toBe("192.168.210.0/24");
  expect(payload.address_plan.cisco_management).toBe("192.168.210.204");
  expect(payload.address_plan.ilo).toBe("192.168.210.201");
  expect(payload.address_plan.esxi_management).toBe("192.168.210.203");
  expect(payload.address_plan.netapp_cluster_mgmt).toBe("192.168.210.220");
  expect(payload.global_settings.gateway).toBe("192.168.210.1");
  expect(payload.global_settings.dns_servers).toEqual(["192.168.210.1", "1.1.1.1"]);
  expect(payload.global_settings.ntp_servers).toEqual(["192.168.210.1", "192.168.210.2"]);
  expect(payload.global_settings.snmp_servers).toEqual(["192.168.210.31", "192.168.210.32"]);
  expect(payload.global_settings.vlan_id).toBe("120");
  expect(payload.global_settings.mtu).toBe(9000);
  expect(payload.global_settings.snmp_version).toBe("v3");
  expect(payload.features.enable_snmp).toBe(true);
  expect(payload.features.storage_protocol).toBe("iscsi");
  expect(JSON.stringify(payload)).not.toMatch(/password|secret|P@ssw0rd/i);
  expect(workflowRunAttempted).toBe(false);
});

test("saved kits only manages kit selection and subnet-derived creation", async ({ page }) => {
  await page.goto("/lab-profiles");

  await expect(page.getByRole("heading", { name: "Saved Kits", exact: true })).toBeVisible();
  const home = page.getByTestId("saved-kits-home");
  await expect(home).toBeVisible();
  await expect(home).toContainText("Current Lab");
  await expect(home).toContainText("Server + NetApp + vCenter");
  await expect(home).not.toContainText(/runtime|source|store|global|profile|capabilities|intent_only/i);

  const changePanel = page.locator("details[aria-label='Change kit']");
  const createPanel = page.locator("details[aria-label='Create a new kit']");
  await expect(changePanel).not.toHaveAttribute("open", "");
  await expect(createPanel).toHaveAttribute("open", "");
  await expect(page.locator(".primary:visible")).toHaveCount(1);
  await expect(page.locator(".primary:visible")).toContainText("Create kit");
  await expect(home.getByRole("link", { name: "Continue with this kit" })).toBeVisible();
  await expect(createPanel).not.toContainText(/runtime|source|store|global|profile|capabilities|intent_only/i);
  await expect(page.locator(".lab-profile-metrics")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Global Settings" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Core Addresses" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "NetApp Capabilities" })).toHaveCount(0);
  await expect(page.getByText("Save as lab setup")).toHaveCount(0);

  await createPanel.getByLabel("Kit name").fill("Rack 08 Edge Lab");
  await createPanel.getByLabel("Subnet network").fill("192.168.210.0");
  const preview = createPanel.getByLabel("Derived address preview");
  await expect(preview).toContainText("192.168.210.204");
  await expect(preview).toContainText("192.168.210.201");
  await expect(preview).toContainText("192.168.210.203");
  await expect(preview).toContainText("192.168.210.220");

  const createProfileRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "POST" && url.pathname === "/api/v1/lab/profiles";
  });
  const activateProfileRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "POST" && url.pathname === "/api/v1/lab/profiles/visual-profile/activate";
  });
  await createPanel.getByRole("button", { name: "Create kit" }).click();
  const request = await createProfileRequest;
  await activateProfileRequest;
  const payload = request.postDataJSON() as Record<string, any>;
  expect(payload.name).toBe("Rack 08 Edge Lab");
  expect(payload.address_plan.subnet).toBe("192.168.210.0/24");
  expect(payload.address_plan.cisco_management).toBe("192.168.210.204");
  expect(payload.address_plan.netapp_cluster_mgmt).toBe("192.168.210.220");
  await expect(page).toHaveURL(/\/overview$/);

  await page.goto("/lab-profiles");
  await expect(home).toContainText("Rack 08 Edge Lab");
  await expect(home).toContainText("Saved and active");
  await expect(createPanel).not.toHaveAttribute("open", "");
  await expect(changePanel).not.toHaveAttribute("open", "");
  await expect(createPanel.getByLabel("Kit name")).not.toBeVisible();
  await expect(page.locator(".primary:visible")).toHaveCount(1);
  await expect(page.locator(".primary:visible")).toContainText("Continue with this kit");
  await changePanel.locator(":scope > summary").click();
  await expect(changePanel.getByLabel("Saved kit")).toHaveValue("visual-profile");
  await expect(changePanel.getByText("Lab Defaults")).toBeVisible();
});

test("new kit build type stays explicit while the subnet is entered normally", async ({ page }) => {
  await page.goto("/lab-profiles#new");

  const createPanel = page.locator("details[aria-label='Create a new kit']");
  const kitName = createPanel.getByLabel("Kit name");
  const buildType = createPanel.getByRole("combobox", { name: "Build type" });
  const subnet = createPanel.getByLabel("Subnet network");
  const addressRange = createPanel.getByRole("combobox", { name: "Address range" });

  await kitName.fill("Local RAID Input Lab");
  await buildType.selectOption("local");
  await expect(buildType).toHaveValue("local");
  await expect(addressRange).toHaveValue("24");

  await addressRange.selectOption("29");
  await expect(buildType).toHaveValue("local");
  await expect(addressRange).toHaveValue("29");

  await subnet.fill("");
  await expect(subnet).toHaveValue("");
  await subnet.pressSequentially("10.238.207.16");
  await expect(subnet).toHaveValue("10.238.207.16");
  await expect(kitName).toHaveValue("Local RAID Input Lab");

  await buildType.selectOption("shared");
  await expect(buildType).toHaveValue("shared");
  await expect(addressRange).toHaveValue("24");
  await expect(subnet).toHaveValue("10.238.207.0");

  await buildType.selectOption("local");
  await expect(buildType).toHaveValue("local");
  await expect(addressRange).toHaveValue("24");
  await expect(kitName).toHaveValue("Local RAID Input Lab");

  const preview = createPanel.getByLabel("Derived address preview");
  await expect(preview).toContainText("Local storage");
  await expect(preview).toContainText("Server disks");

  const createProfileRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "POST" && url.pathname === "/api/v1/lab/profiles";
  });
  await createPanel.getByRole("button", { name: "Create kit" }).click();
  const request = await createProfileRequest;
  const payload = request.postDataJSON() as Record<string, any>;

  expect(payload.name).toBe("Local RAID Input Lab");
  expect(payload.address_plan.subnet).toBe("10.238.207.0/24");
  expect(payload.address_plan.netapp_cluster_mgmt).toBeNull();
  expect(payload.devices.netapp).toBeNull();
  expect(payload.features.netapp_enabled).toBe(false);
  expect(payload.features.vcenter_enabled).toBe(false);
  expect(payload.features.storage_protocol).toBe("none");
  expect(payload.global_settings.netapp_enabled).toBe(false);
  await expect(page).toHaveURL(/\/overview$/);
});

test("saved kits switch and history stay behind the selected-kit decision", async ({ page }) => {
  const runtimeState = labProfiles();
  const savedProfile = JSON.parse(JSON.stringify(runtimeState.active_profile)) as Record<string, any>;
  savedProfile.id = "rack-07-edge";
  savedProfile.active = false;
  savedProfile.name = "Rack 07 Edge Lab";
  savedProfile.source = "saved";
  savedProfile.history = [
    {
      address_plan: savedProfile.address_plan,
      name: "Rack 07 Edge Lab",
      saved_at: "2026-07-16T22:00:00Z",
      version: 1
    },
    {
      address_plan: savedProfile.address_plan,
      name: "Rack 07 Edge Lab",
      saved_at: "2026-07-17T22:00:00Z",
      version: 2
    }
  ];
  let profileState = {
    ...runtimeState,
    profiles: [savedProfile]
  };

  await page.route("**/api/v1/lab/profiles/rack-07-edge/activate", async (route) => {
    const activeSavedProfile = { ...savedProfile, active: true };
    profileState = activeLabProfilesFromProfile(activeSavedProfile);
    return json(route, profileState);
  });
  await page.route("**/api/v1/lab/profiles", async (route) => {
    if (route.request().method() === "GET") return json(route, profileState);
    return route.fallback();
  });

  await page.goto("/lab-profiles");
  await expect(page.getByTestId("saved-kits-home")).toContainText("Current Lab");
  await expect(page.locator("details[aria-label='Create a new kit']")).not.toHaveAttribute("open", "");
  await expect(page.locator("details[aria-label='Change kit']")).not.toHaveAttribute("open", "");
  await expect(page.locator(".primary:visible")).toHaveCount(1);
  await expect(page.locator(".primary:visible")).toContainText("Continue with this kit");
  await expect(page.getByRole("columnheader", { name: "Saved" })).toHaveCount(0);

  const details = page.locator("details.saved-kits-details");
  await details.locator(":scope > summary").click();
  await expect(details.getByText("Latest save")).toBeVisible();
  await expect(details.locator(".saved-kits-history-latest strong")).toContainText("2026");
  await expect(details.getByRole("columnheader", { name: "Saved" })).toHaveCount(0);
  await details.locator("details.saved-kits-full-history > summary").click();
  await expect(details.getByRole("columnheader", { name: "Saved" })).toBeVisible();

  const changePanel = page.locator("details[aria-label='Change kit']");
  await changePanel.locator(":scope > summary").click();
  await expect(changePanel.getByRole("button", { name: "Use this kit" })).toHaveClass(/primary/);
  const activateRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "POST" && url.pathname === "/api/v1/lab/profiles/rack-07-edge/activate";
  });
  await changePanel.getByRole("button", { name: "Use this kit" }).click();
  await activateRequest;
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByTestId("operator-home")).toContainText("Rack 07 Edge Lab");
});

test("operator home answers the next action without dashboard clutter", async ({ page }) => {
  await page.goto("/overview");

  const home = page.getByTestId("operator-home");
  await expect(home).toBeVisible();
  await expect(home).toContainText("Current Lab");
  await expect(home).toContainText("Server + NetApp + vCenter");
  await expect(home.getByRole("img", { name: /ready, .*blocked, .*not checked/ })).toHaveCount(1);
  await expect(home.getByTestId("operator-home-primary-action")).toHaveCount(1);
  await expect(home.getByTestId("operator-home-primary-action")).toBeVisible();
  await expect(home.getByTestId("operator-home-primary-action")).toContainText("Review Build Plan");
  await expect(home.getByTestId("operator-home-view-details")).toHaveCount(0);
  await expect(home.getByText("View all device details")).toHaveCount(0);
  const currentState = home.getByLabel("Current state summary");
  const attention = currentState.getByLabel("Needs your attention");
  await expect(attention).toContainText("Cisco firmware");
  await expect(attention.locator(".operator-rail-blocker")).toHaveCount(2);
  await expect(attention).toContainText("HPE Storage firmware");
  await expect(attention).toContainText("ROMMON baseline missing/manual review");
  await expect(attention).not.toContainText(/more items? .*device details/i);
  await expect(attention.getByText("Firmware needs proof")).toHaveCount(0);

  await expect(page.locator("section[aria-label='Overview reference']")).toHaveCount(0);
  await expect(page.locator("section[aria-label='Scenario setup lanes']")).toHaveCount(0);
  await expect(page.locator("[data-region-id='lab-safety']")).toHaveCount(0);
  await expect(page.locator("[data-region-id='topology']")).toHaveCount(0);
  await expect(page.locator("section[aria-label='Lab topology'], section[aria-label='Living lab topology']")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Readiness at a glance" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Firmware Compliance" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Active Blockers" })).toHaveCount(0);
  await expect(page.locator("nav").getByText("Edit Config")).toHaveCount(0);
  await expect(page.locator("nav").getByText("Settings")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Shared profile policy" })).toHaveCount(0);

  await expect(page.getByRole("heading", { name: "Lab Values" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Currently Accessible" })).toHaveCount(0);
  await expect(page.getByText(/what is healthy/i)).toHaveCount(0);
  await expect(page.getByText(/what is next/i)).toHaveCount(0);
  await expect(page.getByText("Artifact")).toHaveCount(0);
  await expect(home).not.toContainText("Provider");
  await expect(home).not.toContainText("provider");
  await expect(home).not.toContainText("runtime");
  await expect(home).not.toContainText("dependency graph");
  await expect(home).not.toContainText("raw");
  await expect(home).not.toContainText("logs");
  await expect(home).not.toContainText("console");
  await expect(home).not.toContainText(/CISCO_[A-Z_]+/);
  await expect(page.getByText("Change this page")).toHaveCount(0);
});

test("operator home gives a clear kit action when no kit is selected", async ({ page }) => {
  labProfileScenario = "none";
  await page.goto("/overview");

  const home = page.getByTestId("operator-home");
  const primary = home.getByTestId("operator-home-primary-action");
  await expect(home).toContainText("Choose a lab kit before running setup.");
  await expect(home).toContainText("Select or create a kit to load the address plan and readiness checks.");
  await expect(home).not.toContainText("No kit selected is in");
  await expect(home).toContainText("Select or create a kit before checking readiness.");
  await expect(primary).toHaveCount(1);
  await expect(primary).toBeEnabled();
  await expect(primary).toContainText("Create or select a kit");
  await expect(primary).not.toContainText("Opening");

  await primary.click();
  await expect(page).toHaveURL(/\/lab-profiles#new$/);
});

test("map-first overview makes the topology the home surface", async ({ page }) => {
  await page.goto("/overview");

  const layout = page.locator(".operator-home-layout");
  const mapColumn = layout.locator(".operator-home-map-column");
  const map = mapColumn.locator("section[aria-label='Lab topology'], section[aria-label='Living lab topology']");
  const rail = layout.getByRole("complementary", { name: "Operator Home status and next action" });

  await expect(map).toBeVisible();
  await expect(rail).toBeVisible();
  await expect(layout.locator(".operator-home-map-column")).toHaveCount(1);
  await expect(layout.locator(".operator-home-rail")).toHaveCount(1);
  const headingBox = await map.locator("h2").first().boundingBox();
  expect(headingBox, "topology device-count heading has a layout box").not.toBeNull();
  await expect(map.locator(".system-setup-picker"), "system setup picker is retired from the map header").toHaveCount(0);
  await expect(map).toContainText("Cisco Switch");
  await expect(map).toContainText(/subnet 192\.168\.1\.0\/24/i);
  await expect(rail.getByTestId("operator-home-primary-action")).toHaveCount(1);
  await expect(rail.locator(".operator-rail-primary")).toHaveCount(1);
  await expect(page.getByTestId("lab-build-journey")).toHaveCount(0);
  await expect(rail).not.toContainText(/provider|runtime|payload/i);
});

test("overview topology nodes stay compact and move setup into direct drawers", async ({ page }) => {
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  const map = topology.getByLabel("Device topology");
  const nodes = map.locator(".overview-node");
  await expect(nodes).toHaveCount(5);
  for (let index = 0; index < 5; index += 1) {
    const node = nodes.nth(index);
    await expect(node.locator(".overview-node-label")).toHaveCount(1);
    await expect(node.locator(".overview-node-meta")).toHaveCount(1);
  }
  await expect(topology.locator(".topology-node-faceplate, .topology-node-chips")).toHaveCount(0);
  await expect(map).not.toContainText(/BMC read-only checks|Direct host management|VLAN 220/i);

  await topology.getByRole("button", { name: /^Cisco Switch,/ }).click();
  const switchDrawer = page.getByLabel("Cisco Switch setup");
  await expect(switchDrawer).toBeVisible();
  await expect(switchDrawer.getByLabel("Management IP", { exact: true })).toHaveValue("192.168.1.204");
  await expect(switchDrawer.getByRole("heading", { name: "Access" })).toBeVisible();
  await expect(switchDrawer.getByRole("heading", { name: "Network" })).toBeVisible();
  await expect(switchDrawer.getByRole("heading", { name: "Services" })).toBeVisible();
  await expect(switchDrawer).not.toContainText(/Apply Bootstrap|Factory reset|Upgrade firmware/i);
});

test("operator home opens one ordered build plan with one primary action", async ({ page }) => {
  await page.goto("/overview");
  const latestRequest = page.waitForRequest((request) => request.url().includes("/api/v1/lab-build/runs/latest"));
  await page.getByTestId("operator-home-primary-action").click();
  await expect(page).toHaveURL(/\/run-center$/);
  expect(new URL((await latestRequest).url()).searchParams.get("kit_id")).toBe("runtime-profile");

  const journey = page.getByTestId("lab-build-journey");
  const plan = journey.getByLabel("Build Plan");
  await expect(page.locator(".page-title-block .eyebrow")).toHaveText("Run");
  await expect(journey).toBeVisible();
  await expect(page.getByTestId("operator-home")).toHaveCount(0);
  await expect(plan.getByRole("heading", { name: "This lab is ready to follow one ordered build plan." })).toBeVisible();
  await expect(plan.getByLabel("Plan summary")).toContainText("8 stages");
  await expect(plan.locator(".lab-build-summary > div")).toHaveCount(0);
  await expect(plan).not.toContainText("checks are ready");
  await expect(plan).toContainText("Network, iLO, and local storage are proven before Start Build.");
  await expect(plan.getByLabel("Next build step")).toContainText("Boot the ESXi installer");
  await expect(plan.getByLabel("Next build step")).toContainText("Pauses for your approval");
  await expect(plan.getByLabel("Next build step").getByRole("listitem")).toHaveCount(0);
  await expect(plan.getByLabel("Next build step")).not.toContainText("Configure the management network");
  expect(((await plan.getByLabel("Next build step").textContent()) || "").match(/Boot the ESXi installer/g)).toHaveLength(1);
  await expect(plan.getByLabel("Ordered build steps")).not.toBeVisible();
  await plan.getByText("View full build sequence").click();
  await expect(plan.getByLabel("Ordered build steps")).toBeVisible();
  await expect(plan.getByLabel("Ordered build steps").getByRole("listitem")).toHaveCount(8);
  await expect(plan.getByLabel("Ordered build steps")).toContainText("Shared storage must be ready before the compute host can use it.");
  await expect(plan.getByTestId("lab-build-primary-action")).toHaveCount(1);
  await expect(plan.getByTestId("lab-build-primary-action")).toContainText("Start Build");
  await expect(journey.getByRole("button", { name: "Close build journey" })).toHaveCount(0);
  await expect(plan).not.toContainText("provider");
  await expect(plan).not.toContainText("payload");
  await expect(plan).not.toContainText("dependency graph");
});

test("build plan keeps its next action visible without mobile overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/overview");
  await page.getByTestId("operator-home-primary-action").click();
  await expect(page).toHaveURL(/\/run-center$/);

  const journey = page.getByTestId("lab-build-journey");
  await expect(journey.getByTestId("lab-build-primary-action")).toBeVisible();
  await expect(journey.getByTestId("lab-build-primary-action")).toContainText("Start Build");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("run console pauses at a guarded change without exposing duplicate consoles", async ({ page }) => {
  await page.goto("/overview");
  await page.getByTestId("operator-home-primary-action").click();
  await expect(page).toHaveURL(/\/run-center$/);
  await page.getByTestId("lab-build-primary-action").click();

  const journey = page.getByTestId("lab-build-journey");
  const runConsole = journey.getByLabel("Run Console");
  await expect(runConsole).toBeVisible();
  await expect(runConsole).toContainText("Step 1 of 8");
  await expect(runConsole).toContainText("Waiting for approval: Boot the ESXi installer.");
  await expect(runConsole.getByTestId("lab-build-primary-action")).toHaveCount(1);
  await expect(runConsole.getByTestId("lab-build-primary-action")).toContainText("Continue Build");
  await expect(runConsole.getByRole("button", { name: "Open lab map" })).toHaveCount(1);
  await expect(runConsole.getByRole("button", { name: "Open Details" })).toHaveCount(0);
  await expect(runConsole.locator("details.lab-build-advanced")).not.toHaveAttribute("open");
  await expect(runConsole.getByLabel("Technical build log")).not.toBeVisible();
  await expect(page.getByText("Operator Console")).toHaveCount(0);

  await runConsole.getByRole("button", { name: "Open lab map" }).click();
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByTestId("lab-build-journey")).toHaveCount(0);
  await expect(page.locator("section[aria-label='Lab topology'], section[aria-label='Living lab topology']")).toBeVisible();
});

test("guarded build continuation submits exact waiting evidence", async ({ page }) => {
  await page.goto("/overview");
  await page.getByTestId("operator-home-primary-action").click();
  await expect(page).toHaveURL(/\/run-center$/);
  await page.getByTestId("lab-build-primary-action").click();

  const resumeRequest = page.waitForRequest((request) => (
    decodeURIComponent(new URL(request.url()).pathname).endsWith("/lab-build:test/resume")
  ));
  await page.getByLabel("Run Console").getByTestId("lab-build-primary-action").click();
  const payload = (await resumeRequest).postDataJSON() as Record<string, unknown>;

  expect(payload).toEqual({
    action_run_id: "workflow-action:esxi.rebuild-install:test",
    run_revision: 8,
    waiting_nonce: "waiting-nonce-1234567890"
  });
  await expect(page.getByLabel("Completion Report")).toBeVisible();
});

test("running builds can only refresh status", async ({ page }) => {
  await page.route("**/api/v1/lab-build/runs/latest?*", (route) => json(route, labBuildRunningRun()));
  await page.goto("/overview");
  await page.getByTestId("operator-home-primary-action").click();
  await expect(page).toHaveURL(/\/run-center$/);

  const console = page.getByLabel("Run Console");
  await expect(console.getByTestId("lab-build-primary-action")).toContainText("Refresh Status");
  await expect(console.getByRole("button", { name: "Resume Build" })).toHaveCount(0);
  await expect(console.getByRole("button", { name: "Continue Build" })).toHaveCount(0);
});

test("failed build shows one completion report and retry only when safe", async ({ page }) => {
  await page.route("**/api/v1/lab-build/runs", (route) => json(route, labBuildFailedRun()));
  await page.goto("/overview");
  await page.getByTestId("operator-home-primary-action").click();
  await expect(page).toHaveURL(/\/run-center$/);
  await page.getByTestId("lab-build-primary-action").click();

  const report = page.getByLabel("Completion Report");
  await expect(report).toBeVisible();
  await expect(report.getByLabel("Build result counts")).toHaveCount(1);
  await expect(report.getByLabel("Build result counts").getByText("Completed", { exact: true })).toHaveCount(1);
  await expect(report.getByLabel("Build result counts").getByText("Warnings", { exact: true })).toHaveCount(1);
  await expect(report.getByLabel("Build result counts").getByText("Failed", { exact: true })).toHaveCount(1);
  await expect(report).toContainText("Check the management connection and retry.");
  await expect(report.getByText(/PROVIDER_MODE/)).not.toBeVisible();
  await expect(report.getByTestId("lab-build-primary-action")).toHaveCount(1);
  await expect(report.getByTestId("lab-build-primary-action")).toContainText("Retry Check");
  await expect(report.getByLabel("Technical build log")).not.toBeVisible();
});

test("overview keeps map links explicit without legacy device details", async ({ page }) => {
  await page.goto("/overview");

  await expect(page.locator("section[aria-label='Lab topology'], section[aria-label='Living lab topology']")).toBeVisible();
  await expect(page.locator("details.advanced-drawer").filter({ hasText: "Advanced proof" })).toHaveCount(0);
  await expect(page.getByTestId("operator-home-view-details")).toHaveCount(0);

  const topology = page.locator("section[aria-label='Lab topology'], section[aria-label='Living lab topology']");
  const zonedMap = topology.getByLabel("Zoned lab map");
  if (await zonedMap.count()) {
    await expect(zonedMap).toBeVisible();
    await expect(zonedMap).toContainText("Management");
    await expect(zonedMap).toContainText("Storage & compute");
    await expect(zonedMap).toContainText("vCenter");
    await expect(zonedMap).toContainText("Cisco Switch");
    await expect(zonedMap).toContainText("HPE Gen10");
    await expect(zonedMap).toContainText("NetApp ONTAP");
    await expect(topology.getByLabel("Current lab links")).toContainText(/NFS 10G path|iSCSI 10G planned/);
    const currentMapLinkClasses = await topology.locator(".topology-link").evaluateAll((links) => links.map((link) => link.getAttribute("class") || ""));
    expect(currentMapLinkClasses.length, "current topology renders connection lines").toBeGreaterThan(0);
    expect(
      currentMapLinkClasses.every((className) => /\btopology-link-(reachable|unreachable)\b/.test(className)),
      "current topology lines are explicitly green/red reachable states"
    ).toBe(true);
  } else {
    await expect(topology).toContainText("Cisco Switch");
    await expect(topology).toContainText("NetApp ONTAP");
    const overviewLinkClasses = await topology.locator(".overview-link").evaluateAll((links) => links.map((link) => link.getAttribute("class") || ""));
    expect(overviewLinkClasses.length, "legacy topology renders connection lines").toBeGreaterThan(0);
    expect(
      overviewLinkClasses.every((className) => /\bis-(reachable|unreachable)\b/.test(className)),
      "legacy topology lines are explicitly green/red reachable states"
    ).toBe(true);
  }
  await expect(page.locator("details.advanced-drawer").filter({ hasText: "Advanced proof" })).toHaveCount(0);
});

test("overview map does not mark configured providers reachable without live evidence", async ({ page }) => {
  const staleProviders = providerStatuses().map((provider) => ({
    ...provider,
    checked_at: null,
    freshness: "not_checked",
    is_current: false,
    last_probe_time: null,
    source_type: "not_checked",
    status: "ready"
  }));
  const staleValidation = labValidation();
  staleValidation.validation_items = staleValidation.validation_items.map((item) => ({
    ...item,
    freshness: "not_checked",
    last_checked: null,
    source_type: "not_checked",
    status: "not_checked"
  }));
  const staleVcenter = {
    ...vcenterNetappReadiness(),
    checked_at: null,
    checks: { vm_inventory_visible: { count: 0, visible: false } },
    freshness: "not_checked",
    is_current: false,
    source_type: "not_checked",
    status: "not_checked"
  };
  await page.route("**/api/v1/providers/status", (route) => json(route, staleProviders));
  await page.route("**/api/v1/lab/validation", (route) => json(route, staleValidation));
  await page.route("**/api/v1/lab/vcenter-netapp/readiness", (route) => json(route, staleVcenter));

  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await expect
    .poll(() => topology.locator(".overview-link").count(), {
      message: "overview map renders connection lines"
    })
    .toBeGreaterThan(0);
  await expect(topology.locator(".overview-link.is-reachable")).toHaveCount(0);
  await expect(topology.locator(".overview-link:not(.is-unreachable)")).toHaveCount(0);
});

test("overview map ignores stale positive iLO validation when provider access is not checked", async ({ page }) => {
  const notCheckedProviders = providerStatuses().map((provider) => ({
    ...provider,
    checked_at: null,
    freshness: "unknown",
    is_current: false,
    last_probe_time: null,
    source_type: "not_checked",
    status: "ready"
  }));
  const staleValidation = labValidation();
  staleValidation.validation_items = staleValidation.validation_items.map((item) =>
    item.id === "ilo"
      ? {
          ...item,
          freshness: "current",
          last_checked: "2026-07-18T13:23:38.251258+00:00",
          source_type: "live_probe",
          status: "ready"
        }
      : {
          ...item,
          freshness: "not_checked",
          last_checked: null,
          source_type: "not_checked",
          status: "not_checked"
        }
  );
  await page.route("**/api/v1/providers/status", (route) => json(route, notCheckedProviders));
  await page.route("**/api/v1/lab/validation", (route) => json(route, staleValidation));

  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await expect(topology.getByRole("button", { name: "HPE iLO, Not checked" })).toBeVisible();
  const iloLink = topology.locator("[aria-label='Cisco switch to HPE iLO not reachable']");
  await expect(iloLink).toHaveClass(/is-unreachable/);
});

test("overview map keeps iLO locked when proof is not bound to the current access target", async ({ page }) => {
  await page.route("**/api/v1/providers/ilo-redfish/access-settings", (route) =>
    json(route, iloAccessSettings({
      host: "192.168.1.11",
      last_probe_target_matches_access_host: false,
      last_probe_target_source: "active_lab_profile"
    }))
  );
  await page.route("**/api/v1/lab/validation", (route) => json(route, labValidationNotChecked()));

  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await expect(topology.getByRole("button", { name: "HPE iLO, Not checked" })).toBeVisible();
  await expect(topology.locator("[aria-label='Cisco switch to HPE iLO not reachable']")).toHaveClass(/is-unreachable/);
});

test("overview map shows the proven current iLO address while keeping the planned address separate", async ({ page }) => {
  const plannedMismatchProviders = providerStatuses().map((provider) =>
    provider.id === "ilo-redfish"
      ? {
          ...provider,
          configuration: {
            ...provider.configuration,
            last_probe_target_matches_active_profile: false,
            last_probe_target_matches_configured_candidates: true,
            last_probe_status: "ok"
          },
          status: "ready"
        }
      : provider
  );
  await page.route("**/api/v1/providers/status", (route) => json(route, plannedMismatchProviders));
  await page.route("**/api/v1/providers/ilo-redfish/access-settings", (route) =>
    json(route, iloAccessSettings({
      host: "192.168.1.11",
      last_probe_target_matches_access_host: true,
      last_probe_target_source: "operator_first_contact"
    }))
  );

  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  const iloNode = topology.getByRole("button", { name: "HPE iLO, Ready" });
  await expect(iloNode).toBeVisible();
  await expect(iloNode).toContainText("192.168.1.11");
  await iloNode.click();
  const firstContact = page.getByLabel("iLO access credentials");
  await expect(firstContact).toContainText("Planned final iLO: 192.168.1.201");
  await expect(firstContact.getByLabel("iLO proof route")).toContainText("192.168.1.11");
});

test("editing the visible iLO target invalidates proof until that exact target is rechecked", async ({ page }) => {
  await page.route("**/api/v1/providers/ilo-redfish/access-settings", (route) =>
    json(route, iloAccessSettings({
      host: "192.168.1.11",
      last_probe_status: "ok",
      last_probe_target_matches_access_host: true,
      last_probe_target_source: "operator_first_contact"
    }))
  );
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await topology.getByRole("button", { name: /^HPE iLO,/ }).click();
  const firstContact = page.getByLabel("iLO access credentials");
  const proof = firstContact.getByLabel("iLO first-contact proof");
  await expect(firstContact.getByLabel("iLO host or initial IP")).toHaveValue("192.168.1.11");
  await expect(proof).toContainText("May go green");

  await firstContact.getByLabel("iLO host or initial IP").fill("192.168.1.201");
  await expect(proof.getByLabel("iLO proof route")).toContainText("192.168.1.201");
  await expect(proof).toContainText("Map locked");
  await expect(proof).not.toContainText("fresh proof, so the map may turn green");
});

test("iLO access-settings failure falls back to the initial current address, never the planned address", async ({ page }) => {
  const profiles = labProfiles();
  for (const plan of [
    profiles.active_profile.address_plan,
    profiles.active_profile.resolved_address_plan,
    profiles.active_context.active_profile.address_plan,
    profiles.active_context.active_profile.resolved_address_plan,
    profiles.active_context.resolved_address_plan,
    profiles.runtime_profile.address_plan,
    profiles.runtime_profile.resolved_address_plan
  ]) {
    (plan as Record<string, unknown>).ilo_initial = "192.168.1.11";
  }
  await page.route("**/api/v1/lab/profiles*", (route) => json(route, profiles));
  await page.route("**/api/v1/providers/ilo-redfish/access-settings", (route) =>
    route.fulfill({
      body: JSON.stringify({ detail: "iLO access settings unavailable" }),
      contentType: "application/json",
      status: 500
    })
  );
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await topology.getByRole("button", { name: /^HPE iLO,/ }).click();
  const firstContact = page.getByLabel("iLO access credentials");
  await expect(firstContact.getByLabel("iLO host or initial IP")).toHaveValue("192.168.1.11");
  await expect(firstContact.getByLabel("iLO proof route")).toContainText("192.168.1.11");
  await expect(firstContact.getByLabel("iLO first-contact proof")).toContainText("Map locked");
  await expect(firstContact.getByRole("link", { name: "Open iLO web UI" })).toHaveAttribute("href", "https://192.168.1.11");
});

test("overview iLO drawer puts first contact before planned config and runs the standalone access check", async ({ page }) => {
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await topology.getByRole("button", { name: /^HPE iLO,/ }).click();
  const drawer = page.getByLabel("HPE iLO setup");
  await expect(drawer).toBeVisible();
  const firstContact = drawer.getByLabel("iLO access credentials");
  await expect(firstContact).toBeVisible();
  await expect(firstContact).toContainText("Sign in and first contact");
  await expect(firstContact.getByLabel("iLO username / UID")).toBeVisible();
  await expect(firstContact.getByLabel("iLO password")).toBeVisible();
  await expect(firstContact.getByRole("button", { name: "Check this iLO IP" })).toBeVisible();
  const iloSetup = drawer.getByLabel("iLO setup settings");
  await expect(iloSetup).toContainText("DNS Name");
  await expect(iloSetup).toContainText("NTP Servers");
  await expect(iloSetup).toContainText("SNMP Version");
  await expect(iloSetup).toContainText("System Location");
  await expect(iloSetup).toContainText("Disable all IPv6 options");
  await expect(iloSetup).toContainText("Local users");
  await expect(iloSetup.getByRole("button", { name: "Save iLO setup plan" })).toBeVisible();
  await expect(drawer.getByRole("heading", { name: "Sign-in", exact: true })).toHaveCount(0);
  await expect(drawer.getByRole("button", { name: "Save sign-in" })).toHaveCount(0);
  const drawerOrder = await drawer.locator(".map-drawer-body").evaluate((body) =>
    Array.from(body.children).map((child) => child.getAttribute("aria-label") || child.textContent || "")
  );
  expect(drawerOrder.findIndex((item) => item.includes("iLO access credentials"))).toBeLessThan(
    drawerOrder.findIndex((item) => item.includes("iLO config plan"))
  );

  await firstContact.getByLabel("iLO host or initial IP").fill("192.168.1.201");
  await firstContact.getByLabel("iLO username / UID").fill("Administrator");
  await firstContact.getByLabel("iLO password").fill("secret");
  const accessSave = page.waitForRequest((request) =>
    request.method() === "PUT" &&
    new URL(request.url()).pathname === "/api/v1/providers/ilo-redfish/access-settings"
  );
  const accessCheck = page.waitForRequest((request) =>
    request.method() === "POST" &&
    actionIdFromRunPath(new URL(request.url()).pathname) === "ilo.reachability"
  );
  await firstContact.getByRole("button", { name: "Check this iLO IP" }).click();
  const payload = (await accessSave).postDataJSON() as Record<string, unknown>;
  expect(payload).toMatchObject({
    host: "192.168.1.201",
    password: "secret",
    username: "Administrator",
    verify_tls: false
  });
  const accessCheckPayload = (await accessCheck).postDataJSON() as Record<string, unknown>;
  expect(accessCheckPayload).toMatchObject({ ilo_host: "192.168.1.201" });
  await expect(firstContact).toContainText("iLO access check finished");
});

test("operator home shows actionable blockers once in plain language", async ({ page }) => {
  const blocked = labValidation();
  blocked.overall_status = "blocked";
  blocked.next_action = "Set the Cisco switch management IP, then refresh readiness.";
  blocked.top_blocker = {
    copyable_command: "make provider-lab-cisco-setup-readiness",
    current_value: "missing",
    evidence_links: [],
    expected_value: "192.168.1.204",
    problem: "CISCO_MGMT_NOT_CONFIGURED - Cisco management IP is not ready.",
    recommended_action: "Open Network and set the Cisco switch management IP.",
    recheck_command: "make provider-lab-cisco-setup-readiness",
    source: "CISCO_MGMT_NOT_CONFIGURED",
    where_to_fix: "Cisco switch setup"
  };
  blocked.validation_items = [
    {
      ...blocked.validation_items[0],
      current_state: "Management IP is missing",
      next_action: "Set the Cisco switch management IP.",
      setup_summary: "Cisco switch management IP is not ready.",
      status: "blocked"
    },
    ...blocked.validation_items.slice(1)
  ];
  await page.route("**/api/v1/lab/validation", (route) => json(route, blocked));

  await page.goto("/overview");

  const home = page.getByTestId("operator-home");
  await expect(home.getByLabel("Needs your attention")).toContainText("Cisco management IP is not ready.");
  await expect(home.getByLabel("Needs your attention")).toContainText("Select Cisco switch on the map");
  await expect(home.getByLabel("Needs your attention")).not.toContainText("CISCO_MGMT_NOT_CONFIGURED");
  await expect(home.locator(".operator-rail-blocker").filter({ hasText: "Cisco management IP is not ready." })).toHaveCount(1);
  await expect(page.locator("section[aria-label='Lab topology'], section[aria-label='Living lab topology']")).toBeVisible();
});

test("zoned map opens the device workspace directly", async ({ page }) => {
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await expect(topology).toBeVisible();
  const status = topology.locator(".overview-map-pills");
  await expect(status).toContainText("Live lab");
  await expect(status).toContainText("Subnet matches host");
  await expect(status).not.toContainText("topology items ready");

  const linkClasses = await topology.locator(".overview-link").evaluateAll((links) =>
    links.map((link) => link.getAttribute("class") || "")
  );
  expect(linkClasses.length, "overview map renders connection lines").toBeGreaterThan(0);
  expect(
    linkClasses.every((className) => /\bis-(reachable|unreachable)\b/.test(className)),
    "overview map lines expose only explicit reachable or unreachable states"
  ).toBe(true);

  const vcenterNode = topology.getByRole("button", { name: /^vCenter,/ });
  await expect(vcenterNode).toContainText("vCenter");
  await expect(vcenterNode).not.toContainText("direct ESXi inventory");
  await expect(vcenterNode).not.toContainText("created by this app");

  await topology.getByRole("button", { name: /^Cisco Switch,/ }).click();
  const switchDrawer = page.getByLabel("Cisco Switch setup");
  await expect(switchDrawer).toBeVisible();
  await expect(switchDrawer.getByRole("heading", { name: "Cisco Switch" })).toBeVisible();
  await expect(switchDrawer.getByLabel("Management IP", { exact: true })).toHaveValue("192.168.1.204");
  await expect(switchDrawer.getByRole("button", { name: "Save changes" })).toBeVisible();
  await expect(switchDrawer).toContainText("hardware untouched");
  await expect(switchDrawer).not.toContainText(/Apply|Factory reset|Rebuild|Upgrade/i);
  await switchDrawer.getByRole("button", { name: "Close device panel" }).click();
  await expect(switchDrawer).toHaveCount(0);

  await topology.getByRole("button", { name: /^HPE iLO,/ }).click();
  const iloDrawer = page.getByLabel("HPE iLO setup");
  await expect(iloDrawer).toBeVisible();
  await expect(iloDrawer.getByRole("heading", { name: "HPE iLO" })).toBeVisible();
  await expect(iloDrawer.getByLabel("iLO IP", { exact: true })).toHaveValue("192.168.1.201");
  await expect(iloDrawer.getByLabel("Initial iLO IP", { exact: true })).toBeVisible();
  const firstContact = iloDrawer.getByLabel("iLO access credentials");
  await expect(firstContact).toContainText("Sign in and first contact");
  await expect(firstContact.getByLabel("iLO username / UID")).toBeVisible();
  await expect(firstContact.getByLabel("iLO password")).toBeVisible();
  await expect(firstContact.getByRole("button", { name: "Save iLO access" })).toBeVisible();
  await expect(iloDrawer.getByRole("heading", { name: "Sign-in", exact: true })).toHaveCount(0);
  await expect(iloDrawer).not.toContainText(/Reset Server Power|Boot ESXi Installer|Apply RAID/i);
});

test("overview device drawers never expose destructive primary actions", async ({ page }) => {
  const workflowPosts: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname.includes("/workflows/actions/")) {
      workflowPosts.push(new URL(request.url()).pathname);
    }
  });

  await page.goto("/overview");
  const topology = page.getByRole("region", { name: "Lab topology" });
  for (const item of [
    { button: /^Cisco Switch,/, drawer: "Cisco Switch setup" },
    { button: /^HPE iLO,/, drawer: "HPE iLO setup" },
    { button: /^ESXi Host,/, drawer: "ESXi Host setup" },
    { button: /^NetApp ONTAP,/, drawer: "NetApp ONTAP setup" },
    { button: /^vCenter,/, drawer: "vCenter setup" }
  ] as const) {
    await topology.getByRole("button", { name: item.button }).click();
    const drawer = page.getByLabel(item.drawer);
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("button", { name: /apply|factory reset|rebuild|upgrade|power reset/i })).toHaveCount(0);
    await expect(drawer.getByRole("link", { name: /apply|factory reset|rebuild|upgrade|power reset/i })).toHaveCount(0);
    await expect(drawer).toContainText(/hardware untouched|does not probe or change hardware/i);
    await drawer.getByRole("button", { name: "Close device panel" }).click();
  }

  expect(workflowPosts, "opening and inspecting direct setup drawers runs no workflow").toEqual([]);
});

test("overview device workspace advanced safe checks expose only read-only workflow actions", async ({ page }) => {
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  for (const item of [
    { button: /^Cisco Switch,/, drawer: "Cisco Switch setup" },
    { button: /^HPE iLO,/, drawer: "HPE iLO setup" },
    { button: /^ESXi Host,/, drawer: "ESXi Host setup" },
    { button: /^NetApp ONTAP,/, drawer: "NetApp ONTAP setup" },
    { button: /^vCenter,/, drawer: "vCenter setup" }
  ] as const) {
    await topology.getByRole("button", { name: item.button }).click();
    const drawer = page.getByLabel(item.drawer);
    await expect(drawer.locator("details, .design-workspace-advanced, .design-device-action-list")).toHaveCount(0);
    await expect(drawer.getByRole("button", { name: /apply|reset|rebuild|upgrade/i })).toHaveCount(0);
    await drawer.getByRole("button", { name: "Close device panel" }).click();
  }

  await topology.getByLabel("Local storage offshoot from HPE iLO").click();
  const raidDrawer = page.getByLabel("Local RAID planner drawer");
  await expect(raidDrawer.getByLabel("Local RAID inventory required")).toBeVisible();
  await expect(raidDrawer.getByLabel("Selectable local RAID drive bays from iLO inventory")).toHaveCount(0);
  await expect(raidDrawer.getByRole("button", { name: /Apply RAID|Reset HPE RAID|Factory reset|Boot ESXi Installer/i })).toHaveCount(0);
});

test("overview device matrix opens one unified editor per map node", async ({ page }) => {
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  const cases = [
    { button: /^Cisco Switch,/, drawer: "Cisco Switch setup", fields: ["Management IP", "DNS servers"] },
    { button: /^HPE iLO,/, drawer: "HPE iLO setup", fields: ["iLO IP", "Initial iLO IP"] },
    { button: /^ESXi Host,/, drawer: "ESXi Host setup", fields: ["ESXi IP", "Embedded NIC"] },
    { button: /^NetApp ONTAP,/, drawer: "NetApp ONTAP setup", fields: ["Cluster mgmt IP", "SVM mgmt IP"] },
    { button: /^vCenter,/, drawer: "vCenter setup", fields: ["vCenter IP", "ESXi host"] }
  ] as const;

  for (const item of cases) {
    await topology.getByRole("button", { name: item.button }).click();
    const drawer = page.getByLabel(item.drawer);
    await expect(drawer).toBeVisible();
    for (const field of item.fields) {
      await expect(drawer.getByLabel(field, { exact: true }), `${item.drawer} exposes ${field} inline`).toBeVisible();
    }
    await expect(drawer.locator("input")).not.toHaveCount(0);
    await expect(drawer.getByRole("button", { name: "Save changes" })).toBeVisible();
    await expect(drawer.getByRole("link", { name: /Open full setup|Open setup/i })).toHaveCount(0);
    await expect(page.locator("aside.map-drawer")).toHaveCount(1);
    await drawer.getByRole("button", { name: "Close device panel" }).click();
  }
});

test("overview device drawer avoids duplicate setup links when checks are unavailable", async ({ page }) => {
  workflowActionsOverride = [];
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await topology.getByRole("button", { name: /^ESXi Host,/ }).click();
  const drawer = page.getByLabel("ESXi Host setup");

  await expect(drawer).toBeVisible();
  await expect(drawer.getByLabel("ESXi IP", { exact: true })).toHaveValue("192.168.1.203");
  await expect(drawer.getByRole("link", { name: /Open setup|Open full setup/i })).toHaveCount(0);
  await expect(drawer).not.toContainText("No read-only test registered");
  await expect(drawer.getByRole("button", { name: /apply|reset|rebuild|upgrade/i })).toHaveCount(0);
  await expect(page.locator("aside.map-drawer")).toHaveCount(1);
});

test("setup pages avoid self-linking when read-only checks are unavailable", async ({ page }) => {
  workflowActionsOverride = [];
  await page.goto("/server");

  const workspace = page.locator("section[aria-label='DL360 Gen10 workspace']");
  await expect(workspace).toBeVisible();
  const primaryAction = workspace.locator(":scope > .design-device-primary-action .design-plan-action");
  await expect(primaryAction).toHaveCount(1);
  await expect(primaryAction).toContainText("Finish setup first");
  await expect(primaryAction).toBeDisabled();
  await expect(workspace.getByRole("link", { name: "Open setup" })).toHaveCount(0);
  await expect(workspace).not.toContainText("No read-only test registered");
  await expect(workspace.getByLabel("DL360 Gen10 essentials")).toBeVisible();
});

test("overview device drawer resolves values from the saved active profile", async ({ page }) => {
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await topology.getByRole("button", { name: /^Cisco Switch,/ }).click();
  const drawer = page.getByLabel("Cisco Switch setup");

  await expect(drawer.getByLabel("Management IP", { exact: true })).toHaveValue("192.168.1.204");
  await expect(drawer.getByLabel("Management VLAN", { exact: true })).toHaveValue("10");
  await expect(drawer.getByLabel("DNS servers", { exact: true })).not.toHaveValue("");
  await expect(drawer.getByLabel("Management IP", { exact: true })).not.toHaveValue("Not planned");
  await expect(drawer).toContainText("Saves the plan only");
});

test("setup faceplate element clicks reveal concise details only after intent", async ({ page }) => {
  const cases: Array<{
    assignmentLabel?: string;
    click: RegExp;
    note: string;
    path: string;
    workspace: string;
  }> = [
    {
      assignmentLabel: "Switch port assignment",
      click: /^Switch port 1$/,
      note: "which VLAN lane it belongs to",
      path: "/network",
      workspace: "Cisco switch"
    },
    {
      assignmentLabel: "Drive bay assignment",
      click: /^Drive bay 1/,
      note: "saved RAID role",
      path: "/server",
      workspace: "DL360 Gen10"
    },
    {
      click: /^e0a$/,
      note: "shared storage path",
      path: "/storage",
      workspace: "NetApp ONTAP"
    }
  ];

  for (const item of cases) {
    await page.goto(item.path);
    const workspace = page.locator(`section[aria-label='${item.workspace} workspace']`);
    const essentials = workspace.getByLabel(`${item.workspace} essentials`);
    const visualEditor = workspace.getByLabel(`${item.workspace} visual setup editor`);
    await expect(essentials, `${item.workspace} setup fields are visible before physical planning`).toBeVisible();
    await expect(visualEditor, `${item.workspace} setup page keeps the visual editor behind intent`).toBeVisible();
    await expect(visualEditor, `${item.workspace} uses calmer physical-layout wording`).toContainText(/Physical layout|Plan ports and bays|Inspect faceplate/);
    await expect(visualEditor, `${item.workspace} avoids old imperative planning copy`).not.toContainText("Click the physical part to plan it");
    await expect(workspace.getByLabel(`${item.workspace} interactive faceplate`), `${item.workspace} faceplate starts collapsed`).not.toBeVisible();
    const essentialsBox = await essentials.boundingBox();
    const visualBox = await visualEditor.boundingBox();
    expect((essentialsBox?.y ?? 0), `${item.workspace} shows input fields before physical layout`).toBeLessThan(visualBox?.y ?? Number.MAX_SAFE_INTEGER);
    await visualEditor.locator(":scope > summary").click();
    await expect(workspace.getByLabel(`${item.workspace} interactive faceplate`), `${item.workspace} setup page shows the faceplate after intent`).toBeVisible();
    await workspace.getByRole("button", { name: item.click }).first().click();
    if (item.assignmentLabel) {
      await expect(workspace.getByLabel(item.assignmentLabel), `${item.workspace} shows concise element planning after intent`).toContainText(item.note);
      await expect(workspace.getByLabel(item.assignmentLabel), `${item.workspace} keeps element copy operator-facing`).not.toContainText(/device_settings|workflow|live-proof/i);
    } else {
      const elementNote = workspace.locator(".design-selected-element-note");
      await expect(elementNote, `${item.workspace} shows a compact element note`).toContainText(item.note);
      await expect(elementNote, `${item.workspace} keeps default element copy operator-facing`).not.toContainText(/proof|source|device_settings|workflow|live-proof|read-only/i);
    }
    await expect(workspace.getByLabel(`${item.workspace} advanced checks and proof`), `${item.workspace} still keeps proof closed`).not.toHaveAttribute("open", "");
  }
});

test("topology directs storage exceptions to the NetApp setup drawer", async ({ page }) => {
  const validation = labValidation();
  validation.validation_items = validation.validation_items.map((item) => (
    item.id === "netapp"
      ? { ...item, current_state: "Not reachable", next_action: "Refresh NetApp readiness.", status: "blocked" }
      : item
  ));
  await page.route("**/api/v1/lab/validation", (route) => json(route, validation));
  await page.route("**/api/v1/providers/status", (route) => json(route, [
    providerStatus("cisco-console", "Cisco", "network", "ready"),
    providerStatus("ilo-redfish", "HPE iLO", "server", "ready"),
    providerStatus("esxi-readonly", "ESXi", "virtualization", "ready"),
    providerStatus("netapp-ontap", "NetApp ONTAP", "storage", "blocked")
  ]));
  await page.goto("/overview");

  const home = page.getByTestId("operator-home");
  const topology = page.getByRole("region", { name: "Lab topology" });
  await expect(home.getByLabel("Needs your attention")).toContainText(/NetApp|not reachable|Refresh/i);
  await expect(topology.locator("[aria-label='ESXi host to NetApp ONTAP not reachable']")).toHaveClass(/is-unreachable/);

  await topology.getByRole("button", { name: /^NetApp ONTAP,/ }).click();
  const drawer = page.getByLabel("NetApp ONTAP setup");
  await expect(drawer.getByLabel("Cluster mgmt IP", { exact: true })).toHaveValue("192.168.1.220");
  await expect(drawer.getByRole("link", { name: /Open Storage/i })).toHaveCount(0);
});

test("overview map makes single-server local RAID mode unmistakable", async ({ page }) => {
  labProfileScenario = "single";
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  const map = topology.getByLabel("Device topology");
  const localStorage = topology.getByRole("button", { name: "Local storage offshoot from HPE iLO" });
  await expect(localStorage).toBeVisible();
  await expect(localStorage).toContainText("primary datastore");
  await expect(map).toContainText("HPE iLO");
  await expect(map).toContainText("Cisco Switch");
  await expect(map).not.toContainText("NetApp ONTAP");

  await localStorage.click();
  const planner = page.getByLabel("Local RAID planner drawer").locator(".local-raid-planner");
  await expect(planner).toContainText("Drive bay RAID planner");
  await planner.getByRole("button", { name: /Read storage from iLO/ }).click();
  await expect(planner.getByLabel("Selectable local RAID drive bays")).toContainText("Bay 5");
  await planner.getByRole("button", { name: /Bay 5/ }).click();
  await planner.getByRole("button", { name: "Hot spare", exact: true }).click();
  await planner.getByLabel("RAID level for Datastore array").selectOption("RAID10");
  await expect(planner.getByLabel("Local RAID group connections")).toContainText("Drive bays: 5");
  await expect(planner.getByLabel("Local RAID draft summary")).toContainText("RAID10");
  await planner.getByRole("button", { name: "Save visual RAID plan" }).click();
  await expect(planner).toContainText("Hardware untouched");
  await expect(planner).not.toContainText(/Apply RAID|Reset HPE RAID|Factory reset|Boot ESXi Installer/i);
});

test("overview flags saved subnet mismatch and keeps kit changes available", async ({ page }) => {
  healthHostIpv4Addresses = ["10.10.8.99", "172.20.10.3"];
  await page.goto("/overview");

  const topology = page.locator("section[aria-label='Lab topology'], section[aria-label='Living lab topology']");

  await expect(topology).toContainText("Subnet mismatch");
  await expect(topology).toContainText("Active setup targets 192.168.1.0/24");
  await expect(topology).toContainText("10.10.8.99");

  const editSubnet = page.locator("header[aria-label='Application header']").getByRole("link", { name: "Create or change kit" });
  await expect(editSubnet).toHaveAttribute("href", "/lab-profiles#new");
  await editSubnet.click();
  await expect(page).toHaveURL(/\/lab-profiles#new$/);
  await expect(page.getByRole("heading", { name: "Saved Kits", exact: true })).toBeVisible();
});

test("overview routes kit changes to Saved Kits without running workflows", async ({ page }) => {
  let workflowRunAttempted = false;
  await page.route("**/api/v1/workflows/actions/*/run", async (route) => {
    workflowRunAttempted = true;
    await route.continue();
  });

  await page.goto("/overview");

  const topology = page.locator("section[aria-label='Living lab topology']");
  await expect(topology.locator("section[aria-label='System setup picker']")).toHaveCount(0);
  await page.locator("header[aria-label='Application header']").getByRole("link", { name: "Create or change kit" }).click();
  await expect(page).toHaveURL(/\/lab-profiles#new$/);
  await expect(page.getByRole("heading", { name: "Saved Kits", exact: true })).toBeVisible();
  expect(workflowRunAttempted).toBe(false);
});

test("overview keeps the surface map-first until a node opens its direct setup drawer", async ({ page }) => {
  healthHostIpv4Addresses = ["10.10.8.99", "172.20.10.3"];
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await expect(topology.getByLabel("Device topology")).toBeVisible();
  await expect(page.locator("[aria-label='Design mode rack composer'], [aria-label='Design topology blueprint']")).toHaveCount(0);
  await expect(page.locator("[aria-label='Device workspace overlay']")).toHaveCount(0);
  await expect(topology).toContainText("Subnet mismatch");

  await topology.getByRole("button", { name: /^Cisco Switch,/ }).click();
  const drawer = page.getByLabel("Cisco Switch setup");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByLabel("Management IP", { exact: true })).toHaveValue("192.168.1.204");
  await expect(drawer.getByLabel("Management VLAN", { exact: true })).toHaveValue("10");
  await expect(drawer.getByRole("button", { name: "Save changes" })).toBeVisible();
  await expect(drawer.locator("details, .design-blueprint-stage, .design-rack-stage")).toHaveCount(0);
  await expect(drawer.getByRole("button", { name: /Apply Bootstrap|Upgrade|Factory reset/i })).toHaveCount(0);
});

test("overview map surface stays stable and scalable", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  const map = topology.getByLabel("Device topology");
  await expect(map).toBeVisible();
  await expect(map.locator(".overview-node")).toHaveCount(5);
  await expect(topology.locator(".overview-link")).not.toHaveCount(0);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  const box = await topology.boundingBox();
  expect(box).not.toBeNull();
  expect(box?.width ?? 0).toBeGreaterThan(700);
});

test("overview mobile topology keeps every current device reachable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 860 });
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  const map = topology.getByLabel("Device topology");
  await expect(map).toBeVisible();
  await expect(map.locator(".overview-node")).toHaveCount(5);
  await expect(topology.getByRole("button", { name: /^Cisco Switch,/ })).toBeVisible();
  await expect(topology.getByRole("button", { name: /^HPE iLO,/ })).toBeVisible();
  await expect(topology.getByRole("button", { name: /^ESXi Host,/ })).toBeVisible();
  await expect(topology.getByRole("button", { name: /^NetApp ONTAP,/ })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("operator surfaces stay responsive across mobile and desktop widths", async ({ page }) => {
  const routes = [
    "/overview",
    "/setup/defaults",
    "/firmware-upgrades",
    "/network",
    "/server",
    "/storage",
    "/virtualization",
    "/run-center",
    "/validation",
    "/lab-profiles",
    "/media"
  ];

  for (const route of routes) {
    await expectResponsiveShell(page, route, { width: 390, height: 900 });
    await expectResponsiveShell(page, route, { width: 1280, height: 900 });
  }
});

test("overview direct edits stay local until the operator saves the plan", async ({ page }) => {
  const profileWrites: string[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (request.method() !== "GET" && path.startsWith("/api/v1/lab-profiles")) profileWrites.push(path);
  });
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await topology.getByRole("button", { name: /^ESXi Host,/ }).click();
  let drawer = page.getByLabel("ESXi Host setup");
  const esxiIp = drawer.getByLabel("ESXi IP", { exact: true });
  await expect(esxiIp).toHaveValue("192.168.1.203");
  await esxiIp.fill("192.168.1.250");
  await drawer.getByRole("button", { name: "Close device panel" }).click();

  await topology.getByRole("button", { name: /^ESXi Host,/ }).click();
  drawer = page.getByLabel("ESXi Host setup");
  await expect(drawer.getByLabel("ESXi IP", { exact: true })).toHaveValue("192.168.1.203");
  expect(profileWrites, "closing an unsaved drawer never commits profile or hardware state").toEqual([]);
});

test("overview retires setup lanes in favor of the single-server map", async ({ page }) => {
  labProfileScenario = "single";
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await expect(topology).toContainText(/3 devices/);
  await expect(topology.getByRole("button", { name: /^Cisco Switch,/ })).toBeVisible();
  await expect(topology.getByRole("button", { name: /^HPE iLO,/ })).toBeVisible();
  await expect(topology.getByRole("button", { name: /^ESXi Host,/ })).toBeVisible();
  await expect(topology.getByRole("button", { name: /^NetApp ONTAP,|^vCenter,/ })).toHaveCount(0);
  await expect(topology.getByLabel("Local storage offshoot from HPE iLO")).toContainText("primary datastore");
  await expect(page.locator("section[aria-label='Scenario setup lanes'], .system-setup-picker")).toHaveCount(0);
});

test("single-server map opens local datastore guidance beside the ESXi setup drawer", async ({ page }) => {
  labProfileScenario = "single";
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await expect(topology.getByRole("button", { name: /^NetApp ONTAP,|^vCenter,/ })).toHaveCount(0);

  await topology.getByRole("button", { name: /^ESXi Host,/ }).click();
  const esxiDrawer = page.getByLabel("ESXi Host setup");
  await expect(esxiDrawer.getByLabel("ESXi IP", { exact: true })).toHaveValue("192.168.1.203");
  await expect(esxiDrawer.getByLabel("iLO IP", { exact: true })).toHaveCount(0);
  await expect(esxiDrawer.getByRole("button", { name: /Rebuild|Install|Apply/i })).toHaveCount(0);
  await esxiDrawer.getByRole("button", { name: "Close device panel" }).click();

  await topology.getByLabel("Local storage offshoot from HPE iLO").click();
  const raidDrawer = page.getByLabel("Local RAID planner drawer");
  await expect(raidDrawer).toContainText("No iLO drive inventory yet.");
  await raidDrawer.getByRole("button", { name: /Read storage from iLO/ }).click();
  await expect(raidDrawer.getByLabel("Local RAID context")).toContainText("Server-local datastore");
  await expect(raidDrawer.getByRole("button", { name: /Apply RAID|Reset HPE RAID|Factory reset/i })).toHaveCount(0);
});

test("overview removes superseded layout and console surfaces from operator mode", async ({ page }) => {
  await page.goto("/overview");
  const home = page.getByTestId("operator-home");
  await expect(home).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Change this page" })).toHaveCount(0);
  await expect(page.locator("[data-region-id='topology']")).toHaveCount(0);
  await expect(page.locator("section[aria-label='Lab topology'], section[aria-label='Living lab topology']")).toBeVisible();
  await expect(page.locator("details.advanced-drawer")).toHaveCount(0);
  await expect(page.getByText("Discover Console")).toHaveCount(0);
  await expect(page.getByText("Refresh Cisco Console")).toHaveCount(0);
  await expect(page.getByText("Refresh NetApp Consoles")).toHaveCount(0);

  await expect(page.locator("section[aria-label='Lab topology'], section[aria-label='Living lab topology']")).toBeVisible();
  await expect(page.getByTestId("operator-home-view-details")).toHaveCount(0);
  await expect(page.locator("details.advanced-drawer").filter({ hasText: "Advanced proof" })).toHaveCount(0);
});

test("storage page defaults to canonical NetApp workspace and hides protocol internals", async ({ page }) => {
  await page.route("**/api/v1/providers/netapp-ontap/nfs-vcenter-readiness", (route) => json(route, {
    ...netappNfsVcenterReadiness(),
    blockers: [
      "NetApp cluster management REST is not reachable.",
      "NFS LIF `192.168.1.230` is not accepting TCP/2049."
    ],
    message: "NetApp NFS datastore cannot be checked yet.",
    next_safe_action: "PROVIDER MODE=Read-only lab or PROVIDER_MODE=local-lab-readwrite is required before opening a real NetApp console.",
    status: "blocked"
  }));

  await page.goto("/storage");

  const launcher = page.getByLabel("Storage and NetApp setup launcher");
  const summary = page.getByLabel("Storage and NetApp launcher summary");
  const workspace = page.locator("section[aria-label='NetApp ONTAP workspace']");
  await expect(launcher).toBeVisible();
  await expect(summary).toContainText("NetApp shared datastore");
  await expect(summary).toContainText("NFS");
  await expect(summary).toContainText("Cluster IP");
  await expect(summary).not.toContainText("Data path");
  await expect(summary.locator(".storage-netapp-workspace-facts > span")).toHaveCount(3);
  await expect(workspace).toBeVisible();
  await expect(page.locator(".operator-feedback", { hasText: "Loading" })).toHaveCount(0);
  await expect(workspace.getByRole("heading", { name: "NetApp ONTAP", exact: true })).toBeVisible();
  await expect(workspace.getByLabel("NetApp ONTAP main setup fields")).toContainText("Cluster IP");
  await expect(workspace.getByLabel("NetApp ONTAP main setup fields")).toContainText("Storage mode");
  await expect(workspace.getByLabel("NetApp ONTAP credential setup")).toContainText("Reference only");
  await expect(workspace.locator(":scope > .design-device-primary-action .design-plan-action")).toHaveCount(1);
  await expect(workspace.getByRole("button", { name: "Run NetApp read-only check" })).toBeVisible();
  await expect(workspace.getByLabel("NetApp workspace storage controls")).not.toBeVisible();
  await expect(workspace.getByLabel("Guarded iSCSI apply")).not.toBeVisible();
  await expect(page.getByLabel("Storage Path")).toHaveCount(0);
  await expect(page.getByLabel("Storage path details")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open storage details" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "View storage details" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Change storage path" })).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Change this page" })).toHaveCount(0);
  await expect(page.locator("section[aria-label='Storage reference']")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Apply iSCSI/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /factory|reset/i })).toHaveCount(0);
  const mainText = await visibleMainText(page);
  expect(mainText).not.toMatch(/REST is not reachable|TCP\/2049|target portal|igroup|VMFS|PROVIDER[_ ]MODE|\bprovider\b/i);

  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto("/storage");
  const noBodyOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
  expect(noBodyOverflow).toBeTruthy();
});

test("single-server storage page shows local path without shared storage clutter", async ({ page }) => {
  labProfileScenario = "single";
  await page.goto("/storage");

  const summary = page.getByLabel("Storage and NetApp launcher summary");
  const serverWorkspace = page.locator("section[aria-label='DL360 Gen10 workspace']");
  await expect(summary).toContainText("Server-local RAID");
  await expect(summary).toContainText("Local");
  await expect(summary).toContainText("Server local");
  await expect(serverWorkspace).toBeVisible();
  await expect(page.locator("section[aria-label='NetApp ONTAP workspace']")).toHaveCount(0);
  await expect(summary).not.toContainText("NetApp shared datastore");
  await expect(page.locator("section[aria-label='Storage reference']")).toHaveCount(0);
});

test("storage NetApp workspace reveals migrated NFS iSCSI previews and guarded boundary", async ({ page }) => {
  await page.goto("/storage");

  const workspace = page.locator("section[aria-label='NetApp ONTAP workspace']");
  await expect(workspace).toBeVisible();
  await expect(workspace.getByLabel("NetApp workspace storage controls")).not.toBeVisible();
  await expect(workspace.getByRole("button", { name: /Apply iSCSI/ })).toHaveCount(0);

  const advanced = await openWorkspaceAdvanced(page, "NetApp ONTAP");
  const controls = advanced.getByLabel("NetApp workspace storage controls");
  await expect(controls).toBeVisible();
  await expect(controls).toContainText("Console");
  await expect(controls).toContainText("NFS validate");
  await expect(controls).toContainText("NetApp iSCSI");
  await expect(controls).toContainText("ESXi iSCSI");
  await expect(controls).toContainText("Setup Preview");
  await expect(controls).toContainText("Preview iSCSI");
  await expect(controls).toContainText("Validate iSCSI");
  await expect(controls).toContainText("Preview ESXi iSCSI");
  await expect(controls).toContainText("Validate ESXi iSCSI");
  const guardedApply = advanced.getByLabel("Guarded iSCSI apply");
  await expect(guardedApply).toBeVisible();
  await expect(guardedApply.getByRole("button", { name: /Apply iSCSI/ })).toBeVisible();
  await expect(guardedApply).toContainText("Apply iSCSI stays behind the existing backend gate");
});

test("single-server map removes vCenter and keeps direct ESXi setup separate from iLO", async ({ page }) => {
  labProfileScenario = "single";
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await expect(topology.getByRole("button", { name: /^vCenter,|^NetApp ONTAP,/ })).toHaveCount(0);
  await expect(topology.getByLabel("Local storage offshoot from HPE iLO")).toContainText("primary datastore");

  await topology.getByRole("button", { name: /^ESXi Host,/ }).click();
  const drawer = page.getByLabel("ESXi Host setup");
  await expect(drawer.getByLabel("ESXi IP", { exact: true })).toBeVisible();
  await expect(drawer.getByLabel("iLO IP", { exact: true })).toHaveCount(0);
  await expect(drawer.getByLabel("vCenter IP", { exact: true })).toHaveCount(0);
  await expect(drawer.getByRole("button", { name: /Rebuild|Install|Apply|Reset/i })).toHaveCount(0);
});

test("top nav and map device drawers keep setup direct without dead settings drawers", async ({ page }) => {
  await page.goto("/overview");

  const header = page.getByRole("banner", { name: "Application header" });
  await expect(header.getByRole("navigation", { name: "Primary navigation" }).getByRole("link")).toHaveCount(5);
  await expect(header.getByRole("link", { name: "Create or change kit" })).toHaveAttribute("href", "/lab-profiles#new");
  await expect(header.getByRole("button", { name: "Settings" })).toHaveCount(0);
  await expect(page.locator(".system-setup-picker, section.tab-settings-drawer")).toHaveCount(0);

  const topology = page.getByRole("region", { name: "Lab topology" });
  const linkClasses = await topology.locator(".overview-link").evaluateAll((links) =>
    links.map((link) => link.getAttribute("class") || "")
  );
  expect(linkClasses.length).toBeGreaterThan(0);
  expect(linkClasses.every((className) => /\bis-(reachable|unreachable)\b/.test(className))).toBe(true);

  for (const device of [
    { button: /^Cisco Switch,/, drawer: "Cisco Switch setup", field: "Management IP" },
    { button: /^HPE iLO,/, drawer: "HPE iLO setup", field: "iLO IP" },
    { button: /^ESXi Host,/, drawer: "ESXi Host setup", field: "ESXi IP" },
    { button: /^NetApp ONTAP,/, drawer: "NetApp ONTAP setup", field: "Cluster mgmt IP" },
    { button: /^vCenter,/, drawer: "vCenter setup", field: "vCenter IP" }
  ] as const) {
    await topology.getByRole("button", { name: device.button }).click();
    const drawer = page.getByLabel(device.drawer);
    await expect(drawer.getByLabel(device.field, { exact: true })).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Save changes" })).toBeVisible();
    await expect(drawer.locator("details")).toHaveCount(0);
    await drawer.getByRole("button", { name: "Close device panel" }).click();
  }

  await topology.getByLabel("Local storage offshoot from HPE iLO").click();
  const raidDrawer = page.getByLabel("Local RAID planner drawer");
  await expect(raidDrawer).toContainText("No iLO drive inventory yet.");
  await raidDrawer.getByRole("button", { name: /Read storage from iLO/ }).click();
  await expect(raidDrawer.getByLabel("Local RAID context")).toContainText("boot/staging");
  await expect(raidDrawer.getByRole("button", { name: /Apply RAID|Reset HPE RAID|Factory reset|Boot ESXi Installer/i })).toHaveCount(0);
});

test("overview map keeps single-server local storage as an iLO offshoot", async ({ page }) => {
  labProfileScenario = "single";
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await expect(topology.getByRole("button", { name: /^HPE iLO,/ })).toBeVisible();
  await expect(topology.getByRole("button", { name: /^ESXi Host,/ })).toBeVisible();
  await expect(topology.getByRole("button", { name: /^NetApp ONTAP,/ })).toHaveCount(0);
  await expect(topology.getByRole("button", { name: /^vCenter,/ })).toHaveCount(0);
  const localStorage = topology.getByLabel("Local storage offshoot from HPE iLO");
  await expect(localStorage).toContainText("Local storage");
  await expect(localStorage).toContainText("primary datastore");
  await expect(topology.locator(".overview-link-offshoot")).toHaveCount(1);
  await localStorage.click();
  const raidDrawer = page.getByLabel("Local RAID planner drawer");
  await expect(raidDrawer).toContainText("No iLO drive inventory yet.");
  await raidDrawer.getByRole("button", { name: /Read storage from iLO/ }).click();
  await expect(raidDrawer.locator(".local-raid-planner")).toContainText("Server-local datastore");
  await raidDrawer.getByRole("button", { name: /Bay 6/ }).click();
  await raidDrawer.getByRole("button", { name: "Hot spare", exact: true }).click();
  await raidDrawer.getByLabel("RAID level for Datastore array").selectOption("RAID10");
  await raidDrawer.getByRole("button", { name: "Save visual RAID plan" }).click();
  await expect(raidDrawer).toContainText("Visual RAID plan saved");
  await expect(raidDrawer).not.toContainText(/Apply RAID|Reset HPE RAID|Factory reset|Boot ESXi Installer/i);
  await raidDrawer.getByRole("button", { name: "Close local RAID planner" }).click();

  await topology.getByRole("button", { name: /^HPE iLO,/ }).click();
  let drawer = page.getByLabel("HPE iLO setup");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByLabel("iLO IP", { exact: true })).toBeVisible();
  await expect(drawer.getByLabel("ESXi IP", { exact: true })).toHaveCount(0);
  await drawer.getByRole("button", { name: "Close device panel" }).click();

  await topology.getByRole("button", { name: /^ESXi Host,/ }).click();
  drawer = page.getByLabel("ESXi Host setup");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByLabel("ESXi IP", { exact: true })).toBeVisible();
  await expect(drawer.getByLabel("iLO IP", { exact: true })).toHaveCount(0);
});


test("overview local storage reads only from the current iLO access host", async ({ page }) => {
  let discoveryReads = 0;
  page.on("request", (request) => {
    if (
      request.method() === "GET" &&
      new URL(request.url()).pathname === "/api/v1/providers/ilo-redfish/hpe-storage-discovery"
    ) {
      discoveryReads += 1;
    }
  });
  await page.route("**/api/v1/providers/ilo-redfish/access-settings", (route) =>
    json(route, iloAccessSettings({
      fallback_hosts: ["192.168.1.201"],
      host: "192.168.1.11",
      host_source: "runtime_env",
      last_probe_status: "not_checked",
      last_probe_target_matches_access_host: false
    }))
  );

  await page.goto("/overview");
  await expect.poll(() => discoveryReads).toBeGreaterThan(0);
  const mapDiscoveryReads = discoveryReads;

  const topology = page.getByRole("region", { name: "Lab topology" });
  await topology.getByLabel("Local storage offshoot from HPE iLO").click();
  const raidDrawer = page.getByLabel("Local RAID planner drawer");
  await expect(raidDrawer).toContainText("No iLO drive inventory yet.");
  expect(discoveryReads, "opening local storage does not fetch or display unbound inventory").toBe(mapDiscoveryReads);

  const exactRead = page.waitForRequest((request) =>
    request.method() === "POST" &&
    actionIdFromRunPath(new URL(request.url()).pathname) === "raid.discovery"
  );
  await raidDrawer.getByRole("button", { name: "Read storage from iLO 192.168.1.11" }).click();

  const exactReadPayload = (await exactRead).postDataJSON() as Record<string, unknown>;
  expect(exactReadPayload).toEqual({ ilo_host: "192.168.1.11" });
  const liveDriveGrid = raidDrawer.getByLabel("Selectable local RAID drive bays from iLO inventory");
  await expect(liveDriveGrid).toContainText("Bay 1");
  await expect(liveDriveGrid).toContainText("Live: ESXi OS · RAID1");
  await expect(liveDriveGrid).toContainText("Live: VM datastore · RAID5");
  await expect(liveDriveGrid).toContainText("Live: Hot spare");
  expect(discoveryReads).toBeGreaterThan(mapDiscoveryReads);
});


test("overview local storage stays locked when exact-target evidence is blocked", async ({ page }) => {
  let discoveryReads = 0;
  let failedExactRead = false;
  page.on("request", (request) => {
    if (
      request.method() === "GET" &&
      new URL(request.url()).pathname === "/api/v1/providers/ilo-redfish/hpe-storage-discovery"
    ) {
      discoveryReads += 1;
    }
  });
  await page.route("**/api/v1/providers/ilo-redfish/access-settings", (route) =>
    json(
      route,
      iloAccessSettings({
        fallback_hosts: ["192.168.1.201"],
        host: "192.168.1.11",
        host_source: "runtime_env",
        last_probe_status: failedExactRead ? "failed" : "ok",
        last_probe_target_matches_access_host: true
      })
    )
  );
  await page.route("**/api/v1/providers/ilo-redfish/hpe-storage-discovery", (route) =>
    json(
      route,
      failedExactRead
        ? {
            ...hpeStorageDiscovery(),
            blockers: ["Exact-target iLO storage inventory was not available."],
            controllers: [],
            logical_drives: [],
            physical_drives: [],
            storage_inventory_available: false
          }
        : hpeStorageDiscovery()
    )
  );
  await page.route("**/api/v1/workflows/actions/raid.discovery/run", (route) => {
    failedExactRead = true;
    return json(route, {
      ...workflowActionRun("raid.discovery"),
      blockers: ["Exact-target iLO storage inventory was not available."],
      evidence_status: "blocked",
      status: "failed"
    });
  });

  await page.goto("/overview");
  await expect.poll(() => discoveryReads).toBeGreaterThan(0);

  const topology = page.getByRole("region", { name: "Lab topology" });
  await expect(topology.getByRole("button", { name: "HPE iLO, Ready" })).toBeVisible();
  await expect(topology.locator("[aria-label='Local storage path reachable']")).toHaveClass(/is-reachable/);
  await topology.getByLabel("Local storage offshoot from HPE iLO").click();
  const raidDrawer = page.getByLabel("Local RAID planner drawer");
  await raidDrawer.getByRole("button", { name: "Read storage from iLO 192.168.1.11" }).click();

  await expect(raidDrawer).toContainText("Exact-target iLO storage inventory was not available.");
  await expect(raidDrawer.getByLabel("Selectable local RAID drive bays from iLO inventory")).toHaveCount(0);
  await expect(topology.getByRole("button", { name: "HPE iLO, Ready" })).toHaveCount(0);
  await expect(topology.locator("[aria-label='Local storage path not reachable']")).toHaveClass(/is-unreachable/);
});


test("operator button matrix keeps default actions simple and safe", async ({ page }) => {
  const forbiddenDefaultCopy = /ACKNOWLEDGE|NETAPP_ISCSI_SETUP|APPLY NETAPP ISCSI SETUP|Apply iSCSI|Factory reset|Reset HPE RAID|Boot ESXi Installer|PROVIDER_MODE|PROVIDER MODE/i;
  const surfaces: Array<{ label: string; path: string; primary: () => ReturnType<Page["locator"]> }> = [
    { label: "Overview", path: "/overview", primary: () => page.getByTestId("operator-home-primary-action") },
    { label: "Lab Defaults", path: "/setup/defaults", primary: () => page.locator(".lab-defaults-actions .operator-primary-button") },
    { label: "Network", path: "/network", primary: () => page.locator("section[aria-label='Cisco switch workspace'] > .design-device-primary-action .design-plan-action") },
    { label: "Server", path: "/server", primary: () => page.locator("section[aria-label='DL360 Gen10 workspace'] > .design-device-primary-action .design-plan-action") },
    { label: "Storage", path: "/storage", primary: () => page.locator("section[aria-label='NetApp ONTAP workspace'] > .design-device-primary-action .design-plan-action") },
    { label: "Virtualization", path: "/virtualization", primary: () => page.locator("section[aria-label='vCenter VCSA workspace'] > .design-device-primary-action .design-plan-action") },
    { label: "Firmware", path: "/firmware-upgrades", primary: () => page.getByRole("button", { name: "Check versions" }) },
    { label: "Software Media", path: "/media", primary: () => page.locator(".page-actions .primary") },
    { label: "Validation", path: "/validation", primary: () => page.locator(".validation-readiness-actions .operator-primary-button") },
    { label: "Run Center", path: "/run-center", primary: () => page.getByTestId("lab-build-primary-action") }
  ];

  for (const surface of surfaces) {
    await page.goto(surface.path);
    const primary = surface.primary();
    await expect(primary, `${surface.label} has one primary action`).toHaveCount(1);
    await expect(primary.first(), `${surface.label} primary action is visible`).toBeVisible();
    const label = await primary.first().evaluate((element) => (element.textContent || "").replace(/\s+/g, " ").trim());
    expect(label, `${surface.label} primary action has a short label`).toMatch(/^[^.!?]{1,36}$/);
    expect(await visibleMainText(page), `${surface.label} hides guarded/destructive copy by default`).not.toMatch(forbiddenDefaultCopy);
  }
});

test("operator primary check buttons run only expected read-only workflows", async ({ page }) => {
  const forbiddenActionIds = /^(raid\.apply|raid\.reset-commit|esxi\.rebuild-install|ilo\.reset-server|netapp\.factory-reset-apply|netapp\.setup-apply|firmware\.upgrade-apply-placeholder|cisco\.apply-bootstrap|vcenter\.attach-esxi-apply|esxi\.netapp-datastore-apply|esxi\.vm-deploy-apply)$/;
  const actionCatalog = new Map(workflowActions().map((action) => [String(action.action_id), action]));
  const capturedActionIds: string[] = [];

  page.on("request", (request) => {
    if (request.method() !== "POST") return;
    const url = new URL(request.url());
    if (!url.pathname.match(/^\/api\/v1\/workflows\/actions\/.+\/run$/)) return;
    capturedActionIds.push(actionIdFromRunPath(url.pathname));
  });

  const cases: Array<{ click: () => Promise<void>; expectedActionIds: string[]; label: string; path: string }> = [
    {
      click: () => page.locator("section[aria-label='Cisco switch workspace'] > .design-device-primary-action").getByRole("button", { name: "Run Cisco read-only check" }).click(),
      expectedActionIds: ["cisco.ssh-readonly-probe"],
      label: "Network",
      path: "/network"
    },
    {
      click: () => page.locator("section[aria-label='DL360 Gen10 workspace'] > .design-device-primary-action").getByRole("button", { name: "Test DL360 Gen10" }).click(),
      expectedActionIds: ["esxi.management-validation"],
      label: "Server",
      path: "/server"
    },
    {
      click: () => page.locator("section[aria-label='NetApp ONTAP workspace'] > .design-device-primary-action").getByRole("button", { name: "Run NetApp read-only check" }).click(),
      expectedActionIds: ["netapp.setup-preview"],
      label: "Storage",
      path: "/storage"
    },
    {
      click: () => page.locator("section[aria-label='vCenter VCSA workspace'] > .design-device-primary-action").getByRole("button", { name: "Test vCenter VCSA" }).click(),
      expectedActionIds: ["vcenter-netapp.readiness"],
      label: "Virtualization",
      path: "/virtualization"
    },
    {
      click: () => page.getByRole("button", { name: "Check versions" }).click(),
      expectedActionIds: ["firmware.inventory"],
      label: "Firmware",
      path: "/firmware-upgrades"
    }
  ];

  for (const surface of cases) {
    for (const actionId of surface.expectedActionIds) {
      const action = actionCatalog.get(actionId);
      expect(action, `${surface.label} primary action ${actionId} is registered in the workflow catalog`).toBeTruthy();
      expect(["read_only", "report_only"], `${surface.label} primary action ${actionId} is cataloged as safe to run`)
        .toContain(String(action?.mode));
      expect(action?.ui_run_supported, `${surface.label} primary action ${actionId} is UI runnable only as a safe action`).toBeTruthy();
    }
    capturedActionIds.length = 0;
    await page.goto(surface.path);
    await surface.click();
    await expect.poll(
      () => capturedActionIds.length,
      { message: `${surface.label} runs only its expected primary workflow action count`, timeout: 5000 }
    ).toBe(surface.expectedActionIds.length);
    expect(capturedActionIds, `${surface.label} never starts guarded/write actions from the default primary button`)
      .not.toEqual(expect.arrayContaining([expect.stringMatching(forbiddenActionIds)]));
    expect([...capturedActionIds].sort(), `${surface.label} primary button target`).toEqual([...surface.expectedActionIds].sort());
  }
});

test("operator pages avoid test-mode wording for live run controls", async ({ page }) => {
  for (const path of ["/overview", "/network", "/server", "/storage", "/virtualization", "/firmware-upgrades", "/validation"]) {
    await page.goto(path);
    await expect(page.getByText("Run Test")).toHaveCount(0);
    await expect(page.getByText("Use these buttons to test or change this part of the lab.")).toHaveCount(0);
  }
});

test("setup pages load while remaining run actions stay registered", async ({ page }) => {
  for (const path of ["/network", "/server", "/storage", "/virtualization"]) {
    await page.goto(path);
    await expect(page.getByText(/no backend action is registered yet/i)).toHaveCount(0);
    await expect(page.getByText(/missing a runnable backend action/i)).toHaveCount(0);
  }

  await page.route("**/api/v1/lab/validation", (route) => json(route, labValidationNotChecked()));
  await page.goto("/validation");
  const response = page.waitForResponse((nextResponse) =>
    nextResponse.url().includes("/api/v1/workflows/actions/build-verification.run-full/run") &&
    nextResponse.request().method() === "POST"
  );
  await page.getByRole("button", { name: /Run validation/i }).click();
  await expect((await response).ok()).toBeTruthy();
  await expect(page.getByText(/no backend action is registered yet/i)).toHaveCount(0);
  await expect(page.getByText(/missing a runnable backend action/i)).toHaveCount(0);
});

test("network default opens canonical Cisco workspace and hides retired network forms", async ({ page }) => {
  await page.goto("/network");

  const launcher = page.getByLabel("Cisco switch setup launcher");
  const workspace = page.locator("section[aria-label='Cisco switch workspace']");
  await expect(launcher).toBeVisible();
  await expect(workspace).toBeVisible();
  await expect(workspace.getByRole("heading", { name: "Cisco Switch" })).toBeVisible();
  await expect(workspace.getByLabel("Cisco switch main setup fields")).toContainText("Management IP");
  await expect(workspace.getByLabel("Cisco switch main setup fields")).toContainText("Storage VLAN");
  await expect(workspace.getByLabel("Cisco switch credential setup")).toContainText("Reference only");
  await expect(workspace.getByRole("button", { name: "Run Cisco read-only check" })).toBeVisible();

  const visualEditor = workspace.getByLabel("Cisco switch visual setup editor");
  await expect(visualEditor).toContainText("Plan ports and bays");
  await expect(workspace.getByLabel("Cisco switch interactive faceplate")).not.toBeVisible();
  await visualEditor.locator(":scope > summary").click();
  await expect(workspace.getByRole("button", { name: "Switch port 1", exact: true })).toBeVisible();

  await expect(workspace.getByLabel("Cisco workspace network controls")).not.toBeVisible();
  await expect(page.getByLabel("Switch Access")).toHaveCount(0);
  await expect(page.locator("section[aria-label='Network details']")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Apply Bootstrap/i })).toHaveCount(0);
});

test("network console first contact pins one exact cable before read-only identity verification", async ({ page }) => {
  const unsafeDiscoveryRequests: string[] = [];
  page.on("request", (request) => {
    if (/prompt-readiness|discover-console|providers\/cisco-console\/probe/.test(request.url())) {
      unsafeDiscoveryRequests.push(request.url());
    }
  });

  await page.goto("/network");

  const panel = page.getByLabel("Cisco console first contact");
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("heading", { name: "Choose the physical Cisco cable" })).toBeVisible();
  await expect(panel).toContainText("Cisco default: 9600");
  await expect(panel).toContainText("Modern NetApp: 115200");
  await expect(panel.getByRole("button", { name: "This is the Cisco cable" })).toHaveCount(2);
  await expect(panel.getByRole("button", { name: /Verify Cisco identity/i })).toBeDisabled();

  const prolific = panel.locator("article", { hasText: "COM5" });
  await expect(prolific).toContainText("Prolific USB-to-Serial");
  await expect(prolific).toContainText("067B:2303");
  await expect(prolific).toContainText("USB port 1-6");
  await prolific.getByRole("button", { name: "This is the Cisco cable" }).click();

  await expect(prolific.getByRole("button", { name: "Cisco cable selected" })).toBeVisible();
  await expect(panel.getByRole("button", { name: /Verify Cisco identity/i })).toBeEnabled();
  const verifyResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/cisco-console/verify-identity") &&
    response.request().method() === "POST"
  );
  await panel.getByRole("button", { name: /Verify Cisco identity/i }).click();
  const requestPayload = (await verifyResponse).request().postDataJSON() as Record<string, unknown>;

  expect(requestPayload).toEqual({
    baud: 9600,
    candidate_fingerprint: "candidate-prolific-com5",
    port: "COM5"
  });
  await expect(panel).toContainText("This adapter is verified as Cisco");
  await expect(panel).toContainText("C9300-48P");
  await expect(panel).toContainText("show version, show inventory");
  expect(unsafeDiscoveryRequests).toEqual([]);
});

test("network console first contact fails closed when the pinned cable answers as NetApp", async ({ page }) => {
  await page.route("**/api/v1/providers/cisco-console/verify-identity", (route) => json(route, {
    baud: 115200,
    blockers: ["The selected console answered as NetApp, not Cisco."],
    candidate_fingerprint: "candidate-prolific-com5",
    checked_at: checkedAt,
    commands_attempted: [],
    detected_vendor: "netapp",
    identity_verified: false,
    message: "NetApp ONTAP console signature detected. No Cisco commands were sent.",
    model: null,
    port: "COM5",
    prompt_state: "ontap_prompt",
    provider_id: "cisco-console",
    read_only: true,
    serial_fingerprint: null,
    software_version: null,
    status: "blocked",
    warnings: []
  }));
  await page.goto("/network");

  const panel = page.getByLabel("Cisco console first contact");
  const prolific = panel.locator("article", { hasText: "COM5" });
  await prolific.getByRole("button", { name: "This is the Cisco cable" }).click();
  await panel.getByLabel("Expected console baud").selectOption("115200");
  await panel.getByRole("button", { name: /Verify Cisco identity/i }).click();

  await expect(panel).toContainText("NetApp console detected — stopped safely");
  await expect(panel).toContainText("No Cisco commands were sent");
  await expect(panel).toContainText("Wrong console");
  await expect(panel).not.toContainText("This adapter is verified as Cisco");
});

test("lab defaults keeps all DNS NTP and SNMP values visible without advanced or expected-device clutter", async ({ page }) => {
  await page.goto("/setup/defaults");

  await expect(page.getByRole("heading", { name: "Lab Defaults", exact: true })).toBeVisible();
  const network = page.getByLabel("Network defaults");
  await expect(network.getByLabel("Subnet", { exact: true })).toBeVisible();
  await expect(network.getByLabel("Gateway", { exact: true })).toBeVisible();
  await expect(network.getByLabel("DNS defaults")).toBeVisible();
  await expect(network.getByLabel("NTP defaults")).toBeVisible();
  await expect(network.getByLabel("SNMP defaults")).toBeVisible();
  await expect(network.getByLabel("SNMP version")).toHaveValue("v2c");

  await network.getByRole("button", { name: "Add DNS server" }).click();
  await network.getByRole("button", { name: "Add NTP server" }).click();
  await network.getByRole("button", { name: "Add SNMP manager" }).click();
  await expect(network.getByRole("textbox", { name: "DNS server 2", exact: true })).toBeVisible();
  await expect(network.getByRole("textbox", { name: "NTP server 2", exact: true })).toBeVisible();
  await expect(network.getByRole("textbox", { name: "SNMP manager 2", exact: true })).toBeVisible();

  await expect(page.getByText("Expected devices", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Advanced", { exact: true })).toHaveCount(0);
  await expect(page.locator("details")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Save defaults" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Apply|Reset|Rebuild|Upgrade/i })).toHaveCount(0);
});

test("network no-kit state does not show stale loading feedback", async ({ page }) => {
  labProfileScenario = "none";
  await page.route("**/api/v1/providers/cisco-ios-xe/setup-readiness", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    return json(route, ciscoSetupReadiness());
  });

  await page.goto("/network");

  await expect(page.getByLabel("Cisco switch setup launcher")).toBeVisible();
  await expect(page.locator("section[aria-label='Cisco switch workspace']")).toBeVisible();
  await expect(page.locator(".operator-feedback", { hasText: "Loading" })).toHaveCount(0);
});

test("network Cisco workspace reveals migrated settings and nested read-only proof", async ({ page }) => {
  await page.goto("/network");
  const workspace = page.locator("section[aria-label='Cisco switch workspace']");
  await expect(workspace).toBeVisible();
  await expect(workspace.getByLabel("Cisco switch main setup fields")).toContainText("Management IP");
  await expect(workspace.getByLabel("Cisco switch main setup fields")).toContainText("Storage VLAN");
  await openCredentialReferences(page, "Cisco switch", ["CISCO_TEST_PASSWORD"]);
  await expect(workspace.getByLabel("Cisco switch edit settings")).toContainText("More settings");
  await expect(workspace.getByLabel("Cisco switch edit settings")).toContainText("Profile only");
  await expect.poll(
    () => workspace.getByLabel("Cisco switch edit settings").evaluate((node) => (node as HTMLDetailsElement).open),
    { message: "Cisco optional setup fields start collapsed" }
  ).toBe(false);
  await expect(workspace.getByLabel("Cisco switch quick setup fields")).not.toBeVisible();
  await expect(workspace.getByLabel("Cisco switch more setup fields")).not.toBeVisible();
  const networkFields = await openWorkspaceEditGroup(page, "Cisco switch", "Network");
  await expect(networkFields).toContainText("Port profiles");
  const accessFields = await openWorkspaceEditGroup(page, "Cisco switch", "Access");
  await expect(accessFields).toContainText("Black-hole VLAN");
  await expect(accessFields).toContainText("ACL lanes");
  await expect(workspace.getByLabel("Cisco workspace network controls")).not.toBeVisible();

  const advanced = await openWorkspaceAdvanced(page, "Cisco switch");
  const controls = advanced.getByLabel("Cisco workspace network controls");
  await expect(controls).toBeVisible();
  await expect(controls).toContainText("Network-page checks moved into the switch workspace");
  await expect(controls).toContainText("Management IP");
  await expect(controls).toContainText("Setup readiness");
  await expect(controls).toContainText("SSH probe");
  await expect(controls).toContainText("Intent diff");
  await expect(controls).toContainText("Firmware");
  await expect(controls).toContainText("Refresh live evidence");
  await expect(controls).toContainText("Cisco Access Live Check");
  const planProof = controls.getByLabel("Cisco switch plan proof");
  await expect(planProof.locator(":scope > summary")).toContainText("Port, VLAN, and guardrail proof");
  await planProof.locator(":scope > summary").click();
  await expect(page.getByLabel("Cisco switch driver")).toBeVisible();
});

test("network primary check runs through the Cisco read-only workspace action", async ({ page }) => {
  await page.goto("/network");

  const runResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/cisco.ssh-readonly-probe/run") &&
    response.request().method() === "POST"
  );
  await page.locator("section[aria-label='Cisco switch workspace'] > .design-device-primary-action").getByRole("button", { name: "Run Cisco read-only check" }).click();
  await expect((await runResponse).ok()).toBeTruthy();
  await expect(page.locator("section[aria-label='Cisco switch workspace']")).toContainText("Cisco SSH Read-Only Probe:");
});

test("network default hides internal mode vocabulary", async ({ page }) => {
  await page.route("**/api/v1/providers/cisco/setup-readiness", (route) => json(route, {
    ...ciscoSetupReadiness(),
    blockers: ["Cisco SSH is not reachable.", "PROVIDER_MODE=local-lab-readwrite runtime missing credential"],
    management_configured: false,
    message: "PROVIDER MODE=mock runtime provider credential is missing.",
    next_safe_action: "PROVIDER MODE=mock runtime provider password missing.",
    status: "blocked"
  }));

  await page.goto("/network");
  const workspace = page.locator("section[aria-label='Cisco switch workspace']");
  await expect(workspace).toBeVisible();
  await expect(workspace.getByLabel("Cisco workspace network controls")).not.toBeVisible();
  const text = await visibleMainText(page);
  expect(text ?? "").not.toMatch(/PROVIDER[_ ]MODE/i);
  expect(text ?? "").not.toMatch(/\bprovider\b/i);
  expect(text ?? "").not.toMatch(/\bruntime\b/i);
});

test("network surface has no horizontal overflow on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/network");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("server default opens canonical Compute workspace and keeps guarded actions out of first glance", async ({ page }) => {
  await page.goto("/server");

  const launcher = page.getByLabel("Compute and iLO setup launcher");
  const workspace = page.locator("section[aria-label='DL360 Gen10 workspace']");
  await expect(launcher).toBeVisible();
  await expect(workspace).toBeVisible();
  await expect(workspace.getByRole("heading", { name: "DL360 Gen10" })).toBeVisible();
  await expect(page.getByLabel("Compute and iLO launcher summary")).toContainText("iLO IP");
  await expect(page.getByLabel("Compute and iLO launcher summary")).toContainText("ESXi IP");
  await expect(page.getByLabel("Compute and iLO launcher summary")).toContainText("Storage path");
  await expect(workspace.getByLabel("DL360 Gen10 main setup fields")).toContainText("iLO IP");
  await expect(workspace.getByLabel("DL360 Gen10 main setup fields")).toContainText("ESXi IP");
  await expect(workspace.getByLabel("DL360 Gen10 credential setup")).toContainText("Reference only");
  await expect(workspace.getByRole("button", { name: "Test DL360 Gen10" })).toBeVisible();
  await expect(workspace.getByLabel("DL360 Gen10 interactive faceplate")).not.toBeVisible();
  await expect(workspace.getByLabel("Server workspace checks")).not.toBeVisible();
  await expect(workspace.getByRole("button", { name: /reset|rebuild|apply|install/i })).toHaveCount(0);
  await expect(workspace).not.toContainText(/\bprovider\b|\bruntime\b/i);
});

test("server workspace reveals migrated setup, storage path, service pack, and RAID evidence", async ({ page }) => {
  await page.goto("/server");

  const workspace = page.locator("section[aria-label='DL360 Gen10 workspace']");
  await expect(workspace.getByLabel("DL360 Gen10 main setup fields")).toContainText("iLO IP");
  await expect(workspace.getByLabel("DL360 Gen10 main setup fields")).toContainText("ESXi IP");
  await openCredentialReferences(page, "DL360 Gen10", ["ILO_TEST_PASSWORD", "ESXI_TEST_PASSWORD"]);
  await expect(workspace.getByLabel("DL360 Gen10 edit settings")).toContainText("More settings");
  await expect(workspace.getByLabel("DL360 Gen10 edit settings")).toContainText("Profile only");
  await expect.poll(
    () => workspace.getByLabel("DL360 Gen10 edit settings").evaluate((node) => (node as HTMLDetailsElement).open),
    { message: "Server optional setup fields start collapsed" }
  ).toBe(false);
  await expect(workspace.getByLabel("DL360 Gen10 more setup fields")).not.toBeVisible();
  const storageGroup = await openWorkspaceEditGroup(page, "DL360 Gen10", "Storage");
  await expect(storageGroup).toContainText("RAID controller");
  await expect(storageGroup).toContainText("Boot RAID");
  await expect(storageGroup).not.toContainText("Data RAID");
  await expect(workspace.getByLabel("Server workspace checks")).not.toBeVisible();

  const advanced = await openWorkspaceAdvanced(page, "DL360 Gen10");
  const serverControls = advanced.getByLabel("Server workspace checks");
  await expect(serverControls).toBeVisible();
  await expect(serverControls).toContainText("ESXi and RAID checks");
  await expect(serverControls).toContainText("Validate RAID");
  await expect(serverControls).toContainText("Preview RAID");
  await expect(serverControls).toContainText("Check RAID Pending");
  await expect(serverControls).toContainText("HPE Service Pack");
  await expect(serverControls).toContainText("Storage path");
  await expect(serverControls.getByLabel("RAID guarded write boundary")).toContainText("stay off this map");
  await expect(page.getByRole("button", { name: /Reset HPE RAID|Apply RAID|Boot ESXi Installer/i })).toHaveCount(0);
});

test("server workspace primary check runs through the ESXi read-only action endpoint", async ({ page }) => {
  await page.goto("/server");

  const runResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/esxi.management-validation/run") &&
    response.request().method() === "POST"
  );
  await page.locator("section[aria-label='DL360 Gen10 workspace'] > .design-device-primary-action").getByRole("button", { name: "Test DL360 Gen10" }).click();
  await expect((await runResponse).ok()).toBeTruthy();
  await expect(page.locator("section[aria-label='DL360 Gen10 workspace']")).toContainText("ESXi Live Check:");
});

test("server blocker copy hides internal mode vocabulary", async ({ page }) => {
  await page.route("**/api/v1/providers/ilo-redfish/esxi-install-readiness", (route) => json(route, {
    ...esxiInstallReadiness(),
    blockers: ["PROVIDER_MODE=local-lab-readwrite runtime provider credential is missing."],
    message: "PROVIDER MODE=mock runtime provider credential is missing.",
    next_safe_action: "PROVIDER_MODE=mock runtime provider password missing.",
    status: "blocked"
  }));

  await page.goto("/server");
  const workspace = page.locator("section[aria-label='DL360 Gen10 workspace']");
  await expect(workspace).toBeVisible();
  await expect(workspace.getByLabel("Server workspace checks")).not.toBeVisible();
  const text = await visibleMainText(page);
  expect(text ?? "").not.toMatch(/PROVIDER[_ ]MODE/i);
  expect(text ?? "").not.toMatch(/\bprovider\b/i);
  expect(text ?? "").not.toMatch(/\bruntime\b/i);
});

test("server RAID blocker copy stays out of default operator mode", async ({ page }) => {
  await page.route("**/api/v1/providers/ilo-redfish/hpe-raid-plan-preview", (route) => json(route, {
    ...hpeRaidPlanPreview(),
    blockers: ["Saved intent requests destructive wipe/delete planning. Execution remains disabled."],
    message: "Saved intent requests destructive wipe/delete planning. Execution remains disabled.",
    status: "blocked"
  }));

  await page.goto("/server");
  const workspace = page.locator("section[aria-label='DL360 Gen10 workspace']");
  await expect(workspace).toBeVisible();
  await expect(workspace.getByLabel("Server workspace checks")).not.toBeVisible();
  const text = await visibleMainText(page);
  expect(text).not.toMatch(/destructive wipe\/delete planning|Execution remains disabled|Applying it is locked/i);
});

test("server surface has no horizontal overflow on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/server");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("virtualization default opens canonical vCenter workspace and hides old VM panels", async ({ page }) => {
  await page.goto("/virtualization");

  const summary = page.getByLabel("Virtualization launcher summary");
  const workspace = page.locator("section[aria-label='vCenter VCSA workspace']");
  await expect(summary).toContainText("Control path");
  await expect(summary).toContainText("vCenter");
  await expect(summary).toContainText("Target");
  await expect(summary).toContainText("Datastore");
  await expect(summary).not.toContainText("VM path");
  await expect(summary.locator(".virtualization-vcenter-workspace-facts > span")).toHaveCount(3);
  await expect(workspace).toBeVisible();
  await expect(page.locator(".operator-feedback", { hasText: "Loading" })).toHaveCount(0);
  await expect(workspace.getByRole("heading", { name: "vCenter VCSA", exact: true })).toBeVisible();
  await expect(workspace.getByLabel("vCenter VCSA main setup fields")).toContainText("Management IP");
  await expect(workspace.getByLabel("vCenter VCSA main setup fields")).toContainText("Datastore");
  await expect(workspace.getByLabel("vCenter VCSA credential setup")).toContainText("Reference only");
  await expect(workspace.locator(":scope > .design-device-primary-action .design-plan-action")).toHaveCount(1);
  await expect(workspace.getByRole("button", { name: "Test vCenter VCSA" })).toBeVisible();
  await expect(workspace.getByLabel("vCenter workspace virtualization controls")).not.toBeVisible();
  await expect(workspace.getByRole("button", { name: /deploy|attach|create|delete|migrate|write/i })).toHaveCount(0);
  await expect(page.getByLabel("VM Management")).toHaveCount(0);
  await expect(page.locator("section[aria-label='VM details']")).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Change this page" })).toHaveCount(0);
  await expect(page.getByText("Virtualization setup shape")).toHaveCount(0);
  await expect(page.getByText("Virtualization readiness at a glance")).toHaveCount(0);
  await expect(page.getByText("vCenter source")).toHaveCount(0);
  const text = await visibleMainText(page);
  expect(text ?? "").not.toMatch(/\bprovider\b/i);
  expect(text ?? "").not.toMatch(/\bruntime\b/i);
  expect(text ?? "").not.toMatch(/\bpayload\b/i);
  expect(text ?? "").not.toMatch(/\bpost-attach\b/i);
  expect(text ?? "").not.toMatch(/\bsource\b/i);
  expect(text ?? "").not.toMatch(/\bfreshness\b/i);
});

test("virtualization no-kit state does not show stale loading feedback", async ({ page }) => {
  labProfileScenario = "none";
  await page.goto("/virtualization");

  await expect(page.getByLabel("Virtualization setup launcher")).toBeVisible();
  await expect(page.locator("section[aria-label='vCenter VCSA workspace']")).toBeVisible();
  await expect(page.locator(".operator-feedback", { hasText: "Loading" })).toHaveCount(0);
});

test("setup surfaces hide stale loading while background checks are slow", async ({ page }) => {
  const slowEmpty = async (route: Route) => {
    await new Promise((resolve) => setTimeout(resolve, 5000));
    return json(route, []);
  };
  await page.route("**/api/v1/workflows/actions", slowEmpty);
  await page.route("**/api/v1/firmware/summary", slowEmpty);
  await page.route("**/api/v1/lab/firmware-compliance**", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 5000));
    return json(route, null);
  });
  await page.route("**/api/v1/firmware/file-selections", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 5000));
    return json(route, { selected_files: {} });
  });

  for (const [path, heading] of [
    ["/setup/cisco", "Cisco Switch"],
    ["/setup/ilo", "Compute & iLO"],
    ["/setup/storage", "Storage & NetApp"],
    ["/setup/firmware", "Keep every device on the expected version."]
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    await expect(page.locator(".operator-feedback", { hasText: "Loading" })).toHaveCount(0);
  }
});

test("virtualization vCenter workspace reveals migrated checks and guarded boundary", async ({ page }) => {
  await page.goto("/virtualization");

  const workspace = page.locator("section[aria-label='vCenter VCSA workspace']");
  await expect(workspace.getByLabel("vCenter VCSA main setup fields")).toContainText("Management IP");
  await expect(workspace.getByLabel("vCenter VCSA main setup fields")).toContainText("Datastore");
  await openCredentialReferences(page, "vCenter VCSA", ["VCENTER_PASSWORD"]);
  await expect(workspace.getByLabel("vCenter VCSA edit settings")).toContainText("More settings");
  await expect(workspace.getByLabel("vCenter VCSA edit settings")).toContainText("Profile only");
  await expect.poll(
    () => workspace.getByLabel("vCenter VCSA edit settings").evaluate((node) => (node as HTMLDetailsElement).open),
    { message: "vCenter optional setup fields start collapsed" }
  ).toBe(false);
  await expect(workspace.getByLabel("vCenter VCSA more setup fields")).not.toBeVisible();
  await expect(workspace.getByLabel("vCenter workspace virtualization controls")).not.toBeVisible();

  const advanced = await openWorkspaceAdvanced(page, "vCenter VCSA");
  const controls = advanced.getByLabel("vCenter workspace virtualization controls");
  await expect(controls).toBeVisible();
  await expect(controls).toContainText("vCenter and VM checks");
  await expect(controls).toContainText("vCenter Live Check");
  await expect(controls).toContainText("vCenter Install Readiness");
  await expect(controls).toContainText("Validate Datastore");
  await expect(controls).toContainText("Validate VM Inventory");
  await expect(controls.getByLabel("vCenter guarded write boundary")).toContainText("stay off this map");
});

test("virtualization check runs through the read-only action endpoint", async ({ page }) => {
  await page.goto("/virtualization");

  const runResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/vcenter-netapp.readiness/run") &&
      response.request().method() === "POST"
  );
  await page.locator("section[aria-label='vCenter VCSA workspace'] > .design-device-primary-action").getByRole("button", { name: "Test vCenter VCSA" }).click();
  await expect((await runResponse).ok()).toBeTruthy();
  await expect(page.locator("section[aria-label='vCenter VCSA workspace']")).toContainText("vCenter Live Check:");
});

test("single-server virtualization defaults to direct ESXi without vCenter blocker", async ({ page }) => {
  labProfileScenario = "single";
  await page.goto("/virtualization");

  const summary = page.getByLabel("Virtualization launcher summary");
  const serverWorkspace = page.locator("section[aria-label='DL360 Gen10 workspace']");
  await expect(summary).toContainText("Direct ESXi");
  await expect(summary).toContainText("Server local datastore");
  await expect(serverWorkspace).toBeVisible();
  await expect(page.locator("section[aria-label='vCenter VCSA workspace']")).toHaveCount(0);
  await expect(page.getByLabel("vCenter VCSA credential setup")).toHaveCount(0);
  await expect(summary).not.toContainText(/blocker|required/i);
});

test("virtualization blocker copy hides internal mode vocabulary", async ({ page }) => {
  await page.route("**/api/v1/lab/vcenter-netapp/readiness", (route) => json(route, {
    ...vcenterNetappReadiness(),
    blockers: ["PROVIDER_MODE=local-lab-readwrite runtime provider credential is missing."],
    message: "PROVIDER MODE=mock runtime provider credential is missing.",
    next_safe_action: "PROVIDER_MODE=mock runtime provider password missing.",
    status: "blocked"
  }));

  await page.goto("/virtualization");
  const workspace = page.locator("section[aria-label='vCenter VCSA workspace']");
  await expect(workspace).toBeVisible();
  await expect(workspace.getByLabel("vCenter workspace virtualization controls")).not.toBeVisible();
  const text = await visibleMainText(page);
  expect(text ?? "").not.toMatch(/PROVIDER[_ ]MODE/i);
  expect(text ?? "").not.toMatch(/\bprovider\b/i);
  expect(text ?? "").not.toMatch(/\bruntime\b/i);
});

test("virtualization surface has no horizontal overflow on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/virtualization");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("map switch drawer shows direct access settings without proof clutter", async ({ page }) => {
  await page.goto("/overview");

  const topology = page.getByRole("region", { name: "Lab topology" });
  await topology.getByRole("button", { name: /^Cisco Switch,/ }).click();
  const drawer = page.getByLabel("Cisco Switch setup");

  await expect(drawer).toBeVisible();
  await expect(drawer.getByLabel("Management IP", { exact: true })).toHaveValue("192.168.1.204");
  await expect(drawer.getByLabel("Management VLAN", { exact: true })).toHaveValue("10");
  await expect(drawer.getByLabel("Storage VLAN", { exact: true })).toHaveCount(0);
  await expect(drawer.getByRole("heading", { name: "Sign-in" })).toBeVisible();
  await expect(drawer.getByRole("link", { name: /Open full setup/i })).toHaveCount(0);
  await expect(drawer.locator("details, .design-schema-inventory")).toHaveCount(0);
  await expect(drawer).not.toContainText(/ACKNOWLEDGE DEVICE RECONFIGURATION|current-intent diff|raw proof/i);
  await expect(drawer.getByRole("button", { name: /Apply Bootstrap|Factory reset|Upgrade/i })).toHaveCount(0);
});

test("Cisco current-intent drift stays on the canonical read-only evidence surface", async ({ page }) => {
  await page.goto("/overview");
  const topology = page.getByRole("region", { name: "Lab topology" });
  await topology.getByRole("button", { name: /^Cisco Switch,/ }).click();
  await expect(page.getByLabel("Cisco Switch setup")).not.toContainText("Refresh live evidence");

  await page.goto("/network");
  const advanced = await openWorkspaceAdvanced(page, "Cisco switch");
  const controls = advanced.getByLabel("Cisco workspace network controls");
  await controls.getByText("More read-only checks").click();

  const intentResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/cisco/current-intent-diff") &&
    response.request().method() === "POST"
  );
  await controls.getByRole("button", { name: /Refresh live evidence/ }).click();
  await expect((await intentResponse).ok()).toBeTruthy();
  await expect(controls).toContainText("Cisco current-to-intent diff completed");
  await expect(controls).toContainText("Intent diff");
  await expect(controls).toContainText("Needs review");
  await expect(controls.getByRole("button", { name: /Apply|Reset|Upgrade/i })).toHaveCount(0);
});

test("remaining operator pages expose simplified setup surfaces without old settings controls", async ({ page }) => {
  await page.goto("/firmware-upgrades");
  await expect(page.getByLabel("Firmware version decisions")).toBeVisible();
  await expect(page.locator("section[aria-label='Firmware reference']")).toHaveCount(0);

  await page.goto("/validation");
  const readiness = page.getByLabel("Readiness Check");
  await expect(readiness).toBeVisible();
  await expect(readiness).toContainText("Ready to ship?");
  await expect(readiness).toContainText("Ready to ship");
  await expect(readiness).toContainText("5 / 5 ready");
  await expect(readiness.getByText("5 / 5 ready")).toHaveCount(1);
  await expect(readiness).toContainText("All required checks are ready and the report exists.");
  await expect(page.locator(".validation-readiness-actions .operator-primary-button")).toHaveCount(1);
  await expect(page.locator(".validation-readiness-actions .operator-primary-button")).toContainText("Review report");
  await expect(page.getByRole("button", { name: "Run validation" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open report details" })).toBeVisible();
  await expect(page.getByRole("button", { name: "View details" })).toHaveCount(0);
  await expect(page.locator("section[aria-label='Validation reference']")).toHaveCount(0);
  await expect(page.locator("section[aria-label='Validation scenario scope']")).toHaveCount(0);
  await expect(page.getByText("Raw proof links")).toHaveCount(0);
  await expect(readiness.getByRole("button", { name: "Generate Handoff Report" })).toHaveCount(0);
  await expect(readiness.getByRole("button", { name: /factory|reset|rebuild/i })).toHaveCount(0);
  await expect(readiness.getByRole("button", { name: "Run equipment sweep" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Generate Handoff Report" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Apply NetApp Factory Reset|Reset HPE RAID|Boot ESXi Installer|Reset Server Power/ })).toHaveCount(0);
  await expect(page.locator("details.validation-danger-zone")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Settings" })).toHaveCount(0);

  await page.getByRole("button", { name: "Open report details" }).click();
  const details = page.getByLabel("Validation details");
  await expect(details.getByLabel("Kit readiness details")).toBeVisible();
  await expect(details).toContainText("What was checked");
  await expect(details).toContainText("What changed");
  await expect(details).toContainText("Report files");
  await expect(details).toContainText("Live equipment");
  await expect(details.getByRole("button", { name: "Run equipment sweep" })).toBeVisible();
  await expect(details.getByRole("button", { name: "Run equipment sweep" })).not.toHaveClass(/operator-primary-button/);
  await expect(details).not.toContainText("Validation Signals");
  await expect(details).not.toContainText("Golden State");
  await expect(details).not.toContainText(/\bprovider\b/i);
  await expect(details).not.toContainText(/\bruntime\b/i);
  await expect(details).not.toContainText(/\bpayload\b/i);
  await expect(details).not.toContainText(/\braw\b/i);
  await expect(details.getByRole("button", { name: "Create report" })).toHaveCount(0);
  await expect(details.locator("details.advanced-drawer")).not.toHaveAttribute("open", "");
  await details.locator("details.advanced-drawer > summary").click();
  await expect(details.getByLabel("Validation reference")).toBeVisible();
  await expect(details).toContainText("Validation Signals");

  await page.goto("/lab-profiles");
  await expect(page.getByRole("heading", { name: "Saved Kits", exact: true })).toBeVisible();
  await expect(page.getByTestId("saved-kits-home")).toBeVisible();
  await expect(page.getByRole("link", { name: "Create or change kit" })).toHaveAttribute("href", "/lab-profiles#new");
  const createKit = page.getByLabel("Create a new kit");
  await expect(createKit).toHaveAttribute("open", "");
  await expect(createKit.getByRole("button", { name: "Create kit" })).toBeVisible();
  await expect(createKit.getByRole("button", { name: "Create kit" })).toHaveClass(/primary/);
  await expect(page.getByRole("heading", { name: "Shared profile policy" })).toHaveCount(0);
  await expect(page.getByLabel("Global profile feature toggles")).toHaveCount(0);
  await expect(page.getByLabel("Lab default feature toggles")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Save (Global Defaults|As Lab Setup)/ })).toHaveCount(0);

  await expect(page.getByRole("button", { name: "Settings" })).toHaveCount(0);
});

test("validation details runs the registered read-only equipment sweep", async ({ page }) => {
  const capturedActionIds: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "POST") return;
    const url = new URL(request.url());
    if (!url.pathname.match(/^\/api\/v1\/workflows\/actions\/.+\/run$/)) return;
    capturedActionIds.push(actionIdFromRunPath(url.pathname));
  });

  await page.goto("/validation");
  await expect(page.locator(".validation-readiness-actions .operator-primary-button")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Run equipment sweep" })).toHaveCount(0);
  await page.getByRole("button", { name: "Open report details" }).click();
  await page.getByLabel("Validation details").getByRole("button", { name: "Run equipment sweep" }).click();

  await expect.poll(
    () => capturedActionIds,
    { message: "Validation details only starts the read-only equipment sweep", timeout: 5000 }
  ).toEqual(["operator-readonly-sweep.real-lab"]);
});

test("details-tier proof buttons outside overview keep read-only and guarded boundaries", async ({ page }) => {
  const providerPosts: string[] = [];
  const workflowPosts: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "POST") return;
    const url = new URL(request.url());
    if (url.pathname.match(/^\/api\/v1\/workflows\/actions\/.+\/run$/)) {
      workflowPosts.push(actionIdFromRunPath(url.pathname));
    }
    if (url.pathname.startsWith("/api/v1/providers/")) {
      providerPosts.push(url.pathname);
    }
  });

  await page.goto("/network");
  const ciscoAdvanced = await openWorkspaceAdvanced(page, "Cisco switch");
  const planProof = ciscoAdvanced.getByLabel("Cisco switch plan proof");
  await planProof.locator(":scope > summary").click();
  const ciscoDriver = page.getByLabel("Cisco switch driver");
  const refreshButton = ciscoDriver.getByRole("button", { name: /Refresh live evidence/ });
  await expect(refreshButton).toBeEnabled();
  const ciscoProbeResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/cisco-ansible/probe") &&
    response.request().method() === "POST"
  );
  const ciscoIntentResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/cisco/current-intent-diff") &&
    response.request().method() === "POST"
  );
  await refreshButton.click();
  await expect((await ciscoProbeResponse).ok()).toBeTruthy();
  await expect((await ciscoIntentResponse).ok()).toBeTruthy();
  await expect(ciscoDriver.getByRole("button", { name: /Apply|Write|Bootstrap/i })).toHaveCount(0);
  await expect(ciscoDriver).toContainText("before any guarded apply");

  await page.goto("/storage");
  const netappAdvanced = await openWorkspaceAdvanced(page, "NetApp ONTAP");
  const storageActions = netappAdvanced.getByLabel("NetApp workspace storage controls");
  const guardedApply = netappAdvanced.getByLabel("Guarded iSCSI apply");
  await expect(storageActions).toBeVisible();
  await expect(guardedApply).toBeVisible();

  const previewResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/netapp-ontap/iscsi-setup-preview")
  );
  await storageActions.getByRole("button", { name: "Preview iSCSI" }).click();
  await expect((await previewResponse).ok()).toBeTruthy();
  await expect(storageActions).toContainText(/Preview iSCSI:/);

  const applyResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/netapp-ontap/iscsi-setup-apply") &&
    response.request().method() === "POST"
  );
  await guardedApply.getByRole("button", { name: /Apply iSCSI/ }).click();
  await expect((await applyResponse).ok()).toBeTruthy();
  await expect(storageActions).toContainText(/Apply iSCSI gate evaluated: Blocked/);
  await expect(guardedApply).toContainText(/ONTAP writes not attempted/);

  const validateResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/netapp-ontap/iscsi-setup-validate") &&
    response.request().method() === "POST"
  );
  await storageActions.getByRole("button", { name: "Validate iSCSI" }).click();
  await expect((await validateResponse).ok()).toBeTruthy();
  await expect(storageActions).toContainText(/Validate iSCSI:/);

  const esxiPreviewResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/esxi-readonly/iscsi-datastore-preview") &&
    response.request().method() === "POST"
  );
  await storageActions.getByRole("button", { name: "Preview ESXi iSCSI" }).click();
  await expect((await esxiPreviewResponse).ok()).toBeTruthy();
  await expect(storageActions).toContainText(/Preview ESXi iSCSI:/);

  const esxiValidateResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/esxi-readonly/iscsi-datastore-validate") &&
    response.request().method() === "POST"
  );
  await storageActions.getByRole("button", { name: "Validate ESXi iSCSI" }).click();
  await expect((await esxiValidateResponse).ok()).toBeTruthy();
  await expect(storageActions).toContainText(/Validate ESXi iSCSI:/);

  expect(providerPosts, "details-tier buttons use provider read/proof or guarded-gate endpoints")
    .toEqual(expect.arrayContaining([
      "/api/v1/providers/cisco-ansible/probe",
      "/api/v1/providers/cisco/current-intent-diff",
      "/api/v1/providers/netapp-ontap/iscsi-setup-apply",
      "/api/v1/providers/netapp-ontap/iscsi-setup-validate",
      "/api/v1/providers/esxi-readonly/iscsi-datastore-preview",
      "/api/v1/providers/esxi-readonly/iscsi-datastore-validate"
    ]));
  expect(workflowPosts, "details-tier proof buttons do not start guarded workflow actions").toEqual([]);
});

test("validation readiness card hides raw provider-mode vocabulary in blockers", async ({ page }) => {
  const blocked = labValidation();
  blocked.overall_status = "blocked";
  blocked.next_action = "PROVIDER MODE=Read-only lab or PROVIDER_MODE=local-lab-readwrite is required before provider runtime validation.";
  blocked.top_blocker = {
    problem: "PROVIDER_MODE=local-lab-readwrite is required before provider runtime validation.",
    title: "Provider mode missing"
  };
  blocked.validation_items = [
    {
      ...blocked.validation_items[0],
      current_state: "Blocked",
      next_action: "PROVIDER MODE=Read-only lab is required before provider validation.",
      setup_summary: "PROVIDER_MODE is unavailable.",
      status: "blocked"
    },
    ...blocked.validation_items.slice(1)
  ];
  await page.route("**/api/v1/lab/validation", (route) => json(route, blocked));

  await page.goto("/validation");

  const readiness = page.getByLabel("Readiness Check");
  await expect(readiness).toContainText("Blocked");
  await expect(readiness).toContainText("Needs one fix");
  await expect(readiness.getByText("Needs attention")).toBeVisible();
  await expect(readiness.getByRole("link", { name: "Fix Cisco switch" })).toBeVisible();
  await expect(readiness.getByRole("button", { name: "Run validation" })).toHaveCount(0);
  await expect(readiness).not.toContainText(/PROVIDER[_ ]MODE/i);
  await expect(readiness).not.toContainText(/\bprovider\b/i);
  await expect(readiness).not.toContainText(/\bruntime\b/i);

  await page.getByRole("button", { name: "Open report details" }).click();
  const details = page.getByLabel("Validation details");
  await expect(details).not.toContainText(/\bprovider\b/i);
  await expect(details).not.toContainText(/\bruntime\b/i);
});

test("validation next action matches lab safety acknowledgement blockers", async ({ page }) => {
  const blocked = labValidation();
  blocked.overall_status = "blocked";
  blocked.next_action = "Review firmware manual baseline after lab safety gates are complete.";
  blocked.top_blocker = {
    problem: "Required lab acknowledgement flags are missing before real lab probes.",
    title: "Lab safety gates missing"
  };
  blocked.validation_items = [
    {
      ...blocked.validation_items[0],
      category: "firmware",
      current_state: "Blocked",
      id: "firmware-manual-baseline",
      label: "Firmware",
      next_action: "Review the firmware manual baseline.",
      setup_summary: "Firmware manual baseline needs review.",
      status: "blocked"
    },
    ...blocked.validation_items.slice(1)
  ];
  await page.route("**/api/v1/lab/validation", (route) => json(route, blocked));

  await page.goto("/validation");

  const readiness = page.getByLabel("Readiness Check");
  await expect(readiness).toContainText("Required lab acknowledgement flags are missing before real lab probes.");
  await expect(readiness.getByRole("link", { name: "Review lab safety" })).toHaveAttribute("href", "/overview#lab-safety");
  await expect(readiness.getByRole("link", { name: "Fix firmware" })).toHaveCount(0);
});

test("validation no-kit state does not show stale loading feedback", async ({ page }) => {
  labProfileScenario = "none";
  await page.route("**/api/v1/lab/validation", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    return json(route, labValidationNotChecked());
  });

  await page.goto("/validation");

  await expect(page.getByLabel("Readiness Check")).toBeVisible();
  await expect(page.locator(".operator-feedback", { hasText: "Loading" })).toHaveCount(0);
});

test("storage iSCSI evidence and guarded apply stay off the Overview drawer", async ({ page }) => {
  await page.goto("/overview");
  const topology = page.getByRole("region", { name: "Lab topology" });
  await topology.getByRole("button", { name: /^NetApp ONTAP,/ }).click();
  const mapDrawer = page.getByLabel("NetApp ONTAP setup");
  await expect(mapDrawer.getByRole("button", { name: /Apply iSCSI|Factory reset/i })).toHaveCount(0);
  await expect(mapDrawer).not.toContainText("NETAPP_ISCSI_SETUP_APPLY");

  await page.goto("/storage");
  const advanced = await openWorkspaceAdvanced(page, "NetApp ONTAP");
  const controls = advanced.getByLabel("NetApp workspace storage controls");
  const guardedApply = advanced.getByLabel("Guarded iSCSI apply");

  const previewResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/netapp-ontap/iscsi-setup-preview")
  );
  await controls.getByRole("button", { name: "Preview iSCSI" }).click();
  await expect((await previewResponse).ok()).toBeTruthy();
  await expect(controls).toContainText(/Preview iSCSI:/);

  const applyResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/netapp-ontap/iscsi-setup-apply") &&
    response.request().method() === "POST"
  );
  await guardedApply.getByRole("button", { name: /Apply iSCSI/ }).click();
  await expect((await applyResponse).ok()).toBeTruthy();
  await expect(guardedApply).toContainText("1/4 satisfied");
  await expect(guardedApply).toContainText(/ONTAP writes not attempted/);
  await expect(guardedApply).toContainText(/NETAPP_ISCSI_SETUP_CONFIRM="APPLY NETAPP ISCSI SETUP"/);

  const validateResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/netapp-ontap/iscsi-setup-validate") &&
    response.request().method() === "POST"
  );
  await controls.getByRole("button", { name: "Validate iSCSI" }).click();
  await expect((await validateResponse).ok()).toBeTruthy();
  await expect(controls).toContainText(/Validate iSCSI:/);
});

test("advanced proof is collapsed and operator labels hide raw statuses", async ({ page }) => {
  await page.goto("/validation");

  await expect(page.locator("details.advanced-drawer")).toHaveCount(0);
  await page.getByRole("button", { name: "Open report details" }).click();
  const advanced = page.locator("details.advanced-drawer").first();
  await expect(advanced).not.toHaveAttribute("open", "");
  await expect(page.getByText("Golden State / Handoff", { exact: true })).toHaveCount(0);
  await advanced.locator(":scope > summary").click();
  const validation = page.locator("section[aria-label='Validation reference']");
  await expect(validation.getByText("Golden State / Handoff", { exact: true })).toBeVisible();
  await expect(validation).toContainText("Validation Signals");
  await expect(page.getByText("Artifact")).toHaveCount(0);
  await expect(page.getByText("manual_review")).toHaveCount(0);
  await expect(page.getByText("not_configured_yet")).toHaveCount(0);

  await page.goto("/overview");
  await expect(page.getByText("local-lab-readwrite")).toHaveCount(0);
  await expect(page.getByText(/PROVIDER_MODE/)).toHaveCount(0);
});

test("firmware decisions replace the retired map with four operator columns", async ({ page }) => {
  await page.goto("/firmware-upgrades");

  await expect(page.getByRole("heading", { name: /Keep every device on the expected version/ })).toBeVisible();
  const table = page.getByLabel("Firmware version decisions");
  await expect(table.getByRole("columnheader")).toHaveCount(4);
  await expect(table.getByRole("columnheader", { name: "Device" })).toBeVisible();
  await expect(table.getByRole("columnheader", { name: "Current version" })).toBeVisible();
  await expect(table.getByRole("columnheader", { name: "Target version" })).toBeVisible();
  await expect(table.getByRole("columnheader", { name: "Action" })).toBeVisible();
  await expect(page.getByLabel("Firmware upgrade map")).toHaveCount(0);
  await expect(page.getByText("Firmware Repository")).toHaveCount(0);
  await expect(table).toContainText("Cisco Switch");
  await expect(table).toContainText("17.15.05");
  await expect(table.getByRole("button", { name: "Upgrade", exact: true }).first()).toBeVisible();
  await expect(table.getByRole("button", { name: "Bypass", exact: true }).first()).toBeVisible();
  await expect(table.locator("select")).toHaveCount(0);
  await expect(table).toContainText(/upgrades available - .* current - .* not checked/);
});

test("firmware decisions keep target and action copy honest", async ({ page }) => {
  await page.goto("/firmware-upgrades");

  const table = page.getByLabel("Firmware version decisions");
  await expect(table).toContainText(/Review baseline|Upgrade available|Target not set/);
  await expect(table, "minimum baselines keep the comparison qualifier in the operator target column").toContainText(">= 17.9");
  const netappRow = table.locator("tbody tr").filter({ hasText: "NetApp" }).first();
  await expect(netappRow, "minimum baselines say they meet the target instead of implying an exact version match").toContainText("Meets target");
  await expect(netappRow, "minimum baselines do not look like exact current-version matches").not.toContainText("Already current");
  await expect(table).toContainText("Bypass");
  await expect(table).not.toContainText("cisco-ios-xe-firmware.bin");
  await expect(table).not.toContainText("P95170_001_gen10spp");
  await expect(page.getByText("Apply Lock")).toHaveCount(0);
  await expect(page.getByText("Post-check")).toHaveCount(0);
});

test("firmware bypass collapses the row to one recorded choice", async ({ page }) => {
  const workflowPosts: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "POST") return;
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/v1/workflows/actions/")) workflowPosts.push(url.pathname);
  });

  await page.goto("/firmware-upgrades");

  const table = page.getByLabel("Firmware version decisions");
  const row = table.locator("tbody tr").filter({ hasText: "Cisco Switch" }).first();
  await expect(row.getByRole("button", { name: "Upgrade", exact: true })).toBeVisible();
  await expect(row.getByRole("button", { name: "Bypass", exact: true })).toBeVisible();

  await row.getByRole("button", { name: "Bypass", exact: true }).click();
  await expect(row).toContainText("Bypassed - left as-is");
  await expect(row.getByRole("button", { name: "Upgrade", exact: true })).toHaveCount(0);
  await expect(row.getByRole("button", { name: "Bypass", exact: true })).toHaveCount(0);
  await expect(row.getByRole("button", { name: "Undo", exact: true })).toBeVisible();
  expect(workflowPosts, "Bypass records the choice locally without starting a workflow").toEqual([]);

  await row.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(row.getByRole("button", { name: "Upgrade", exact: true })).toBeVisible();
  await expect(row.getByRole("button", { name: "Bypass", exact: true })).toBeVisible();
});

test("firmware upgrade collapses to guarded planning only", async ({ page }) => {
  const workflowPosts: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "POST") return;
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/v1/workflows/actions/")) workflowPosts.push(url.pathname);
  });

  await page.goto("/firmware-upgrades");

  const table = page.getByLabel("Firmware version decisions");
  const row = table.locator("tbody tr").filter({ hasText: "Cisco Switch" }).first();
  const upgrade = row.getByRole("button", { name: "Upgrade", exact: true });
  await expect(upgrade).toBeEnabled();

  const planResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/firmware.upgrade-plan/run") &&
    response.request().method() === "POST"
  );
  await upgrade.click();
  await expect((await planResponse).ok()).toBeTruthy();

  await expect(row).toContainText("Upgrade queued");
  await expect(row.getByRole("button", { name: "Upgrade", exact: true })).toHaveCount(0);
  await expect(row.getByRole("button", { name: "Bypass", exact: true })).toHaveCount(0);
  await expect(row.getByRole("button", { name: "Undo", exact: true })).toBeVisible();
  expect(workflowPosts, "Upgrade starts only the guarded planning workflow").toEqual([
    "/api/v1/workflows/actions/firmware.upgrade-plan/run"
  ]);
  expect(workflowPosts, "Upgrade never starts a firmware apply workflow from the table")
    .not.toEqual(expect.arrayContaining([
      expect.stringMatching(/firmware\.upgrade-apply-placeholder|netapp\.ontap-upgrade-apply/i)
    ]));

  await row.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(row.getByRole("button", { name: "Upgrade", exact: true })).toBeVisible();
  await expect(row.getByRole("button", { name: "Bypass", exact: true })).toBeVisible();
});

test("firmware version check still uses the guarded workflow runner", async ({ page }) => {
  await page.goto("/firmware-upgrades");

  const scanResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/firmware.inventory/run") &&
    response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Check versions" }).click();
  await expect((await scanResponse).ok()).toBeTruthy();
  await expect(page.getByText("Protected firmware action")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Upgrade", exact: true }).first()).toBeVisible();
});

test("software media keeps inventory details behind one read-only action", async ({ page }) => {
  await page.goto("/media");

  const home = page.getByTestId("software-media-home");
  await expect(page.locator("h1", { hasText: "Software Media" })).toBeVisible();
  await expect(home).toContainText("Place files here");
  await expect(home).toContainText("1 file");
  await expect(home).toContainText("Ready");
  await expect(page.getByRole("button", { name: "Check media" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "File" })).toHaveCount(0);
  await expect(page.getByText("Advanced media metadata")).toHaveCount(0);

  const refreshResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/media-inventory") && response.request().method() === "GET"
  );
  await page.getByRole("button", { name: "Check media" }).click();
  await expect((await refreshResponse).ok()).toBeTruthy();

  await page.getByText("Open media files").click();
  await expect(page.getByRole("columnheader", { name: "File" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "cat9k_iosxe.17.15.05.SPA.bin" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "Cisco IOS XE firmware" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Source" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Apply|Install|Upgrade|Reset/i })).toHaveCount(0);
});

test("saved lab setup global defaults use active profile values and never render secret material", async ({ page }) => {
  await page.goto("/lab-profiles");

  await expect(page.getByTestId("saved-kits-home")).toContainText("Current Lab");
  await expect(page.getByRole("heading", { name: "Shared profile policy" })).toHaveCount(0);
  await expect(page.getByLabel("Global profile feature toggles")).toHaveCount(0);
  await expect(page.getByLabel("Lab default feature toggles")).toHaveCount(0);
  await expect(page.locator("nav").getByText("Settings")).toHaveCount(0);
  await expect(page.getByText("Secret values are hidden")).toHaveCount(0);
  await expect(page.locator("input[type='password']")).toHaveCount(0);
});

test("legacy settings paths redirect to overview and the contextual drawer is removed", async ({ page }) => {
  await page.goto("/overview");
  await expect(page.getByRole("button", { name: "Settings" })).toHaveCount(0);
  await expect(page.locator("section.tab-settings-drawer")).toHaveCount(0);

  await page.goto("/config");
  await expect(page).toHaveURL(/\/overview/);
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();

  await page.goto("/settings");
  await expect(page).toHaveURL(/\/overview/);
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
});

test("safe read-only page action still invokes the workflow runner", async ({ page }) => {
  const notChecked = labValidationNotChecked();
  await page.route("**/api/v1/lab/validation", (route) => json(route, notChecked));
  await page.goto("/validation");

  const runResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/build-verification.run-full/run")
  );
  await page.getByRole("button", { name: /Run validation/i }).click();
  await expect((await runResponse).ok()).toBeTruthy();
  await expect(page.getByText(/Run Full Verification:/)).toBeVisible();
});

test("create report primary action calls the handoff API and reports completion", async ({ page }) => {
  const readyWithoutReport = labValidation();
  readyWithoutReport.handoff_report = "";
  await page.route("**/api/v1/lab/validation", (route) => json(route, readyWithoutReport));
  await page.goto("/validation");

  const handoffResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/lab/validation/handoff")
  );
  await page.getByRole("button", { name: "Create report" }).click();
  await expect((await handoffResponse).ok()).toBeTruthy();
  await expect(page.getByText("Report is ready.")).toBeVisible();
});

test("validation exposes guarded factory reset and automated rebuild verification", async ({ page }) => {
  await page.goto("/validation");
  await expect(page.getByRole("button", { name: /Apply NetApp Factory Reset|Reset HPE RAID|Boot ESXi Installer|Reset Server Power/ })).toHaveCount(0);
  await expect(page.locator("details.validation-danger-zone")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Advanced" })).toHaveCount(0);

  await page.evaluate(() => {
    window.localStorage.setItem("infra-config-operator-ui-mode", "advanced");
  });
  await page.reload();
  await expect(page.getByRole("button", { name: "Advanced" })).toHaveCount(0);
  await expect(page.locator("details.validation-danger-zone")).toHaveCount(1);
  await page.locator("details.validation-danger-zone > summary").click();

  const resetPanel = page.locator("section[aria-label='Factory Reset and Rebuild']");
  await expect(resetPanel.getByRole("heading", { name: "Start from scratch" })).toBeVisible();
  await expect(resetPanel).toContainText("Plan");
  await expect(resetPanel).toContainText("Reset");
  await expect(resetPanel).toContainText("Validate");
  await expect(resetPanel).toContainText("Stage inventory");
  await expect(resetPanel).toContainText("Real run readiness");
  await expect(resetPanel).toContainText("Connected consoles");
  await expect(resetPanel).toContainText("Console discovery");
  await expect(resetPanel).toContainText("Cisco and NetApp consoles are physically connected");
  await expect(resetPanel).toContainText("Real read-only");
  await expect(resetPanel).toContainText("Guarded real run");
  await expect(resetPanel).toContainText("Restore partner");
  await expect(resetPanel).toContainText("Execution");
  await expect(resetPanel).toContainText("In-process API");
  await expect(resetPanel).toContainText("Make/subprocess");
  await expect(resetPanel).toContainText("Apply Setup");
  await expect(resetPanel).toContainText("Apply");
  await expect(resetPanel).toContainText("Configure-back action is registered");
  await expect(resetPanel).toContainText("NetApp factory reset");
  await expect(resetPanel).toContainText("HPE RAID reset");
  await expect(resetPanel).toContainText("ESXi rebuild");
  await expect(resetPanel.getByRole("button", { name: "Run Full Lab Build Plan" })).toHaveCount(0);
  await expect(resetPanel.getByRole("button", { name: "Apply NetApp Factory Reset" })).toHaveCount(0);

  const planAndVerify = resetPanel.getByLabel("Plan and verify");
  await expect(planAndVerify).not.toHaveAttribute("open", "");
  await planAndVerify.locator(":scope > summary").click();

  const buildPlanResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/full-lab.build-plan/run") &&
    response.request().method() === "POST"
  );
  await resetPanel.getByRole("button", { name: "Run Full Lab Build Plan" }).click();
  await expect((await buildPlanResponse).ok()).toBeTruthy();

  const repairPlanResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/full-lab.repair/run") &&
    response.request().method() === "POST"
  );
  await resetPanel.getByRole("button", { name: "Run Golden-State Repair Plan" }).click();
  await expect((await repairPlanResponse).ok()).toBeTruthy();
  const deviceResetControls = resetPanel.getByLabel("Device reset controls");
  await expect(deviceResetControls).not.toHaveAttribute("open", "");
  await deviceResetControls.locator(":scope > summary").click();

  const previewResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/netapp.factory-reset-preview/run") &&
    response.request().method() === "POST"
  );
  await resetPanel.getByRole("button", { name: "Preview NetApp Factory Reset" }).click();
  await expect((await previewResponse).ok()).toBeTruthy();

  for (const label of ["Apply NetApp Factory Reset", "Reset HPE RAID", "Boot ESXi Installer", "Reset Server Power"]) {
    const button = resetPanel.getByRole("button", { name: label });
    await expect(button).toBeVisible();
    await expect(button).toBeDisabled();
    await expect(button).toHaveAttribute("title", /guarded confirmation/i);
  }
});

test("validation details do not expose optional smoke controls in normal reports", async ({ page }) => {
  await page.goto("/validation");
  await expect(page.locator("details.validation-danger-zone")).toHaveCount(0);
  await page.getByRole("button", { name: "Open report details" }).click();

  const details = page.getByLabel("Validation details");
  await expect(details.getByRole("button", { name: "Run Read-Only Sweep" })).toHaveCount(0);
  await expect(details.getByRole("button", { name: "Run Real Provider Smoke" })).toHaveCount(0);
  await expect(details.getByRole("button", { name: "Generate Handoff Report" })).toHaveCount(0);
});

test("blocked workflow runs render an advisory diagnosis card", async ({ page }) => {
  await page.route("**/api/v1/lab/validation", (route) => json(route, labValidationNotChecked()));
  await page.route("**/api/v1/workflows/actions/build-verification.run-full/run", (route) =>
    route.fulfill({
      body: JSON.stringify({
        ...workflowActionRun("build-verification.run-full"),
        blockers: ["Command exceeded the 180s safe action runner timeout."],
        executed: true,
        return_code: null,
        status: "blocked",
        summary: "Safe read-only/report-only endpoint ran and reported blockers."
      }),
      contentType: "application/json"
    })
  );
  await page.route("**/api/v1/workflows/actions/build-verification.run-full/diagnosis", (route) =>
    route.fulfill({
      body: JSON.stringify({
        ...workflowActionDiagnosis("build-verification.run-full"),
        confidence: "high",
        evidence: [{ detail: "Command exceeded the 180s safe action runner timeout.", label: "Blocker" }],
        explanation: "Run a read-only reachability check before retrying the validation path.",
        probable_cause: "The workflow runner timed out before collecting complete evidence.",
        status: "blocked",
        suggested_next_action: "Run Build Verification Toolchain Check"
      }),
      contentType: "application/json"
    })
  );
  await page.goto("/validation");

  const runResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/build-verification.run-full/run")
  );
  await page.getByRole("button", { name: /Run validation/i }).click();

  await expect((await runResponse).ok()).toBeTruthy();
  await expect(page.getByLabel("Advisory diagnosis")).toBeVisible();
  await expect(page.getByLabel("Advisory diagnosis")).toContainText("The workflow runner timed out before collecting complete evidence.");
  await expect(page.getByLabel("Advisory diagnosis")).toContainText("Diagnosis is advisory and does not execute workflow actions.");
});

test("testing assistant queues a redacted fix request from the current route", async ({ page }) => {
  const workflowRequests: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/api\/v1\/workflows\/actions\/[^/]+\/run$/.test(new URL(request.url()).pathname)) {
      workflowRequests.push(request.url());
    }
  });

  await page.goto("/network");
  await expect(page).toHaveURL(/\/network/);

  await page.getByRole("button", { name: "Report issue" }).click();
  await expect(page.getByRole("dialog", { name: "Testing Assistant" })).toBeVisible();
  await expect(page.getByText("/network")).toBeVisible();
  await expect(page.getByText("No hardware action is run from this report.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Queue fix request" })).toBeDisabled();
  await expect(page.getByLabel("Network details")).toBeVisible();
  await page.getByLabel("Network details").check();
  await page.getByLabel("What went wrong?").fill("Clicked the Cisco validation button and the status looked stale.");
  const packetRequest = page.waitForRequest((request) =>
    request.url().includes("/api/v1/operator-issue-packets") && request.method() === "POST"
  );
  const changeRequest = page.waitForRequest((request) =>
    request.url().includes("/api/v1/ai-change-requests") && request.method() === "POST"
  );
  await page.getByRole("button", { name: "Queue fix request" }).click();

  const packetPayload = (await packetRequest).postDataJSON() as Record<string, unknown>;
  const changePayload = (await changeRequest).postDataJSON() as Record<string, unknown>;
  await expect(page.getByLabel("Feedback queued")).toContainText("Feedback queued");
  await expect(page.getByLabel("Feedback queued")).toContainText("Operator reported an issue on Network");
  const summaryText = (await page.locator(".operator-issue-result > span").allTextContents()).join(" ");
  expect(summaryText).not.toContain("artifacts/codex-runs/operator-issue-packets");
  await expect(page.getByRole("button", { name: "Copy handoff" })).toHaveCount(0);
  expect(packetPayload.route).toBe("/network");
  expect(String((packetPayload.ui_context as Record<string, unknown>).target)).toContain("Network details");
  expect(changePayload.route).toBe("/network");
  expect(changePayload.target).toContain("Network details");
  expect(Array.isArray(changePayload.regions)).toBeTruthy();
  expect((changePayload.regions as Array<Record<string, unknown>>)).toHaveLength(1);
  expect((changePayload.regions as Array<Record<string, unknown>>)[0].id).toBe("network-details");
  expect(workflowRequests).toHaveLength(0);

  await expect(page.getByLabel("Feedback queued").getByText("Open feedback details")).toBeVisible();
  await expect(page.getByLabel("Feedback queued").getByText("View details")).toHaveCount(0);
  await page.getByLabel("Feedback queued").getByText("Open feedback details").click();
  await expect(page.getByText("Review note: docs/change-requests/20260707T161900Z-Network.md")).toBeVisible();
  await page.getByLabel("Feedback queued").getByText("Advanced request data").click();
  await expect(page.getByText("Packet artifact")).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy handoff" })).toBeVisible();
});

test("request detail shows mock lifecycle guardrails before planning", async ({ page }) => {
  const request = {
    created_at: checkedAt,
    environment: "dev",
    expiry_date: "2026-12-31",
    id: "req-vm-1",
    notes: "Need a short-lived app test VM.",
    owner: "platform-team",
    request_type: "vm_deploy",
    requester: "local-dev-user",
    site: "lab-a",
    status: "approved",
    updated_at: checkedAt,
    vm_deploy: {
      cluster: "compute-a",
      cpu: 2,
      datastore: null,
      disk_gb: 80,
      memory_gb: 8,
      network: "dev-vlan-100",
      storage_tier: "silver",
      template: "ubuntu-24.04",
      vm_name: "app-dev-001"
    }
  };
  await page.route("**/api/v1/catalog", (route) =>
    json(route, {
      clusters_by_site: { "lab-a": ["compute-a"] },
      datastores: ["ds-lab-a-01"],
      environments: ["dev", "test", "prod"],
      networks: [{ environments: ["dev"], name: "dev-vlan-100", vlan_id: 100 }],
      sites: ["lab-a"],
      storage_tiers: ["bronze", "silver", "gold"],
      templates: ["ubuntu-24.04"]
    })
  );
  await page.route("**/api/v1/requests/req-vm-1/readiness", (route) =>
    json(route, {
      blockers: [],
      current_status: "approved",
      next_action: "plan",
      ready_for_approval: false,
      ready_for_execute: false,
      ready_for_plan: true,
      ready_for_submit: false,
      request_id: "req-vm-1",
      summary: "Approved request is ready for mock dry-run planning.",
      warnings: []
    })
  );
  await page.route("**/api/v1/requests/req-vm-1/artifacts", (route) => json(route, []));
  await page.route("**/api/v1/requests/req-vm-1", (route) => json(route, request));

  await page.goto("/requests/req-vm-1");

  const guardrails = page.getByLabel("VM request lifecycle guardrails");
  await expect(guardrails).toBeVisible();
  await expect(guardrails).toContainText("Current state");
  await expect(guardrails).toContainText("approved");
  await expect(guardrails).toContainText("Next safe action");
  await expect(guardrails).toContainText("plan");
  await expect(guardrails).toContainText("Mock-only boundary");
  await expect(guardrails).toContainText("No provider changes");
  await expect(guardrails).toContainText("Creates a mock-only dry-run plan");
  await expect(guardrails).toContainText("do not call vCenter, ESXi, storage, network, IPAM, or provider endpoints");
  await expect(page.getByRole("button", { name: "Plan" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Execute" })).toBeDisabled();
});

test("workflow runner surfaces plain-text API errors", async ({ page }) => {
  await page.route("**/api/v1/lab/validation", (route) => json(route, labValidationNotChecked()));
  await page.route("**/api/v1/workflows/actions/build-verification.run-full/run", (route) =>
    route.fulfill({
      body: "workflow runner temporarily unavailable",
      contentType: "text/plain",
      status: 503
    })
  );
  await page.goto("/validation");

  const runResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/build-verification.run-full/run")
  );
  await page.getByRole("button", { name: /Run validation/i }).click();

  await expect((await runResponse).status()).toBe(503);
  await expect(page.getByText("workflow runner temporarily unavailable")).toBeVisible();
});

test("workflow runner surfaces primitive array API detail errors", async ({ page }) => {
  await page.route("**/api/v1/lab/validation", (route) => json(route, labValidationNotChecked()));
  await page.route("**/api/v1/workflows/actions/build-verification.run-full/run", (route) =>
    route.fulfill({
      body: JSON.stringify({ detail: ["first blocker", "second blocker"] }),
      contentType: "application/json",
      status: 422
    })
  );
  await page.goto("/validation");

  const runResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/build-verification.run-full/run")
  );
  await page.getByRole("button", { name: /Run validation/i }).click();

  await expect((await runResponse).status()).toBe(422);
  await expect(page.getByText("first blocker; second blocker")).toBeVisible();
});

test("workflow runner surfaces malformed JSON API responses", async ({ page }) => {
  await page.route("**/api/v1/lab/validation", (route) => json(route, labValidationNotChecked()));
  await page.route("**/api/v1/workflows/actions/build-verification.run-full/run", (route) =>
    route.fulfill({
      body: "{not valid json",
      contentType: "application/json",
      status: 200
    })
  );
  await page.goto("/validation");

  const runResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/build-verification.run-full/run")
  );
  await page.getByRole("button", { name: /Run validation/i }).click();

  await expect((await runResponse).status()).toBe(200);
  await expect(page.getByText("Invalid JSON response from /api/v1/workflows/actions/build-verification.run-full/run.")).toBeVisible();
});

test("workflow runner surfaces network API failures", async ({ page }) => {
  await page.route("**/api/v1/lab/validation", (route) => json(route, labValidationNotChecked()));
  await page.route("**/api/v1/workflows/actions/build-verification.run-full/run", (route) =>
    route.abort("failed")
  );
  await page.goto("/validation");

  await page.getByRole("button", { name: /Run validation/i }).click();

  await expect(page.getByText("Network error while requesting /api/v1/workflows/actions/build-verification.run-full/run.")).toBeVisible();
});

test("overview device inventory adds, opens known and generic panels, and removes devices", async ({ page }) => {
  await page.goto("/overview");
  for (const name of ["Cisco Switch", "HPE iLO", "ESXi Host", "NetApp ONTAP"]) {
    await expect(page.getByText(name, { exact: true })).toBeVisible();
  }

  await page.getByRole("button", { name: "Add device" }).click();
  await page.getByLabel("Device type").fill("packet_broker");
  await page.getByLabel("Device name").fill("Packet Broker A");
  await page.getByLabel("Device host").fill("packet-a.local");
  await page.getByRole("button", { name: "Save device" }).click();
  await expect(page.getByText("Packet Broker A", { exact: true })).toBeVisible();

  await page.getByText("Packet Broker A", { exact: true }).click();
  await expect(page.getByLabel("Packet Broker A details")).toContainText("packet-a.local");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete device" }).click();
  await expect(page.getByText("Packet Broker A", { exact: true })).toHaveCount(0);

  await page.getByText("Cisco Switch", { exact: true }).click();
  await expect(page.getByLabel("Cisco Switch setup")).toBeVisible();
});

test("DHCP inventory devices show observed addresses as read-only evidence", async ({ page }) => {
  await page.goto("/overview");
  await page.getByRole("button", { name: "Add device" }).click();
  await page.getByLabel("Device type").fill("packet_broker");
  await page.getByLabel("Device name").fill("DHCP Packet Broker");
  await page.getByLabel("Device addressing mode").selectOption("dhcp");

  const host = page.getByLabel("Device host");
  await expect(host).toBeDisabled();
  await expect(host).toHaveAttribute("placeholder", "No address observed yet");
  await expect(page.getByText("Assigned by the network, not editable.")).toBeVisible();

  await page.getByRole("button", { name: "Save device" }).click();
  await expect(page.getByText("DHCP Packet Broker", { exact: true })).toBeVisible();
  await expect(page.getByText("No address observed yet · DHCP", { exact: true })).toBeVisible();
});

async function installApiMocks(page: Page) {
  let firmwareFileSelections = firmwareFileSelectionState({});
  let labSafety = labSafetySettings();
  let activeProfiles = activeLabProfilesFixture();
  let savedProfile: Record<string, unknown> | null = null;
  let labBuildRun: Record<string, unknown> | null = null;
  // Ids mimic real database UUIDs on purpose: link resolution must work by
  // device type, never by magic id values the backend does not produce.
  // Lazily initialized per scenario: single-server labs have no NetApp in
  // their inventory, mirroring an operator who removed or never added it.
  let deviceInventory: ReturnType<typeof inventoryDevice>[] | null = null;
  const seededDeviceInventory = () => {
    if (deviceInventory === null) {
      deviceInventory = [
        inventoryDevice("f2c1a9d0-4b31-4a5e-9d10-000000000001", "cisco_switch", "Cisco Switch", "192.168.1.204"),
        inventoryDevice("f2c1a9d0-4b31-4a5e-9d10-000000000002", "ilo", "HPE iLO", "192.168.1.201"),
        inventoryDevice("f2c1a9d0-4b31-4a5e-9d10-000000000003", "esxi_host", "ESXi Host", "192.168.1.203"),
        ...(labProfileScenario === "single"
          ? []
          : [
              inventoryDevice("f2c1a9d0-4b31-4a5e-9d10-000000000004", "netapp", "NetApp ONTAP", "192.168.1.220"),
              inventoryDevice("f2c1a9d0-4b31-4a5e-9d10-000000000005", "vcenter", "vCenter", "192.168.1.205")
            ])
      ];
    }
    return deviceInventory;
  };
  const topologyDesignDrafts = new Map<string, Record<string, unknown>>();
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
          host_ipv4_addresses: healthHostIpv4Addresses,
          lab_subnet_cidr: "192.168.1.0/24",
          operator_runtime_mode: "local-lab-readwrite",
          provider_mode: "local-lab-readwrite",
          status: "ok"
        })
      });
    }
    if (!url.pathname.startsWith("/api/v1/")) {
      return route.continue();
    }
    if (url.pathname === "/api/v1/device-inventory") {
      const devices = seededDeviceInventory();
      if (request.method() === "POST") {
        const payload = request.postDataJSON() as Record<string, unknown>;
        const created = inventoryDevice(
          `custom-${devices.length}`,
          String(payload.device_type),
          String(payload.display_name),
          String(payload.host || ""),
          String(payload.notes || ""),
          payload.dhcp_enabled === true
        );
        devices.push(created);
        return json(route, created);
      }
      return json(route, devices);
    }
    if (url.pathname.startsWith("/api/v1/device-inventory/")) {
      const id = url.pathname.split("/").pop();
      if (request.method() === "DELETE") {
        deviceInventory = seededDeviceInventory().filter((device) => device.id !== id);
        return json(route, null);
      }
    }
    if (url.pathname.startsWith("/api/v1/lab/profiles/") && request.method() === "PUT") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      const profile = {
        ...(savedProfile ? activeProfiles : activeLabProfilesFixture()).active_profile,
        ...payload,
        id: url.pathname.split("/").pop() || "runtime",
        source: "saved",
        updated_at: checkedAt
      };
      savedProfile = profile;
      activeProfiles = activeLabProfilesFromProfile(savedProfile);
      return json(route, profile);
    }
    if (url.pathname.startsWith("/api/v1/lab/profiles/") && url.pathname.endsWith("/activate")) {
      if (savedProfile) {
        activeProfiles = activeLabProfilesFromProfile(savedProfile);
      }
      return json(route, savedProfile ? activeProfiles : activeLabProfilesFixture());
    }
    if (url.pathname === "/api/v1/lab/profiles") {
      if (request.method() === "POST") {
        const payload = request.postDataJSON() as Record<string, unknown>;
        savedProfile = {
          ...activeLabProfilesFixture().active_profile,
          ...payload,
          id: "visual-profile",
          source: "saved",
          updated_at: checkedAt
        };
        activeProfiles = activeLabProfilesFromProfile(savedProfile);
        return json(route, savedProfile);
      }
      return json(route, savedProfile ? activeProfiles : activeLabProfilesFixture());
    }
    if (url.pathname === "/api/v1/lab/profiles/runtime/activate") {
      return json(route, savedProfile ? activeProfiles : activeLabProfilesFixture());
    }
    if (url.pathname === "/api/v1/lab/credentials") {
      return json(route, labCredentials());
    }
    if (url.pathname === "/api/v1/lab/topology-design-draft") {
      if (request.method() === "PUT") {
        const payload = request.postDataJSON() as Record<string, unknown>;
        const draft = topologyDesignDraftFixture(payload, "saved");
        topologyDesignDrafts.set(String(draft.id), draft);
        return json(route, draft);
      }
      const profileId = url.searchParams.get("profile_id") || "runtime";
      const scenario = url.searchParams.get("scenario") || "server_netapp_direct";
      const subnet = url.searchParams.get("subnet") || null;
      const key = topologyDesignDraftId(profileId, scenario, subnet);
      return json(route, topologyDesignDrafts.get(key) ?? topologyDesignDraftFixture({ profile_id: profileId, scenario, subnet }, "default"));
    }
    if (url.pathname === "/api/v1/reports/issues") {
      return json(route, reportCenter());
    }
    if (url.pathname === "/api/v1/requests") {
      return json(route, []);
    }
    if (url.pathname === "/api/v1/lab-build/plan") {
      return json(route, labBuildPlan());
    }
    if (url.pathname === "/api/v1/lab-build/runs/latest") {
      return json(route, labBuildRun);
    }
    if (url.pathname === "/api/v1/lab-build/runs" && request.method() === "POST") {
      labBuildRun = labBuildWaitingRun();
      return json(route, labBuildRun);
    }
    if (url.pathname.endsWith("/resume") && url.pathname.startsWith("/api/v1/lab-build/runs/")) {
      labBuildRun = labBuildCompletedRun();
      return json(route, labBuildRun);
    }
    if (url.pathname.includes("/api/v1/lab-build/runs/") && url.pathname.endsWith("/retry")) {
      labBuildRun = labBuildWaitingRun({ retryReady: true });
      return json(route, labBuildRun);
    }
    if (url.pathname.startsWith("/api/v1/lab-build/runs/")) {
      return json(route, labBuildRun ?? labBuildWaitingRun());
    }
    if (url.pathname.match(/^\/api\/v1\/workflow-runs\/[^/]+\/artifacts$/)) {
      return json(route, workflowRunArtifacts());
    }
    if (url.pathname.match(/^\/api\/v1\/workflow-runs\/[^/]+$/)) {
      return json(route, workflowRunDetail(url.pathname.split("/").pop() || "advanced-run-1"));
    }
    if (url.pathname === "/api/v1/workflow-runs") {
      return json(route, []);
    }
    if (url.pathname === "/api/v1/audit-events") {
      return json(route, auditEvents());
    }
    if (url.pathname === "/api/v1/settings/lab-safety") {
      if (request.method() === "PUT") {
        const payload = request.postDataJSON() as Record<string, unknown>;
        labSafety = labSafetySettings(payload);
      }
      return json(route, labSafety);
    }
    if (url.pathname === "/api/v1/workflows/stages") {
      return json(route, workflowStages());
    }
    if (url.pathname === "/api/v1/workflows/actions") {
      return json(route, workflowActionsOverride ?? workflowActions());
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
    if (url.pathname === "/api/v1/providers/cisco-console/identity-candidates") {
      return json(route, ciscoConsoleIdentityCandidates());
    }
    if (url.pathname === "/api/v1/providers/cisco-console/verify-identity") {
      const payload = request.postDataJSON() as { baud?: number; candidate_fingerprint?: string; port?: string };
      return json(route, ciscoConsoleIdentityVerified(payload));
    }
    if (url.pathname === "/api/v1/providers/cisco-ansible/probe") {
      return json(route, ciscoSshProbe());
    }
    if (url.pathname === "/api/v1/providers/cisco/current-intent-diff") {
      return json(route, ciscoCurrentIntentDiff());
    }
    if (url.pathname === "/api/v1/providers/ilo-redfish/hpe-raid-plan-preview") {
      return json(route, hpeRaidPlanPreview());
    }
    if (url.pathname === "/api/v1/providers/ilo-redfish/hpe-storage-discovery") {
      return json(route, hpeStorageDiscovery());
    }
    if (url.pathname === "/api/v1/providers/ilo-redfish/vsan-readiness") {
      return json(route, hpeVsanReadiness());
    }
    if (url.pathname === "/api/v1/providers/ilo-redfish/access-settings") {
      if (request.method() === "PUT") {
        const payload = request.postDataJSON() as { host?: string; username?: string; password?: string; verify_tls?: boolean };
        return json(route, iloAccessSettings({
          host: payload.host || "192.168.1.201",
          password_configured: Boolean(payload.password),
          username: payload.username || "Administrator",
          verify_tls: payload.verify_tls ?? false
        }));
      }
      return json(route, iloAccessSettings());
    }
    if (url.pathname === "/api/v1/providers/ilo-redfish/hpe-raid-pending") {
      return json(route, hpeRaidPending());
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
    if (url.pathname === "/api/v1/providers/netapp-ontap/live-state") {
      return json(route, netappLiveState());
    }
    if (url.pathname === "/api/v1/providers/netapp-ontap/iscsi-setup-preview") {
      return json(route, netappIscsiSetupPreview());
    }
    if (url.pathname === "/api/v1/providers/netapp-ontap/iscsi-setup-apply") {
      return json(route, netappIscsiSetupApplyBlocked());
    }
    if (url.pathname === "/api/v1/providers/netapp-ontap/iscsi-setup-validate") {
      return json(route, netappIscsiSetupValidation());
    }
    if (url.pathname === "/api/v1/providers/esxi-readonly/iscsi-datastore-preview") {
      return json(route, esxiIscsiDatastorePreview());
    }
    if (url.pathname === "/api/v1/providers/esxi-readonly/iscsi-datastore-validate") {
      return json(route, esxiIscsiDatastoreValidation());
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
    if (url.pathname === "/api/v1/firmware/file-selections") {
      if (request.method() === "PUT") {
        const payload = request.postDataJSON() as { selected_files?: Record<string, string> };
        firmwareFileSelections = firmwareFileSelectionState(payload.selected_files ?? {});
      }
      return json(route, firmwareFileSelections);
    }
    if (url.pathname === "/api/v1/media-inventory") {
      return json(route, mediaInventory());
    }
    if (url.pathname === "/api/v1/operator-issue-packets") {
      return json(route, operatorIssuePacket(request.postDataJSON() as Record<string, unknown>));
    }
    if (url.pathname === "/api/v1/ui-intent") {
      return json(route, uiIntentResponse(request.postDataJSON() as Record<string, unknown>));
    }
    if (url.pathname === "/api/v1/ai-change-requests") {
      return json(route, aiChangeRequest(request.postDataJSON() as Record<string, unknown>));
    }
    if (url.pathname === "/api/v1/workflows/actions/build-verification.run-full/run") {
      return json(route, workflowActionRun("build-verification.run-full"));
    }
    if (url.pathname.endsWith("/diagnosis")) {
      return json(route, workflowActionDiagnosis(actionIdFromDiagnosisPath(url.pathname)));
    }
    if (url.pathname.endsWith("/run")) {
      return json(route, workflowActionRun(actionIdFromRunPath(url.pathname)));
    }
    if (url.pathname.endsWith("/runs")) {
      const actionId = url.pathname.match(/\/api\/v1\/workflows\/actions\/(.+)\/runs$/)?.[1] ?? "";
      return json(route, actionId === "esxi.rebuild-install" ? [workflowActionRun(actionId)] : []);
    }
    return json(route, {});
  });
}

function json(route: Route, body: unknown) {
  return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
}

function inventoryDevice(id: string, deviceType: string, displayName: string, host: string, notes = "", dhcpEnabled = false) {
  return {
    id,
    device_type: deviceType,
    display_name: displayName,
    host: host || null,
    dhcp_enabled: dhcpEnabled,
    notes: notes || null,
    created_at: checkedAt,
    updated_at: checkedAt
  };
}

function labBuildPlan() {
  return {
    blockers: [],
    deployment_mode: "Server + shared storage + central management",
    headline: "This lab is ready to follow one ordered build plan.",
    kit_id: "runtime-profile",
    kit_name: "Runtime Lab",
    primary_action: "Start Build",
    status: "ready",
    steps: labBuildSteps(),
    supporting_message: "8 steps will run in dependency order and pause at guarded changes."
  };
}

function labBuildSteps() {
  return [
    labBuildStep({
      action_id: "esxi.rebuild-install",
      action_mode: "destructive",
      can_retry: false,
      description: "Run the guarded server power/reset stage that requests a boot from previously prepared ESXi installer media. This stage does not install or configure ESXi.",
      label: "Boot the ESXi installer",
      operator_path: "/virtualization",
      order: 1,
      provides: ["esxi-installer-boot-requested"],
      rationale: "The guarded action requests installer boot through iLO; it is not proof that ESXi was installed or configured.",
      step_id: "esxi-installer-boot",
      suggested_action: "Open Virtualization Setup, approve only the guarded installer boot, then resume this build."
    }),
    labBuildStep({
      action_id: "esxi.management-validation",
      depends_on: ["esxi-installer-boot-requested"],
      description: "After ESXi installation and initial host configuration, confirm target-bound management evidence.",
      label: "Validate ESXi management",
      order: 2,
      operator_path: "/virtualization",
      provides: ["hypervisor"],
      rationale: "An installer boot request alone never establishes a usable ESXi host.",
      step_id: "hypervisor"
    }),
    labBuildStep({
      action_id: "netapp.setup-apply",
      action_mode: "write",
      depends_on: ["hypervisor"],
      description: "Apply the saved storage system identity, network, and service plan.",
      label: "Configure shared storage",
      operator_path: "/storage",
      order: 3,
      provides: ["storage-system"],
      step_id: "storage-system"
    }),
    labBuildStep({
      action_id: "netapp.nfs-setup-apply",
      action_mode: "write",
      depends_on: ["storage-system"],
      description: "Create the selected shared-storage service for this kit.",
      label: "Configure NFS storage",
      operator_path: "/storage",
      order: 4,
      provides: ["shared-storage"],
      step_id: "storage-service"
    }),
    labBuildStep({
      action_id: "esxi.netapp-datastore-apply",
      action_mode: "write",
      depends_on: ["hypervisor", "shared-storage"],
      description: "Make shared storage available to the compute host.",
      label: "Connect shared storage to the compute host",
      operator_path: "/virtualization",
      order: 5,
      provides: ["datastore"],
      rationale: "Shared storage must be ready before the compute host can use it.",
      step_id: "datastore"
    }),
    labBuildStep({
      action_id: "vcenter.install-apply",
      action_mode: "write",
      depends_on: ["datastore"],
      description: "Deploy the saved central management appliance to the ready datastore.",
      label: "Deploy central management",
      operator_path: "/virtualization",
      order: 6,
      provides: ["vcenter"],
      step_id: "vcenter"
    }),
    labBuildStep({
      action_id: "vcenter.attach-esxi-apply",
      action_mode: "write",
      depends_on: ["hypervisor", "vcenter"],
      description: "Add the compute host to central management after both are ready.",
      label: "Add the compute host",
      operator_path: "/virtualization",
      order: 7,
      provides: ["managed-hypervisor"],
      step_id: "vcenter-attach"
    }),
    labBuildStep({
      action_id: "full-lab.validation",
      depends_on: ["datastore", "managed-hypervisor"],
      description: "Run the final checks and prepare the build summary.",
      label: "Verify and prepare handoff",
      operator_path: "/validation",
      order: 8,
      provides: ["handoff-ready"],
      step_id: "handoff"
    })
  ];
}

function labBuildStep(overrides: Record<string, unknown> = {}) {
  return {
    action_id: "test.action",
    action_mode: "read_only",
    action_run_id: null,
    can_retry: true,
    depends_on: [],
    description: "Complete this build step.",
    finished_at: null,
    label: "Build step",
    lease_expires_at: null,
    optional: false,
    operator_message: "Waiting for the build to start.",
    operator_path: "/overview",
    order: 1,
    provides: [],
    rationale: null,
    started_at: null,
    status: "not_started",
    step_id: "step",
    suggested_action: "Correct the issue and retry.",
    summary: "not_started",
    technical_details: "",
    waiting_nonce: null,
    ...overrides
  };
}

function labBuildWaitingRun({ retryReady = false }: { retryReady?: boolean } = {}) {
  const steps = labBuildSteps();
  const currentIndex = retryReady ? 1 : 0;
  if (retryReady) {
    steps[0] = labBuildStep({
      ...steps[0],
      action_run_id: "action:esxi-installer-boot",
      finished_at: checkedAt,
      operator_message: "Boot the ESXi installer completed.",
      started_at: checkedAt,
      status: "succeeded",
      summary: "complete",
      technical_details: "{\"status\":\"completed\"}"
    });
  }
  steps[currentIndex] = labBuildStep({
    ...steps[currentIndex],
    operator_message: retryReady
      ? "Validate ESXi management is ready to retry."
      : "Waiting for approval: Boot the ESXi installer.",
    started_at: checkedAt,
    status: retryReady ? "not_started" : "waiting",
    summary: retryReady ? "not_started" : "operator_approval_required",
    technical_details: "Action remains protected by its existing confirmation and safety gates.",
    waiting_nonce: retryReady ? null : "waiting-nonce-1234567890"
  });
  for (let index = currentIndex + 1; index < steps.length; index += 1) {
    steps[index] = labBuildStep({
      ...steps[index],
      operator_message: `Blocked by: ${steps[currentIndex].label}.`,
      status: "blocked",
      summary: "dependency_not_ready"
    });
  }
  const completed = retryReady ? 1 : 0;
  const current = steps[currentIndex];
  return {
    counts: { completed, failed: steps.length - completed - 1, warnings: 0 },
    current_step_id: String(current.step_id),
    deployment_mode: "Server + shared storage + central management",
    finished_at: null,
    headline: retryReady ? "Validate ESXi management is ready to retry." : "Waiting at step 1 of 8.",
    kit_id: "runtime-profile",
    kit_name: "Runtime Lab",
    operator_message: String(current.operator_message),
    progress: { completed, percent: retryReady ? 13 : 0, total: steps.length },
    report_artifact: null,
    revision: retryReady ? 9 : 8,
    run_id: "lab-build:test",
    started_at: checkedAt,
    status: "waiting",
    steps,
    suggested_action: String(current.suggested_action),
    updated_at: checkedAt
  };
}

function labBuildCompletedRun() {
  const steps = labBuildSteps().map((step) => labBuildStep({
    ...step,
    action_run_id: `action:${step.step_id}`,
    finished_at: checkedAt,
    operator_message: `${step.label} completed.`,
    started_at: checkedAt,
    status: "succeeded",
    summary: "complete",
    technical_details: "{\"status\":\"completed\"}"
  }));
  return {
    counts: { completed: steps.length, failed: 0, warnings: 0 },
    current_step_id: null,
    deployment_mode: "Server + shared storage + central management",
    finished_at: checkedAt,
    headline: "Lab build completed.",
    kit_id: "runtime-profile",
    kit_name: "Runtime Lab",
    operator_message: "The selected kit completed every build step.",
    progress: { completed: steps.length, percent: 100, total: steps.length },
    report_artifact: "artifacts/codex-runs/lab-build-runs/lab-build-test.md",
    revision: 12,
    run_id: "lab-build:test",
    started_at: checkedAt,
    status: "completed",
    steps,
    suggested_action: "Review and export the completion report.",
    updated_at: checkedAt
  };
}

function labBuildRunningRun() {
  const run = labBuildWaitingRun();
  const steps = run.steps as Array<Record<string, unknown>>;
  steps[0] = {
    ...steps[0],
    lease_expires_at: "2099-01-01T00:00:00Z",
    operator_message: "Boot the ESXi installer is running.",
    status: "running",
    summary: "running",
    waiting_nonce: null
  };
  return {
    ...run,
    headline: "Building the lab.",
    operator_message: "The current check is still running.",
    revision: 9,
    status: "running"
  };
}

function labBuildFailedRun() {
  const steps = labBuildSteps();
  steps[0] = labBuildStep({
    ...steps[0],
    action_run_id: "action:esxi-installer-boot",
    finished_at: checkedAt,
    operator_message: "Boot the ESXi installer completed.",
    started_at: checkedAt,
    status: "succeeded",
    summary: "complete"
  });
  steps[1] = labBuildStep({
    ...steps[1],
    action_run_id: "action:hypervisor",
    finished_at: checkedAt,
    operator_message: "Validate ESXi management failed.",
    started_at: checkedAt,
    status: "failed",
    suggested_action: "Check the management connection and retry.",
    summary: "failed",
    technical_details: "{\"blockers\":[\"PROVIDER_MODE is unavailable\"]}"
  });
  for (let index = 2; index < steps.length; index += 1) {
    steps[index] = labBuildStep({
      ...steps[index],
      can_retry: false,
      operator_message: "Blocked by: Validate ESXi management.",
      status: "blocked",
      summary: "dependency_not_ready"
    });
  }
  return {
    counts: { completed: 1, failed: steps.length - 1, warnings: 0 },
    current_step_id: "hypervisor",
    deployment_mode: "Server + shared storage + central management",
    finished_at: checkedAt,
    headline: "Build stopped at step 2 of 8.",
    kit_id: "runtime-profile",
    kit_name: "Runtime Lab",
    operator_message: "Validate ESXi management failed.",
    progress: { completed: 1, percent: 13, total: steps.length },
    report_artifact: null,
    revision: 7,
    run_id: "lab-build:failed",
    started_at: checkedAt,
    status: "failed",
    steps,
    suggested_action: "Check the management connection and retry.",
    updated_at: checkedAt
  };
}

function uiIntentResponse(payload: Record<string, unknown>) {
  const request = String(payload.request || "").toLowerCase();
  const regions = Array.isArray(payload.regions) ? payload.regions as Array<Record<string, unknown>> : [];
  const selected = regions.filter((region) => {
    const haystack = `${region.id || ""} ${region.label || ""}`.toLowerCase();
    return request.split(/[^a-z0-9]+/).some((token) => token.length > 3 && haystack.includes(token));
  });
  const op = request.includes("collapse")
    ? "collapse"
    : request.includes("show") || request.includes("restore")
      ? "show"
      : "hide";
  const scoped = selected.length === 0 && regions.length === 1 && ["hide", "show", "collapse", "expand", "moveUp", "moveDown"].includes(op)
    ? regions
    : selected;
  const ops = scoped.map((region) => ({ op, region_id: String(region.id) }));
  const labels = scoped.map((region) => String(region.label || region.id));
  const verb = op === "collapse" ? "Collapsed" : op === "show" ? "Showed" : "Hid";
  return {
    ops,
    source: "local_rules",
    summary: ops.length ? `${verb}: ${labels.join(", ")}.` : "No safe layout change matched this page."
  };
}

function aiChangeRequest(payload: Record<string, unknown>) {
  return {
    artifact: `docs/change-requests/20260707T161900Z-${String(payload.page || "page")}.md`,
    message: "Sent to the Claude+Codex mailbox and saved as a review artifact.",
    next_action: "Claude and Codex read docs/agent-chat.md; implement on a branch, fast-verify, and request review before applying.",
    request_id: "20260707T161900Z",
    status: "queued"
  };
}

function topologyDesignDraftFixture(payload: Record<string, unknown>, source: "default" | "saved") {
  const profileId = String(payload.profile_id || "runtime");
  const scenario = String(payload.scenario || "server_netapp_direct");
  const subnet = typeof payload.subnet === "string" ? payload.subnet : null;
  const placements = normalizeTopologyDesignPlacements(payload.placements, scenario);
  const deviceSettings = normalizeTopologyDesignDeviceSettings(payload.device_settings, scenario, subnet);
  const laneSettings = normalizeTopologyDesignLaneSettings(payload.lane_settings, scenario);
  const connectionSettings = normalizeTopologyDesignConnectionSettings(payload.connection_settings, scenario);
  return {
    draft_saved: source === "saved",
    hardware_touched: false,
    id: topologyDesignDraftId(profileId, scenario, subnet),
    message: source === "saved"
      ? "Topology design draft loaded from persistent store."
      : "Topology design draft is using scenario defaults until saved.",
    persistence_inventory: [
      {
        choice: "scenario",
        commit_state: "draft_only",
        hardware_effect: "none",
        persists_to: "topology design draft store"
      },
      {
        choice: "rack placements",
        commit_state: "draft_only",
        hardware_effect: "none",
        persists_to: "topology design draft store"
      }
    ],
    connection_settings: connectionSettings,
    device_settings: deviceSettings,
    lane_settings: laneSettings,
    placements,
    profile_id: profileId,
    scenario,
    source,
    store_path: ".local/topology-design-drafts.json",
    subnet,
    updated_at: source === "saved" ? checkedAt : null
  };
}

function topologyDesignDraftId(profileId: string, scenario: string, subnet: string | null) {
  return `${profileId}:${scenario}:${subnet || "no-subnet"}`.replace(/[^A-Za-z0-9_.:-]+/g, "_");
}

function normalizeTopologyDesignConnectionSettings(value: unknown, scenario: string) {
  const input = value && typeof value === "object" ? value as Record<string, Record<string, unknown>> : {};
  const defaults: Record<string, Record<string, string>> = {
    "switch-server": {
      lane: "management",
      mtu: "1500",
      protocol: "management + vmkernel",
      source: "Cisco C9300",
      status: "planned",
      target: "ESXi host vmnic/iLO",
      vlan: "100"
    },
    "server-vm": {
      lane: "virtualization",
      mtu: "1500",
      protocol: "vSphere API / VM network",
      source: "vCenter",
      status: "planned",
      target: "VM inventory",
      vlan: "100"
    }
  };
  if (scenario !== "single_server_local_storage") {
    defaults["switch-netapp"] = {
      lane: "storage",
      mtu: "9000",
      protocol: "NFS / iSCSI VLANs",
      source: "Cisco C9300",
      status: "planned",
      target: "NetApp e0a/e0b",
      vlan: "220"
    };
    defaults["server-netapp"] = {
      lane: "storage",
      mtu: "9000",
      protocol: "datastore path",
      source: "ESXi vmkernel",
      status: "planned",
      target: "NetApp datastore LIFs",
      vlan: "220"
    };
  }
  for (const [connection, settings] of Object.entries(input)) {
    if (!defaults[connection] || !settings || typeof settings !== "object") continue;
    for (const [key, raw] of Object.entries(settings)) {
      if (typeof raw === "string") defaults[connection][key] = raw;
    }
  }
  return defaults;
}

function normalizeTopologyDesignLaneSettings(value: unknown, scenario: string) {
  const input = value && typeof value === "object" ? value as Record<string, Record<string, unknown>> : {};
  const defaults: Record<string, Record<string, string>> = {
    management: {
      mtu: "1500",
      protocol: "HTTPS, SSH, Redfish, ONTAP REST",
      purpose: "Device access and control plane",
      source: "Operator workstation / Cisco",
      target: "iLO, ESXi, NetApp, vCenter",
      vlan: "100"
    },
    storage: {
      mtu: scenario === "single_server_local_storage" ? "1500" : "9000",
      protocol: scenario === "single_server_local_storage" ? "local datastore" : "NFS primary / iSCSI optional",
      purpose: scenario === "single_server_local_storage" ? "Local datastore control" : "VM datastore traffic",
      source: scenario === "single_server_local_storage" ? "HPE RAID / ESXi local disks" : "ESXi vmkernel",
      target: scenario === "single_server_local_storage" ? "server-local RAID datastore" : "NetApp SVM datastore LIFs",
      vlan: scenario === "single_server_local_storage" ? "local" : "220"
    },
    virtualization: {
      mtu: "1500",
      protocol: "vSphere API, VM networks",
      purpose: "Inventory, templates, and VM handoff",
      source: "vCenter",
      target: "VM networks and datastore inventory",
      vlan: "100"
    }
  };
  for (const [lane, settings] of Object.entries(input)) {
    if (!defaults[lane] || !settings || typeof settings !== "object") continue;
    for (const [key, raw] of Object.entries(settings)) {
      if (typeof raw === "string") defaults[lane][key] = raw;
    }
  }
  return defaults;
}

function normalizeTopologyDesignDeviceSettings(value: unknown, scenario: string, subnet: string | null = null) {
  const input = value && typeof value === "object" ? value as Record<string, Record<string, unknown>> : {};
  const base = topologyDesignSubnetBase(subnet) || "192.168.1";
  const defaults: Record<string, Record<string, string>> = {
    switch: { gateway: `${base}.1`, management_ip: `${base}.204`, mgmt_vlan: "100", storage_vlan: "220", ports: "server and storage ports" },
    "server-gen10": { gateway: `${base}.1`, management_ip: `${base}.201`, raid_boot: "RAID1", raid_data: "RAID6 or local datastore" },
    "server-gen10plus": { gateway: `${base}.1`, management_ip: `${base}.201`, raid_boot: "RAID1", raid_data: "RAID6 or local datastore" },
    vcenter: { gateway: `${base}.1`, management_ip: `${base}.205`, datastore: "validated datastore" },
    windows: { vm_network: "management VLAN", role: "guest workload" }
  };
  if (scenario !== "single_server_local_storage") {
    defaults.netapp = {
      gateway: `${base}.1`,
      iscsi_lifs: `${base}.240, ${base}.241, ${base}.242, ${base}.243`,
      management_ip: `${base}.220`,
      nfs_lifs: `${base}.230, ${base}.231`,
      protocol: "NFS primary, iSCSI optional",
      ports: "e0a/e0b"
    };
  }
  for (const [part, settings] of Object.entries(input)) {
    if (!defaults[part] || !settings || typeof settings !== "object") continue;
    for (const [key, raw] of Object.entries(settings)) {
      if (typeof raw === "string") defaults[part][key] = raw;
    }
  }
  return defaults;
}

function topologyDesignSubnetBase(subnet: string | null) {
  if (!subnet || !subnet.includes(".")) return null;
  const octets = subnet.split("/", 1)[0].split(".").slice(0, 3);
  return octets.length === 3 && octets.every((octet) => /^\d+$/.test(octet)) ? octets.join(".") : null;
}

function normalizeTopologyDesignPlacements(value: unknown, scenario: string) {
  const input = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const defaults: Record<string, string | null> = {
    u1: "switch",
    u2: "server-gen10",
    u3: scenario === "single_server_local_storage" ? null : "netapp",
    u4: null,
    virtual: scenario === "server_netapp_vcenter" ? "vcenter" : null
  };
  return {
    u1: typeof input.u1 === "string" ? input.u1 : defaults.u1,
    u2: typeof input.u2 === "string" ? input.u2 : defaults.u2,
    u3: typeof input.u3 === "string" && scenario !== "single_server_local_storage" ? input.u3 : defaults.u3,
    u4: typeof input.u4 === "string" ? input.u4 : defaults.u4,
    virtual: typeof input.virtual === "string" && ["vcenter", "windows"].includes(input.virtual) ? input.virtual : defaults.virtual
  };
}

function auditEvents() {
  return [
    {
      actor: "local-dev-user",
      created_at: checkedAt,
      data_json: { changed_fields: ["lab_acknowledge_real_hardware"] },
      event_type: "settings.lab_safety.updated",
      from_status: null,
      id: "audit-lab-safety",
      message: "Lab safety runtime settings were updated.",
      request_id: null,
      to_status: null,
      workflow_run_id: null
    }
  ];
}

function workflowRunDetail(id = "advanced-run-1") {
  return {
    created_at: checkedAt,
    error_message: null,
    id,
    plan_json: {
      request_intent: {
        site: "Lab",
        vm: {
          cluster: "Edge Cluster",
          cpu: 2,
          datastore: "netapp_nfs_ds01",
          disk_gb: 80,
          memory_gb: 8,
          network: "VM Network",
          template: "Windows Server 2022",
          vm_name: "w2k22-preview"
        }
      },
      review_before_execute: {
        message: "Advanced review can inspect the preview proof without changing operator mode.",
        status: "ready"
      },
      stage_events: [
        {
          message: "Read-only validation proof was collected.",
          stage: "validation",
          status: "completed"
        }
      ],
      steps: [
        {
          name: "Collect validation proof",
          status: "completed",
          target: "Lab Builder"
        }
      ],
      summary: "Preview plan for advanced route proof."
    },
    provider: "local-preview",
    request_id: "request-advanced-1",
    result_json: {
      executed_steps: [
        {
          name: "Collect validation proof",
          status: "completed",
          target: "Lab Builder"
        }
      ],
      message: "Advanced route proof completed.",
      mock_task_id: "task-advanced-1",
      mock_vm_id: "vm-advanced-1",
      provider: "local-preview",
      stage_events: [
        {
          message: "Preview proof finished.",
          stage: "validation",
          status: "completed"
        }
      ]
    },
    status: "completed",
    updated_at: checkedAt,
    workflow_id: "workflow-advanced-1",
    workflow_slug: "advanced-proof-route"
  };
}

function workflowRunArtifacts() {
  return [
    {
      created_at: checkedAt,
      description: "Redacted local proof artifact for the advanced route gate.",
      downloadable: false,
      download_url: null,
      id: "artifact-advanced-route",
      kind: "proof",
      metadata: {
        event_count: 1,
        provider: "local-preview",
        run_status: "completed",
        step_count: 1
      },
      mock_only: true,
      redacted: true,
      request_id: "request-advanced-1",
      status: "completed",
      title: "Advanced route proof",
      updated_at: checkedAt,
      workflow_run_id: "advanced-run-1"
    }
  ];
}

function labSafetySettings(overrides: Record<string, unknown> = {}) {
  const values = {
    lab_acknowledge_data_loss_risk: false,
    lab_acknowledge_device_reconfiguration: false,
    lab_acknowledge_lab_only: false,
    lab_acknowledge_real_hardware: false,
    lab_environment: null,
    ...overrides
  };
  const flag = (name: keyof typeof values, label: string, description: string) => {
    const value = values[name];
    const enabled = name === "lab_environment" ? value === "isolated-real-lab" : value === true;
    return {
      description,
      enabled,
      label,
      name,
      required: true,
      source: value === null || value === false ? "environment" : "runtime",
      status: enabled ? "enabled" : "missing",
      value
    };
  };
  const flags = [
    flag("lab_environment", "Isolated real lab", "Confirms this runtime is pointed at an isolated lab, not production."),
    flag("lab_acknowledge_real_hardware", "Real hardware acknowledgement", "Allows read-only probes to contact configured lab hardware."),
    flag("lab_acknowledge_device_reconfiguration", "Device reconfiguration acknowledgement", "Acknowledges guarded workflows may change lab device configuration."),
    flag("lab_acknowledge_data_loss_risk", "Data loss risk acknowledgement", "Acknowledges rebuild/reset workflows can destroy existing lab data."),
    flag("lab_acknowledge_lab_only", "Lab-only acknowledgement", "Confirms these permissions apply only to this local lab environment.")
  ];
  return {
    confirmation_phrase: "ACKNOWLEDGE REAL LAB RISK",
    device_reconfiguration_confirmation_phrase: "ACKNOWLEDGE DEVICE RECONFIGURATION",
    flags,
    next_safe_action: flags.every((item) => item.enabled)
      ? "Real lab prerequisites are satisfied for read-only probes."
      : "Complete real lab prerequisites before relying on live provider probes.",
    store_path: ".local/lab-safety-settings.json",
    updated_at: checkedAt
  };
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
    readAction("firmware.compliance-check", "Check Compliance", "firmware-upgrade", "firmware"),
    firmwareUpgradePlanAction,
    firmwareUpgradeApplyPlaceholderAction,
    netappOntapUpgradeApplyAction,
    readAction("cisco.setup-readiness", "Cisco Access Live Check", "cisco", "cisco"),
    readAction("cisco.ssh-readonly-probe", "Cisco SSH Read-Only Probe", "cisco", "cisco"),
    readAction("cisco.current-intent-diff", "Cisco Current Intent Diff", "cisco", "cisco"),
    readAction("cisco.discover-console", "Refresh Cisco Console", "cisco", "cisco"),
    readAction("ilo.reachability", "iLO Live Check", "ilo", "ilo-redfish"),
    readAction("ilo.auth", "iLO Auth Live Check", "ilo", "ilo-redfish"),
    readAction("ilo.inventory", "iLO Inventory Read", "ilo", "ilo-redfish"),
    readAction("esxi.management-validation", "ESXi Live Check", "esxi", "esxi"),
    readAction("esxi.ssh-api-check", "ESXi SSH/API Live Check", "esxi", "esxi"),
    readAction("esxi.iscsi-datastore-preview", "Preview ESXi iSCSI Datastore", "esxi", "esxi"),
    readAction("esxi.iscsi-datastore-validate", "Validate ESXi iSCSI Datastore", "esxi", "esxi"),
    readAction("raid.validate", "Validate RAID", "raid", "ilo-redfish"),
    readAction("netapp.live-state", "NetApp Live Check", "netapp", "netapp-ontap"),
    readAction("netapp.validate-setup", "Validate NetApp Setup", "netapp", "netapp-ontap"),
    readAction("netapp.iscsi-setup-preview", "Preview NetApp iSCSI", "netapp", "netapp-ontap"),
    readAction("netapp.iscsi-setup-validate", "Validate NetApp iSCSI", "netapp", "netapp-ontap"),
    readAction("netapp.nfs-setup-validate", "Validate NFS", "netapp", "netapp-ontap"),
    readAction("netapp.console-autodiscovery", "Refresh NetApp Consoles", "netapp", "netapp-ontap"),
    readAction("netapp.component-firmware-inventory", "Refresh ONTAP", "netapp", "netapp-ontap"),
    readAction("vcenter-netapp.readiness", "vCenter Live Check", "vcenter", "vcenter"),
    readAction("vcenter.install-readiness", "vCenter Install Readiness", "vcenter", "vcenter"),
    readAction("vcenter.post-attach-validation", "Validate Datastore", "vcenter", "vcenter"),
    readAction("esxi.vm-deploy-validate", "Validate VM Inventory", "esxi", "esxi"),
    readAction("firmware.inventory", "Scan All Firmware", "firmware-upgrade", "firmware"),
    readAction("lab-validation.summary", "Refresh Evidence", "validation", "lab-validation"),
    readAction("provider-smoke.real-lab", "Run Real Provider Smoke", "build-verification", "provider-smoke"),
    readAction("operator-readonly-sweep.real-lab", "Run Operator Read-Only Sweep", "build-verification", "operator-sweep"),
    apiReadAction("full-lab.build-plan", "Run Full Lab Build Plan", "full-lab", "full-lab", "/api/v1/lab/full-rebuild-summary"),
    readAction("full-lab.repair", "Run Golden-State Repair Plan", "full-lab", "full-lab"),
    readAction("full-lab.validation", "Run Full Lab Validation", "full-lab", "full-lab"),
    readAction("full-lab.handoff-report", "Generate Handoff Report", "full-lab", "full-lab"),
    readAction("netapp.factory-reset-preview", "Preview NetApp Factory Reset", "netapp", "netapp-ontap"),
    readAction("netapp.factory-reset-validate", "Validate NetApp Factory Reset", "netapp", "netapp-ontap"),
    writeAction("cisco.save-config", "Save Config", "cisco", "cisco"),
    writeAction("esxi.recover-management", "Recover ESXi", "esxi", "esxi"),
    writeAction("esxi.netapp-datastore-apply", "Mount Datastore", "esxi", "esxi"),
    writeAction("vcenter.attach-esxi-apply", "Attach ESXi", "vcenter", "vcenter"),
    writeAction("esxi.vm-deploy-apply", "Deploy VM", "esxi", "esxi"),
    writeAction("netapp.factory-reset-apply", "Apply NetApp Factory Reset", "netapp", "netapp-ontap", "destructive"),
    writeAction("raid.reset-commit", "Reset HPE RAID", "raid", "ilo-redfish", "destructive"),
    writeAction("esxi.rebuild-install", "Boot ESXi Installer", "esxi", "esxi", "destructive"),
    writeAction("ilo.reset-server", "Reset Server Power", "ilo", "ilo-redfish", "destructive")
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

function apiReadAction(action_id: string, label: string, stage: string, provider: string, api_endpoint: string) {
  return workflowAction({
    action_id,
    api_endpoint,
    api_method: "GET",
    category: "verify",
    command: null,
    current_availability: "available",
    label,
    mode: "read_only",
    provider,
    source_type: "api_endpoint",
    stage,
    stage_label: label,
    ui_run_supported: true
  });
}

function writeAction(action_id: string, label: string, stage: string, provider: string, mode: "write" | "destructive" = "write") {
  return workflowAction({
    action_id,
    category: "apply",
    current_availability: "manual_command_required",
    guarded_run_supported: true,
    label,
    mode,
    provider,
    required_confirmations: [`CONFIRM ${label.toUpperCase()}`],
    stage,
    stage_label: label,
    ui_run_supported: false,
    ui_run_blockers: ["guarded workflow requires confirmation"]
  });
}

function actionIdFromRunPath(pathname: string) {
  return pathname.match(/\/api\/v1\/workflows\/actions\/(.+)\/run$/)?.[1] ?? "build-verification.run-full";
}

function actionIdFromDiagnosisPath(pathname: string) {
  return pathname.match(/\/api\/v1\/workflows\/actions\/(.+)\/diagnosis$/)?.[1] ?? "build-verification.run-full";
}

function workflowActionDiagnosis(actionId: string) {
  const run = workflowActionRun(actionId);
  return {
    action_id: actionId,
    action_label: run.action_label,
    advisory_source: "local_rules",
    ai_enabled: false,
    confidence: run.status === "blocked" ? "high" : "medium",
    evidence: run.blockers.map((blocker) => ({ detail: blocker, label: "Blocker" })),
    explanation: run.status === "blocked"
      ? "The app refused to proceed before making changes. Run a read-only check before retrying a guarded path."
      : "The latest run completed without a blocking failure.",
    probable_cause: run.status === "blocked"
      ? "A guarded action was blocked before it could make changes."
      : "The latest run did not report a blocking failure.",
    recent_runs: [
      {
        blocker_count: run.blockers.length,
        finished_at: run.finished_at,
        run_id: run.run_id,
        status: run.status,
        summary: run.summary,
        trace_artifact: run.trace_artifact,
        warning_count: run.warnings.length
      }
    ],
    run_id: run.run_id,
    safety_notes: [
      "Diagnosis is advisory and does not execute workflow actions.",
      "Suggested action ids are limited to read-only or report-only actions when available."
    ],
    status: run.status,
    suggested_action_id: run.status === "blocked" ? "firmware.compliance-check" : actionId,
    suggested_action_safe: true,
    suggested_next_action: run.status === "blocked" ? "Run Firmware Compliance Check" : "Review evidence artifacts."
  };
}

function operatorIssuePacket(payload: Record<string, unknown>) {
  const route = String(payload.route || "/overview");
  const pageTitle = String(payload.page_title || "Overview");
  const operatorNote = String(payload.operator_note || "");
  const run = workflowActionRun("build-verification.run-full");
  return {
    packet_id: "20260706T000000Z__network",
    created_at: "2026-07-06T00:00:00+00:00",
    route,
    page_title: pageTitle,
    operator_note: operatorNote,
    ui_context: payload.ui_context ?? {},
    ai_enabled: false,
    advisory_source: "local_rules",
    summary: operatorNote
      ? `Operator reported an issue on ${pageTitle}: ${operatorNote}`
      : `Operator requested an issue packet on ${pageTitle}.`,
    recent_problem_runs: [
      {
        run_id: run.run_id,
        action_id: run.action_id,
        stage_id: run.stage_id,
        started_at: run.started_at,
        finished_at: run.finished_at,
        status: "blocked",
        source_type: run.source_type,
        freshness: run.freshness,
        command: run.command,
        report_artifacts: run.report_artifacts,
        summary: run.summary,
        blockers: ["Validation remained blocked."],
        warnings: run.warnings,
        next_action: run.next_action
      }
    ],
    diagnoses: [
      {
        action_id: run.action_id,
        status: "blocked",
        confidence: "medium",
        probable_cause: "The latest validation run reported blockers.",
        suggested_next_action: "Run the read-only validation check again.",
        suggested_action_id: run.action_id,
        suggested_action_safe: true
      }
    ],
    suggested_next_steps: [
      "Attach this packet to the AI/code review prompt before changing behavior.",
      "Reproduce from the route and active UI context listed in the packet.",
      "After any fix, run .\\scripts\\fast-verify.ps1 from the app directory."
    ],
    safety_notes: ["Issue packets are advisory and do not execute workflow actions."],
    artifact: "artifacts/codex-runs/operator-issue-packets/20260706T000000Z__network.json",
    markdown_artifact: "artifacts/codex-runs/operator-issue-packets/20260706T000000Z__network.md",
    copy_prompt: `Please fix this Lab Builder issue.\nRoute: ${route}\nOperator note: ${operatorNote}`
  };
}

function workflowActionRun(actionId: string) {
  const isFirmwareUpgrade = actionId === "firmware.upgrade-apply-placeholder";
  const isOperatorSweep = actionId === "operator-readonly-sweep.real-lab";
  const isCiscoShow = actionId === "cisco.ssh-readonly-probe";
  return {
    action_id: actionId,
    action_label: isFirmwareUpgrade ? "Run Upgrade Placeholder" : "Run Full Verification",
    blockers: isFirmwareUpgrade ? ["requires guarded firmware update workflow"] : [],
    checked_at: checkedAt,
    command: "make provider-lab-build-verification",
    executed: !isFirmwareUpgrade,
    finished_at: checkedAt,
    freshness: "current",
    mode: isFirmwareUpgrade ? "upgrade" : "read_only",
    next_action: isFirmwareUpgrade ? "requires guarded firmware update workflow" : "Review evidence artifacts, then continue with the next safe stage.",
    not_mock: true,
    report_artifacts: ["artifacts/codex-runs/build-verification-report.md"],
    return_code: isFirmwareUpgrade ? null : 0,
    run_id: `workflow-action:${actionId}:test`,
    source_type: "live_probe",
    stage_id: isFirmwareUpgrade ? "firmware-upgrade" : "build-verification",
    stage_label: isFirmwareUpgrade ? "Firmware / Upgrade Center" : "Build Verification",
    started_at: checkedAt,
    status: isFirmwareUpgrade ? "blocked" : "completed",
    stderr_summary: "",
    stdout_summary: isFirmwareUpgrade
      ? ""
      : isCiscoShow
        ? JSON.stringify({
          command_evidence: {
            "show interface Gi1/0/2": {
              captured: true,
              stdout_summary: ["Gi1/0/2 is up, line protocol is up", "Hardware is Gigabit Ethernet, address redacted"]
            },
            "show running-config interface Gi1/0/2": {
              captured: true,
              stdout_summary: ["interface Gi1/0/2", "description ilo", "switchport access vlan 10"]
            },
            "show interfaces status": {
              captured: true,
              stdout_summary: ["Gi1/0/2   ilo                connected    10         a-full  a-1000 10/100/1000BaseTX"]
            }
          }
        })
        : "verification passed",
    summary: isFirmwareUpgrade ? "Guarded action was not run because required gates were not satisfied." : "Safe read-only/report-only action completed.",
    trace_artifact: "artifacts/codex-runs/workflow-action-runs/test.json",
    warnings: isOperatorSweep
      ? ["Read-only sweep passed the required path, but optional parity checks reported blockers: esxi.iscsi-datastore-validate."]
      : []
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
    configuration: id === "ilo-redfish"
      ? {
          last_probe_status: "ok",
          last_probe_target_fingerprint_present: true,
          last_probe_target_matches_active_profile: true,
          last_probe_target_matches_configured_candidates: true
        }
      : {},
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
      safe_next_action: "Run Cisco Access Live Check.",
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

function ciscoConsoleIdentityCandidates() {
  return {
    checked_at: checkedAt,
    message: "Two serial endpoints are present. Choose the physical Cisco cable before verification.",
    provider_id: "cisco-console",
    status: "not_checked",
    candidates: [
      {
        candidate_fingerprint: "candidate-intel-com3",
        description: "Intel(R) Active Management Technology - SOL",
        manufacturer: "Intel",
        port: "COM3",
        recommended: false,
        recommended_bauds: [9600, 115200],
        serial_present: false,
        transport: "system_serial",
        usb_location: null,
        vid_pid: null
      },
      {
        candidate_fingerprint: "candidate-prolific-com5",
        description: "Prolific USB-to-Serial Comm Port",
        manufacturer: "Prolific",
        port: "COM5",
        recommended: true,
        recommended_bauds: [9600, 115200],
        serial_present: false,
        transport: "usb_serial",
        usb_location: "USB port 1-6",
        vid_pid: "067B:2303"
      }
    ]
  };
}

function ciscoConsoleIdentityVerified(payload: { baud?: number; candidate_fingerprint?: string; port?: string }) {
  return {
    baud: payload.baud ?? 9600,
    blockers: [],
    candidate_fingerprint: payload.candidate_fingerprint ?? "candidate-prolific-com5",
    checked_at: checkedAt,
    commands_attempted: ["show version", "show inventory"],
    detected_vendor: "cisco",
    identity_verified: true,
    message: "Fresh Cisco IOS XE identity proof matched the selected adapter.",
    model: "C9300-48P",
    port: payload.port ?? "COM5",
    prompt_state: "privileged_exec",
    provider_id: "cisco-console",
    read_only: true,
    serial_fingerprint: "sha256:67ab…c912",
    software_version: "17.15.05",
    status: "ready",
    warnings: []
  };
}

function ciscoSshProbe() {
  return {
    blockers: [],
    checked_at: checkedAt,
    command_results: {
      "show version": {
        captured: true,
        command: "show version",
        returncode: 0,
        stdout_summary: ["Cisco IOS XE Software, Version 17.15.05"],
        version_hint: "17.15.05"
      },
      "show vlan brief": {
        captured: true,
        command: "show vlan brief",
        returncode: 0,
        stdout_summary: [
          "VLAN Name                             Status    Ports",
          "1    default                          active    Gi1/0/7",
          "10   LAB-MGMT-10                      active    Gi1/0/1, Gi1/0/2, Gi1/0/3",
          "20   ESXI-HOSTS                       active    Gi1/0/5",
          "30   STORAGE-NFS                      active",
          "999  BLACKHOLE-PARKING                active"
        ]
      },
      "show interfaces status": {
        captured: true,
        command: "show interfaces status",
        returncode: 0,
        stdout_summary: [
          "Port      Name               Status       Vlan       Duplex  Speed Type",
          "Gi1/0/1   app-host           connected    10         a-full  a-1000 10/100/1000BaseTX",
          "Gi1/0/2   ilo                connected    10         a-full  a-1000 10/100/1000BaseTX",
          "Gi1/0/3   esxi-uplink-a      connected    10         a-full  a-1000 10/100/1000BaseTX",
          "Gi1/0/4   esxi-uplink-b      connected    trunk      a-full  a-1000 10/100/1000BaseTX",
          "Gi1/0/5   netapp-a           connected    20         a-full  a-1000 10/100/1000BaseTX",
          "Gi1/0/6   netapp-b           connected    30         a-full  a-1000 10/100/1000BaseTX",
          "Gi1/0/7   unknown            connected    1          a-full  a-1000 10/100/1000BaseTX",
          "Gi1/0/8                      notconnect   999        auto    auto   10/100/1000BaseTX"
        ]
      }
    },
    fallback: "paramiko",
    message: "Read-only Cisco SSH probe completed through Paramiko fallback.",
    not_attempted: ["configure terminal", "write memory", "reload", "VLAN, interface, user, or firmware changes"],
    provider_id: "cisco-ansible",
    safe_show_commands: ["show version", "show interfaces status", "show vlan brief"],
    status: "ok",
    warnings: []
  };
}

function ciscoCurrentIntentDiff() {
  return {
    action: "cisco-current-intent-diff",
    blockers: [],
    candidate_config_preview: {
      commands: ["vlan 999", " name BLACKHOLE-PARKING", " exit"],
      not_attempted: ["configuration mode execution", "write memory", "reload", "VLAN deletion"],
      notes: ["Unexpected VLANs are not removed by the candidate preview."],
      requires_operator_review: true,
      status: "ready",
      summary: "3 candidate command lines generated from parsed drift."
    },
    checked_at: checkedAt,
    current: {
      ports: [
        { port: "Gi1/0/1", status: "connected", vlan: "10" },
        { port: "Gi1/0/2", status: "connected", vlan: "10" },
        { port: "Gi1/0/3", status: "connected", vlan: "10" },
        { port: "Gi1/0/4", status: "connected", vlan: "trunk" },
        { port: "Gi1/0/5", status: "connected", vlan: "20" },
        { port: "Gi1/0/6", status: "connected", vlan: "30" },
        { port: "Gi1/0/7", status: "connected", vlan: "1" },
        { port: "Gi1/0/8", status: "notconnect", vlan: "999" }
      ],
      vlans: [
        { id: "1", name: "default", status: "active" },
        { id: "10", name: "LAB-MGMT-10", status: "active" },
        { id: "20", name: "ESXI-HOSTS", status: "active" },
        { id: "30", name: "STORAGE-NFS", status: "active" }
      ]
    },
    diff: {
      drift_count: 3,
      guardrails: {
        acl_lanes: {
          matched: ["MGMT-IN"],
          missing: ["STORAGE-NFS-IN", "DROP-ALL"],
          reason: "One or more intended ACL lanes were not found in read-only include output.",
          status: "warning"
        },
        blackhole_vlan: {
          matched: [],
          missing: ["999"],
          reason: "Black-hole parking VLAN is missing.",
          status: "warning"
        },
        bpdu_guard: {
          matched: ["spanning-tree portfast bpduguard default"],
          missing: [],
          reason: "BPDU guard was found in read-only include output.",
          status: "ready"
        }
      },
      ports: [
        {
          current: { port: "Gi1/0/3", status: "connected", vlan: "10" },
          port: "Gi1/0/3",
          reason: "Expected trunk, saw VLAN 10.",
          status: "drift"
        }
      ],
      vlans: {
        missing: ["999"],
        unexpected: []
      }
    },
    freshness: "current",
    message: "Cisco current-to-intent diff completed with live read-only evidence.",
    next_safe_action: "Review VLAN/interface/guardrail drift before guarded config apply.",
    provider_id: "cisco-ansible",
    remediation_plan: {
      command_count: 3,
      safe_to_render_commands: true,
      status: "warning",
      summary: "3 remediation area(s) need review; 3 candidate command line(s) are renderable.",
      steps: [
        {
          detail: "999",
          label: "Create missing VLANs",
          next_action: "Review generated VLAN commands before any guarded apply.",
          status: "warning"
        },
        {
          detail: "1 port drift item(s).",
          label: "Align intended ports",
          next_action: "Review access/trunk mode changes against the physical cabling plan.",
          status: "warning"
        },
        {
          detail: "acl_lanes: STORAGE-NFS-IN, acl_lanes: DROP-ALL, blackhole_vlan: 999",
          label: "Review guardrails",
          next_action: "Treat ACL lanes as review-only until exact source/destination policy is approved.",
          status: "warning"
        },
        {
          detail: "No unexpected VLANs were parsed.",
          label: "Preserve unexpected VLANs",
          next_action: "Do not delete unexpected VLANs from this preview; investigate ownership first.",
          status: "ready"
        }
      ]
    },
    source_type: "live_probe",
    status: "warning",
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

function hpeStorageDiscovery() {
  const driveLink = (index: number) => ({
    "@odata.id": `/redfish/v1/Chassis/DE009000/Drives/${index}`
  });
  return {
    blockers: [],
    controllers: [{ display_label: "Smart Array P408i-a", model: "HPE Smart Array P408i-a SR Gen10" }],
    last_probe_time: checkedAt,
    logical_drives: [
      {
        display_label: "ESXi OS",
        raid_level: "RAID1",
        Links: { Drives: [driveLink(0), driveLink(1)] }
      },
      {
        display_label: "VM datastore",
        raid_level: "RAID5",
        Links: { Drives: [driveLink(2), driveLink(3), driveLink(4), driveLink(5), driveLink(7)] }
      }
    ],
    next_safe_action: "Review discovered drives and save a plan-only RAID intent.",
    physical_drives: Array.from({ length: 8 }, (_, index) => {
      const bay = String(index + 1);
      return {
        "@odata.id": driveLink(index)["@odata.id"],
        Status: { Health: "OK", State: index === 6 ? "StandbySpare" : "Enabled" },
        bay_id: bay,
        capacity_label: "1.92 TB",
        display_label: `Bay ${bay}`,
        health: "OK",
        media_type: "SSD"
      };
    }),
    provider_id: "ilo-redfish",
    server: { model: "DL360 Gen10" },
    source: "cached iLO Redfish probe",
    storage_inventory_available: true,
    warnings: []
  };
}

function hpeVsanReadiness() {
  return {
    apply_enabled: false,
    blockers: [],
    controller: {
      apply_enabled: false,
      current_operating_mode: "Mixed",
      firmware: "1.66",
      mode_meaning: "Mixed: drives outside RAID volumes pass through raw",
      model: "HPE Smart Array P408i-a SR Gen10"
    },
    drives: Array.from({ length: 8 }, (_, index) => ({
      apply_enabled: false,
      bay_id: String(index + 1),
      capacity_bytes: 1_920_000_000_000,
      capacity_label: "1.92 TB",
      health: "OK",
      media_type: "SSD",
      volume_name: index < 2 ? "ESXi OS" : null,
      vsan_status: index < 2 ? "in_raid_volume" : "passthrough_ready"
    })),
    last_probe_time: checkedAt,
    next_safe_action: "Review architecture readiness.",
    options: [
      { apply_enabled: false, detail: "Keep candidate drives outside logical volumes. Destructive deletion is guarded and unavailable.", id: "stay_mixed", title: "Stay in Mixed mode" },
      { apply_enabled: false, detail: "Controller-wide destructive switch and reboot; guarded and unavailable.", id: "switch_hba", title: "Switch the controller to HBA mode" },
      { apply_enabled: false, detail: "Architecture readiness is not certification; verify ESXi, driver, and firmware in the VMware Compatibility Guide.", id: "vmware_compatibility", title: "Verify VMware compatibility" }
    ],
    provider_id: "ilo-redfish",
    source: "cached iLO Redfish probe",
    storage_inventory_available: true,
    summary: { passthrough_ready_capacity_bytes: 11_520_000_000_000, passthrough_ready_count: 6, physical_drive_count: 8 }
  };
}

function labCredentials() {
  const group = (
    id: string,
    label: string,
    hint: string,
    fields: Array<{ configured: boolean; env_var: string; field: string; is_secret: boolean; value: string | null }>
  ) => ({
    configured: fields.every((field) => field.configured),
    fields,
    hint,
    id,
    label
  });
  const field = (
    name: string,
    envVar: string,
    value: string | null,
    isSecret = false
  ) => ({
    configured: isSecret || Boolean(value),
    env_var: envVar,
    field: name,
    is_secret: isSecret,
    value
  });
  return {
    groups: [
      group("cisco", "Cisco switch", "Credentials used for switch access.", [
        field("cisco_username", "ANSIBLE_CISCO_USER", "administrator"),
        field("cisco_password", "ANSIBLE_CISCO_PASSWORD", null, true),
        field("cisco_enable_password", "ANSIBLE_CISCO_ENABLE_PASSWORD", null, true)
      ]),
      group("ilo", "HPE iLO", "Credentials used for iLO first contact.", [
        field("ilo_host", "ILO_TEST_HOST", "192.168.1.201"),
        field("ilo_username", "ILO_TEST_USERNAME", "Administrator"),
        field("ilo_password", "ILO_TEST_PASSWORD", null, true)
      ]),
      group("esxi", "ESXi", "Credentials used for direct ESXi access.", [
        field("esxi_host", "ESXI_TEST_HOST", "192.168.1.203"),
        field("esxi_username", "ESXI_TEST_USERNAME", "root"),
        field("esxi_password", "ESXI_TEST_PASSWORD", null, true)
      ]),
      group("netapp", "NetApp ONTAP", "Credentials used for ONTAP access.", [
        field("netapp_username", "NETAPP_TEST_USERNAME", "admin"),
        field("netapp_password", "NETAPP_TEST_PASSWORD", null, true)
      ]),
      group("vcenter", "vCenter", "Credentials used for vCenter access.", [
        field("vcenter_username", "VCENTER_TEST_USERNAME", "administrator@vsphere.local"),
        field("vcenter_password", "VCENTER_TEST_PASSWORD", null, true)
      ])
    ],
    next_safe_action: "Use the device drawer to save sign-in values.",
    restart_required: false,
    store_path: ".env.local.real-lab"
  };
}

function iloSetupIntentFixture(overrides: Record<string, unknown> = {}) {
  return {
    provider_id: "ilo-redfish",
    apply_enabled: false,
    created_at: null,
    updated_at: null,
    network: {
      dhcp_enabled: null,
      hostname: null,
      management_ip: null,
      subnet_mask_or_prefix: null,
      gateway: null,
      vlan: null
    },
    users: [],
    license: { advanced_license_key_ref: null, expected_status: null },
    snmp: {
      enabled: false,
      version: "v3",
      system_location: null,
      system_contact: null,
      system_role: null,
      destinations: [],
      community_or_user_ref_labels: [],
      snmpv3_security_name: null,
      snmpv3_auth_protocol: "MD5",
      snmpv3_auth_passphrase_ref: null,
      snmpv3_privacy_protocol: "DES",
      snmpv3_privacy_passphrase_ref: null
    },
    ipv6: {
      disable_all: true,
      disable_dhcpv6_dns_server: true,
      disable_dhcpv6_domain_name: true,
      disable_dhcpv6_sntp_settings: true,
      disable_dhcpv6_stateful_mode: true,
      disable_dhcpv6_stateless_mode: true
    },
    time: {
      use_dhcp_supplied_time_settings: null,
      timezone: null,
      ntp_servers: [],
      interface_type: null
    },
    dns_domain: { domain_name: null, dns_servers: [] },
    notes: null,
    ...overrides
  };
}

function iloDiscoveredSettingsFixture(overrides: Record<string, unknown> = {}) {
  return {
    provider_id: "ilo-redfish",
    source: "cached read-only iLO probe",
    probe_time: checkedAt,
    available: true,
    network: {
      dhcp_enabled: false,
      hostname: "DOP-X87-iLOSrv4",
      management_ip: "192.168.1.201",
      subnet_mask_or_prefix: "255.255.255.0",
      gateway: "192.168.1.1",
      vlan: null
    },
    dns_domain: { domain_name: "lab.example", dns_servers: ["8.8.8.8", "2.2.2.2"] },
    time: { timezone: null, ntp_servers: [], ntp_protocol_enabled: null },
    license: { status: null, name: null },
    snmp: { enabled: true },
    users: [
      { username: "Administrator", role: "Administrator", enabled: true },
      { username: "X59_OA", role: "Operator", enabled: true }
    ],
    ...overrides
  };
}

test("iLO settings prefill from device values when nothing is saved yet", async ({ page }) => {
  await page.route("**/api/v1/providers/ilo-redfish/setup-intent", (route) =>
    json(route, iloSetupIntentFixture())
  );
  await page.route("**/api/v1/providers/ilo-redfish/discovered-settings", (route) =>
    json(route, iloDiscoveredSettingsFixture())
  );

  await page.goto("/overview");
  await page.getByRole("region", { name: "Lab topology" }).getByRole("button", { name: /^HPE iLO,/ }).click();

  const settings = page.locator("section[aria-label='iLO setup settings']");
  await expect(settings).toBeVisible();
  await expect(settings).toContainText("Pre-filled with values read from the device");
  await expect(settings.getByLabel("DNS Name")).toHaveValue("DOP-X87-iLOSrv4");
  await expect(settings.getByLabel("Subnet Mask / Prefix")).toHaveValue("255.255.255.0");
  await expect(settings.getByLabel("Gateway")).toHaveValue("192.168.1.1");
  await expect(settings.getByLabel("DNS Servers")).toHaveValue("8.8.8.8, 2.2.2.2");
  await expect(settings.locator(".from-device-hint").first()).toBeVisible();
  await expect(settings.getByRole("checkbox", { name: /SNMP enabled/ })).toBeChecked();
  await expect(settings.getByLabel("Username Label").first()).toHaveValue("Administrator");
});

test("saved iLO settings win over discovered device values", async ({ page }) => {
  await page.route("**/api/v1/providers/ilo-redfish/setup-intent", (route) =>
    json(route, iloSetupIntentFixture({
      created_at: checkedAt,
      updated_at: checkedAt,
      network: {
        dhcp_enabled: true,
        hostname: "operator-chosen-name",
        management_ip: null,
        subnet_mask_or_prefix: null,
        gateway: null,
        vlan: null
      }
    }))
  );
  await page.route("**/api/v1/providers/ilo-redfish/discovered-settings", (route) =>
    json(route, iloDiscoveredSettingsFixture())
  );

  await page.goto("/overview");
  await page.getByRole("region", { name: "Lab topology" }).getByRole("button", { name: /^HPE iLO,/ }).click();

  const settings = page.locator("section[aria-label='iLO setup settings']");
  const dnsName = settings.getByLabel("DNS Name");
  await expect(dnsName).toHaveValue("operator-chosen-name");
  // The operator's saved value differs from the device value, so no
  // "from device" hint may appear on that field.
  await expect(
    settings.locator("label.field", { hasText: "DNS Name" }).locator(".from-device-hint")
  ).toHaveCount(0);
  // SNMP: saved intent exists, so its false wins over the device's true.
  await expect(settings.getByRole("checkbox", { name: /SNMP enabled/ })).not.toBeChecked();
  // A saved record wins completely: deliberately-empty DNS servers and users
  // must not be refilled from the device.
  await expect(settings.getByLabel("DNS Servers")).toHaveValue("");
  await expect(settings).toContainText("No local user references saved.");
});

test("editing a prefilled iLO setting saves the operator's value through the unchanged intent path", async ({ page }) => {
  let savedIntentBody: Record<string, unknown> | null = null;
  await page.route("**/api/v1/providers/ilo-redfish/setup-intent", (route) => {
    if (route.request().method() === "PUT") {
      savedIntentBody = route.request().postDataJSON() as Record<string, unknown>;
      return json(route, iloSetupIntentFixture({
        created_at: checkedAt,
        updated_at: checkedAt,
        ...savedIntentBody
      }));
    }
    return json(route, iloSetupIntentFixture());
  });
  await page.route("**/api/v1/providers/ilo-redfish/discovered-settings", (route) =>
    json(route, iloDiscoveredSettingsFixture())
  );

  await page.goto("/overview");
  await page.getByRole("region", { name: "Lab topology" }).getByRole("button", { name: /^HPE iLO,/ }).click();

  const settings = page.locator("section[aria-label='iLO setup settings']");
  const dnsName = settings.getByLabel("DNS Name");
  await expect(dnsName).toHaveValue("DOP-X87-iLOSrv4");
  await dnsName.fill("renamed-by-operator");
  await settings.getByRole("button", { name: "Save iLO setup plan" }).click();

  await expect(settings).toContainText("Saved iLO settings locally. Hardware untouched.");
  expect(savedIntentBody).not.toBeNull();
  const network = (savedIntentBody as Record<string, unknown>).network as Record<string, unknown>;
  expect(network.hostname).toBe("renamed-by-operator");
  // Untouched prefilled values ride along as the operator's accepted values.
  expect(network.gateway).toBe("192.168.1.1");
});

test("clicking a device before the inventory loads still opens its drawer and survives the swap", async ({ page }) => {
  // Hold the inventory response so the map renders profile-derived fallback
  // nodes first — the state an operator clicks into on a slow backend.
  await page.route("**/api/v1/device-inventory", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await new Promise((resolve) => setTimeout(resolve, 2500));
    return json(route, [
      inventoryDevice("f2c1a9d0-4b31-4a5e-9d10-00000000000a", "ilo", "HPE iLO", "192.168.1.201")
    ]);
  });

  await page.goto("/overview");
  const topology = page.getByRole("region", { name: "Lab topology" });
  await topology.getByRole("button", { name: /^HPE iLO,/ }).click();

  // Drawer opens immediately from the fallback node...
  const drawer = page.getByLabel("HPE iLO setup");
  await expect(drawer).toBeVisible();

  // ...and stays open once the UUID inventory nodes replace the fallback,
  // now carrying the inventory actions.
  await expect(drawer.getByRole("button", { name: "Edit inventory details" })).toBeVisible({ timeout: 10_000 });
});

test("iLO DHCP mode shows discovered addresses and saves no static address intent", async ({ page }) => {
  let savedIntentBody: Record<string, unknown> | null = null;
  await page.route("**/api/v1/providers/ilo-redfish/setup-intent", (route) => {
    if (route.request().method() === "PUT") {
      savedIntentBody = route.request().postDataJSON() as Record<string, unknown>;
      return json(route, iloSetupIntentFixture({
        created_at: checkedAt,
        updated_at: checkedAt,
        ...savedIntentBody
      }));
    }
    return json(route, iloSetupIntentFixture());
  });
  await page.route("**/api/v1/providers/ilo-redfish/discovered-settings", (route) =>
    json(route, iloDiscoveredSettingsFixture())
  );

  await page.goto("/overview");
  await page.getByRole("region", { name: "Lab topology" }).getByRole("button", { name: /^HPE iLO,/ }).click();

  const settings = page.locator("section[aria-label='iLO setup settings']");
  // "DHCP" is a substring of several field labels (Use DHCP Time, the DHCPv6
  // toggles) — anchor on the exact field span instead.
  const dhcp = settings
    .locator("label.field")
    .filter({ has: page.getByText("DHCP", { exact: true }) })
    .locator("select");
  const managementIp = settings.getByLabel("Management IP");
  const subnet = settings.getByLabel("Subnet Mask / Prefix");
  const gateway = settings.getByLabel("Gateway");

  await managementIp.fill("198.51.100.20");
  await subnet.fill("255.255.0.0");
  await gateway.fill("198.51.100.1");
  await dhcp.selectOption("true");

  await expect(managementIp).toBeDisabled();
  await expect(subnet).toBeDisabled();
  await expect(gateway).toBeDisabled();
  await expect(managementIp).toHaveValue("192.168.1.201");
  await expect(subnet).toHaveValue("255.255.255.0");
  await expect(gateway).toHaveValue("192.168.1.1");
  await expect(settings.getByLabel("DNS Name")).toBeEnabled();

  await dhcp.selectOption("false");
  await expect(managementIp).toBeEnabled();
  await expect(managementIp).toHaveValue("198.51.100.20");
  await expect(subnet).toHaveValue("255.255.0.0");
  await expect(gateway).toHaveValue("198.51.100.1");

  await dhcp.selectOption("true");
  await settings.getByRole("button", { name: "Save iLO setup plan" }).click();
  await expect(settings).toContainText("Saved iLO settings locally. Hardware untouched.");

  const network = (savedIntentBody as Record<string, unknown>).network as Record<string, unknown>;
  expect(network.dhcp_enabled).toBe(true);
  expect(network.management_ip).toBeNull();
  expect(network.subnet_mask_or_prefix).toBeNull();
  expect(network.gateway).toBeNull();
});

test("local RAID draft starts from the live discovered layout instead of the canned template", async ({ page }) => {
  await page.goto("/overview");
  await page.getByRole("region", { name: "Lab topology" })
    .getByRole("button", { name: "Local storage offshoot from HPE iLO" }).click();

  const planner = page.locator("section[aria-label='Local RAID planner']");
  await expect(planner).toContainText("No iLO drive inventory yet.");
  await planner.getByRole("button", { name: /Read storage from iLO/ }).click();

  await expect(planner).toContainText("draft starts from the last device-read layout");
  // Fixture live layout: RAID1 volume on bays 1-2, RAID5 volume on bays
  // 3-6+8, bay 7 is a standby spare. The canned template would have made
  // bay 7 "Data" and defaulted the datastore group to RAID6.
  const bay = (id: string) => planner.locator("button.local-raid-bay").filter({ hasText: `Bay ${id}` });
  await expect(bay("1")).toHaveClass(/is-boot/);
  await expect(bay("2")).toHaveClass(/is-boot/);
  await expect(bay("3")).toHaveClass(/is-datastore/);
  await expect(bay("7")).toHaveClass(/is-spare/);
  await expect(bay("8")).toHaveClass(/is-datastore/);
  await expect(bay("3")).toContainText("Live: VM datastore · RAID5");
  await expect(planner.getByLabel(/RAID level for (Datastore|Staging) array/)).toHaveValue("RAID5");
});

test("local storage drawer renders cross-view vSAN readiness by paired physical bay", async ({ page }) => {
  await page.goto("/overview");
  await page.getByRole("region", { name: "Lab topology" })
    .getByRole("button", { name: "Local storage offshoot from HPE iLO" }).click();
  const planner = page.locator("section[aria-label='Local RAID planner']");
  await planner.getByRole("button", { name: /Read storage from iLO/ }).click();
  const vsan = planner.getByRole("region", { name: "vSAN readiness" });
  await expect(vsan).toContainText("Mixed: drives outside RAID volumes pass through raw");
  await expect(vsan).toContainText("6 drives / 10.48 TiB passthrough-ready for vSAN");
  await expect(vsan.locator(".vsan-drive").filter({ hasText: "Bay 1" })).toContainText("In Raid Volume");
  await expect(vsan.locator(".vsan-drive").filter({ hasText: "Bay 3" })).toContainText("Passthrough Ready");
  await expect(vsan.getByRole("button")).toHaveCount(0);
});

test("local RAID draft refuses the live seed when volume members cannot be paired to bays", async ({ page }) => {
  const mismatched = hpeStorageDiscovery() as Record<string, unknown>;
  // Volume member resources point at a different Redfish view than the
  // physical drives (the real cross-view failure seen on a DL380), so no
  // member can be paired to a bay.
  mismatched.logical_drives = (mismatched.logical_drives as Array<Record<string, unknown>>).map(
    (volume, index) => ({
      ...volume,
      Links: {
        Drives: [{ "@odata.id": `/redfish/v1/Systems/1/Storage/DE07B000/Drives/${index}` }]
      }
    })
  );
  await page.route("**/api/v1/providers/ilo-redfish/hpe-storage-discovery", (route) =>
    json(route, mismatched)
  );

  await page.goto("/overview");
  await page.getByRole("region", { name: "Lab topology" })
    .getByRole("button", { name: "Local storage offshoot from HPE iLO" }).click();

  const planner = page.locator("section[aria-label='Local RAID planner']");
  await planner.getByRole("button", { name: /Read storage from iLO/ }).click();

  // Bays render from inventory, but the seed is refused: no device-read
  // claim, and the draft stays on the canned template (bay 7 is not spare).
  await expect(planner.locator("button.local-raid-bay").first()).toBeVisible();
  await expect(planner).not.toContainText("draft starts from the last device-read layout");
  await expect(
    planner.locator("button.local-raid-bay").filter({ hasText: "Bay 7" })
  ).not.toHaveClass(/is-spare/);
});

test("local RAID live seed pairs DL380 cross-view members through hardware fingerprints", async ({ page }) => {
  const crossView = hpeStorageDiscovery() as Record<string, unknown>;
  const physical = crossView.physical_drives as Array<Record<string, unknown>>;
  physical.forEach((drive, index) => {
    drive.hardware_identity_fingerprint_sha256 = String(index + 1).padStart(64, "0");
  });
  crossView.logical_drives = (crossView.logical_drives as Array<Record<string, unknown>>).map((volume) => ({
    ...volume,
    Links: {
      Drives: ((volume.Links as { Drives: Array<Record<string, unknown>> }).Drives).map((_, memberIndex) => {
        const offset = String(volume.display_label).includes("ESXi") ? 0 : 2;
        const driveIndex = offset + memberIndex;
        return {
          "@odata.id": `/redfish/v1/Systems/1/Storage/DE07B000/Drives/${driveIndex}`,
          hardware_identity_fingerprint_sha256: String(driveIndex + 1).padStart(64, "0")
        };
      })
    }
  }));
  await page.route("**/api/v1/providers/ilo-redfish/hpe-storage-discovery", (route) => json(route, crossView));
  await page.goto("/overview");
  await page.getByRole("region", { name: "Lab topology" })
    .getByRole("button", { name: "Local storage offshoot from HPE iLO" }).click();
  const planner = page.locator("section[aria-label='Local RAID planner']");
  await planner.getByRole("button", { name: /Read storage from iLO/ }).click();
  await expect(planner).toContainText("draft starts from the last device-read layout");
  await expect(planner.locator("button.local-raid-bay").filter({ hasText: "Bay 1" }).first()).toHaveClass(/is-boot/);
  await expect(planner.locator("button.local-raid-bay").filter({ hasText: "Bay 3" }).first()).toHaveClass(/is-datastore/);
});

function iloAccessSettings(overrides: Record<string, unknown> = {}) {
  return {
    env_path: ".env.local.real-lab",
    fallback_hosts: ["192.168.1.201"],
    host: "192.168.1.201",
    host_source: "active_lab_profile",
    last_probe_message: "Read-only Redfish probe completed.",
    last_probe_freshness: "current",
    last_probe_is_current: true,
    last_probe_status: "ok",
    last_probe_target_fingerprint_present: true,
    last_probe_target_matches_access_host: true,
    last_probe_target_matches_configured_candidates: true,
    last_probe_target_source: "active_lab_profile",
    last_probe_time: checkedAt,
    next_safe_action: "Run iLO Inventory Read to refresh live iLO reachability and storage inventory.",
    password_configured: true,
    provider_id: "ilo-redfish",
    updated_at: null,
    username: "Administrator",
    username_configured: true,
    verify_tls: false,
    ...overrides
  };
}

function hpeRaidPending() {
  return {
    blockers: [],
    checked_at: checkedAt,
    message: "No pending RAID changes.",
    next_safe_action: "Preview RAID before any guarded apply or reset.",
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

function netappLiveState() {
  const nfsChecks = ["192.168.1.230", "192.168.1.231"].map((address) => ({ address, port: 2049, reachable: true }));
  const iscsiChecks = ["192.168.1.240", "192.168.1.241", "192.168.1.242", "192.168.1.243"].map((address) => ({ address, port: 3260, reachable: true }));
  return {
    blockers: [],
    checked_at: checkedAt,
    message: "NetApp live state is ready for NFS and protocol-ready for iSCSI.",
    provider_id: "netapp-ontap",
    runtime_state: {
      api: { access_values_present: true },
      console: {
        baud: 115200,
        prompt_label: "NetApp login prompt",
        prompt_state: "login_required",
        selected_path: "COM4"
      },
      management: {
        cluster_mgmt_ip: "192.168.1.220",
        rest_443_reachable: true,
        ssh_22_reachable: true
      },
      protocol_options: {
        iscsi: {
          active: false,
          blockers: ["iSCSI LUN, igroup, and datastore mount are not yet part of the guarded setup path."],
          checks: iscsiChecks,
          label: "iSCSI",
          lifs: ["192.168.1.240", "192.168.1.241", "192.168.1.242", "192.168.1.243"],
          port: 3260,
          reachable_lif_count: 4,
          ready: false,
          service_status: "ready"
        },
        nfs: {
          active: true,
          blockers: [],
          checks: nfsChecks,
          label: "NFS",
          lifs: ["192.168.1.230", "192.168.1.231"],
          port: 2049,
          reachable_lif_count: 2,
          ready: true,
          service_status: "ready"
        }
      },
      storage: {
        blockers: [],
        checks: { nfs_lifs_2049: nfsChecks },
        nfs_lifs_detected: ["192.168.1.230", "192.168.1.231"],
        protocol: "nfs",
        ready: true,
        service_enabled: true,
        service_status: "ready"
      }
    },
    status: "ready",
    warnings: []
  };
}

function netappIscsiSetupPreview() {
  return {
    action: "iscsi-setup-preview",
    apply_enabled: false,
    blockers: [],
    checked_at: checkedAt,
    iscsi_plan: {
      datastore_name: "netapp_iscsi_ds01",
      igroup_name: "esxi_hosts",
      initiator_iqns: ["iqn.1998-01.com.vmware:host-a"],
      iscsi_lifs: ["192.168.1.240", "192.168.1.241", "192.168.1.242", "192.168.1.243"],
      lun_name: "esxi_lun_01",
      lun_size: "1TB"
    },
    message: "NetApp iSCSI setup preview generated. No LUN, igroup, ESXi, or datastore write action was run.",
    not_attempted: ["ONTAP REST write", "iSCSI LUN, igroup, initiator, and VMFS datastore creation"],
    protocol_readiness: {
      lifs: ["192.168.1.240", "192.168.1.241", "192.168.1.242", "192.168.1.243"],
      ready: true,
      reachable_lif_count: 4,
      service_status: "ready"
    },
    provider_id: "netapp-ontap",
    required_flags: [
      "PROVIDER_MODE=local-lab-readwrite",
      "NETAPP_ISCSI_SETUP_APPLY=true",
      'NETAPP_ISCSI_SETUP_CONFIRM="APPLY NETAPP ISCSI SETUP"',
      "NETAPP_ISCSI_SETUP_ALLOW_STORAGE_CREATE=true"
    ],
    status: "preview_only",
    warnings: ["Guarded iSCSI create-and-mount workflow is not implemented yet."]
  };
}

function netappIscsiSetupValidation() {
  return {
    ...netappIscsiSetupPreview(),
    action: "iscsi-setup-validation",
    blockers: [
      "NetApp iSCSI LUN is missing.",
      "NetApp iSCSI igroup is missing.",
      "NetApp iSCSI LUN map is missing."
    ],
    message: "NetApp iSCSI setup validation completed with read-only protocol and inventory checks.",
    status: "blocked"
  };
}

function netappIscsiSetupApplyBlocked() {
  return {
    ...netappIscsiSetupPreview(),
    action: "iscsi-setup-apply",
    apply: {
      esxi_writes_attempted: false,
      ontap_writes_attempted: false,
      transcript_summary: ["Apply gates blocked before ONTAP REST write session started."],
      vcenter_writes_attempted: false
    },
    blockers: [
      "NETAPP_ISCSI_SETUP_APPLY=true is required.",
      'NETAPP_ISCSI_SETUP_CONFIRM="APPLY NETAPP ISCSI SETUP" is required.',
      "NETAPP_ISCSI_SETUP_ALLOW_STORAGE_CREATE=true is required."
    ],
    flag_state: {
      local_lab_readwrite: true,
      netapp_iscsi_setup_allow_storage_create: false,
      netapp_iscsi_setup_apply: false,
      netapp_iscsi_setup_confirm: false,
      provider_mode: "local-lab-readwrite"
    },
    message: "NetApp iSCSI setup apply was refused before any ONTAP write command.",
    status: "blocked"
  };
}

function esxiIscsiDatastorePreview() {
  return {
    action: "esxi-iscsi-datastore-preview",
    apply_enabled: false,
    blockers: [],
    checked_at: checkedAt,
    current_state: {
      adapter_count: 1,
      adapters: ["vmhba64"],
      datastore: {
        mounted: true,
        name: "netapp_iscsi_ds01",
        type: "VMFS-6"
      },
      datastore_visible: true,
      iscsi_path_count: 1,
      iscsi_paths: [{ adapter: "vmhba64", target: "iqn.1992-08.com.netapp:sn.test" }],
      target_iqn_seen: true
    },
    iscsi_plan: {
      datastore_name: "netapp_iscsi_ds01",
      target_iqn: "iqn.1992-08.com.netapp:sn.test"
    },
    message: "ESXi iSCSI datastore preview completed with read-only ESXi checks.",
    not_attempted: ["VMFS format", "datastore create or mount"],
    provider_id: "esxi-readonly",
    remediation_plan: {
      status: "ready",
      summary: "ESXi iSCSI path is ready; keep create/mount work behind the guarded apply lane.",
      read_only: true,
      apply_not_attempted: ["target portal add", "iSCSI login", "adapter rescan", "VMFS create or mount"],
      steps: [
        {
          label: "Confirm ONTAP SAN objects",
          status: "ready",
          detail: "Target IQN iqn.1992-08.com.netapp:sn.test with LUN esxi_lun_01.",
          next_action: "Validate NetApp iSCSI until target IQN, LUN, igroup, and LUN map are present."
        },
        {
          label: "Establish active iSCSI session",
          status: "ready",
          detail: "1 active path(s); target IQN seen: true.",
          next_action: "Add the NetApp target portal, rescan the iSCSI adapter, and confirm an active session to the target IQN."
        },
        {
          label: "Confirm VMFS datastore visibility",
          status: "ready",
          detail: "Datastore netapp_iscsi_ds01 is visible.",
          next_action: "After the LUN is visible, run the guarded datastore create or mount lane and revalidate VMFS visibility."
        }
      ]
    },
    status: "preview_ready",
    warnings: ["Read-only only. No ESXi iSCSI login, target add, adapter rescan, VMFS creation, datastore mount, or vCenter registration was attempted."]
  };
}

function esxiIscsiDatastoreValidation() {
  return {
    ...esxiIscsiDatastorePreview(),
    action: "esxi-iscsi-datastore-validation",
    message: "ESXi iSCSI datastore validation completed with read-only ESXi checks.",
    status: "ready"
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

function labValidationNotChecked() {
  const validation = labValidation();
  validation.freshness = "not_checked";
  validation.handoff_report = "";
  validation.next_action = "Run validation to see whether this kit is ready.";
  validation.overall_status = "not_checked";
  validation.progress_counts = { blocked: 0, not_configured: 0, partial: 0, ready: 0 };
  validation.proof_links = [];
  validation.source_type = "not_checked";
  validation.top_blocker = null;
  validation.validation_items = validation.validation_items.map((item) => ({
    ...item,
    current_state: "Not checked",
    evidence_artifacts: [],
    freshness: "not_checked",
    last_checked: null,
    next_action: "Run validation.",
    proof_points: [],
    setup_summary: "Not checked yet.",
    source_type: "not_checked",
    status: "not_checked",
    warnings: []
  }));
  return validation;
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

function firmwareFileSelectionState(selected_files: Record<string, string>) {
  return {
    apply_enabled: false,
    blockers: [],
    checked_at: checkedAt,
    freshness: "live",
    message: Object.keys(selected_files).length ? "Firmware file selections are saved in local runtime state." : "No firmware file selections are saved yet.",
    next_safe_action: "Validate the upgrade path before any firmware apply workflow.",
    provider_id: "firmware-file-selections",
    selected_files,
    source_type: "operator_config",
    status: Object.keys(selected_files).length ? "ready" : "not_configured_yet",
    store_path: ".local/firmware-file-selections.json",
    updated_at: checkedAt,
    warnings: []
  };
}

function mediaInventory() {
  return {
    configured_directories: ["/home/administrator/infra-config-portal/artifacts/Media"],
    configured_directory_paths: ["/home/administrator/infra-config-portal/artifacts/Media"],
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
      netapp_iscsi_lifs: ["192.168.1.240", "192.168.1.241", "192.168.1.242", "192.168.1.243"],
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
        iscsi_lifs: ["192.168.1.240", "192.168.1.241", "192.168.1.242", "192.168.1.243"],
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
      deployment_label: "Server + NetApp + vCenter",
      deployment_mode: "server_netapp_vcenter",
      deployment_supported: true,
      netapp_disabled_reason: null,
      netapp_enabled: true,
      storage_location: "netapp_shared",
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
      netapp_iscsi_lifs: ["192.168.1.240", "192.168.1.241", "192.168.1.242", "192.168.1.243"],
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

function singleServerLabProfiles() {
  const state = JSON.parse(JSON.stringify(labProfiles()));
  const profile = state.active_profile;
  profile.name = "Single Server Runtime Lab";
  profile.features = {
    ...profile.features,
    deployment_label: "Single server + local ESXi storage",
    deployment_mode: "single_server_local_storage",
    deployment_supported: true,
    netapp_disabled_reason: "Single-server profile uses server-local storage.",
    netapp_enabled: false,
    storage_location: "server_local",
    storage_protocol: "local",
    vcenter_disabled_reason: "Single-server profile does not require vCenter.",
    vcenter_enabled: false
  };
  profile.global_settings = {
    ...profile.global_settings,
    netapp_disabled_reason: "Single-server profile uses server-local storage.",
    netapp_enabled: false,
    vcenter_enabled: false
  };
  profile.devices = {
    ...profile.devices,
    netapp: null,
    vcenter: null
  };
  profile.not_in_scope_stages = ["netapp", "vcenter-netapp"];
  state.active_context.active_profile = profile;
  state.active_context.enabled_features = profile.features;
  state.active_context.not_in_scope_stages = profile.not_in_scope_stages;
  state.runtime_profile = profile;
  return state;
}

function noActiveLabProfiles() {
  const state = JSON.parse(JSON.stringify(labProfiles()));
  return {
    ...state,
    active_profile: null,
    active_context: {
      ...state.active_context,
      active_profile: null
    },
    profiles: [],
    runtime_profile: null
  };
}

function activeLabProfilesFixture() {
  if (labProfileScenario === "none") return noActiveLabProfiles();
  return labProfileScenario === "single" ? singleServerLabProfiles() : labProfiles();
}

function activeLabProfilesFromProfile(profile: Record<string, unknown>) {
  const state = JSON.parse(JSON.stringify(activeLabProfilesFixture()));
  const resolvedAddressPlan = profile.address_plan ?? profile.resolved_address_plan;
  const normalizedProfile = {
    ...profile,
    resolved_address_plan: resolvedAddressPlan
  };
  state.active_profile = normalizedProfile;
  state.active_context.active_profile = normalizedProfile;
  state.active_context.enabled_features = normalizedProfile.features;
  state.active_context.resolved_address_plan = resolvedAddressPlan;
  state.active_context.topology = normalizedProfile.profile_topology;
  state.runtime_profile = normalizedProfile;
  state.profiles = [normalizedProfile];
  return state;
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
