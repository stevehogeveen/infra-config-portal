import { expect, test, type Page, type Route } from "@playwright/test";

const checkedAt = "2026-06-09T21:00:00Z";
let labProfileScenario: "shared" | "single" = "shared";
let healthHostIpv4Addresses = ["192.168.1.99"];

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
  labProfileScenario = "shared";
  healthHostIpv4Addresses = ["192.168.1.99"];
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
    "Validation"
  ]);

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.goto("/lab-setup");
  await expect(page).toHaveURL(/\/overview/);
  await page.goto("/network");
  await expect(page.getByRole("heading", { name: "Network", exact: true })).toBeVisible();
  await page.goto("/server");
  await expect(page.getByRole("heading", { name: "Server", exact: true })).toBeVisible();
  await page.goto("/storage");
  await expect(page.getByRole("heading", { name: "Storage", exact: true })).toBeVisible();
  await page.goto("/virtualization");
  await expect(page.getByRole("heading", { name: "Virtualization", exact: true })).toBeVisible();
  await page.goto("/firmware-upgrades");
  await expect(page.getByRole("heading", { name: "Firmware Upgrades", exact: true })).toBeVisible();
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

test("overview shows active setup, lab values, and access without dashboard clutter", async ({ page }) => {
  await page.goto("/overview");

  const overview = page.locator("section[aria-label='Overview reference']");

  await expect(overview.getByRole("heading", { name: "Readiness at a glance" })).toBeVisible();
  await expect(overview).toContainText("Active blockers");
  await expect(overview).toContainText("Server ready");
  await expect(overview).toContainText("Firmware compliance");
  await expect(overview).toContainText("VM requests");
  await expect(overview).toContainText("Server + NetApp + vCenter");
  await expect(overview).toContainText("HPE iLO");
  await expect(overview).toContainText("Cisco Switch");
  await expect(overview).toContainText("NetApp ONTAP");
  await expect(overview).toContainText("Current State:");
  await expect(overview).toContainText("Target:");
  await expect(overview).toContainText("Gap:");
  await expect(overview).toContainText("Setup lanes");
  await expect(overview).toContainText("Server Access");
  await expect(overview).toContainText("RAID And Local Storage");
  await expect(overview).toContainText("Cisco Network");
  await expect(overview).toContainText("ONTAP Storage");
  await expect(overview).toContainText("vCenter And VM Handoff");
  await expect(overview.locator("details.setup-lane-details").first()).toContainText("Additional options");
  await expect(overview).toContainText("Next safe actions");
  await expect(overview).toContainText("Firmware Compliance");
  await expect(overview).toContainText("Active Blockers");
  await expect(overview).toContainText("192.168.1.204");
  await expect(overview).toContainText("192.168.1.201");
  await expect(overview).toContainText("192.168.1.220");
  await expect(page.locator("nav").getByText("Edit Config")).toHaveCount(0);
  await expect(page.locator("nav").getByText("Settings")).toHaveCount(0);
  await expect(page.getByText("Real lab").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Shared profile policy" })).toHaveCount(0);

  await expect(page.getByRole("heading", { name: "Lab Values" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Currently Accessible" })).toHaveCount(0);
  await expect(page.getByText(/what is healthy/i)).toHaveCount(0);
  await expect(page.getByText(/what is next/i)).toHaveCount(0);
  await expect(page.getByText("Artifact")).toHaveCount(0);
});

test("overview flags saved subnet mismatch and links to subnet editing", async ({ page }) => {
  healthHostIpv4Addresses = ["10.10.8.99", "172.20.10.3"];
  await page.goto("/overview");

  const topology = page.locator("section[aria-label='Living lab topology']");

  await expect(topology).toContainText("Subnet mismatch");
  await expect(topology).toContainText("Active setup targets 192.168.1.0/24");
  await expect(topology).toContainText("10.10.8.99");

  const updateSubnet = topology.getByRole("link", { name: "Update subnet" });
  await expect(updateSubnet).toHaveAttribute("href", "/network#network-profile");
  await updateSubnet.click();
  await expect(page).toHaveURL(/\/network#network-profile$/);
  await expect(page.locator("#network-profile")).toBeVisible();
});

test("overview design mode can stage the current host subnet as draft intent", async ({ page }) => {
  healthHostIpv4Addresses = ["10.10.8.99", "172.20.10.3"];
  await page.goto("/overview");

  await page.getByRole("button", { name: "Design" }).click();

  const composer = page.locator("div[aria-label='Design mode rack composer']");
  await expect(composer.getByLabel("Host network check")).toContainText("Subnet mismatch");
  await expect(composer.getByLabel("Host network check")).toContainText("10.10.8.99");
  await composer.getByRole("button", { name: "Stage host subnet" }).click();
  await expect(composer.getByLabel("Draft subnet")).toHaveValue("10.10.8.0/24");
  await expect(composer).toContainText("Host subnet 10.10.8.0/24 staged as a draft");
  await composer.getByRole("button", { name: "Rebase addresses" }).click();
  await expect(composer.getByLabel("Design address map")).toContainText("10.10.8.204");
});

test("overview design mode renders an intent-only rack composer", async ({ page }) => {
  await page.goto("/overview");

  await page.getByRole("button", { name: "Design" }).click();

  const composer = page.locator("div[aria-label='Design mode rack composer']");
  await expect(composer).toBeVisible();
  await expect(composer).toContainText("Parts shelf");
  await expect(composer).toContainText("Rack A");
  await expect(composer).toContainText("Cisco switch");
  await expect(composer).toContainText("DL360 Gen10");
  await expect(composer).toContainText("NetApp ONTAP");
  await expect(composer).toContainText("server_netapp_vcenter");
  await expect(composer).toContainText("Hardware untouched until guarded applies.");
  await expect(composer.getByLabel("Topology draft controls")).toContainText("Server + NetApp + vCenter");
  await expect(composer.getByLabel("Topology draft controls")).toContainText("Profile sync");
  await expect(composer.getByLabel("Topology draft controls")).toContainText("Cisco switch");
  await expect(composer.getByRole("button", { name: /Commit visual draft|Profile current/ })).toBeVisible();
  await expect(composer.getByRole("button", { name: "Commit draft to profile" })).toBeVisible();
  await expect(composer.getByRole("link", { name: "Edit profile form" })).toHaveAttribute("href", "/network#network-profile");
  await expect(composer.getByLabel("Profile sync preview")).toContainText(/draft value[s]? differ/);
  await expect(composer.getByLabel("Profile sync preview")).toContainText("Draft:");
  await expect(composer.getByLabel("Profile sync preview")).toContainText("Saved:");
  await expect(composer.getByLabel("Design address map")).toContainText("iSCSI LIFs");
  await expect(composer.getByLabel("Design address map")).toContainText("192.168.1.240");
  await expect(composer.getByLabel("Design readiness checklist")).toContainText("Profile sync");
  await expect(composer.getByLabel("Design readiness checklist")).toContainText("Subnet can rebase");
  await composer.getByText("Review packet").click();
  await expect(composer.getByLabel("Design review packet")).toContainText("server_netapp_vcenter");
  await expect(composer.getByLabel("Design review packet")).toContainText("Intent-only visual draft");
  await expect(composer.getByLabel("Design cabling map")).toContainText("NetApp ports");
  await expect(composer.getByLabel("Design cabling map")).toContainText("e0a/e0b");
  await composer.getByRole("button", { name: /NetApp ports/ }).click();
  await expect(composer.locator("section[aria-label='NetApp ONTAP workspace']")).toBeVisible();
  await expect(composer.getByLabel("Topology draft controls")).toContainText("NetApp ONTAP");
  await composer.getByRole("button", { name: /iSCSI LIFs/ }).click();
  await expect(composer.locator("section[aria-label='NetApp ONTAP workspace']")).toBeVisible();
  await composer.getByRole("button", { name: /Cisco C9300/ }).click();
  const switchWorkspace = composer.locator("section[aria-label='Cisco switch workspace']");
  await expect(switchWorkspace).toBeVisible();
  await expect(switchWorkspace.getByLabel("Cisco switch state")).toContainText(/Draft|Saved/);
  await expect(switchWorkspace.getByLabel("Cisco switch state")).toContainText(/source: (profile drift|persisted design draft|local draft defaults)/);
  await expect(switchWorkspace.getByLabel("Cisco switch state")).toContainText("source: no read-only run yet");
  await expect(switchWorkspace.getByLabel("Cisco switch interactive faceplate")).toBeVisible();
  await switchWorkspace.getByRole("button", { name: "Switch port 1", exact: true }).click();
  await expect(composer).toContainText("Cisco switch port 1 selected");
  const switchPortInspector = switchWorkspace.locator("section[aria-label='Cisco switch port 1 inspector']");
  await expect(switchPortInspector).toBeVisible();
  await expect(switchPortInspector).toContainText("device_settings.switch.ports");
  await expect(switchPortInspector).toContainText("device_settings.switch.port_profiles");
  await expect(switchPortInspector).toContainText("workflow action result");
  await expect(switchWorkspace.getByLabel("Cisco switch Network")).toContainText("Management IP");
  await expect(composer.getByRole("button", { name: "Use NFS" })).toHaveAttribute("aria-pressed", "true");
  await composer.getByRole("button", { name: "Use iSCSI" }).click();
  await expect(composer.getByRole("button", { name: "Use iSCSI" })).toHaveAttribute("aria-pressed", "true");
  await expect(composer.locator("section[aria-label='Design topology blueprint']")).toContainText("iSCSI datastore path");
  await composer.getByRole("button", { name: "Use NFS" }).click();
  await expect(composer.getByRole("button", { name: "Use NFS" })).toHaveAttribute("aria-pressed", "true");
  await expect(composer.locator("section[aria-label='Design topology blueprint']")).toContainText("Cisco C9300");
  await expect(composer.locator("section[aria-label='Design topology blueprint']")).toContainText("Open workspace");
  await expect(switchWorkspace).toBeVisible();
  await expect(switchWorkspace.getByLabel("Cisco switch schema inventory")).toContainText("Management IP");
  await expect(switchWorkspace.getByLabel("Cisco switch schema inventory")).toContainText("device_settings.switch.management_ip -> address_plan.cisco_management");
  await expect(switchWorkspace.getByLabel("Cisco switch schema inventory")).toContainText("Draft-only visual intent");
  await expect(composer.locator("section[aria-label='Cisco switch safe checks and next actions']")).toContainText("Cisco Firmware Inventory");
  await expect(switchWorkspace).toContainText("fabric and VLAN control");
  await expect(switchWorkspace.getByLabel("BPDU guard")).toHaveValue("enabled on edge access ports");
  await switchWorkspace.getByLabel("Black-hole VLAN").fill("998");
  await switchWorkspace.getByLabel("ACL lanes").fill("MGMT-IN, STORAGE-NFS-IN, DROP-ALL, QUARANTINE");
  await expect(switchWorkspace.getByLabel("Black-hole VLAN")).toHaveValue("998");
  await composer.getByRole("button", { name: /datastore path connection/ }).focus();
  await composer.getByRole("button", { name: /datastore path connection/ }).press("Enter");
  await expect(composer.locator("section[aria-label='Server to NetApp editor']")).toBeVisible();
  await composer.locator("section[aria-label='Server to NetApp editor']").getByLabel("Protocol").fill("NFS primary plus iSCSI standby");
  await composer.locator("section[aria-label='Server to NetApp editor']").getByLabel("Status").fill("planned - needs live session");
  await expect(composer.locator("[aria-label='Server to NetApp draft summary']")).toContainText("planned - needs live session");
  await expect(composer.locator("section[aria-label='Design topology blueprint']")).toContainText("NFS primary plus iSCSI standby");
  await switchWorkspace.getByRole("button", { name: /Cisco Firmware Inventory/ }).click();
  await expect(composer.locator("section[aria-label='Cisco switch safe checks and next actions']")).toContainText("Cisco Firmware Inventory: Ready");
  await expect(composer.locator("section[aria-label='Cisco switch safe checks and next actions']")).toContainText("Last: Ready");
  await expect(switchWorkspace.getByLabel("Cisco switch state")).toContainText("source: last Cisco Firmware Inventory");
  await composer.getByRole("button", { name: /NFS lane/ }).click();
  await expect(composer.locator("section[aria-label='Storage / SAN lane editor']")).toBeVisible();
  await composer.locator("section[aria-label='Storage / SAN lane editor']").getByLabel("MTU").fill("9100");
  await expect(composer.locator("section[aria-label='Storage / SAN lane editor']").getByLabel("MTU")).toHaveValue("9100");
  await composer.getByRole("button", { name: /Cisco C9300/ }).click();
  await expect(switchWorkspace).toBeVisible();
  await switchWorkspace.getByRole("textbox", { name: /^Storage VLAN/ }).fill("230");
  await expect(switchWorkspace.getByRole("textbox", { name: /^Storage VLAN/ })).toHaveValue("230");
  await expect(switchWorkspace).toContainText("230");
  await composer.getByLabel("Draft subnet").fill("192.168.500.0/24");
  await composer.getByRole("button", { name: "Rebase addresses" }).click();
  await expect(composer).toContainText("Each subnet octet must be between 0 and 255.");
  await expect(composer.getByLabel("Design readiness checklist")).toContainText("Fix subnet before rebase");
  await expect(composer.getByLabel("Subnet presets")).toContainText("High 200s");
  await composer.getByRole("button", { name: /High 200s/ }).click();
  await expect(composer).toContainText("Valid /24 subnet");
  await composer.getByRole("button", { name: "Rebase addresses" }).click();
  await expect(composer.getByLabel("Draft subnet")).toHaveValue("192.168.200.0/24");
  await expect(composer.locator("section[aria-label='Design topology blueprint']")).toContainText("192.168.200.204");
  await expect(composer.getByLabel("Design address map")).toContainText("192.168.200.240");
  await expect(composer.getByLabel("Design review packet")).toContainText("192.168.200.0/24");
  await expect(switchWorkspace.getByRole("textbox", { name: /^Management IP/ })).toHaveValue("192.168.200.204");
  await expect(composer.locator("section[aria-label='Server to NetApp editor']").getByLabel("Target")).toHaveValue("NetApp 192.168.200.230, 192.168.200.231");
  await composer.locator(".design-part").filter({ hasText: "DL360 Gen10+" }).click();
  await expect(composer.locator(".design-rack")).toContainText("DL360 Gen10+");
  const gen10PlusWorkspace = composer.locator("section[aria-label='DL360 Gen10+ workspace']");
  await gen10PlusWorkspace.getByRole("button", { name: "Drive bay 1", exact: true }).click();
  await expect(gen10PlusWorkspace.locator("section[aria-label='DL360 Gen10+ drive bay 1 inspector']")).toContainText("device_settings.server-gen10plus.raid_data");
  await expect(gen10PlusWorkspace.getByLabel("DL360 Gen10+ schema inventory")).toContainText("Server model");
  await expect(gen10PlusWorkspace.getByLabel("DL360 Gen10+ schema inventory")).toContainText("devices.server_model");
  const profileUpdate = page.waitForRequest((request) =>
    request.method() === "POST" && request.url().endsWith("/api/v1/lab/profiles")
  );
  await composer.getByRole("button", { name: "Commit draft to profile" }).click();
  const profilePayload = (await profileUpdate).postDataJSON() as Record<string, any>;
  expect(profilePayload.subnet_cidr).toBe("192.168.200.0/24");
  expect(profilePayload.address_plan.cisco_management).toBe("192.168.200.204");
  expect(profilePayload.address_plan.netapp_nfs_lifs).toContain("192.168.200.230");
  expect(profilePayload.profile_topology).toBe("server_netapp_vcenter");
  expect(profilePayload.features.deployment_mode).toBe("server_netapp_vcenter");
  expect(profilePayload.features.storage_protocol).toBe("nfs");
  expect(profilePayload.devices.server_model).toBe("gen10plus");
  expect(profilePayload.devices.netapp.blackhole_vlan).toBe("998");
  expect(profilePayload.devices.netapp.acl_lanes).toContain("QUARANTINE");
  expect(profilePayload.devices.netapp.storage_vlan).toBe("230");
  await expect(composer).toContainText("Visual draft committed to the saved lab profile");
  await expect(composer.getByLabel("Profile sync preview")).toContainText("Draft matches profile");
  await expect(composer.getByLabel("Design readiness checklist")).toContainText("Draft matches profile");
  await expect(composer.getByLabel("Profile sync preview")).toContainText("Storage VLAN");

  await page.reload();
  await page.getByRole("button", { name: "Design" }).click();
  await expect(page.locator("div[aria-label='Design mode rack composer']").locator(".design-rack")).toContainText("DL360 Gen10+");
  await expect(composer.locator(".design-rack")).toContainText("DL360 Gen10+");
  await expect(composer.getByLabel("Profile sync preview")).toContainText("Draft matches profile");
});

test("overview design mode visual blueprint stays stable", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 1400 });
  await page.goto("/overview");

  await page.getByRole("button", { name: "Design" }).click();
  await page.evaluate(() => {
    const hideIssueTrigger = () => {
      document.querySelectorAll("button").forEach((button) => {
        if (button.textContent?.includes("Report issue")) {
          button.style.display = "none";
        }
      });
    };
    hideIssueTrigger();
    new MutationObserver(hideIssueTrigger).observe(document.body, { childList: true, subtree: true });
  });

  const blueprint = page.locator("section[aria-label='Design topology blueprint']");
  await expect(blueprint).toBeVisible();
  await expect(blueprint).toContainText("Cisco C9300");
  await expect(blueprint).toContainText("NetApp ONTAP");
  await expect(blueprint).toHaveScreenshot("overview-design-blueprint.png", {
    animations: "disabled",
    maxDiffPixelRatio: 0.005
  });
});

test("overview design mode switches scenario drafts without committing hardware", async ({ page }) => {
  await page.goto("/overview");

  await page.getByRole("button", { name: "Design" }).click();

  const composer = page.locator("div[aria-label='Design mode rack composer']");
  const rack = composer.locator(".design-rack");
  const plan = composer.locator("aside[aria-label='Design plan summary']");

  await expect(composer.getByRole("button", { name: /Single server local/ })).toHaveAttribute("aria-pressed", "false");
  await composer.getByRole("button", { name: /Single server local/ }).click();

  await expect(plan).toContainText("single_server_local_storage");
  await expect(composer.getByLabel("Deployment archetype")).toContainText("Single server - local RAID");
  await expect(composer.getByLabel("Deployment archetype")).toContainText("Sparse local mode");
  await expect(composer).toContainText("Local storage lane");
  await expect(composer).toContainText("server-local RAID datastore");
  await expect(composer.locator("section[aria-label='Design topology blueprint']")).not.toContainText("NetApp ONTAP");
  await expect(composer.locator("section[aria-label='Design topology blueprint']")).not.toContainText("vCenter VCSA");
  await expect(rack).not.toContainText("NetApp ONTAP");
  await composer.getByRole("button", { name: /HPE DL360 Gen10/ }).click();
  const localServerWorkspace = composer.locator("section[aria-label='DL360 Gen10 workspace']");
  await expect(localServerWorkspace.getByLabel("DL360 Gen10 Storage")).toContainText("Local RAID and drive layout");
  await expect(localServerWorkspace.getByRole("textbox", { name: /^Data RAID/ })).toHaveValue("RAID6 local datastore");
  await expect(composer).toContainText("Hardware untouched until guarded applies.");
  await composer.getByRole("button", { name: /Add Windows Server to topology/ }).click();
  await expect(rack).toContainText("Windows Server");
  await expect(composer.locator("section[aria-label='Windows Server workspace']")).toBeVisible();

  await plan.getByRole("button", { name: "Reset draft" }).click();
  await expect(composer).toContainText("Persistent design draft saved");

  await composer.getByRole("button", { name: /Server \+ NetApp \+ vCenter/ }).click();
  await expect(plan).toContainText("server_netapp_vcenter");
  await expect(rack).toContainText("NetApp ONTAP");
  await expect(rack).toContainText("vCenter VCSA");
});

test("overview setup lanes distinguish single-server local storage from shared storage", async ({ page }) => {
  labProfileScenario = "single";
  await page.goto("/overview");

  const lanes = page.locator("section[aria-label='Scenario setup lanes']");
  await expect(lanes).toContainText("Single server + local ESXi storage");
  await expect(lanes).toContainText("Local datastore");

  const ontapLane = lanes.locator(".setup-lane-card").filter({ hasText: "ONTAP Storage" });
  await expect(ontapLane).toContainText("Plan Only");
  await expect(ontapLane).toContainText("Out of scope for this scenario.");
  await expect(ontapLane).toContainText("No action required for local-storage scenario.");

  const vcenterLane = lanes.locator(".setup-lane-card").filter({ hasText: "vCenter And VM Handoff" });
  await expect(vcenterLane).toContainText("Plan Only");
  await expect(vcenterLane).toContainText("Optional for this scenario.");
  await expect(vcenterLane).toContainText("No action required unless vCenter is selected.");
});

test("storage page switches to local datastore guidance for single-server setup", async ({ page }) => {
  labProfileScenario = "single";
  await page.goto("/storage");

  await expect(page.getByRole("button", { name: "Run Local Storage Live Check" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run NetApp Live Check" })).toHaveCount(0);

  const scenario = page.locator(".storage-scenario-card");
  await expect(scenario).toContainText("Single server with local ESXi storage");
  await expect(scenario).toContainText("RAID + ESXi local datastore");
  await expect(scenario).toContainText("NetApp can stay skipped for this build");

  const storage = page.locator("section[aria-label='Storage reference']");
  await expect(storage).toContainText("Local ESXi Datastore");
  await expect(storage).toContainText("Shared Storage Optional");
  await expect(storage).toContainText("No NetApp action is required unless the active setup changes to shared storage.");
});

test("virtualization page switches to direct ESXi guidance when vCenter is out of scope", async ({ page }) => {
  labProfileScenario = "single";
  await page.goto("/virtualization");

  await expect(page.getByRole("button", { name: "Run ESXi Live Check" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run vCenter Live Check" })).toHaveCount(0);

  const reference = page.locator("section[aria-label='Virtualization reference']");
  await expect(reference).toContainText("Single server + local ESXi storage");
  await expect(reference).toContainText("vCenter not in this setup.");
  await expect(reference).toContainText("Direct ESXi workflow");
  await expect(reference).toContainText("Server local datastore");
});

test("each side tab exposes a dedicated run button without dead settings drawers", async ({ page }) => {
  const pages = [
    ["/overview", "Run Refresh Access"],
    ["/network", "Run Live Switch Check"],
    ["/server", "Run Server Live Check"],
    ["/storage", "Run NetApp Live Check"],
    ["/virtualization", "Run vCenter Live Check"],
    ["/firmware-upgrades", "Run Scan Firmware"],
    ["/validation", "Run Validation"]
  ] as const;

  for (const [path, runButtonName] of pages) {
    await page.goto(path);
    await expect(page.getByRole("button", { name: "Settings" })).toHaveCount(0);
    await expect(page.locator("section.tab-settings-drawer")).toHaveCount(0);
    await expect(page.getByRole("button", { name: runButtonName }).first()).toBeVisible();
  }
});

test("operator pages avoid test-mode wording for live run controls", async ({ page }) => {
  for (const path of ["/network", "/server", "/storage", "/virtualization", "/firmware-upgrades", "/validation"]) {
    await page.goto(path);
    await expect(page.getByText("Run Test")).toHaveCount(0);
    await expect(page.getByText("Use these buttons to test or change this part of the lab.")).toHaveCount(0);
  }
});

test("side tab run buttons invoke registered workflow actions", async ({ page }) => {
  const pages = [
    ["/network", "Run Live Switch Check", "cisco.current-intent-diff"],
    ["/server", "Run Server Live Check", "ilo.reachability"],
    ["/storage", "Run NetApp Live Check", "netapp.live-state"],
    ["/virtualization", "Run vCenter Live Check", "vcenter-netapp.readiness"],
    ["/validation", "Run Validation", "build-verification.run-full"]
  ] as const;

  for (const [path, runButtonName, actionId] of pages) {
    await page.goto(path);
    const response = page.waitForResponse((nextResponse) =>
      nextResponse.url().includes(`/api/v1/workflows/actions/${actionId}/run`) &&
      nextResponse.request().method() === "POST"
    );
    await page.getByRole("button", { name: runButtonName }).click();
    await expect((await response).ok()).toBeTruthy();
    await expect(page.getByText(/no backend action is registered yet/i)).toHaveCount(0);
    await expect(page.getByText(/missing a runnable backend action/i)).toHaveCount(0);
  }
});

test("network shows switch access, settings, and blockers without proof clutter", async ({ page }) => {
  await page.goto("/network");

  const network = page.locator("section[aria-label='Network reference']");

  await expect(network.getByRole("heading", { name: "Network readiness at a glance" })).toBeVisible();
  await expect(network).toContainText("Switch status");
  await expect(network).toContainText("Access paths");
  await expect(network).toContainText("DNS / NTP");
  await expect(network).toContainText("Cisco firmware");
  await expect(network).toContainText("Cisco Switch");
  await expect(network).toContainText("Console");
  await expect(network).toContainText("SSH / SCP");
  await expect(network).toContainText("Current State:");
  await expect(network).toContainText("Target:");
  await expect(network).toContainText("Gap:");
  await expect(network).toContainText("Next safe actions");
  await expect(network).toContainText("Real lab prerequisites");
  await expect(network).toContainText("Hardware contact gates");
  await expect(network).toContainText("Console adapter");
  await expect(network).toContainText("Real hardware acknowledgement");
  await expect(network).toContainText("ACKNOWLEDGE DEVICE RECONFIGURATION");
  await expect(network).toContainText("Network Settings");
  await expect(network).toContainText("Active Blockers");
  await expect(network).toContainText("192.168.1.204");
});

test("network Cisco driver surfaces current-intent guardrail drift", async ({ page }) => {
  await page.goto("/network");

  const intentResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/cisco/current-intent-diff") &&
    response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Refresh live evidence" }).click();
  await expect((await intentResponse).ok()).toBeTruthy();

  const driver = page.locator("section[aria-label='Cisco switch driver']");
  await expect(driver).toContainText("Live intent parsed");
  await expect(driver).toContainText("1 live interface mismatch needs review before apply.");
  await expect(driver).toContainText("Evidence: current-intent diff, 8 interface rows, 4 VLAN rows parsed");
  await expect(driver).toContainText("Gi1/0/3");
  await expect(driver).toContainText("Expected trunk, saw VLAN 10.");
  await expect(driver).toContainText("Black-hole VLAN");
  await expect(driver).toContainText("Missing: 999");
  await expect(driver).toContainText("STORAGE-NFS-IN");
  await expect(driver).toContainText("DROP-ALL");
  await expect(driver).toContainText("Remediation review");
  await expect(driver).toContainText("3 remediation area(s) need review; 3 candidate command line(s) are renderable.");
  await expect(driver).toContainText("Create missing VLANs");
  await expect(driver).toContainText("Align intended ports");
  await expect(driver).toContainText("Review guardrails");
  await expect(driver).toContainText("Treat ACL lanes as review-only until exact source/destination policy is approved.");
  await expect(driver).toContainText("Preserve unexpected VLANs");
  await expect(driver).toContainText("3 candidate command lines generated from parsed drift.");
  await expect(driver).toContainText("vlan 999");
  await expect(driver).toContainText("name BLACKHOLE-PARKING");
  await expect(driver).not.toContainText("interface vlan 10");
});

test("redesigned operator pages expose reference panels with safe action guidance", async ({ page }) => {
  const pages = [
    ["/server", "Server reference", "Server readiness at a glance", "Server Signals"],
    ["/storage", "Storage reference", "Storage readiness at a glance", "Storage Signals"],
    ["/virtualization", "Virtualization reference", "Virtualization readiness at a glance", "Virtualization Signals"],
    ["/firmware-upgrades", "Firmware reference", "Firmware readiness at a glance", "Firmware Components"],
    ["/validation", "Validation reference", "Validation readiness at a glance", "Validation Signals"]
  ] as const;

  for (const [path, ariaLabel, heading, tableTitle] of pages) {
    await page.goto(path);
    const reference = page.locator(`section[aria-label='${ariaLabel}']`).first();
    await expect(reference.getByRole("heading", { name: heading })).toBeVisible();
    await expect(reference).toContainText("Current state and targets");
    await expect(reference).toContainText("Current State:");
    await expect(reference).toContainText("Target:");
    await expect(reference).toContainText("Gap:");
    await expect(reference).toContainText("Next safe actions");
    await expect(reference).toContainText(tableTitle);
    await expect(reference).toContainText("Active Blockers");
    await expect(page.getByRole("button", { name: "Settings" })).toHaveCount(0);
    if (path === "/storage") {
      const protocols = page.getByLabel("Storage protocol options");
      await expect(protocols).toContainText("NFS");
      await expect(protocols).toContainText("iSCSI");
      await expect(protocols).toContainText("192.168.1.240");
      await expect(protocols).toContainText("TCP/3260");
      const iscsiPath = page.getByLabel("iSCSI setup path");
      await expect(iscsiPath).toContainText("iSCSI setup path");
      await expect(iscsiPath).toContainText("Preview Only");
      await expect(iscsiPath).toContainText("esxi_lun_01");
      await expect(iscsiPath).toContainText("esxi_hosts");
      await expect(page.getByText("Real iSCSI apply gates and write evidence")).toBeVisible();
      await expect(page.getByText("ESXi iSCSI remediation")).toBeVisible();
      await expect(page.locator(".iscsi-remediation-panel")).toContainText("Establish active iSCSI session");
      await expect(page.getByText("Not evaluated")).toBeVisible();
      await expect(iscsiPath).toContainText("ESXi iSCSI evidence");
      await expect(iscsiPath).toContainText("1 adapters / 1 paths / datastore visible");
      await expect(page.getByRole("button", { name: "Preview iSCSI" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Apply iSCSI" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Validate iSCSI" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Preview ESXi iSCSI" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Validate ESXi iSCSI" })).toBeVisible();
    }
  }

  await page.goto("/lab-profiles");
  await expect(page.getByRole("heading", { name: "Shared profile policy" })).toBeVisible();
  await expect(page.getByLabel("Global profile feature toggles")).toContainText("Allow IPv6");
  await expect(page.getByRole("button", { name: /Save (Global Defaults|As Lab Setup)/ })).toBeVisible();

  await page.goto("/network");
  const networkReference = page.locator("section[aria-label='Network reference']").first();
  await expect(page.getByRole("button", { name: "Run Live Switch Check" })).toBeVisible();
  await expect(networkReference).toContainText("Cisco access is ready.");
  await expect(networkReference).toContainText("Cisco Switch");
});

test("storage iSCSI preview apply and validation buttons expose the honest guarded path", async ({ page }) => {
  await page.goto("/storage");

  const previewResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/netapp-ontap/iscsi-setup-preview")
  );
  await page.getByRole("button", { name: "Preview iSCSI" }).click();
  await expect((await previewResponse).ok()).toBeTruthy();
  await expect(page.getByText(/Preview iSCSI:/)).toBeVisible();

  const applyResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/netapp-ontap/iscsi-setup-apply") &&
    response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Apply iSCSI" }).click();
  await expect((await applyResponse).ok()).toBeTruthy();
  await expect(page.getByText(/Apply iSCSI: Blocked/)).toBeVisible();
  await expect(page.getByLabel("iSCSI setup path")).toContainText("NETAPP_ISCSI_SETUP_APPLY=true is required.");
  await expect(page.getByText("Real iSCSI apply gates and write evidence")).toBeVisible();
  await expect(page.getByText("1/4 satisfied")).toBeVisible();
  await expect(page.getByText(/ONTAP writes not attempted/)).toBeVisible();
  await expect(page.getByText(/NETAPP_ISCSI_SETUP_CONFIRM="APPLY NETAPP ISCSI SETUP"/)).toBeVisible();

  const validateResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/netapp-ontap/iscsi-setup-validate") &&
    response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Validate iSCSI" }).click();
  await expect((await validateResponse).ok()).toBeTruthy();
  await expect(page.getByText(/Validate iSCSI:/)).toBeVisible();
  await expect(page.getByLabel("iSCSI setup path")).toContainText("NetApp iSCSI LUN is missing.");

  const esxiPreviewResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/esxi-readonly/iscsi-datastore-preview") &&
    response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Preview ESXi iSCSI" }).click();
  await expect((await esxiPreviewResponse).ok()).toBeTruthy();
  await expect(page.getByText(/Preview ESXi iSCSI:/)).toBeVisible();
  await expect(page.getByLabel("iSCSI setup path")).toContainText("1 adapters / 1 paths / datastore visible");
  await expect(page.getByText("ESXi iSCSI remediation")).toBeVisible();
  await page.getByText("ESXi iSCSI remediation").click();
  await expect(page.getByText("Confirm VMFS datastore visibility")).toBeVisible();
});

test("advanced proof is collapsed and operator labels hide raw statuses", async ({ page }) => {
  await page.goto("/validation");

  const advanced = page.locator("details.advanced-drawer").first();
  await expect(advanced).not.toHaveAttribute("open", "");
  const validation = page.locator("section[aria-label='Validation reference']");
  await expect(validation.getByText("Golden State / Handoff", { exact: true })).toBeVisible();
  await expect(page.getByText("Golden State means expected working lab state.").first()).toBeVisible();
  await expect(validation).toContainText("Validation Signals");
  await expect(page.getByText("Artifact")).toHaveCount(0);
  await expect(page.getByText("manual_review")).toHaveCount(0);
  await expect(page.getByText("not_configured_yet")).toHaveCount(0);

  await page.goto("/overview");
  await expect(page.getByText("Real lab").first()).toBeVisible();
  await expect(page.getByText("local-lab-readwrite")).toHaveCount(0);
});

test("firmware table renders upgrade path states", async ({ page }) => {
  await page.goto("/firmware-upgrades");

  await expect(page.getByRole("heading", { name: "Firmware Files" })).toBeVisible();
  await expect(page.getByLabel("Firmware Files").getByText("/home/administrator/infra-config-portal/artifacts/Media")).toBeVisible();
  await expect(page.getByRole("button", { name: "Rescan Files" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Media Inventory" })).toBeVisible();

  const advanced = page.locator("details.advanced-drawer").first();
  await advanced.getByText("Firmware proof").click();
  const workspace = advanced.locator("[aria-label='Current view']").first();
  const objects = workspace.locator("[aria-label='Objects']");
  const detail = workspace.locator("[aria-label='Selected object detail']");

  await expect(objects).toContainText("Cisco Switch");
  await expect(detail).toContainText("Cisco Switch");
  await expect(detail).toContainText("IOS XE");
  await expect(detail).toContainText("17.15.05");
  await expect(detail).toContainText("Needs review");
  await expect(detail).toContainText("cat9k_iosxe.17.15.05.SPA.bin");
  await expect(detail).toContainText("Auto-selected");
  const selectionSave = page.waitForResponse((response) =>
    response.url().includes("/api/v1/firmware/file-selections") &&
    response.request().method() === "PUT"
  );
  await detail.getByRole("combobox", { name: /Cisco Switch IOS XE firmware file/ }).selectOption("cat9k_iosxe.17.12.01.SPA.bin");
  await expect((await selectionSave).ok()).toBeTruthy();
  await expect(detail).toContainText("cat9k_iosxe.17.12.01.SPA.bin");
  await expect(detail).toContainText("Selected by user");
  await expect(page.getByText("1 saved")).toBeVisible();
  const selectionClear = page.waitForRequest((request) =>
    request.url().includes("/api/v1/firmware/file-selections") &&
    request.method() === "PUT"
  );
  const selectionClearResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/firmware/file-selections") &&
    response.request().method() === "PUT"
  );
  await detail.getByRole("combobox", { name: /Cisco Switch IOS XE firmware file/ }).selectOption("");
  const selectionClearPayload = selectionClear.then((request) => request.postDataJSON() as { selected_files: Record<string, string> });
  await expect((await selectionClearResponse).ok()).toBeTruthy();
  await expect(await selectionClearPayload).toEqual({ selected_files: {} });
  await expect(detail).toContainText("Auto-selected");
  await expect(page.getByText("Not saved")).toBeVisible();
  await page.getByRole("button", { name: "Rescan Files" }).click();
  await expect(detail).toContainText("cat9k_iosxe.17.15.05.SPA.bin");
  await expect(detail).toContainText("Auto-selected");
  await expect(workspace.getByRole("button", { name: "Scan" })).toHaveCount(0);
  await expect(workspace.getByRole("button", { name: "Validate Path" })).toHaveCount(0);
  await expect(workspace.getByRole("button", { name: "Upgrade" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Validate Upgrade Path" })).toHaveCount(0);

  await objects.getByRole("button", { name: /HPE Server.*Smart Array/ }).click();
  await expect(detail).toContainText("SPP2024.03.00.iso");
  await expect(objects).toContainText("NetApp");
});

test("firmware page scan runs through the workflow runner without placeholder upgrade controls", async ({ page }) => {
  await page.goto("/firmware-upgrades");

  const scanResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/firmware.inventory/run") &&
    response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Run Scan Firmware" }).click();
  await expect((await scanResponse).ok()).toBeTruthy();
  await expect(page.getByText(/Scan All Firmware:/)).toBeVisible();

  const complianceResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/firmware.compliance-check/run") &&
    response.request().method() === "POST"
  );
  await page.locator("details[aria-label='Firmware check and plan']").getByRole("button", { name: "Check Compliance" }).click();
  await expect((await complianceResponse).ok()).toBeTruthy();
  await expect(page.getByText(/Check Compliance:/)).toBeVisible();

  const planResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/firmware.upgrade-plan/run") &&
    response.request().method() === "POST"
  );
  await page.locator("details[aria-label='Firmware check and plan']").getByRole("button", { name: "Plan Firmware Upgrade" }).click();
  await expect((await planResponse).ok()).toBeTruthy();
  await expect(page.getByText(/Plan Upgrade:/)).toBeVisible();

  await expect(page.getByText("Protected firmware action")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Upgrade", exact: true })).toHaveCount(0);
  const ontapUpgrade = page.getByRole("button", { name: "Upgrade ONTAP" });
  await expect(ontapUpgrade).toBeVisible();
  await expect(ontapUpgrade).toBeDisabled();
  await expect(ontapUpgrade).toHaveAttribute("title", /guarded (workflow registration|confirmation)/i);
  await expect(page.getByText(/Run Upgrade Placeholder/)).toHaveCount(0);
});

test("media inventory displays actual file names when exposed by the backend", async ({ page }) => {
  await page.goto("/media");

  await expect(page.getByRole("columnheader", { name: "File" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "cat9k_iosxe.17.15.05.SPA.bin" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "cisco-ios-xe-firmware.bin" })).toHaveCount(0);
});

test("saved lab setup global defaults use active profile values and never render secret material", async ({ page }) => {
  await page.goto("/lab-profiles");

  await expect(page.getByText("Runtime Lab").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Shared profile policy" })).toBeVisible();
  await expect(page.getByLabel("Global profile feature toggles")).toContainText("Block legacy protocols");
  await expect(page.locator("nav").getByText("Settings")).toHaveCount(0);
  await expect(page.getByText("Secret values are hidden")).toHaveCount(0);
  await expect(page.locator("input[type='password']")).toHaveCount(0);
});

test("legacy settings paths redirect to overview and the contextual drawer is removed", async ({ page }) => {
  await page.goto("/network");

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
  await page.goto("/validation");

  const runResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/build-verification.run-full/run")
  );
  await page.getByRole("button", { name: "Run Validation" }).click();
  await expect((await runResponse).ok()).toBeTruthy();
  await expect(page.getByText(/Run Full Verification:/)).toBeVisible();
});

test("generate handoff report button calls the handoff API and reports completion", async ({ page }) => {
  await page.goto("/validation");

  const handoffResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/lab/validation/handoff")
  );
  await page.getByRole("button", { name: "Generate Handoff Report" }).click();
  await expect((await handoffResponse).ok()).toBeTruthy();
  await expect(page.getByText("Generate Handoff Report completed.")).toBeVisible();
});

test("validation exposes guarded factory reset and automated rebuild verification", async ({ page }) => {
  await page.goto("/validation");

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

  const previewResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/netapp.factory-reset-preview/run") &&
    response.request().method() === "POST"
  );
  await resetPanel.getByRole("button", { name: "Preview NetApp Factory Reset" }).click();
  await expect((await previewResponse).ok()).toBeTruthy();

  for (const label of ["Apply NetApp Factory Reset", "Reset HPE RAID", "Rebuild ESXi Host", "Reset Server Power"]) {
    const button = resetPanel.getByRole("button", { name: label });
    await expect(button).toBeVisible();
    await expect(button).toBeDisabled();
    await expect(button).toHaveAttribute("title", /guarded confirmation/i);
  }
});

test("validation read-only sweep surfaces optional parity blockers as warnings", async ({ page }) => {
  await page.goto("/validation");

  const sweepResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/operator-readonly-sweep.real-lab/run")
  );
  await page.getByRole("button", { name: "Run Read-Only Sweep" }).click();
  await expect((await sweepResponse).ok()).toBeTruthy();
  await expect(page.getByText(/optional parity checks reported blockers: esxi\.iscsi-datastore-validate/i)).toBeVisible();
});

test("blocked workflow runs render an advisory diagnosis card", async ({ page }) => {
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
  await page.getByRole("button", { name: "Run Validation" }).click();

  await expect((await runResponse).ok()).toBeTruthy();
  await expect(page.getByLabel("Advisory diagnosis")).toBeVisible();
  await expect(page.getByLabel("Advisory diagnosis")).toContainText("The workflow runner timed out before collecting complete evidence.");
  await expect(page.getByLabel("Advisory diagnosis")).toContainText("Diagnosis is advisory and does not execute workflow actions.");
});

test("operator issue reporter creates a redacted AI-ready packet from the current route", async ({ page }) => {
  await page.goto("/network");

  await page.getByRole("button", { name: "Report issue" }).click();
  await expect(page.getByRole("dialog", { name: "Report testing issue" })).toBeVisible();
  await expect(page.getByText("/network")).toBeVisible();
  await page.getByLabel("What went wrong?").fill("Clicked the Cisco validation button and the status looked stale.");
  await page.getByRole("button", { name: "Create packet" }).click();

  await expect(page.getByLabel("Generated issue packet")).toContainText("Operator reported an issue on Network");
  await expect(page.getByLabel("Generated issue packet")).toContainText("artifacts/codex-runs/operator-issue-packets");
  await expect(page.getByRole("button", { name: "Copy AI prompt" })).toBeVisible();
});

test("workflow runner surfaces plain-text API errors", async ({ page }) => {
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
  await page.getByRole("button", { name: "Run Validation" }).click();

  await expect((await runResponse).status()).toBe(503);
  await expect(page.getByText("workflow runner temporarily unavailable")).toBeVisible();
});

test("workflow runner surfaces primitive array API detail errors", async ({ page }) => {
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
  await page.getByRole("button", { name: "Run Validation" }).click();

  await expect((await runResponse).status()).toBe(422);
  await expect(page.getByText("first blocker; second blocker")).toBeVisible();
});

test("workflow runner surfaces malformed JSON API responses", async ({ page }) => {
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
  await page.getByRole("button", { name: "Run Validation" }).click();

  await expect((await runResponse).status()).toBe(200);
  await expect(page.getByText("Invalid JSON response from /api/v1/workflows/actions/build-verification.run-full/run.")).toBeVisible();
});

test("workflow runner surfaces network API failures", async ({ page }) => {
  await page.route("**/api/v1/workflows/actions/build-verification.run-full/run", (route) =>
    route.abort("failed")
  );
  await page.goto("/validation");

  await page.getByRole("button", { name: "Run Validation" }).click();

  await expect(page.getByText("Network error while requesting /api/v1/workflows/actions/build-verification.run-full/run.")).toBeVisible();
});

async function installApiMocks(page: Page) {
  let firmwareFileSelections = firmwareFileSelectionState({});
  let labSafety = labSafetySettings();
  let activeProfiles = activeLabProfilesFixture();
  let savedProfile: Record<string, unknown> | null = null;
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
    if (url.pathname === "/api/v1/providers/cisco-ansible/probe") {
      return json(route, ciscoSshProbe());
    }
    if (url.pathname === "/api/v1/providers/cisco/current-intent-diff") {
      return json(route, ciscoCurrentIntentDiff());
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
      return json(route, []);
    }
    return json(route, {});
  });
}

function json(route: Route, body: unknown) {
  return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
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
    readAction("esxi.management-validation", "ESXi Live Check", "esxi", "esxi"),
    readAction("esxi.ssh-api-check", "ESXi SSH/API Live Check", "esxi", "esxi"),
    readAction("esxi.iscsi-datastore-preview", "Preview ESXi iSCSI Datastore", "esxi", "esxi"),
    readAction("esxi.iscsi-datastore-validate", "Validate ESXi iSCSI Datastore", "esxi", "esxi"),
    readAction("raid.validate", "Validate RAID", "raid", "ilo-redfish"),
    readAction("netapp.live-state", "NetApp Live Check", "netapp", "netapp-ontap"),
    readAction("netapp.nfs-setup-validate", "Validate NFS", "netapp", "netapp-ontap"),
    readAction("netapp.console-autodiscovery", "Refresh NetApp Consoles", "netapp", "netapp-ontap"),
    readAction("netapp.component-firmware-inventory", "Refresh ONTAP", "netapp", "netapp-ontap"),
    readAction("vcenter-netapp.readiness", "vCenter Live Check", "vcenter", "vcenter"),
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
    writeAction("esxi.rebuild-install", "Rebuild ESXi Host", "esxi", "esxi", "destructive"),
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
    stdout_summary: isFirmwareUpgrade ? "" : "verification passed",
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

function activeLabProfilesFixture() {
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
