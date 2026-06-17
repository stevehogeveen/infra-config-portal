import { expect, test, type Page, type Route } from "@playwright/test";

const checkedAt = "2026-06-17T18:20:00Z";
const hpeUpgradePathValue = "HPE iLO:hpe_ilo_firmware:2.91";
const upgradePathValue = "NetApp ONTAP:netapp_ontap_version:9.14.1P1";

type ControlCenterConfigMock = {
  blockers: string[];
  credential_storage: string;
  freshness: string;
  ip_mode: "ipv4" | "ipv6" | "both";
  retry_count: number;
  snmp_credential_status: "missing" | "configured";
  snmp_credential_version: "v2" | "v3" | null;
  snmp_version: "v2" | "v3";
  source_type: string;
  store_path: string;
  target: string;
  timeout_seconds: number;
  updated_at: string | null;
  warnings: string[];
};

type ControlCenterSettingsMock = {
  api_base_url: string;
  blockers: string[];
  default_ip_mode: "ipv4" | "ipv6" | "both";
  default_retry_count: number;
  default_snmp_version: "v2" | "v3";
  default_timeout_seconds: number;
  firmware_repository: string;
  freshness: string;
  logging_verbosity: "errors" | "normal" | "debug";
  source_type: string;
  store_path: string;
  updated_at: string | null;
  warnings: string[];
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!window.sessionStorage.getItem("control-center-e2e-storage-cleared")) {
      window.localStorage.clear();
      window.sessionStorage.setItem("control-center-e2e-storage-cleared", "true");
    }
  });
  await installApiMocks(page);
});

test("renders the WebUIs Control Center sidebar and dashboard", async ({ page }) => {
  await page.goto("/dashboard");

  await expect(page.getByRole("heading", { name: "WebUIs Control Center" })).toBeVisible();
  await expect(page.locator(".control-nav-link")).toHaveText([
    "Dashboard",
    "Configure",
    "Run",
    "Firmware",
    "Results",
    "Logs",
    "Settings"
  ]);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("heading", { exact: true, name: "Current Target" })).toBeVisible();
  await expect(page.getByRole("heading", { exact: true, name: "Firmware Summary" })).toBeVisible();
  await expect(page.locator(".quick-link-row").getByRole("link", { name: "Configure" })).toBeVisible();
  await expect(page.locator(".quick-link-row").getByRole("link", { name: "Run" })).toBeVisible();
  await expect(page.locator(".quick-link-row").getByRole("link", { name: "Firmware" })).toBeVisible();

  const nav = page.locator(".control-nav");
  for (const pageName of ["Configure", "Run", "Firmware", "Results", "Logs", "Settings", "Dashboard"]) {
    await nav.getByRole("link", { name: pageName }).click();
    await expect(page.getByRole("heading", { exact: true, name: pageName })).toBeVisible();
  }

  await page.goto("/control-center?section=action-catalog&action=build-verification.run-full");
  await expect(page).toHaveURL(/\/run$/);
  await expect(page.getByRole("heading", { exact: true, name: "Run" })).toBeVisible();
  await page.goto("/control-center?section=firmware&device=netapp");
  await expect(page).toHaveURL(/\/firmware$/);
  await expect(page.getByRole("heading", { exact: true, name: "Firmware" })).toBeVisible();
  await page.goto("/control-center?section=reports");
  await expect(page).toHaveURL(/\/results$/);
  await expect(page.getByRole("heading", { exact: true, name: "Results" })).toBeVisible();
  await page.goto("/control-center/logs");
  await expect(page).toHaveURL(/\/logs$/);
  await expect(page.getByRole("heading", { exact: true, name: "Logs" })).toBeVisible();

  await page.goto("/overview");
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("configure saves target, IP mode, SNMPv3 credential presence, timeout, and retry", async ({ page }) => {
  await page.goto("/configure");

  await page.getByLabel("Target host, IP, or range").fill("192.0.2.203");
  await page.getByLabel("IP mode").selectOption("both");
  await page.getByLabel("SNMP version").selectOption("v3");
  await expect(page.getByLabel("SNMPv3 username")).toBeVisible();
  await page.getByLabel("SNMPv3 username").fill("configured-reference");
  await page.getByLabel("SNMPv3 auth password").fill("configured-reference");
  await page.getByLabel("SNMPv3 privacy password").fill("configured-reference");
  await page.getByText("Advanced").click();
  await page.getByLabel("Timeout seconds").fill("12");
  await page.getByLabel("Retry count").fill("2");
  await page.getByRole("button", { name: "Save / apply config" }).click();

  await expect(page.getByText("Configuration saved")).toBeVisible();
  await page.goto("/dashboard");
  await expect(page.getByText("192.0.2.203").first()).toBeVisible();
  await expect(page.getByText("IPv4 and IPv6").first()).toBeVisible();
  await expect(page.getByText("SNMPv3").first()).toBeVisible();
  await expect(page.getByText("Configured").first()).toBeVisible();

  await page.reload();
  await expect(page.getByText("192.0.2.203").first()).toBeVisible();
  await expect(page.getByText("SNMPv3").first()).toBeVisible();
});

test("configure rejects secret-shaped target values before local fallback can persist them", async ({ page }) => {
  await page.goto("/configure");

  await page.getByLabel("Target host, IP, or range").fill("password=not-allowed");
  await page.getByRole("button", { name: "Save / apply config" }).click();

  await expect(page.getByText("Target must not contain secret-shaped values.")).toBeVisible();
  await expect(page.getByText("Configuration saved")).toHaveCount(0);
});

test("run page has one Run button and writes latest result", async ({ page }) => {
  const actionRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/control-center/config" && request.method() === "PUT") {
      const body = request.postDataJSON() as Partial<ControlCenterConfigMock>;
      actionRequests.push(`config:${body.target ?? ""}`);
    }
    if (
      url.pathname === "/api/v1/workflows/actions/build-verification.run-full/run" &&
      request.method() === "POST"
    ) {
      actionRequests.push("run");
    }
  });

  await page.goto("/configure");
  await page.getByLabel("Target host, IP, or range").fill("192.0.2.203");
  await page.getByRole("button", { name: "Save / apply config" }).click();
  await expect(page.getByText("Configuration saved")).toBeVisible();
  actionRequests.length = 0;

  await page.goto("/run");
  await expect(page.getByRole("button", { name: /^Run$/ })).toHaveCount(1);

  const runResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/build-verification.run-full/run") &&
    response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /^Run$/ }).click();
  await expect((await runResponse).ok()).toBeTruthy();
  expect(actionRequests).toEqual(["config:192.0.2.203", "run"]);
  await expect(page.getByText("Safe read-only/report-only action completed.").first()).toBeVisible();

  await page.goto("/results");
  await expect(page.getByText("Run Full Verification").first()).toBeVisible();
  await expect(page.getByText("Success").first()).toBeVisible();
  const runResult = page.locator("section").filter({ hasText: "Latest Run Result" });
  await runResult.getByText("Raw result").click();
  await expect(runResult.locator("pre.control-code")).toContainText('"target": "192.0.2.203"');

  await page.goto("/configure");
  await page.getByLabel("Target host, IP, or range").fill("192.0.2.204");
  await page.goto("/results");
  await expect(page.getByText("No run result")).toBeVisible();
  await expect(page.getByText("Run Full Verification")).toHaveCount(0);
});

test("run and firmware check sync unsaved current config before backend actions", async ({ page }) => {
  const configPayloads: Partial<ControlCenterConfigMock>[] = [];
  const actionRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/control-center/config" && request.method() === "PUT") {
      configPayloads.push(request.postDataJSON() as Partial<ControlCenterConfigMock>);
    }
    if (
      url.pathname === "/api/v1/workflows/actions/build-verification.run-full/run" &&
      request.method() === "POST"
    ) {
      actionRequests.push("run");
    }
    if (url.pathname === "/api/v1/lab/firmware-inventory") {
      actionRequests.push("firmware-check");
    }
  });

  await page.goto("/configure");
  await page.getByLabel("Target host, IP, or range").fill("192.0.2.210");
  await page.getByLabel("IP mode").selectOption("both");
  await page.getByLabel("SNMP version").selectOption("v3");
  await page.getByLabel("SNMPv3 username").fill("configured-reference");
  await page.getByLabel("SNMPv3 auth password").fill("configured-reference");
  await page.getByLabel("SNMPv3 privacy password").fill("configured-reference");
  await page.getByText("Advanced").click();
  await page.getByLabel("Timeout seconds").fill("15");
  await page.getByLabel("Retry count").fill("3");

  await page.getByRole("link", { name: "Continue to Run" }).click();
  await page.getByRole("button", { name: /^Run$/ }).click();
  await expect(page.getByText("Safe read-only/report-only action completed.").first()).toBeVisible();

  expect(configPayloads[0]).toMatchObject({
    ip_mode: "both",
    retry_count: 3,
    snmp_credential_status: "configured",
    snmp_credential_version: "v3",
    snmp_version: "v3",
    target: "192.0.2.210",
    timeout_seconds: 15
  });
  expect(actionRequests).toEqual(["run"]);

  await page.goto("/configure");
  await page.getByLabel("Target host, IP, or range").fill("192.0.2.211");
  await page.locator(".control-nav").getByRole("link", { name: "Firmware" }).click();
  await page.getByRole("button", { name: "Check Firmware" }).click();
  await expect(page.getByText("Firmware check succeeded")).toBeVisible();

  expect(configPayloads[1]).toMatchObject({
    snmp_credential_status: "configured",
    snmp_credential_version: "v3",
    snmp_version: "v3",
    target: "192.0.2.211"
  });
  expect(actionRequests).toEqual(["run", "firmware-check"]);
});

test("run blocks invalid current config before backend action", async ({ page }) => {
  const actionRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (
      url.pathname === "/api/v1/workflows/actions/build-verification.run-full/run" &&
      request.method() === "POST"
    ) {
      actionRequests.push("run");
    }
  });

  await page.goto("/run");
  await page.getByRole("button", { name: /^Run$/ }).click();

  await expect(page.getByText("Run blocked until the current configuration is valid.").first()).toBeVisible();
  await expect(page.getByText("Target host, IP, or range is required.").first()).toBeVisible();
  expect(actionRequests).toEqual([]);

  await page.goto("/results");
  await expect(page.getByText("Run blocked").first()).toBeVisible();
  await page.goto("/logs");
  await expect(page.getByText("Run blocked").first()).toBeVisible();
});

test("firmware page checks visibility, validates, and gates upgrade confirmation", async ({ page }) => {
  const actionRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/control-center/config" && request.method() === "PUT") {
      const body = request.postDataJSON() as Partial<ControlCenterConfigMock>;
      actionRequests.push(`config:${body.target ?? ""}`);
    }
    if (url.pathname === "/api/v1/lab/firmware-inventory") {
      actionRequests.push("firmware-check");
    }
    if (url.pathname === "/api/v1/providers/netapp-ontap/ontap-upgrade/validate") {
      actionRequests.push("firmware-validate");
    }
    if (
      url.pathname === "/api/v1/workflows/actions/netapp.ontap-upgrade-apply/run" &&
      request.method() === "POST"
    ) {
      actionRequests.push("firmware-upgrade");
    }
  });

  await page.goto("/configure");
  await page.getByLabel("Target host, IP, or range").fill("192.0.2.203");
  await page.getByRole("button", { name: "Save / apply config" }).click();
  actionRequests.length = 0;

  await page.goto("/firmware");

  await expect(page.getByRole("heading", { exact: true, name: "Firmware" })).toBeVisible();
  await expect(page.getByRole("heading", { exact: true, name: "Firmware Visibility" })).toBeVisible();
  await expect(page.getByRole("heading", { exact: true, name: "Firmware Upgrade" })).toBeVisible();
  await expect(page.getByRole("heading", { exact: true, name: "Firmware Events" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Validate Firmware" })).toBeDisabled();
  await expect(page.getByText("Select a firmware path before validation.")).toBeVisible();
  await expect(
    page.getByText("Selected firmware, image, or target version is required before validation.")
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Firmware Upgrade" })).toBeDisabled();

  const checkResponse = page.waitForResponse((response) => response.url().includes("/api/v1/lab/firmware-inventory"));
  await page.getByRole("button", { name: "Check Firmware" }).click();
  await expect((await checkResponse).ok()).toBeTruthy();
  expect(actionRequests.splice(0)).toEqual(["config:192.0.2.203", "firmware-check"]);
  await expect(page.getByText("Firmware check succeeded")).toBeVisible();

  await page.getByLabel("Firmware path").selectOption(upgradePathValue);
  await expect(page.getByLabel("Selected firmware, image, or version")).toHaveValue("ontap-9.14.1P1.tgz");
  await expect(page.getByRole("button", { name: "Validate Firmware" })).toBeEnabled();

  const validateResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/providers/netapp-ontap/ontap-upgrade/validate")
  );
  await page.getByRole("button", { name: "Validate Firmware" }).click();
  await expect((await validateResponse).ok()).toBeTruthy();
  expect(actionRequests.splice(0)).toEqual(["config:192.0.2.203", "firmware-validate"]);
  await expect(page.getByText("Firmware validation succeeded")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Firmware Upgrade" })).toBeDisabled();

  await page.reload();
  await expect(page.getByLabel("Firmware path")).toHaveValue(upgradePathValue);
  await expect(page.getByLabel("Selected firmware, image, or version")).toHaveValue("ontap-9.14.1P1.tgz");
  await expect(page.getByRole("button", { name: "Validate Firmware" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Start Firmware Upgrade" })).toBeDisabled();

  await page.getByLabel("Require explicit operator confirmation before any firmware upgrade request is sent.").check();
  await page.getByLabel("Confirmation phrase").fill("UPGRADE ONTAP");
  await expect(page.getByRole("button", { name: "Start Firmware Upgrade" })).toBeEnabled();

  const upgradeResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/workflows/actions/netapp.ontap-upgrade-apply/run") &&
    response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Start Firmware Upgrade" }).click();
  await expect((await upgradeResponse).ok()).toBeTruthy();
  expect(actionRequests.splice(0)).toEqual(["config:192.0.2.203", "firmware-upgrade"]);
  await expect(page.getByText("Firmware upgrade blocked")).toBeVisible();
  await expect(page.getByText("Guarded action was not run because required gates were not satisfied.")).toBeVisible();

  await page.goto("/results");
  const firmwareCheckResult = page.locator("section").filter({ hasText: "Latest Firmware Check Summary" });
  await firmwareCheckResult.getByText("Raw result").click();
  await expect(firmwareCheckResult.locator("pre.control-code")).toContainText('"target": "192.0.2.203"');
  await expect(page.getByText("Latest Firmware Validation Summary")).toBeVisible();
  await expect(
    page
      .locator("section")
      .filter({ hasText: "Latest Firmware Validation Summary" })
      .getByText("Firmware validation completed against the configured baseline.", { exact: true })
  ).toBeVisible();
});

test("firmware check blocks invalid current config before backend inventory", async ({ page }) => {
  const actionRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/lab/firmware-inventory") {
      actionRequests.push("firmware-check");
    }
  });

  await page.goto("/firmware");
  await page.getByRole("button", { name: "Check Firmware" }).click();

  await expect(page.getByText("Firmware check blocked").first()).toBeVisible();
  await expect(page.getByText("Target host, IP, or range is required.").first()).toBeVisible();
  expect(actionRequests).toEqual([]);

  await page.goto("/results");
  await expect(page.getByText("Firmware check blocked").first()).toBeVisible();
  await page.goto("/logs");
  await expect(page.getByText("Firmware check blocked").first()).toBeVisible();
});

test("firmware upgrade stays blocked after selection changes, failed validation, or config changes", async ({ page }) => {
  await page.goto("/configure");
  await page.getByLabel("Target host, IP, or range").fill("192.0.2.203");
  await page.getByRole("button", { name: "Save / apply config" }).click();

  await page.goto("/firmware");
  await page.getByLabel("Firmware path").selectOption(upgradePathValue);

  await page.getByRole("button", { name: "Validate Firmware" }).click();
  await expect(page.getByText("Firmware validation succeeded")).toBeVisible();

  await page.getByLabel("Require explicit operator confirmation before any firmware upgrade request is sent.").check();
  await page.getByLabel("Confirmation phrase").fill("UPGRADE ONTAP");
  await expect(page.getByRole("button", { name: "Start Firmware Upgrade" })).toBeEnabled();

  await page.getByLabel("Selected firmware, image, or version").fill("bad-image.tgz");
  await expect(page.getByRole("button", { name: "Start Firmware Upgrade" })).toBeDisabled();
  await expect(page.getByText("Validate firmware before starting an upgrade.")).toBeVisible();

  await page.getByRole("button", { name: "Validate Firmware" }).click();
  await expect(page.getByText("Firmware validation blocked")).toBeVisible();
  await expect(page.getByText("Firmware validation failed or is blocked. No override is supported.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Firmware Upgrade" })).toBeDisabled();

  await page.getByLabel("Selected firmware, image, or version").fill("ontap-9.14.1P1.tgz");
  await page.getByRole("button", { name: "Validate Firmware" }).click();
  await expect(page.getByText("Firmware validation succeeded")).toBeVisible();

  await page.goto("/configure");
  await page.getByLabel("Target host, IP, or range").fill("192.0.2.204");
  await page.getByRole("button", { name: "Save / apply config" }).click();
  await expect(page.getByText("Configuration saved")).toBeVisible();
  await page.goto("/firmware");

  await expect(page.getByRole("button", { name: "Start Firmware Upgrade" })).toBeDisabled();
  await expect(page.getByText("Validate firmware before starting an upgrade.")).toBeVisible();

  await page.goto("/logs");
  await expect(page.getByText("Config saved").first()).toBeVisible();
  await expect(page.getByText("Firmware validation blocked").first()).toBeVisible();
});

test("firmware upgrade stays disabled when no backend apply action exists", async ({ page }) => {
  const actionRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.includes("/api/v1/workflows/actions/") && url.pathname.endsWith("/run")) {
      actionRequests.push(url.pathname);
    }
  });

  await page.goto("/configure");
  await page.getByLabel("Target host, IP, or range").fill("192.0.2.203");
  await page.getByRole("button", { name: "Save / apply config" }).click();

  await page.goto("/firmware");
  await page.getByLabel("Firmware path").selectOption(hpeUpgradePathValue);
  await expect(page.getByLabel("Selected firmware, image, or version")).toHaveValue("ilo-2.91.fwpkg");
  await page.getByRole("button", { name: "Validate Firmware" }).click();
  await expect(page.getByText("Firmware validation succeeded")).toBeVisible();

  await page.getByLabel("Require explicit operator confirmation before any firmware upgrade request is sent.").check();
  await page.getByLabel("Confirmation phrase").fill("RUN FIRMWARE UPGRADE");

  await expect(page.getByRole("button", { name: "Start Firmware Upgrade" })).toBeDisabled();
  await expect(
    page.getByText("Backend firmware upgrade integration is pending for this selected firmware path.")
  ).toBeVisible();
  expect(actionRequests).toEqual([]);
});

test("firmware path selection persists before validation and still blocks upgrade", async ({ page }) => {
  await page.goto("/configure");
  await page.getByLabel("Target host, IP, or range").fill("192.0.2.203");
  await page.getByRole("button", { name: "Save / apply config" }).click();

  await page.goto("/firmware");
  await page.getByLabel("Firmware path").selectOption(hpeUpgradePathValue);
  await page.getByLabel("Selected firmware, image, or version").fill("");

  await page.reload();

  await expect(page.getByLabel("Firmware path")).toHaveValue(hpeUpgradePathValue);
  await expect(page.getByLabel("Selected firmware, image, or version")).toHaveValue("");
  await expect(page.getByRole("button", { name: "Validate Firmware" })).toBeDisabled();
  await expect(page.getByText("Selected firmware, image, or target version is required before validation.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Firmware Upgrade" })).toBeDisabled();

  await page.getByLabel("Selected firmware, image, or version").fill("ilo-2.91.fwpkg");
  await page.reload();

  await expect(page.getByLabel("Firmware path")).toHaveValue(hpeUpgradePathValue);
  await expect(page.getByLabel("Selected firmware, image, or version")).toHaveValue("ilo-2.91.fwpkg");
  await expect(page.getByRole("button", { name: "Validate Firmware" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Start Firmware Upgrade" })).toBeDisabled();
  await expect(page.getByText("Validate firmware before starting an upgrade.")).toBeVisible();
});

test("settings and logs remain top-level control-center pages", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { exact: true, name: "Settings" })).toBeVisible();
  await page.getByLabel("Default IP mode").selectOption("ipv6");
  await page.getByLabel("Default SNMP version").selectOption("v3");
  await page.getByLabel("Logging verbosity").selectOption("debug");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved")).toBeVisible();

  await page.getByLabel("Firmware repository/source").fill("token=not-allowed");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings must not contain secret-shaped values.")).toBeVisible();

  await page.goto("/logs");
  await expect(page.getByRole("heading", { name: "Logs" })).toBeVisible();
  await expect(page.getByText("Settings changed")).toBeVisible();
  await expect(page.getByText("Settings change failed")).toBeVisible();
});

async function installApiMocks(page: Page) {
  let controlConfig = controlCenterConfig();
  let controlSettings = controlCenterSettings();
  let selectedFirmwareFiles: Record<string, string> = {};

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname === "/health") {
      return json(route, {
        app: "infra-config-portal",
        dev_test_banner: null,
        expected_runtime_mode: "local-lab-readwrite",
        operator_runtime_mode: "real_lab",
        provider_mode: "local-readonly",
        status: "ok"
      });
    }

    if (!url.pathname.startsWith("/api/v1/")) {
      return route.continue();
    }

    if (url.pathname === "/api/v1/settings/provider-mode") {
      return json(route, providerModeSettings());
    }
    if (url.pathname === "/api/v1/providers/status") {
      return json(route, providerStatuses());
    }
    if (url.pathname === "/api/v1/workflows/actions") {
      return json(route, workflowActions());
    }
    if (url.pathname === "/api/v1/audit-events") {
      return json(route, auditEvents());
    }
    if (url.pathname === "/api/v1/control-center/config" && request.method() === "GET") {
      return json(route, controlConfig);
    }
    if (url.pathname === "/api/v1/control-center/config" && request.method() === "PUT") {
      controlConfig = controlCenterConfig(request.postDataJSON() as Partial<ControlCenterConfigMock>);
      return json(route, controlConfig);
    }
    if (url.pathname === "/api/v1/control-center/settings" && request.method() === "GET") {
      return json(route, controlSettings);
    }
    if (url.pathname === "/api/v1/control-center/settings" && request.method() === "PUT") {
      controlSettings = controlCenterSettings(
        request.postDataJSON() as Partial<ControlCenterSettingsMock>
      );
      return json(route, controlSettings);
    }
    if (url.pathname === "/api/v1/firmware/summary") {
      return json(route, firmwareSummaries());
    }
    if (url.pathname === "/api/v1/firmware/file-selections" && request.method() === "GET") {
      return json(route, firmwareFileSelections(selectedFirmwareFiles));
    }
    if (url.pathname === "/api/v1/firmware/file-selections" && request.method() === "PUT") {
      const payload = request.postDataJSON() as { selected_files?: Record<string, string> };
      selectedFirmwareFiles = payload.selected_files ?? {};
      return json(route, firmwareFileSelections(selectedFirmwareFiles));
    }
    if (url.pathname === "/api/v1/lab/firmware-inventory") {
      return json(route, firmwareInventory());
    }
    if (url.pathname === "/api/v1/lab/firmware-compliance") {
      return json(route, firmwareCompliance(selectedFirmwareFiles));
    }
    if (url.pathname === "/api/v1/providers/netapp-ontap/ontap-upgrade/validate" && request.method() === "POST") {
      return json(route, firmwareCompliance(selectedFirmwareFiles));
    }
    if (url.pathname === "/api/v1/workflows/actions/build-verification.run-full/run" && request.method() === "POST") {
      return json(route, workflowActionRun("build-verification.run-full", "Run Full Verification", "completed"));
    }
    if (url.pathname === "/api/v1/workflows/actions/netapp.ontap-upgrade-apply/run" && request.method() === "POST") {
      return json(route, workflowActionRun("netapp.ontap-upgrade-apply", "Upgrade ONTAP", "blocked"));
    }

    return json(route, {});
  });
}

function json(route: Route, body: unknown) {
  return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
}

function providerModeSettings() {
  return {
    current_mode: "local-readonly",
    desired_mode: "local-lab-readwrite",
    dev_test_banner: null,
    expected_runtime_mode: "local-lab-readwrite",
    mode_env_path: ".local/provider-mode.json",
    next_safe_action: "Restart the backend after changing provider mode.",
    options: [],
    pending_restart: false,
    restart_command: "make app-start",
    store_path: ".local/provider-mode.json",
    updated_at: checkedAt
  };
}

function providerStatuses() {
  return [
    {
      blockers: [],
      capabilities: ["status"],
      checked_at: checkedAt,
      configuration: {},
      disabled_actions: [],
      discovery: null,
      evidence_artifacts: [],
      freshness: "live",
      id: "firmware-compliance",
      is_current: true,
      is_operator_visible: true,
      kind: "firmware",
      last_probe_result: null,
      last_probe_time: null,
      message: "Firmware summary is available.",
      mode: "local-readonly",
      name: "Firmware",
      recheck_command: "make provider-lab-firmware-compliance",
      safe_actions: [],
      source_type: "cached_live",
      stale_after_seconds: 86400,
      status: "ready",
      ttl_seconds: 86400,
      warnings: []
    }
  ];
}

function controlCenterConfig(overrides: Partial<ControlCenterConfigMock> = {}): ControlCenterConfigMock {
  return {
    blockers: [],
    credential_storage: "presence_only",
    freshness: "live",
    ip_mode: "ipv4",
    retry_count: 1,
    snmp_credential_status: "missing",
    snmp_credential_version: null,
    snmp_version: "v2",
    source_type: "operator_config",
    store_path: ".local/control-center-state.json",
    target: "",
    timeout_seconds: 8,
    updated_at: checkedAt,
    warnings: [],
    ...overrides
  };
}

function controlCenterSettings(overrides: Partial<ControlCenterSettingsMock> = {}): ControlCenterSettingsMock {
  return {
    api_base_url: "same-origin",
    blockers: [],
    default_ip_mode: "ipv4",
    default_retry_count: 1,
    default_snmp_version: "v2",
    default_timeout_seconds: 8,
    firmware_repository: "Backend firmware repository integration pending",
    freshness: "live",
    logging_verbosity: "normal",
    source_type: "operator_config",
    store_path: ".local/control-center-state.json",
    updated_at: checkedAt,
    warnings: [],
    ...overrides
  };
}

function firmwareSummaries() {
  return [
    {
      apply_enabled: false,
      approved_versions: [{ label: "Approved", status: "approved", version: "2.90" }],
      blocker: null,
      compliance_status: "needs_upgrade",
      component_type: "management_firmware",
      current_versions: [
        { label: "iLO firmware", status: "needs_upgrade", version: "2.80" },
        { label: "Bootloader", status: "current", version: "1.1" }
      ],
      device_id: "ilo",
      disabled_reason: "Backend guarded apply action is not registered.",
      estimated_impact: "iLO firmware upgrade requires maintenance approval.",
      evidence_artifacts: ["artifacts/codex-runs/firmware-inventory-report.md"],
      freshness: "live",
      label: "HPE iLO",
      last_scanned: checkedAt,
      next_action: "Validate firmware evidence; upgrade remains disabled until backend apply exists.",
      package_available: true,
      package_name: "ilo-2.91.fwpkg",
      path_status: "direct",
      prechecks_required: ["iLO firmware prechecks"],
      reboot_required: false,
      required_intermediate_versions: [],
      scan_action_id: "ilo.firmware-inventory",
      severity: "yellow",
      source_type: "cached_live",
      target_version: "2.91",
      upgrade_center_link: "/firmware?device=ilo",
      upgrade_paths: [
        {
          apply_enabled: false,
          baseline_source: "real-lab.yml",
          candidate_files: [],
          component_id: "hpe_ilo_firmware",
          component_label: "iLO firmware",
          current_version: "2.80",
          device_label: "HPE iLO",
          disabled_reason: "Backend guarded apply action is not registered.",
          equipment_label: "Server",
          equipment_type: "management_firmware",
          estimated_impact: "iLO firmware upgrade requires maintenance approval.",
          evidence_artifacts: ["artifacts/codex-runs/firmware-inventory-report.md"],
          freshness: "live",
          last_checked: checkedAt,
          missing_evidence: [],
          next_action: "Validate firmware evidence; upgrade remains disabled until backend apply exists.",
          package_available: true,
          package_name: "ilo-2.91.fwpkg",
          package_version: "2.91",
          path_status: "direct",
          prechecks_required: ["iLO firmware prechecks"],
          reboot_required: true,
          required_intermediate_versions: [],
          scan_action_id: "ilo.firmware-inventory",
          selected_file_name: "ilo-2.91.fwpkg",
          selected_file_path: null,
          selection_source: "test",
          source_type: "cached_live",
          target_version: "2.91"
        }
      ]
    },
    {
      apply_enabled: true,
      approved_versions: [{ label: "Approved", status: "approved", version: "9.14.1P1" }],
      blocker: null,
      compliance_status: "needs_upgrade",
      component_type: "storage_os_and_component_firmware",
      current_versions: [{ label: "ONTAP", status: "needs_upgrade", version: "9.13.1" }],
      device_id: "netapp",
      disabled_reason: "",
      estimated_impact: "ONTAP upgrade requires a maintenance window.",
      evidence_artifacts: ["artifacts/codex-runs/netapp-upgrade-inventory-report.md"],
      freshness: "live",
      label: "NetApp ONTAP",
      last_scanned: checkedAt,
      next_action: "Validate ONTAP upgrade before apply.",
      package_available: true,
      package_name: "ontap-9.14.1P1.tgz",
      path_status: "direct",
      prechecks_required: ["ONTAP prechecks"],
      reboot_required: true,
      required_intermediate_versions: [],
      scan_action_id: "netapp.ontap-upgrade-inventory",
      severity: "yellow",
      source_type: "cached_live",
      target_version: "9.14.1P1",
      upgrade_center_link: "/firmware?device=netapp",
      upgrade_paths: [
        {
          apply_enabled: true,
          baseline_source: "real-lab.yml",
          candidate_files: [],
          component_id: "netapp_ontap_version",
          component_label: "ONTAP",
          current_version: "9.13.1",
          device_label: "NetApp ONTAP",
          disabled_reason: "",
          equipment_label: "Cluster",
          equipment_type: "storage_os",
          estimated_impact: "ONTAP upgrade requires a maintenance window.",
          evidence_artifacts: ["artifacts/codex-runs/netapp-upgrade-inventory-report.md"],
          freshness: "live",
          last_checked: checkedAt,
          missing_evidence: [],
          next_action: "Validate ONTAP upgrade before apply.",
          package_available: true,
          package_name: "ontap-9.14.1P1.tgz",
          package_version: "9.14.1P1",
          path_status: "direct",
          prechecks_required: ["ONTAP prechecks"],
          reboot_required: true,
          required_intermediate_versions: [],
          scan_action_id: "netapp.ontap-upgrade-inventory",
          selected_file_name: "ontap-9.14.1P1.tgz",
          selected_file_path: null,
          selection_source: "test",
          source_type: "cached_live",
          target_version: "9.14.1P1"
        }
      ]
    }
  ];
}

function firmwareFileSelections(selectedFiles: Record<string, string> = { netapp_ontap_version: "ontap-9.14.1P1.tgz" }) {
  return {
    apply_enabled: false,
    blockers: [],
    checked_at: checkedAt,
    freshness: "live",
    message: "File selections loaded.",
    next_safe_action: "Validate firmware before apply.",
    provider_id: "firmware-file-selections",
    selected_files: selectedFiles,
    source_type: "local_state",
    status: "ready",
    store_path: ".local/firmware-file-selections.json",
    updated_at: checkedAt,
    warnings: []
  };
}

function firmwareInventory() {
  return {
    blockers: [],
    checked_at: checkedAt,
    freshness: "live",
    message: "Firmware inventory loaded from backend summary.",
    provider_id: "firmware-compliance",
    report_artifacts: ["artifacts/codex-runs/firmware-inventory-report.md"],
    source_type: "cached_live",
    status: "ok",
    warnings: []
  };
}

function firmwareCompliance(selectedFiles: Record<string, string> = {}) {
  const selectedFirmware = Object.values(selectedFiles).join(" ");
  if (/bad/i.test(selectedFirmware)) {
    return {
      blockers: ["Selected firmware package failed baseline validation."],
      checked_at: checkedAt,
      freshness: "live",
      message: "Firmware validation failed against the configured baseline.",
      provider_id: "firmware-compliance",
      report_artifacts: ["artifacts/codex-runs/firmware-compliance-report.md"],
      source_type: "cached_live",
      status: "blocked",
      warnings: []
    };
  }

  return {
    blockers: [],
    checked_at: checkedAt,
    freshness: "live",
    message: "Firmware validation completed against the configured baseline.",
    provider_id: "firmware-compliance",
    report_artifacts: ["artifacts/codex-runs/firmware-compliance-report.md"],
    source_type: "cached_live",
    status: "needs_upgrade",
    warnings: ["NetApp ONTAP requires upgrade review."]
  };
}

function workflowActions() {
  return [
    workflowAction({
      action_id: "build-verification.run-full",
      category: "verify",
      label: "Run Full Verification",
      mode: "read_only",
      provider: "build-verification",
      source_type: "make_target",
      ui_run_supported: true
    }),
    workflowAction({
      action_id: "netapp.ontap-upgrade-apply",
      category: "upgrade",
      label: "Upgrade ONTAP",
      mode: "upgrade",
      provider: "netapp",
      required_confirmations: ["UPGRADE ONTAP"],
      required_gates: ["NETAPP_ONTAP_UPGRADE_APPLY=true"],
      source_type: "make_target",
      ui_run_supported: false
    })
  ];
}

function workflowAction(overrides: Record<string, unknown>) {
  return {
    action_id: "placeholder",
    api_endpoint: null,
    api_method: null,
    blockers: [],
    category: "verify",
    command: "make provider-lab-build-verification",
    current_availability: "available",
    description: "Mocked workflow action.",
    evidence_artifacts: [],
    guarded_run_blockers: [],
    guarded_run_supported: false,
    inputs: [],
    label: "Action",
    last_run_report: null,
    last_run_status: "not_run",
    last_run_trace: {
      action_id: "placeholder",
      blockers: [],
      command: null,
      finished_at: null,
      freshness: "not_checked",
      next_action: "Run action.",
      report_artifacts: [],
      run_id: "none",
      source_type: "not_checked",
      stage_id: "build-verification",
      started_at: null,
      status: "not_run",
      summary: "No run yet.",
      warnings: []
    },
    mode: "read_only",
    next_action: "Run action.",
    outputs: [],
    provider: "build-verification",
    reports: [],
    required_confirmations: [],
    required_credentials: [],
    required_gates: [],
    required_mode: "local-readonly",
    run_endpoint: "",
    runs_endpoint: "",
    safety_notes: [],
    source_type: "make_target",
    stage: "build-verification",
    stage_label: "Build Verification",
    stale_after_seconds: 86400,
    ui_run_blockers: [],
    ui_run_supported: true,
    ...overrides
  };
}

function workflowActionRun(actionId: string, label: string, status: "blocked" | "completed") {
  const blocked = status === "blocked";
  return {
    action_id: actionId,
    action_label: label,
    blockers: blocked ? ["guarded workflow is blocked by current action policy."] : [],
    checked_at: checkedAt,
    command: blocked ? "make provider-lab-netapp-ontap-upgrade-apply" : "make provider-lab-build-verification",
    executed: !blocked,
    finished_at: checkedAt,
    freshness: "current",
    mode: blocked ? "upgrade" : "read_only",
    next_action: blocked ? "Review guarded workflow gates." : "Review evidence artifacts, then continue.",
    not_mock: true,
    report_artifacts: blocked ? [] : ["artifacts/codex-runs/build-verification-report.md"],
    return_code: blocked ? null : 0,
    run_id: `workflow-action:${actionId}:test`,
    source_type: "live_probe",
    stage_id: blocked ? "netapp" : "build-verification",
    stage_label: blocked ? "NetApp" : "Build Verification",
    started_at: checkedAt,
    status,
    stderr_summary: "",
    stdout_summary: blocked ? "" : "verification passed",
    summary: blocked
      ? "Guarded action was not run because required gates were not satisfied."
      : "Safe read-only/report-only action completed.",
    trace_artifact: null,
    warnings: []
  };
}

function auditEvents() {
  return [
    {
      actor: "system",
      created_at: checkedAt,
      data_json: {},
      event_type: "backend_ready",
      from_status: null,
      id: "audit-1",
      message: "Backend audit log loaded.",
      request_id: null,
      to_status: "ready",
      workflow_run_id: null
    }
  ];
}
