import { expect, test, type Page } from "@playwright/test";

// Build my kit: Welcome -> Check -> Settings -> Ready -> Installing -> Finish. Fixture data only.
async function open(page: Page) {
  await page.route("**/kit-installer-fixture", r => r.fulfill({ contentType: "text/html", body: `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/kitInstallerHarness.tsx');</script></body></html>` }));
  await page.goto("/kit-installer-fixture");
}

function mockLab(page: Page, opts: { volumes?: boolean } = {}) {
  const s = { scope: "read_only", sent: [] as string[], esxi: "not_started", esxiChecks: 0, test: "not_started", testTicks: 0, volumes: !!opts.volumes, preflightFail: false, image: "win2022.ova" };
  const esxi = () => ({ state: s.esxi, active: s.esxi === "installing", message: s.esxi === "verified" ? "ESXi verified." : "Installing ESXi…", phases: {} });
  const test = () => ({ state: s.test, active: s.test === "running", message: s.test === "verified" ? "Acceptance test passed." : "Testing…", lookup: "esx01.lab.test", default_lookup: "esx01.lab.test",
    signin: { username: "Administrator", password_saved: true }, phases: [{ phase: "outside", label: "Windows answers from outside", state: s.test === "verified" ? "ok" : "running", message: null, checks: [] }] });
  return page.route("**/api/**", async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname, method = req.method();
    if (method !== "GET") s.sent.push(`${method} ${path.replace(/^\/api\/v1\/(rack-plans\/fixture\/|runtime\/|providers\/)?/, "")}`);
    const json = (body: unknown) => route.fulfill({ json: body });
    if (path === "/api/v1/rack-plans/fixture") return json({ revision: 1, rack_units: 4, equipment: [
      { id: "s", device_id: "srv", name: "HPE DL360 3", kind: "server", model: "HPE DL360 Gen10", position: 2, height: 1, mount: "rack", ports: 0, bay_count: 10, occupied_bays: [] },
      { id: "w", device_id: "sw", name: "Cisco switch 1", kind: "switch", model: "Catalyst 9300", position: 1, height: 1, mount: "rack", ports: 24, bay_count: 0, occupied_bays: [] }] });
    if (path.endsWith("/preflight")) return json({ state: s.preflightFail ? "fail" : "ok", checked_at: "2026-10-16T10:00:00Z", items: [
      { group: "Server", name: "iLO sign-in", state: "ok", detail: "saved", fix: null },
      { group: "Media", name: "Windows image", state: s.preflightFail ? "fail" : "ok", detail: s.preflightFail ? "missing" : s.image, fix: "Add it on Install Windows." }] });
    if (path.endsWith("/esxi/settings")) return json({ hostname: "esx01", addressing: "static", management_ip: "192.0.2.20", vlan_id: 0, management_nic: "vmnic0", datastore_name: "VMdata", password_set: true, signin_ready: true, saved_at: null,
      data_volume: { raid: "RAID 5", bays: [3, 4, 5], capacity_bytes: 3e12 }, boot_volume: { bays: [1, 2], capacity_bytes: 2.4e11 },
      kit: { profile_id: "fixture", profile_version: 1, saved_profile: true, subnet: "192.0.2.0/24", gateway: "192.0.2.1", dns: ["192.0.2.53"], ntp_enabled: false, ntp: [], domain_name: "lab.test", esxi_management: null, single_server_local: true } });
    if (path.endsWith("/windows/setup")) return json({ images: [], image: "win2022.ova", vm_name: "windows01", datastore: "VMdata", network: "VM Network", saved_at: "x", host: { address: "192.0.2.20", datastores: [], networks: [], problem: null, default_datastore: "VMdata" } });
    if (path.endsWith("/switch-setup/setup")) return json({ settings: { hostname: "lab-sw01", domain: "lab.test", vlan: 1, mode: "dhcp", address: null, prefix: 24, gateway: null, save: true }, defaults: {}, username: "admin", password_configured: true, enable_password_configured: false, console: { port: "COM5", baud: 9600, last: null } });
    if (path === "/api/v1/providers/ilo-redfish/probe") return json({ status: "ok", message: "iLO answered." });
    if (path.endsWith("/switch-setup/status")) return json({ state: "verified", active: false, message: "lab-sw01 answers SSH.", phases: [] });
    if (path.endsWith("/parts-update/status")) return json({ state: "not_started", active: false, message: "", parts: [], phases: [] });
    if (path.endsWith("/parts-update/review")) return json({ review_id: "r1", digest: "d", package: "SPP", parts: [], elsewhere: [], phases: [], restarts: 0, minutes: 0, power: null, blockers: [], expires_at: "2099-01-01T00:00:00Z" });
    if (path.endsWith("/firmware-update/status")) return json({ status: "not_started", active: false, steps: [], message: "", current_step: null, next_action: null, evidence_at: null, operation_id: null, idempotency_key: null, profile_id: "fixture", device_id: "srv" });
    if (path.endsWith("/firmware-update/plan")) return json({ can_apply: false, review_token: null, confirmation_phrase: null, updates: [], blockers: [], warnings: [], not_included: [] });
    if (path.endsWith("/raid-rebuild/status")) return json(s.volumes ? { operation: null, status: "not_started" } : { operation: "create", status: "verified" });
    if (path.endsWith("/disk-preparation")) return json({ blockers: [], volumes: [{ name: "old" }] });
    if (path.endsWith("/esxi/install") && method === "GET") return json(esxi());
    if (path.endsWith("/esxi/installer")) return json({ status: "ready", blockers: [], built: null });
    if (path.endsWith("/esxi/install") && method === "POST") { s.esxi = "installing"; return json(esxi()); }
    if (path.endsWith("/esxi/install/check")) { if (++s.esxiChecks >= 2) s.esxi = "verified"; return json(esxi()); }
    if (path.endsWith("/windows/status")) return json({ state: "verified", active: false, message: "", phases: [] });
    if (path.endsWith("/windows/acceptance")) return json(test());
    if (path.endsWith("/windows/acceptance/start")) { s.test = "running"; return json(test()); }
    if (path.endsWith("/windows/acceptance/advance")) { if (++s.testTicks >= 2) s.test = "verified"; return json(test()); }
    if (path.endsWith("/handover")) return json({ kit: "Test kit", generated_at: "2026-10-16T12:00:00Z", network: { subnet: "192.0.2.0/24", gateway: "192.0.2.1", dns: ["192.0.2.53"], domain: "lab.test" },
      servers: [{ name: "HPE DL360 3", model: "HPE DL360 Gen10", observed_at: null, ilo: { address: "192.0.2.10" }, health: null, boot_disks: null, data_disks: null,
        esxi: { state: "verified", host_name: "esx01", address: "192.0.2.20", verified_at: "2026-10-16T11:00:00Z" }, windows: { state: "verified", vm: "windows01", address: "192.0.2.77", os: "Windows Server 2022", verified_at: null },
        acceptance: { state: "verified", finished_at: "2026-10-16T11:30:00Z" } }],
      switches: [{ name: "Cisco switch 1", model: "Catalyst 9300", address: "192.0.2.2", username: "admin", software: "17.15.5", serial: "FOC0000X000", checked_at: "2026-10-16T11:40:00Z", check_status: "ok", console: "COM5",
        config: { before: "hostname Switch", after: "hostname lab-sw01\nenable secret 9 ********", at: "2026-10-16T11:35:00Z", outcome: "ok", diff: ["--- before setup", "+++ after setup", "@@ -1 +1,2 @@", "-hostname Switch", "+hostname lab-sw01", "+enable secret 9 ********"] } }],
      cables: null, verified: [] });
    if (path.endsWith("/runtime/write-scope/preview")) return json({ review_token: "t", current_scope: s.scope, target_scope: req.postDataJSON().target_scope, confirmation_phrase: "", blockers: [], expires_at: "2099-01-01T00:00:00Z" });
    if (path.endsWith("/runtime/write-scope/apply")) { s.scope = s.scope === "read_only" ? "changed" : "read_only"; return json({ scope: s.scope, active_operations: [], blockers: [] }); }
    if (path.endsWith("/runtime/write-scope")) return json({ scope: s.scope, active_operations: [], blockers: [] });
    return route.fulfill({ status: 404, json: { detail: "unexpected " + method + " " + path } });
  }).then(() => s);
}

test("one approval builds the kit: done steps skipped, ESXi and the test run, finish shows everything", async ({ page }) => {
  test.setTimeout(60000);
  const s = await mockLab(page);
  await open(page);
  await expect(page.getByRole("heading", { name: "Welcome" })).toBeVisible({ timeout: 20000 });
  await expect(page.getByText("HPE DL360 3")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("list", { name: "Pre-flight" })).toContainText("Windows image");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.locator(".ki-settings")).toContainText("esx01 · 192.0.2.20 · datastore VMdata");
  await expect(page.locator(".ki-settings")).toContainText("windows01 · win2022.ova");
  await page.getByRole("button", { name: "Next" }).click();
  const install = page.getByRole("button", { name: "Install" });
  await expect(install).toBeDisabled();
  expect(s.sent).toEqual([]);  // nothing sent before the approval
  await page.getByRole("checkbox").check();
  await install.click();
  await expect(page.getByRole("heading", { name: "Your kit is built" })).toBeVisible({ timeout: 30000 });
  await expect(page.getByText(/^Passed/)).toBeVisible();
  const config = page.locator("details.ho-config");
  await expect(config.locator("summary")).toContainText("3 lines changed");
  await config.locator("summary").click();
  await expect(page.getByLabel("What the setup changed")).toContainText("+hostname lab-sw01");
  await expect(page.getByLabel("Running configuration")).toContainText("enable secret 9 ********");
  expect(s.sent.filter(x => x === "POST esxi/install")).toHaveLength(1);
  expect(s.sent.filter(x => x.includes("acceptance/start"))).toHaveLength(1);
  expect(s.sent.some(x => x.includes("raid-rebuild/apply") || x.includes("switch-setup/start") || x.includes("windows/start"))).toBe(false);
  expect(s.scope).toBe("read_only");
});

test("a red pre-flight item blocks the install", async ({ page }) => {
  const s = await mockLab(page);
  s.preflightFail = true;
  await open(page);
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("alert")).toContainText("Fix the red item");
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();
});

test("existing RAID volumes stop the install with where to go; Try again carries on", async ({ page }) => {
  test.setTimeout(60000);
  const s = await mockLab(page, { volumes: true });
  await open(page);
  for (let i = 0; i < 3; i++) await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Install" }).click();
  const stop = page.getByRole("alert");
  await expect(stop).toContainText("already has RAID volumes");
  await expect(stop.getByRole("link", { name: "Open Disks & RAID" })).toBeVisible();
  expect(s.sent.some(x => x.includes("raid-rebuild"))).toBe(false);
  s.volumes = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Your kit is built" })).toBeVisible({ timeout: 30000 });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  }
});

async function stopAtRaid(page: Page) {
  const s = await mockLab(page, { volumes: true });
  await open(page);
  await expect(page.getByRole("heading", { name: "Welcome" })).toBeVisible({ timeout: 20000 });
  for (let i = 0; i < 3; i++) await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Install" }).click();
  await expect(page.getByRole("alert")).toContainText("already has RAID volumes");
  return s;
}

test("opening the installer again never starts anything by itself", async ({ page }) => {
  test.setTimeout(60000);
  const s = await stopAtRaid(page);
  const before = s.sent.length;
  await page.reload();
  await expect(page.getByRole("heading", { name: "Paused" })).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(500);
  expect(s.sent.length).toBe(before);
  s.volumes = false;
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Your kit is built" })).toBeVisible({ timeout: 30000 });
});

test("a plan changed after the approval needs a new approval", async ({ page }) => {
  test.setTimeout(60000);
  const s = await stopAtRaid(page);
  s.volumes = false;
  s.image = "other-image.ova";
  const before = s.sent.length;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Check" })).toBeVisible();
  await expect(page.getByText("Something in the plan changed since you approved it.")).toBeVisible();
  expect(s.sent.length).toBe(before);
});
