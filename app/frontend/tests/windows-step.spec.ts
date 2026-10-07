import { expect, test, type Page } from "@playwright/test";

// Install Windows: 1 image, 2 VM settings, 3 deploy. Documentation addresses only.
const profile = { id: "fixture", name: "Test kit", source: "saved", version: 1 };
const image = { path: "win2022.ova", name: "win2022.ova", size_bytes: 9e9, kind: "ova", missing: [], windows: true };
const host = { address: "192.0.2.20", networks: ["VM Network"], problem: null, default_datastore: "VMdata",
  datastores: [{ name: "datastore1", capacity: 160e9, free: 158e9 }, { name: "VMdata", capacity: 3.6e12, free: 3.59e12 }] };
const phases = (states: string[]) => [
  { phase: "import", label: "Import windows01 onto VMdata", state: states[0], message: null },
  { phase: "power", label: "Power windows01 on", state: states[1], message: null },
  { phase: "verify", label: "Windows starts and VMware Tools reports its address", state: states[2], message: null },
];

async function open(page: Page) {
  await page.route("**/windows-step-fixture", r => r.fulfill({ contentType: "text/html", body: `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    window.windowsFixture={active_profile:${JSON.stringify(profile)}};await import('/tests/fixtures/windowsStepHarness.tsx');</script></body></html>` }));
  await page.goto("/windows-step-fixture");
}

function mockApi(page: Page, opts: { importFails?: boolean; noImages?: boolean } = {}) {
  const state = { saved: null as any, step: -1, scope: "read_only", sent: [] as string[] };
  const run = () => {
    if (state.step < 0) return { state: "not_started", active: false, phases: [], message: "" };
    if (opts.importFails && state.step >= 1) return { state: "needs_attention", active: true, phases: phases(["failed", "todo", "todo"]), message: "The import stopped: Disk upload failed", vm_name: "windows01" };
    const s = ["sent", "todo", "todo"].map((v, i) => i < state.step ? "ok" : i === state.step ? "sent" : "todo");
    if (state.step >= 3) return { state: "verified", active: false, phases: phases(["ok", "ok", "ok"]), message: "windows01 is running Windows at 192.0.2.77.", vm_name: "windows01",
      address: "192.0.2.77", hostname: "WIN01", guest_os: "Microsoft Windows Server 2022", esxi_address: "192.0.2.20" };
    return { state: "running", active: true, phases: phases(s), message: "Working…", vm_name: "windows01", last_check: null };
  };
  return page.route("**/api/**", async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname, method = req.method();
    if (method !== "GET") state.sent.push(`${method} ${path.replace(/^.*\/(windows|runtime)\//, "$1/")}`);
    if (path === "/api/v1/rack-plans/fixture") return route.fulfill({ json: { revision: 1, rack_units: 4, equipment: [{ id: "s", device_id: "srv", name: "HPE DL360 3", kind: "server", model: "HPE DL360 Gen10", position: 1, height: 1, mount: "rack", ports: 0, bay_count: 10, occupied_bays: [] }] } });
    if (path.endsWith("/windows/setup")) {
      if (method === "PUT") state.saved = { ...req.postDataJSON(), saved_at: new Date().toISOString() };
      return route.fulfill({ json: { images: opts.noImages ? [] : [image], image: state.saved?.image ?? null, vm_name: state.saved?.vm_name ?? null, datastore: state.saved?.datastore ?? null,
        network: state.saved?.network ?? null, saved_at: state.saved?.saved_at ?? null, host } });
    }
    if (path.endsWith("/windows/review")) return route.fulfill({ json: { ready: true, blockers: [], permission: [], image: "win2022.ova", size_bytes: 9e9, vm_name: "windows01",
      datastore: "VMdata", network: "VM Network", address: "192.0.2.20", free_bytes: 3.59e12 } });
    if (path.endsWith("/windows/status")) return route.fulfill({ json: run() });
    if (path.endsWith("/windows/start")) { state.step = 0; return route.fulfill({ json: run() }); }
    if (path.endsWith("/windows/advance")) { state.step += 1; return route.fulfill({ json: run() }); }
    if (path.endsWith("/windows/close")) { state.step = -1; return route.fulfill({ json: { state: "failed", active: false, phases: [], message: "Closed." } }); }
    if (path.endsWith("/runtime/write-scope/preview")) { const target = req.postDataJSON().target_scope; return route.fulfill({ json: { review_token: "t", current_scope: state.scope, target_scope: target, confirmation_phrase: "", blockers: [], expires_at: new Date(Date.now() + 6e5).toISOString() } }); }
    if (path.endsWith("/runtime/write-scope/apply")) { state.scope = state.scope === "read_only" ? "vm_deploy_only" : "read_only"; return route.fulfill({ json: { scope: state.scope, active_operations: [], blockers: [] } }); }
    if (path.endsWith("/runtime/write-scope")) return route.fulfill({ json: { scope: state.scope, active_operations: [], blockers: [] } });
    return route.fulfill({ status: 404, json: { detail: "unexpected " + path } });
  }).then(() => state);
}

test("choose the image and save settings (plan only); VMdata is the default datastore", async ({ page }) => {
  const state = await mockApi(page);
  await open(page);
  const card = page.getByRole("article", { name: "HPE DL360 3" });
  await expect(card).toContainText("ESXi 192.0.2.20");
  const deploy = card.getByRole("button", { name: "Deploy Windows" });
  await expect(deploy).toBeDisabled();
  await card.getByRole("radiogroup", { name: "Windows image" }).getByRole("radio", { name: /win2022\.ova/ }).click();
  const settings = card.getByRole("region", { name: "VM settings" });
  await expect(settings.getByRole("radiogroup", { name: "Datastore for the VM" }).getByRole("radio", { name: /VMdata/ })).toHaveAttribute("aria-checked", "true");
  await settings.getByRole("button", { name: "Save VM settings" }).click();
  await expect.poll(() => state.saved).not.toBeNull();
  expect(state.saved).toMatchObject({ image: "win2022.ova", vm_name: "windows01", datastore: "VMdata", network: "VM Network" });
  await expect(deploy).toBeEnabled();
  expect(state.sent).toEqual(["PUT windows/setup"]);
});

test("one tick and one button import, power on and verify; Done locks read-only", async ({ page }) => {
  test.setTimeout(120000);
  const state = await mockApi(page);
  state.saved = { image: "win2022.ova", vm_name: "windows01", datastore: "VMdata", network: "VM Network", saved_at: new Date().toISOString() };
  await open(page);
  await page.getByRole("button", { name: "Deploy Windows" }).click();
  const box = page.getByRole("dialog", { name: "Deploy Windows on HPE DL360 3" });
  await expect(box.getByRole("heading", { name: "Ready to deploy" })).toBeVisible();
  await expect(box).toContainText("win2022.ova");
  await box.getByRole("checkbox").check();
  await box.getByRole("button", { name: "Deploy Windows" }).click();
  await expect(box.getByRole("heading", { name: "Deploying Windows…" })).toBeVisible();
  expect(state.scope).toBe("vm_deploy_only");
  await expect(box.getByRole("heading", { name: "Complete", exact: true })).toBeVisible({ timeout: 90000 });
  await expect(box).toContainText("windows01 is running Windows at 192.0.2.77.");
  await expect(box).toContainText("Computer name: WIN01");
  await box.getByRole("button", { name: "Done" }).click();
  await expect(box).toHaveCount(0);
  expect(state.scope).toBe("read_only");
  expect(state.sent.filter(s => s === "POST windows/start")).toHaveLength(1);
});

test("a failed import says why and can be closed", async ({ page }) => {
  test.setTimeout(60000);
  const state = await mockApi(page, { importFails: true });
  state.saved = { image: "win2022.ova", vm_name: "windows01", datastore: "VMdata", network: "VM Network", saved_at: new Date().toISOString() };
  await open(page);
  await page.getByRole("button", { name: "Deploy Windows" }).click();
  const box = page.getByRole("dialog", { name: "Deploy Windows on HPE DL360 3" });
  await box.getByRole("checkbox").check();
  await box.getByRole("button", { name: "Deploy Windows" }).click();
  await expect(box.getByRole("heading", { name: "The deployment needs attention" })).toBeVisible({ timeout: 40000 });
  await expect(box.getByRole("alert")).toContainText("Disk upload failed");
  await box.getByRole("button", { name: "Close this run" }).click();
  await expect(box.getByRole("heading", { name: "Ready to deploy" })).toBeVisible();
  expect(state.scope).toBe("read_only");
});

test("no image yet: the page says so and offers the OVA/OVF upload", async ({ page }) => {
  await mockApi(page, { noImages: true });
  await open(page);
  await expect(page.getByText("No OVA or OVF is in the media folder yet.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Choose OVA or OVF file" })).toBeVisible();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 950 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  }
});
