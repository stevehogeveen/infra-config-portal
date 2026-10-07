import { expect, test } from "@playwright/test";

test("defaults track edits, reset, failure and successful save without hardware calls", async ({ page }) => {
  let fail = true;
  const writes: Record<string, any>[] = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/v1/lab/profiles/fixture") {
      writes.push(request.postDataJSON());
      return route.fulfill({ status: fail ? 503 : 200, json: fail ? { detail: "Fixture save unavailable" } : {} });
    }
    throw new Error(`Unexpected API request: ${request.method()} ${request.url()}`);
  });
  await page.route("**/defaults-test", (route) => route.fulfill({
    contentType: "text/html",
    body: `<html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root" class="app-shell-workbench"></div>
    <script type="module">
      import RefreshRuntime from "/@react-refresh";
      RefreshRuntime.injectIntoGlobalHook(window);
      window.$RefreshReg$ = () => {};
      window.$RefreshSig$ = () => (type) => type;
      window.__vite_plugin_react_preamble_installed__ = true;
      const {default: React} = await import("/node_modules/.vite/deps/react.js");
      const {default: ReactDOM} = await import("/node_modules/.vite/deps/react-dom_client.js");
      const {MemoryRouter} = await import("/node_modules/.vite/deps/react-router-dom.js");
      const {OperatorLabDefaultsPage} = await import("/src/operatorPages.tsx");
      await import("/src/styles.css");
      await import("/src/workbenchTheme.css");
      const profile = {id: "fixture", name: "Test kit", source: "saved", version: 1,
        description: "", profile_topology: "single-server", subnet_cidr: "192.0.2.0/24",
        features: {storage_protocol: "local", enable_dns: true, enable_ntp: true},
        devices: {}, address_plan: {subnet: "192.0.2.0/24", ilo: "192.0.2.140", esxi_management: "192.0.2.141", ilo_initial: "198.51.100.17", netapp_iscsi_lifs: [], netapp_nfs_lifs: []},
        resolved_address_plan: {subnet: "192.0.2.0/24", ilo: "192.0.2.140", esxi_management: "192.0.2.141", ilo_initial: "198.51.100.17", netapp_iscsi_lifs: [], netapp_nfs_lifs: []},
        global_settings: {dns_servers: [], ntp_servers: [], gateway: "192.0.2.1"}};
      ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(MemoryRouter, null,
        React.createElement(OperatorLabDefaultsPage, {labProfileState: {active_profile: profile}})));
    </script></body></html>`
  }));
  await page.goto("/defaults-test");
  for (const [toggle, field, add, extra] of [
    ["Enable NTP", "NTP server 1", "Add NTP server", "Timezone"],
    ["Enable SNMP", "SNMP manager 1", "Add SNMP manager", "SNMP version"],
  ]) {
    await page.getByLabel(toggle, { exact: true }).check();
    await page.getByLabel(field, { exact: true }).fill("192.0.2.20");
    await page.getByRole("button", { name: add, exact: true }).click();
    const section = page.getByLabel(field, { exact: true }).locator("xpath=ancestor::section[1]");
    await page.getByLabel(toggle, { exact: true }).uncheck();
    await expect(page.getByLabel(field, { exact: true })).toBeDisabled();
    await expect(page.getByLabel(field, { exact: true })).toHaveCSS("background-color", "rgb(237, 241, 243)");
    await expect(page.getByLabel(extra, { exact: true })).toBeDisabled();
    for (const button of await section.getByRole("button").all()) await expect(button).toBeDisabled();
    await page.getByLabel(toggle, { exact: true }).check();
    await expect(page.getByLabel(field, { exact: true })).toBeEnabled();
    await expect(page.getByLabel(field, { exact: true })).toHaveValue("192.0.2.20");
    await expect(page.getByLabel(extra, { exact: true })).toBeEnabled();
  }
  await page.getByRole("button", { name: "Reset changes" }).click();
  const save = page.getByRole("button", { name: "Save defaults", exact: true });
  await expect(save).toBeDisabled();
  await page.getByLabel("Domain name", { exact: true }).fill("example.test");
  await expect(page.getByText("Unsaved changes", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Reset changes" }).click();
  await expect(page.getByLabel("Domain name", { exact: true })).toHaveValue("");
  await expect(save).toBeDisabled();
  await page.getByLabel("DNS server 1", { exact: true }).fill("192.0.2.53");
  await page.getByLabel("Domain name", { exact: true }).fill("example.test");
  await page.getByLabel("Timezone", { exact: true }).fill("Etc/UTC");
  await save.click();
  await expect(page.getByRole("alert")).toContainText("Fixture save unavailable");
  await expect(page.getByLabel("Domain name", { exact: true })).toHaveValue("example.test");
  fail = false;
  await save.click();
  await expect(page.getByRole("status")).toContainText("Lab defaults saved");
  await expect(save).toBeDisabled();
  expect(writes).toHaveLength(2);
  expect(writes[1].global_settings).toMatchObject({ domain_name: "example.test", timezone: "Etc/UTC", dns_servers: ["192.0.2.53"] });
  expect(writes[1].address_plan.ilo_initial).toBe("198.51.100.17");
  await expect(page.getByText("Existing server access", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Initial iLO connection", exact: true })).toHaveCount(0);
  for (const subnet of ["198.51.100.0/23", "198.51.100.128/27"]) {
    await page.getByLabel("Subnet", { exact: true }).fill(subnet);
    await save.click();
    await expect(save).toBeDisabled();
    expect(writes.at(-1)?.address_plan).toMatchObject({ subnet, ilo: "192.0.2.140", esxi_management: "192.0.2.141", ilo_initial: "198.51.100.17" });
    expect(writes.at(-1)?.gateway).toBe("192.0.2.1");
  }
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: `test-results/defaults-tested-${width}.png`, fullPage: true });
  }
});
