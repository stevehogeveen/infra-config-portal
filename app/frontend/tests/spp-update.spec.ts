import { test, expect, type Page } from "@playwright/test";

// Whole-SPP update: Review update -> Yes/No -> progress -> result.
// Contract: backend app/services/spp_update_contract.py (UpdatePlan, UpdateStatus).
const html = `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/sppUpdateHarness.tsx');</script></body></html>`;

const ids = { profile_id: "kit", device_id: "srv" };
const update = (step_id: string, component: string, from: string, to: string, order: number, restarts: "none" | "ilo" | "host", est_minutes: number | null = null) =>
  ({ step_id, component, from, to, order, restarts, est_minutes });
const plan = (extra: Record<string, unknown> = {}) => ({
  plan_id: "plan-1", ...ids,
  review_token: "review-1", expires_at: new Date(Date.now() + 600000).toISOString(), can_apply: true, confirmation_phrase: "UPDATE FIXTURE SERVER",
  server: { name: "Fixture server", model: "ProLiant DL360 Gen10", manager_generation: 5 },
  package: { file: "gen10spp.iso", release: "2026.05" },
  updates: [update("ilo-148", "iLO", "1.37", "1.48", 1, "ilo", 6), update("ilo-319", "iLO", "1.48", "3.19", 2, "ilo", 6), update("rom-366", "System ROM", "U32 1.46", "3.66", 3, "host", 12)],
  effects: { host_restarts: 1, ilo_restarts: 2, est_total_minutes: 30, power_on_required: false },
  not_included: [{ component: "Broadcom NIC", reason: "No matching firmware in this package." }],
  blockers: [], warnings: ["Storage: 6 erased disks (not affected by this update)."],
  details: { sum: "fixture" }, ...extra,
});
const blockedPlan = (extra: Record<string, unknown> = {}) => plan({ can_apply: false, review_token: null, confirmation_phrase: null, ...extra });
const step = (step_id: string, component: string, from: string, to: string, state: string, verified?: string) =>
  ({ ...update(step_id, component, from, to, 1, "ilo"), state, verified_version: verified ?? null });
const status = (extra: Record<string, unknown> = {}) => ({ ...ids, operation_id: null, idempotency_key: null, status: "not_started", steps: [], current_step: null,
  message: "No update recorded.", next_action: null, evidence_at: null, active: false, ...extra });

type Opts = { status?: () => unknown; plan?: () => unknown; apply?: (body: any) => unknown | "abort"; reconcile?: (body: any) => unknown; verify?: (body: any) => unknown; sppMissing?: boolean };
async function mount(page: Page, opts: Opts = {}) {
  const calls: Array<{ method: string; path: string; body: any }> = [];
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url()), method = route.request().method();
    const body = method === "POST" ? route.request().postDataJSON() : null;
    calls.push({ method, path: url.pathname.replace(/^.*\/firmware-update\//, "spp/"), body });
    if (url.pathname.endsWith("/access-settings")) return route.fulfill({ json: { host: "192.0.2.10", username_configured: true, password_configured: true } });
    if (url.pathname.endsWith("/firmware-assessment")) return route.fulfill({ json: { detected_model: "ProLiant DL360 Gen10", checked_at: "2026-09-29T10:00:00Z",
      rows: [{ component: "iLO", installed: "iLO 5 v1.37", target: "3.19", status: "Update available" }, { component: "System ROM / BIOS", installed: "U32 v1.46", target: "3.66", status: "Update available" }] } });
    if (url.pathname.includes("/firmware-update/")) {
      if (opts.sppMissing) return route.fulfill({ status: 404, json: { detail: "Not Found" } });
      if (url.pathname.endsWith("/status")) return route.fulfill({ json: opts.status?.() ?? status() });
      if (url.pathname.endsWith("/plan")) return route.fulfill({ json: opts.plan?.() ?? plan() });
      if (url.pathname.endsWith("/reconcile")) return route.fulfill({ json: opts.reconcile?.(body) ?? opts.status?.() ?? status() });
      if (url.pathname.endsWith("/verify")) return route.fulfill({ json: opts.verify?.(body) ?? opts.status?.() ?? status() });
      if (url.pathname.endsWith("/apply")) { const result = opts.apply?.(body); if (result === "abort") return route.abort("failed"); return route.fulfill({ json: result }); }
    }
    if (url.pathname.endsWith("/status")) return route.fulfill({ json: { status: "not_started", blockers: [], stages: [] } });
    if (url.pathname.endsWith("/runtime/write-scope")) return route.fulfill({ json: { scope: "mixed", active_operations: [], blockers: [] } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.route("**/spp-fixture", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto("/spp-fixture");
  return calls;
}
const posts = (calls: Array<{ method: string; path: string }>) => calls.filter(call => call.method === "POST").map(call => call.path);
const panel = (page: Page) => page.getByRole("dialog", { name: "Update firmware on Fixture server" });
async function openReview(page: Page) {
  await page.getByRole("button", { name: "Boot-disc update" }).click();
  await panel(page).getByRole("button", { name: "Review update" }).click();
}
async function approve(page: Page) {
  await openReview(page);
  await panel(page).getByRole("button", { name: "Approve and install" }).click();
  await panel(page).getByRole("button", { name: "Yes", exact: true }).click();
}

test("one Review update replaces per-part buttons, and opening it changes nothing", async ({ page }) => {
  const calls = await mount(page);
  await expect(page.getByRole("button", { name: "Boot-disc update" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Update to/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /App can install now/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Boot-disc update" }).click();
  await expect(panel(page).getByRole("button", { name: "Review update" })).toBeVisible();
  expect(posts(calls)).toEqual([]);
});

test("the review is plain: updates, restarts, not included; technical details stay closed", async ({ page }) => {
  const calls = await mount(page);
  await openReview(page);
  const review = panel(page).getByRole("region", { name: "Update plan" });
  await expect(review.getByRole("heading", { name: "3 updates from SPP 2026.05" })).toBeVisible();
  await expect(review).toContainText("Server restarts once. iLO restarts twice · about 30 min in total. Keep power connected.");
  await expect(review.getByText("Not included (1)")).toBeVisible();
  await expect(review.getByText("No matching firmware in this package.")).toBeHidden();
  await expect(review.getByText('"sum": "fixture"')).toBeHidden();
  await expect(review.getByRole("button", { name: "Approve and install" })).toBeEnabled();
  expect(posts(calls)).toEqual(["spp/plan"]);
});

test("approve sends once with the reviewed token, phrase and a key, then shows progress by step id", async ({ page }) => {
  let sent: any = null;
  const calls = await mount(page, { apply: body => { sent = body; return status({ status: "running", active: true, operation_id: "op-1", idempotency_key: body.idempotency_key, current_step: "ilo-148",
    steps: [step("ilo-148", "iLO", "1.37", "1.48", "installing"), step("ilo-319", "iLO", "1.48", "3.19", "waiting"), step("rom-366", "System ROM", "U32 1.46", "3.66", "waiting")] }); } });
  await approve(page);
  const progress = panel(page).getByRole("list", { name: "Update progress" });
  await expect(progress.getByRole("listitem")).toHaveCount(3);
  await expect(progress.getByRole("listitem").first()).toContainText("Installing");
  await expect(progress.getByRole("listitem").first()).toHaveAttribute("aria-current", "step");
  await expect(progress.getByRole("listitem").nth(1)).not.toHaveAttribute("aria-current", "step");
  await expect(panel(page)).toContainText("Keep the server's power connected.");
  expect(sent).toMatchObject({ review_token: "review-1", confirmation_phrase: "UPDATE FIXTURE SERVER" });
  expect(sent.idempotency_key).toMatch(/[0-9a-f-]{36}/);
  expect(posts(calls).filter(path => path === "spp/apply")).toHaveLength(1);
  await expect(page.getByRole("button", { name: "Update in progress · open" })).toBeVisible();
});

test("an apply reply for another device or key does not clear the attempt", async ({ page }) => {
  await mount(page, { apply: body => status({ status: "running", active: true, device_id: "other", idempotency_key: body.idempotency_key, steps: [] }) });
  await approve(page);
  await expect(panel(page).getByText("We don't know yet whether the update started.")).toBeVisible();
  await expect(panel(page)).toContainText("The server's reply did not name this exact request.");
  await expect(panel(page).getByRole("button", { name: /Approve|Review/ })).toHaveCount(0);
});

test("blockers stop the approval and are shown in plain words", async ({ page }) => {
  await mount(page, { plan: () => blockedPlan({ blockers: ["Power supply 2 has no power. Connect it before updating."] }) });
  await openReview(page);
  await expect(panel(page).getByText("Fix this first", { exact: true })).toBeVisible();
  await expect(panel(page).getByText("Power supply 2 has no power. Connect it before updating.")).toBeVisible();
  await expect(panel(page).getByRole("button", { name: "Approve and install" })).toHaveCount(0);
});

test("a plan without can_apply offers no approval even with no blockers", async ({ page }) => {
  await mount(page, { plan: () => blockedPlan() });
  await openReview(page);
  await expect(panel(page).getByText("This review can't be approved. Review again for a fresh plan.")).toBeVisible();
  await expect(panel(page).getByLabel("Confirmation phrase")).toHaveCount(0);
});

test("an empty plan never claims everything matches; it shows why nothing is offered", async ({ page }) => {
  await mount(page, { plan: () => blockedPlan({ updates: [], effects: { host_restarts: 0, ilo_restarts: 0, est_total_minutes: null, power_on_required: false },
    not_included: [{ component: "iLO", reason: "The SUM dependency report is not available yet." }], blockers: ["Target applicability has not been assessed."] }) });
  await openReview(page);
  await expect(panel(page).getByText("No update can be offered from this review.", { exact: false })).toBeVisible();
  await expect(panel(page).getByText(/matches your package/i)).toHaveCount(0);
  await expect(panel(page).getByText("The SUM dependency report is not available yet.")).toBeVisible();
  await expect(panel(page).getByText("Target applicability has not been assessed.")).toBeVisible();
});

test("unknown outcome after a lost response: no approve, no resend; only this profile, device and key unlock it", async ({ page }) => {
  let sentKey = "";
  let statusBody: any = status();
  const calls = await mount(page, { apply: body => { sentKey = body.idempotency_key; return "abort"; }, status: () => statusBody });
  await approve(page);
  await expect(panel(page).getByText("We don't know yet whether the update started.")).toBeVisible();
  await expect(panel(page).getByRole("button", { name: /Approve|Review/ })).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: "Update in progress · open" }).click();
  await expect(panel(page).getByText("We don't know yet whether the update started.")).toBeVisible();
  const running = (extra: Record<string, unknown>) => status({ status: "running", active: true, operation_id: "op-1", current_step: "ilo-148", steps: [step("ilo-148", "iLO", "1.37", "1.48", "installing")], ...extra });
  statusBody = running({ idempotency_key: "a-different-key" });
  await panel(page).getByRole("button", { name: "Check status" }).click();
  await expect(panel(page).getByText("We don't know yet whether the update started.")).toBeVisible();
  statusBody = running({ idempotency_key: sentKey, profile_id: "other-kit" });
  await panel(page).getByRole("button", { name: "Check status" }).click();
  await expect(panel(page).getByText("We don't know yet whether the update started.")).toBeVisible();
  statusBody = running({ idempotency_key: sentKey });
  await panel(page).getByRole("button", { name: "Check status" }).click();
  await expect(panel(page).getByRole("list", { name: "Update progress" })).toBeVisible();
  await expect(panel(page).getByText("We don't know yet whether the update started.")).toHaveCount(0);
  expect(posts(calls).filter(path => path === "spp/apply")).toHaveLength(1);
});

test("an uncertain operation offers only Check status, never a new review", async ({ page }) => {
  await mount(page, { status: () => status({ status: "uncertain", active: true, operation_id: "op-1", idempotency_key: "k", message: "The iLO stopped answering during the send.",
    steps: [step("ilo-148", "iLO", "1.37", "1.48", "uncertain")] }) });
  await page.getByRole("button", { name: "Update in progress · open" }).click();
  await expect(panel(page).getByText("The outcome is unknown.")).toBeVisible();
  await expect(panel(page).getByRole("button", { name: "Check status" })).toBeVisible();
  await expect(panel(page).getByRole("button", { name: /Review/ })).toHaveCount(0);
});

test("a failed run that is still active stays locked; a settled failure offers only a fresh review", async ({ page }) => {
  let active = true;
  await mount(page, { status: () => status({ status: "failed", active, operation_id: "op-1", idempotency_key: "k", message: "System ROM install was rejected by iLO.",
    steps: [step("ilo-148", "iLO", "1.37", "1.48", "done", "1.48"), step("rom-366", "System ROM", "U32 1.46", "3.66", "failed"), step("ctrl-800", "Smart Array", "1.66", "8.00", "not_started")] }) });
  await page.getByRole("button", { name: "Update in progress · open" }).click();
  await expect(panel(page).getByText("The update stopped.")).toBeVisible();
  const items = panel(page).getByRole("list", { name: "Update progress" }).getByRole("listitem");
  await expect(items.nth(0)).toContainText("Done · verified");
  await expect(items.nth(1)).toContainText("Failed");
  await expect(items.nth(2)).toContainText("Not started");
  await expect(panel(page).getByRole("button", { name: /Review|retry/i })).toHaveCount(0);
  active = false;
  await panel(page).getByRole("button", { name: "Check status" }).click();
  await expect(panel(page).getByRole("button", { name: "Review another update" })).toBeVisible();
  await expect(panel(page).getByRole("button", { name: /retry/i })).toHaveCount(0);
});

test("verified: versions and read-only lock are stated, and Done closes", async ({ page }) => {
  await mount(page, { status: () => status({ status: "verified", operation_id: "op-1", idempotency_key: "k", message: "Verified.", steps: [step("ilo-319", "iLO", "1.37", "3.19", "done", "3.19")] }) });
  await page.getByRole("button", { name: "Boot-disc update" }).click();
  await expect(panel(page).getByText("Update finished and verified. The server is back to read-only.")).toBeVisible();
  await panel(page).getByRole("button", { name: "Done" }).click();
  await expect(panel(page)).not.toBeVisible();
});

test("without the whole-package backend the page keeps today's iLO update", async ({ page }) => {
  await mount(page, { sppMissing: true });
  await expect(page.getByRole("button", { name: "Update to 1.48" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Boot-disc update" })).toHaveCount(0);
});

test("No cancels confirmation without sending and keyboard Yes sends exactly once", async ({ page }) => {
  const calls = await mount(page, { apply: body => status({ status: "running", active: true, operation_id: "op", idempotency_key: body.idempotency_key }) });
  await openReview(page);
  await expect(panel(page).getByLabel("Confirmation phrase")).toHaveCount(0);
  await panel(page).getByRole("button", { name: "Approve and install" }).click();
  await expect(panel(page).getByRole("group", { name: "Confirm firmware update" })).toContainText("Fixture server");
  await panel(page).getByRole("button", { name: "No", exact: true }).click();
  expect(posts(calls)).toEqual(["spp/plan"]);
  await panel(page).getByRole("button", { name: "Approve and install" }).click();
  await panel(page).getByRole("button", { name: "Yes", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(panel(page)).toContainText("Keep the server's power connected.");
  expect(posts(calls).filter(path => path === "spp/apply")).toHaveLength(1);
});

test("lost send is reconciled after reload without another apply", async ({ page }) => {
  let sent: any;
  const calls = await mount(page, {
    apply: body => { sent = body; return "abort"; },
    reconcile: body => status({ status: "failed", operation_id: "fence", idempotency_key: body.idempotency_key,
      dispatch_prevented: true, message: "The request was not recorded; delayed dispatch is prevented." }),
  });
  await approve(page);
  await expect(panel(page)).toContainText("We don't know yet whether the update started.");
  await page.reload();
  await page.getByRole("button", { name: "Update in progress · open" }).click();
  expect(posts(calls).filter(path => path === "spp/reconcile")).toHaveLength(0);
  await panel(page).getByRole("button", { name: "Check status" }).click();
  await expect(panel(page).getByRole("button", { name: "Review another update" })).toBeVisible();
  expect(calls.find(call => call.path === "spp/reconcile")?.body).toEqual(sent);
  expect(posts(calls).filter(path => path === "spp/apply")).toHaveLength(1);
  expect(await page.evaluate(() => localStorage.getItem("lab-builder-spp-attempt:kit:srv"))).toBeNull();
});

test("offline review discloses vendor-selected updates and shows real phase progress", async ({ page }) => {
  const calls = await mount(page, {
    plan: () => plan({ execution_mode: "offline", effects: { host_restarts: null, ilo_restarts: null, est_total_minutes: null, power_on_required: false } }),
    apply: body => status({ execution_mode: "offline", status: "running", active: true, operation_id: "op-offline", idempotency_key: body.idempotency_key,
      message: "Mounting the selected SPP.", steps: [step("rom", "System ROM", "1.46", "3.66", "waiting")] }),
  });
  await openReview(page);
  await expect(panel(page)).toContainText("Automatic SPP 2026.05");
  await expect(panel(page)).toContainText("Server may restart");
  await panel(page).getByRole("button", { name: "Approve and install" }).click();
  await expect(panel(page)).toContainText("Install all applicable firmware");
  await panel(page).getByRole("button", { name: "Yes", exact: true }).click();
  await expect(panel(page).getByRole("status")).toContainText("Mounting the selected SPP.");
  await expect(panel(page)).toContainText("Awaiting readback");
  expect(posts(calls).filter(path => path === "spp/apply")).toHaveLength(1);
});

test("offline Check status reconciles the exact operation without repeating apply", async ({ page }) => {
  const calls = await mount(page, {
    status: () => status({ execution_mode: "offline", status: "uncertain", active: true, operation_id: "op-offline", idempotency_key: "k", message: "Interrupted." }),
    verify: () => status({ execution_mode: "offline", status: "verified", operation_id: "op-offline", idempotency_key: "k", message: "Listed firmware verified." }),
  });
  await page.getByRole("button", { name: "Update in progress · open" }).click();
  await panel(page).getByRole("button", { name: "Check status" }).click();
  await expect(panel(page)).toContainText("Listed firmware versions verified. Update media disconnected.");
  expect(calls.find(call => call.path === "spp/verify")?.body).toEqual({ operation_id: "op-offline" });
  expect(posts(calls)).toEqual(["spp/verify"]);
});

for (const width of [1440, 390, 320]) {
  test(`review fits at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await mount(page);
    await openReview(page);
    await expect(panel(page).getByRole("button", { name: "Approve and install" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`spp-review-${width}.png`) });
  });
}

test("a write scope left on by another installer is returned to read-only by itself, then the review appears", async ({ page }) => {
  const calls = await mount(page);
  let scope = "esxi_install_only";
  const scopeCalls: string[] = [];
  await page.route("**/runtime/write-scope**", async route => {
    const path = new URL(route.request().url()).pathname;
    scopeCalls.push(`${route.request().method()} ${path.replace(/^.*\/runtime\//, "")}`);
    if (path.endsWith("/preview")) return route.fulfill({ json: { review_token: "t", current_scope: scope, target_scope: "read_only", confirmation_phrase: "", blockers: [], expires_at: new Date(Date.now() + 6e5).toISOString() } });
    if (path.endsWith("/apply")) { scope = route.request().postDataJSON().review_token === "t" ? "read_only" : scope; return route.fulfill({ json: { scope, active_operations: [], blockers: [] } }); }
    return route.fulfill({ json: { scope, active_operations: [], blockers: [] } });
  });
  await page.route("**/firmware-update/plan**", route => scope === "read_only"
    ? route.fallback()
    : route.fulfill({ status: 409, json: { detail: "Finish other hardware work and return to read-only before SPP maintenance." } }));
  await openReview(page);
  await expect(panel(page).getByRole("region", { name: "Update plan" }).getByRole("heading", { name: "3 updates from SPP 2026.05" })).toBeVisible();
  await expect(panel(page).getByText(/return to read-only/)).toHaveCount(0);
  await expect(panel(page).getByRole("button", { name: /read-only/i })).toHaveCount(0);
  expect(scopeCalls).toEqual(["GET write-scope", "POST write-scope/preview", "POST write-scope/apply"]);
  expect(posts(calls)).toEqual(["spp/plan"]);
});

test("approving a review that is about to expire fetches a fresh review instead of sending", async ({ page }) => {
  let plans = 0;
  const calls = await mount(page, { plan: () => (++plans === 1 ? plan({ expires_at: new Date(Date.now() + 40000).toISOString() }) : plan()) });
  await openReview(page);
  await page.clock.install();
  await page.clock.fastForward(15000);
  await panel(page).getByRole("button", { name: "Approve and install" }).click();
  await panel(page).getByRole("button", { name: "Yes", exact: true }).click();
  await expect.poll(() => plans).toBe(2);
  await expect(panel(page).getByRole("button", { name: "Approve and install" })).toBeEnabled();
  expect(posts(calls)).toEqual(["spp/plan", "spp/plan"]);
});

test("offline run: what the server shows now explains a waiting HPE updater and each part's current version", async ({ page }) => {
  const running = status({ execution_mode: "offline", status: "running", active: true, operation_id: "op-1", idempotency_key: "key-1", current_step: "verify-0",
    message: "HPE's updater is running. Waiting for its reboot and firmware readback.",
    steps: [{ ...step("verify-0", "System ROM / BIOS", "U32 1.46", "3.66", "waiting"), order: 1 }, { ...step("verify-1", "Drive: fixture / 2I:1:5", "HPD1", "HPD9", "waiting"), order: 2 }],
    observed: { checked_at: new Date().toISOString(), power: "On", post_state: "FinishedPost", updater_started: true, restarted_after_updater: false,
      parts: [{ component: "System ROM / BIOS", installed: "U32 v1.46", target: "3.66", at_target: false }, { component: "Drive: fixture / 2I:1:5", installed: "HPD9", target: "HPD9", at_target: true }],
      queued: ["HPE Smart Array P408i-a fixture"], updater_reported_error: true, waiting_for_reboot: true,
      summary: "HPE's updater has finished what it can do without a restart: 1 of 2 parts are already at their new version. HPE's screen is waiting for you: open the iLO remote console and choose Reboot." } });
  const calls = await mount(page, { status: () => running });
  await page.getByRole("button", { name: "Update in progress · open" }).click();
  const now = panel(page).getByRole("status", { name: "What the server shows now" });
  await expect(now).toContainText("choose Reboot");
  await expect(now).toContainText("Queued in the iLO for the restart: HPE Smart Array P408i-a fixture.");
  const progress = panel(page).getByRole("list", { name: "Update progress" });
  await expect(progress).toContainText("Still U32 v1.46 · installs during the restart");
  await expect(progress).toContainText("Now HPD9 · checked again after the restart");
  expect(posts(calls)).toEqual([]);
});
