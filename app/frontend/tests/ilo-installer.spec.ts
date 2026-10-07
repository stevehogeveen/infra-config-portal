import { test, expect, type Page } from "@playwright/test";

// Windows-style iLO installer: Check -> Install -> Finish, no typing; one send, never resent.
const html = `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/firmwareOverviewHarness.tsx');</script></body></html>`;

type Opts = { scope?: string; blockers?: string[]; status?: () => any; apply?: (body: any) => unknown | "abort"; verify?: () => unknown; recovery?: () => unknown; reconcile?: (key: string) => unknown };
async function mount(page: Page, opts: Opts = {}) {
  const calls: Array<{ method: string; path: string; body: any }> = [];
  let scope = opts.scope ?? "mixed";
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url()), method = route.request().method();
    const body = method === "POST" ? route.request().postDataJSON() : null;
    const path = url.pathname.replace(/^.*\/(firmware-execution|runtime)\//, "");
    calls.push({ method, path, body });
    if (url.pathname.includes("/firmware-update/")) return route.fulfill({ status: 404, json: { detail: "Not Found" } });
    if (url.pathname.endsWith("/access-settings")) return route.fulfill({ json: { host: "192.0.2.10", username_configured: true, password_configured: true } });
    if (url.pathname.endsWith("/firmware-assessment")) return route.fulfill({ json: { detected_model: "ProLiant DL360 Gen10", checked_at: "2026-09-29T10:00:00Z",
      rows: [{ component: "iLO", installed: "iLO 5 v1.37", target: "3.19", status: "Update available" }] } });
    if (path === "write-scope") return route.fulfill({ json: { scope, active_operations: [], blockers: [] } });
    if (path === "write-scope/preview") return route.fulfill({ json: { review_token: "scope-t", current_scope: scope, target_scope: body.target_scope, expires_at: new Date(Date.now() + 600000).toISOString(),
      effects: [], blockers: [], confirmation_phrase: body.target_scope === "firmware_only" ? "ONLY UPDATE ILO FIRMWARE" : "" } });
    if (path === "write-scope/apply") { scope = body.confirmation_phrase === "ONLY UPDATE ILO FIRMWARE" ? "firmware_only" : "read_only"; return route.fulfill({ json: { scope, active_operations: [], blockers: [] } }); }
    if (path === "status") return route.fulfill({ json: opts.status?.() ?? { status: "not_started", blockers: [], stages: [] } });
    if (path === "reconcile") return route.fulfill({ json: opts.reconcile?.(url.searchParams.get("idempotency_key") ?? "") ?? { status: "not_started", record_found: false } });
    if (path === "capabilities") return route.fulfill({ json: { device_id: "srv", checked_at: new Date().toISOString(), manager_firmware_version: "iLO 5 v1.37",
      ilo_update_health: { scope: "ilo-only-v1", blockers: opts.blockers ?? [], blocker_details: [], warnings: [], assessment_sha256: "abc" } } });
    if (path === "prepare-spp-bridge") return route.fulfill({ json: { target_version: "1.48", preparation_id: 1, profile_id: "kit", device_id: "srv", package_selection_id: 2, bridge: {},
      authentication: { binary_authenticated: true }, can_apply: false, blockers: [] } });
    if (path === "preview") return route.fulfill({ json: { review_token: "review-1", expires_at: new Date(Date.now() + 600000).toISOString(), target: { name: "Fixture server" },
      operations: [{ order: 1, component: "iLO 5", current_version: "1.37", package_version: "1.48" }], blockers: [], can_apply: true, confirmation_phrase: "INSTALL ILO 1.48" } });
    if (path === "apply") { const result = opts.apply?.(body); if (result === "abort") return route.abort("failed"); return route.fulfill({ json: { profile_id: "kit", device_id: "srv", resource: "firmware-execution", ...(result ?? { status: "running", operation_id: "op-1" }) } }); }
    if (path === "verify") return route.fulfill({ json: opts.verify?.() ?? { status: "running", operation_id: "op-1" } });
    if (path === "recovery-preview") return route.fulfill({ json: opts.recovery?.() ?? {} });
    if (path === "close-unverified") return route.fulfill({ json: { status: "failed", operation_id: "op-1", resolution: "operator_closed_unverified", dispatch_prevented: false } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.route("**/overview-fixture", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto("/overview-fixture");
  return calls;
}
const installer = (page: Page) => page.getByRole("dialog", { name: "iLO firmware update on Fixture server" });
const next = (page: Page, name: string) => installer(page).getByRole("button", { name, exact: true });
const posts = (calls: Array<{ method: string; path: string }>) => calls.filter(call => call.method === "POST").map(call => call.path);

test("No closes without any preparation or hardware action", async ({ page }) => {
  const calls = await mount(page);
  await page.getByRole("button", { name: "Update to 1.48" }).click();
  await expect(next(page, "Yes")).toBeEnabled();
  await expect(installer(page).getByRole("textbox")).toHaveCount(0);
  await next(page, "No").click();
  await expect(installer(page)).toHaveCount(0);
  expect(posts(calls)).toEqual([]);
});

test("one Yes enables firmware access, prepares and sends exactly once", async ({ page }) => {
  let sent: any = null;
  const calls = await mount(page, { apply: body => { sent = body; return { status: "running", operation_id: "op-1" }; } });
  await page.getByRole("button", { name: "Update to 1.48" }).click();
  await expect(installer(page)).toContainText("Install iLO 1.48 on Fixture server?");
  await next(page, "Yes").dblclick();
  await expect.poll(() => posts(calls).filter(p => p === "apply").length).toBe(1);
  expect(sent).toMatchObject({ review_token: "review-1", confirmation_phrase: "INSTALL ILO 1.48" });
  expect(posts(calls)).toEqual(["capabilities", "prepare-spp-bridge", "write-scope/preview", "write-scope/apply", "preview", "apply"]);
  await expect(installer(page).getByRole("textbox")).toHaveCount(0);
});

test("existing firmware access requires no second approval", async ({ page }) => {
  const calls = await mount(page, { scope: "firmware_only" });
  await page.getByRole("button", { name: "Update to 1.48" }).click();
  await next(page, "Yes").click();
  await expect.poll(() => posts(calls).includes("apply")).toBe(true);
  expect(posts(calls)).not.toContain("write-scope/apply");
});

test("hardware warnings do not add a confirmation screen", async ({ page }) => {
  const calls = await mount(page, { blockers: ["Historical cooling warning"] });
  await page.getByRole("button", { name: "Update to 1.48" }).click();
  await next(page, "Yes").click();
  await expect.poll(() => posts(calls).includes("apply")).toBe(true);
});

test("a lost send stays uncertain across closing and is not repeated", async ({ page }) => {
  let recorded: any = { status: "not_started", blockers: [], stages: [] };
  const calls = await mount(page, { scope: "firmware_only", status: () => recorded, apply: () => {
    recorded = { status: "uncertain", operation_id: "op-1", message: "Outcome unknown." }; return "abort";
  } });
  await page.getByRole("button", { name: "Update to 1.48" }).click();
  await next(page, "Yes").click();
  await expect(installer(page).getByRole("heading", { name: "Update outcome unknown" })).toBeVisible();
  await next(page, "Close").click();
  await page.getByRole("button", { name: "Update in progress · open" }).click();
  await expect(next(page, "Yes")).toHaveCount(0);
  expect(posts(calls).filter(p => p === "apply")).toHaveLength(1);
});

test("running operation opens status with no install confirmation", async ({ page }) => {
  await mount(page, { status: () => ({ status: "running", operation_id: "op-1", stages: [] }) });
  await page.getByRole("button", { name: "Update in progress · open" }).click();
  await expect(next(page, "Close")).toBeVisible();
  await expect(next(page, "Yes")).toHaveCount(0);
});

test("a running update checks by itself and shows Complete, with no buttons or failure cards", async ({ page }) => {
  await page.clock.install();
  let recorded: any = { status: "running", operation_id: "op-1", stages: [] };
  const calls = await mount(page, { status: () => recorded, verify: () => {
    recorded = { status: "verified", operation_id: "op-1", stages: [] }; return recorded;
  } });
  await page.getByRole("button", { name: "Update in progress · open" }).click();
  await expect(installer(page).getByRole("progressbar")).toBeVisible();
  await expect(installer(page).getByText("Do not retry", { exact: true })).toHaveCount(0);
  await expect(installer(page).getByRole("heading", { name: /^Installing iLO / })).toBeVisible();
  await expect(installer(page).getByRole("button", { name: /Check if it's done/ })).toHaveCount(0);
  expect(posts(calls)).toEqual([]);
  await page.clock.runFor(21000);
  await expect(installer(page).getByRole("heading", { name: "Complete" })).toBeVisible();
  await expect(installer(page)).toContainText("The iLO is now on");
  expect(posts(calls)).toEqual(["verify"]);
});

for (const width of [1440, 320]) {
  test(`Yes/No fits and supports keyboard at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    const calls = await mount(page);
    await page.getByRole("button", { name: "Update to 1.48" }).click();
    await expect(next(page, "Yes")).toBeEnabled();
    expect(await installer(page).evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`installer-${width}.png`) });
    await next(page, "No").focus();
    await page.keyboard.press("Enter");
    await expect(installer(page)).toHaveCount(0);
    expect(posts(calls)).toEqual([]);
  });
}
