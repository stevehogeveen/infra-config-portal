import { expect, test, type Page } from "@playwright/test";

// Reset for the next person: locked until typed; switch erase needs its own typed name. Fixture data only.
async function open(page: Page) {
  await page.route("**/reset-page-fixture", r => r.fulfill({ contentType: "text/html", body: `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/resetPageHarness.tsx');</script></body></html>` }));
  await page.goto("/reset-page-fixture");
}

function mockApi(page: Page, opts: { enabled?: boolean } = {}) {
  const state = { step: -1, scope: "read_only", sent: [] as string[], applied: [] as string[], signins: ["ESXi root password", "Windows administrator sign-in"], startBody: null as any };
  const reset = () => {
    const phases = [
      { phase: "erase", label: "Erase Cisco switch 1's settings over the console (COM5)", state: state.step >= 1 ? "ok" : "sent", message: null },
      { phase: "restart", label: "Cisco switch 1 starts again as a new switch", state: state.step >= 2 ? "ok" : state.step >= 1 ? "sent" : "todo", message: null },
    ];
    if (state.step < 0) return { state: "not_started", active: false, phases: [], message: "", name: "Cisco switch 1" };
    if (state.step >= 2) return { state: "verified", active: false, phases, message: "Cisco switch 1 is back to factory settings.", name: "Cisco switch 1" };
    return { state: "running", active: true, phases, message: "Erasing the switch…", name: "Cisco switch 1", step: "erasing the saved settings" };
  };
  const summary = () => ({ enabled: opts.enabled ?? true, forget_phrase: "FORGET SIGN-INS",
    servers: [{ device_id: "srv", name: "HPE DL360 3", model: "HPE DL360 Gen10", erases: ["Every RAID volume on its disks", "Then each disk is securely erased (can take hours)"], signins: state.signins }],
    switches: [{ device_id: "sw", name: "Cisco switch 1", model: "Catalyst 9300", console_port: "COM5", erases: ["Its saved settings (startup configuration)", "Its VLAN database (vlan.dat)"], reset: reset(), signins: [] }] });
  return page.route("**/api/**", async route => {
    const req = route.request(), path = new URL(req.url()).pathname, method = req.method();
    if (method !== "GET") state.sent.push(`${method} ${path.replace(/^.*\/(switch-reset|reset|runtime)\//, "$1/")}`);
    if (path.endsWith("/reset")) return route.fulfill({ json: summary() });
    if (path.endsWith("/reset/forget-signins")) { expect(req.postDataJSON()).toEqual({ confirmation: "FORGET SIGN-INS" }); const removed = state.signins.map(x => `HPE DL360 3: ${x}`); state.signins = []; return route.fulfill({ json: { ...summary(), removed } }); }
    if (path.endsWith("/switch-reset/review")) return route.fulfill({ json: { ready: true, blockers: [], permission: [], name: "Cisco switch 1", phrase: "ERASE Cisco switch 1", console_port: "COM5", baud: 9600, model: "C9300-48T", serial: "FOC0000X000", prompt_state: "exec", erases: ["Its saved settings (startup configuration)"] } });
    if (path.endsWith("/switch-reset/start")) { state.startBody = req.postDataJSON(); state.step = 0; return route.fulfill({ json: reset() }); }
    if (path.endsWith("/switch-reset/advance")) { state.step += 1; return route.fulfill({ json: reset() }); }
    if (path.endsWith("/runtime/write-scope/preview")) { const target = req.postDataJSON().target_scope; return route.fulfill({ json: { review_token: "t", current_scope: state.scope, target_scope: target, confirmation_phrase: "", typed_phrase: target === "switch_reset_only", blockers: [], expires_at: new Date(Date.now() + 6e5).toISOString() } }); }
    if (path.endsWith("/runtime/write-scope/apply")) { const body = req.postDataJSON(); state.applied.push(body.confirmation_phrase); state.scope = state.scope === "read_only" ? "switch_reset_only" : "read_only"; return route.fulfill({ json: { scope: state.scope, active_operations: [], blockers: [] } }); }
    if (path.endsWith("/runtime/write-scope")) return route.fulfill({ json: { scope: state.scope, active_operations: [], blockers: [] } });
    return route.fulfill({ status: 404, json: { detail: "unexpected " + path } });
  }).then(() => state);
}

test("turned off for the lab: nothing to unlock", async ({ page }) => {
  await mockApi(page, { enabled: false });
  await open(page);
  await expect(page.getByText("Reset is turned off for this lab.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Wipe disks" })).toHaveCount(0);
});

test("locked until typed; the switch erase needs its own typed name, then locks read-only", async ({ page }) => {
  test.setTimeout(90000);
  const state = await mockApi(page);
  await open(page);
  await expect(page.getByRole("button", { name: "Erase the switch" })).toHaveCount(0);
  await page.getByLabel("Type the unlock phrase").fill("RESET THIS KIT");
  await expect(page.getByRole("region", { name: "Wipe the server disks" })).toContainText("Every RAID volume on its disks");
  await page.getByRole("button", { name: "Erase the switch" }).click();
  const box = page.getByRole("dialog", { name: "Erase Cisco switch 1" });
  const go = box.getByRole("button", { name: "Erase the switch" });
  await expect(go).toBeDisabled();
  await box.getByLabel("Type the erase phrase").fill("ERASE Cisco switch");
  await expect(go).toBeDisabled();
  await box.getByLabel("Type the erase phrase").fill("ERASE Cisco switch 1");
  await expect(go).toBeDisabled();
  await box.getByLabel("Type the permission phrase").fill("ONLY RESET THE SWITCH");
  await go.click();
  await expect(box.getByRole("heading", { name: "Back to factory settings" })).toBeVisible({ timeout: 60000 });
  expect(state.startBody).toEqual({ confirmation: "ERASE Cisco switch 1" });
  expect(state.applied[0]).toBe("ONLY RESET THE SWITCH");
  await expect.poll(() => state.scope).toBe("read_only");
  expect(state.sent.filter(s => s.endsWith("switch-reset/start"))).toHaveLength(1);
  await box.getByRole("button", { name: "Done" }).click();
  await expect(page.getByText("Back to factory settings.")).toBeVisible();
});

test("forget saved sign-ins needs its phrase", async ({ page }) => {
  const state = await mockApi(page);
  await open(page);
  await page.getByLabel("Type the unlock phrase").fill("RESET THIS KIT");
  const step = page.getByRole("region", { name: "Forget saved sign-ins" });
  await expect(step).toContainText("HPE DL360 3: ESXi root password");
  await expect(step.getByRole("button", { name: "Forget them" })).toBeDisabled();
  await step.getByLabel("Type the forget phrase").fill("FORGET SIGN-INS");
  await step.getByRole("button", { name: "Forget them" }).click();
  await expect(step).toContainText("No saved sign-ins left");
  await expect(step).toContainText("Forgot 2 saved sign-ins.");
  expect(state.sent).toContain("POST reset/forget-signins");
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  }
});
