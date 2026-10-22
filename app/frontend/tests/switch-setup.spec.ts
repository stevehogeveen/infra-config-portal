import { expect, test, type Page } from "@playwright/test";

// Switch: 1 console cable (COM port), 2 first setup over the console, 3 SSH check. Documentation addresses only.
const PASSWORD = "Fixture-Pass-1";

async function open(page: Page) {
  await page.route("**/switch-setup-fixture", r => r.fulfill({ contentType: "text/html", body: `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/switchSetupHarness.tsx');</script></body></html>` }));
  await page.goto("/switch-setup-fixture");
}

function mockApi(page: Page) {
  const state = { settings: null as any, password: false, read: null as any, step: -1, scope: "read_only", sent: [] as string[], access: { username: null as string | null, password_configured: false, host: null as string | null } };
  const phases = () => [
    { phase: "configure", label: "Set up lab-sw01 over the console (COM5)", state: state.step >= 1 ? "ok" : "sent", message: null },
    { phase: "verify", label: "lab-sw01 answers SSH at its new address", state: state.step >= 2 ? "ok" : state.step >= 1 ? "sent" : "todo", message: null },
  ];
  const run = () => state.step < 0 ? { state: "not_started", active: false, phases: [], message: "" }
    : state.step >= 2 ? { state: "verified", active: false, phases: phases(), message: "lab-sw01 answers SSH at 192.0.2.50.", address: "192.0.2.50", saved: true, model: "C9300-48T", version: "16.12.04" }
    : { state: "running", active: true, phases: phases(), message: "Setting the switch up…", step: "configuring" };
  return page.route("**/api/**", async route => {
    const req = route.request(), path = new URL(req.url()).pathname, method = req.method();
    if (method !== "GET") state.sent.push(`${method} ${path.replace(/^.*\/(switch-setup|switch-console|switch-access|runtime)\//, "$1/")}`);
    if (path.endsWith("/switch-console/ports")) return route.fulfill({ json: { helper_running: true, bauds: [9600, 115200], saved_port: null, saved_baud: null, problem: null, ports: [
      { port: "COM3", candidate_fingerprint: "f3", description: "Intel(R) Active Management Technology - SOL", manufacturer: "Intel", usb: false, hint: "Built into this PC, not a console cable", recommended: false, recommended_bauds: [9600] },
      { port: "COM5", candidate_fingerprint: "f5", description: "Prolific USB-to-Serial Comm Port", manufacturer: "Prolific", usb: true, hint: "USB console cable", recommended: true, recommended_bauds: [9600] }] } });
    if (path.endsWith("/switch-console/identify")) {
      state.read = { port: "COM5", baud: 9600, answered: true, identity_verified: false, prompt_state: "setup-wizard", state_text: "The switch is new: it is waiting at its first-setup questions. The app sets it up from here.", model: null, version: null, message: null, checked_at: new Date().toISOString() };
      return route.fulfill({ json: state.read });
    }
    if (path.endsWith("/switch-access")) {
      if (method === "PUT") { const body = req.postDataJSON(); state.access = { username: body.username ?? state.access.username, password_configured: state.access.password_configured || !!body.password, host: body.host ?? state.access.host }; }
      return route.fulfill({ json: { device_id: "sw", host: state.access.host, username: state.access.username, username_configured: !!state.access.username, password_configured: state.access.password_configured, enable_password_configured: false, updated_at: null, last_check: null, console: { port: null, baud: null, last: state.read } } });
    }
    if (path.endsWith("/switch-setup/setup")) {
      if (method === "PUT") {
        const { password, enable_password: _enable, username, ...rest } = req.postDataJSON();
        state.password = state.password || !!password;
        state.settings = { ...rest, username };
      }
      const settings = state.settings ? (({ username: _u, ...rest }) => rest)(state.settings) : null;
      return route.fulfill({ json: { settings, username: state.settings?.username ?? null, password_configured: state.password, enable_password_configured: false,
        defaults: { hostname: "cisco-switch-1", domain: "lab.local", vlan: 1, mode: "dhcp", address: null, prefix: 24, gateway: null, save: true, username: "admin" }, console: { port: null, baud: null, last: state.read } } });
    }
    if (path.endsWith("/switch-setup/review")) return route.fulfill({ json: { ready: true, blockers: [], permission: [], console_port: "COM5", baud: 9600, hostname: "lab-sw01", vlan: 1, mode: "dhcp", address: null, prefix: 24, gateway: null, username: "admin", save: true,
      preview: ["configure terminal", " hostname lab-sw01", " username admin privilege 15 secret ********", " interface Vlan1", " ip address dhcp", "end", "write memory"] } });
    if (path.endsWith("/switch-setup/status")) return route.fulfill({ json: run() });
    if (path.endsWith("/switch-setup/start")) { state.step = 0; return route.fulfill({ json: run() }); }
    if (path.endsWith("/switch-setup/advance")) { state.step += 1; return route.fulfill({ json: run() }); }
    if (path.endsWith("/runtime/write-scope/preview")) { const target = req.postDataJSON().target_scope; return route.fulfill({ json: { review_token: "t", current_scope: state.scope, target_scope: target, confirmation_phrase: "", blockers: [], expires_at: new Date(Date.now() + 6e5).toISOString() } }); }
    if (path.endsWith("/runtime/write-scope/apply")) { state.scope = state.scope === "read_only" ? "switch_setup_only" : "read_only"; return route.fulfill({ json: { scope: state.scope, active_operations: [], blockers: [] } }); }
    if (path.endsWith("/runtime/write-scope")) return route.fulfill({ json: { scope: state.scope, active_operations: [], blockers: [] } });
    return route.fulfill({ status: 404, json: { detail: "unexpected " + path } });
  }).then(() => state);
}

test("pick the COM port, read the switch, save settings, then one window sets it up and proves SSH", async ({ page }) => {
  test.setTimeout(90000);
  const state = await mockApi(page);
  await open(page);
  const ports = page.getByRole("radiogroup", { name: "COM port" });
  await expect(ports.getByRole("radio", { name: /COM5/ })).toHaveAttribute("aria-checked", "true", { timeout: 15_000 });
  await expect(page.getByText(/Setup is waiting for step 1.*Choose COM5/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Set up the switch" })).toBeDisabled();
  await page.getByRole("button", { name: "Read the switch" }).click();
  await expect(page.getByText("The switch is new")).toBeVisible();
  expect(state.sent).toEqual(["POST switch-console/identify"]);

  await page.getByLabel("Switch name").fill("lab-sw01");
  await page.getByLabel("Admin password").fill(PASSWORD);
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved. Nothing was sent to the switch.")).toBeVisible();
  const setUp = page.getByRole("button", { name: "Set up the switch" });
  await expect(setUp).toBeEnabled();
  await setUp.click();

  const box = page.getByRole("dialog", { name: "Set up Cisco switch 1" });
  await expect(box.getByRole("heading", { name: "Ready to set up" })).toBeVisible();
  await box.getByText("What is sent to the switch").click();
  await expect(box.locator("pre")).toContainText("secret ********");
  await expect(box.locator("pre")).not.toContainText(PASSWORD);
  await box.getByRole("checkbox").check();
  await box.getByRole("button", { name: "Set up the switch" }).click();
  await expect(box.getByRole("heading", { name: "Complete" })).toBeVisible({ timeout: 40000 });
  await expect(box).toContainText("C9300-48T");
  await expect(box).toContainText("Settings saved on the switch");
  await box.getByRole("button", { name: "Done" }).click();
  await expect(box).toHaveCount(0);
  expect(state.scope).toBe("read_only");
  expect(state.sent.filter(s => s === "POST switch-setup/start")).toHaveLength(1);
});

test("fits a phone", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 900 });
  await open(page);
  await expect(page.getByRole("radiogroup", { name: "COM port" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test("with DHCP the sign-in saves without an address and no SSH check is attempted", async ({ page }) => {
  const state = await mockApi(page);
  await open(page);
  const card = page.getByRole("region", { name: "Management address" });
  await expect(card.getByLabel("Switch address")).not.toHaveAttribute("required", /.*/);
  await card.getByLabel("Switch username").fill("admin");
  await card.getByLabel("Switch password").fill(PASSWORD);
  await card.getByRole("button", { name: "Save sign-in" }).click();
  await expect(card.getByRole("status")).toContainText("The switch has no address yet");
  expect(state.sent.some(s => /^PUT .*switch-access$/.test(s))).toBe(true);
  expect(state.sent.some(s => s.includes("switch-access/check"))).toBe(false);
  await expect(card.getByRole("button", { name: "Saved" })).toBeVisible();
});
