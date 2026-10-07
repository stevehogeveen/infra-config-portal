import { test, expect, type Page, type Route } from "@playwright/test";

const html = `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/guardedExecutionHarness.tsx');</script></body></html>`;

const preview = (device: string) => ({
  review_token: `token-${device}`, expires_at: new Date(Date.now() + 10 * 60000).toISOString(),
  target: { device_id: device, name: device, host: "192.0.2.10", serial: `SERIAL-${device}` },
  component_hash: "sha256:fixture", operations: [{ order: 1, component: "iLO 5", current_version: "1.37", package_version: "3.19" }],
  blockers: [], can_apply: true, confirmation_phrase: `INSTALL ON ${device.toUpperCase()}`,
});

type Handler = (device: string, action: string, route: Route) => Promise<unknown> | unknown;
async function mount(page: Page, handler: Handler) {
  const calls: string[] = [];
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    const device = url.searchParams.get("device_id") || "";
    const action = url.pathname.split("/").pop() || "";
    calls.push(`${action}:${device}`);
    if (!url.pathname.includes("/firmware-execution/") || !["fixture-server", "fixture-other"].includes(device)) {
      await route.fulfill({ status: 404, json: {} });
      throw new Error(`Unexpected ${url.pathname}`);
    }
    await handler(device, action, route);
  });
  await page.route("**/guarded-fixture*", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto("/guarded-fixture?kind=firmware");
  return calls;
}

test("an aborted apply stays uncertain after closing, remounting and reloading; no second apply", async ({ page }) => {
  const calls = await mount(page, (device, action, route) => {
    if (action === "status") return route.fulfill({ json: { status: "not_started" } });
    if (action === "preview") return route.fulfill({ json: preview(device) });
    return route.abort("failed");
  });
  const open = page.getByRole("button", { name: "Review firmware install" });
  await open.click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Confirmation phrase").fill(preview("fixture-server").confirmation_phrase);
  await dialog.getByRole("button", { name: "Install", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("result is unknown");
  await expect(dialog.getByText(/Nothing has been sent/)).toHaveCount(0);
  await expect(dialog.getByRole("status")).toContainText("Sent. The result is unknown");
  await expect(dialog.getByRole("button", { name: "Install", exact: true })).toBeDisabled();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const card = page.getByRole("article", { name: "Operation status" });
  await expect(card).toContainText("Outcome unknown");
  await expect(open).toBeDisabled();
  await expect(page.getByText(/A request was sent and its outcome is unknown/)).toBeVisible();
  // Remount the component, then reload the page: the attempt is still blocking.
  await page.getByRole("button", { name: "Toggle fixture mount" }).click();
  await page.getByRole("button", { name: "Toggle fixture mount" }).click();
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeDisabled();
  await page.reload();
  await expect(page.getByRole("article", { name: "Operation status" })).toContainText("Outcome unknown");
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeDisabled();
  await page.getByRole("button", { name: "Read recorded status" }).click();
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeDisabled();
  expect(calls.filter(call => call.startsWith("apply"))).toHaveLength(1);
});

/*
 * Reconciliation follows backend/app/services/guarded_execution.py: GET reconcile by the exact
 * idempotency key. Only a recorded row whose own idempotency_key equals the stored key, for the
 * same kit/device/resource, unlocks. requested_idempotency_key is an echo and never unlocks.
 */
type Reconcile = (key: string) => Record<string, unknown>;
const scope = { profile_id: "fixture-kit", device_id: "fixture-server", resource: "firmware-execution" };
const missing: Reconcile = key => ({ ...scope, requested_idempotency_key: key, idempotency_key: null, operation_id: null, status: "uncertain", record_found: false, safe_to_retry: false, stages: [] });
const recorded = (status: string, keyFor: (key: string) => string | null, extra: Record<string, unknown> = {}): Reconcile =>
  key => ({ ...scope, requested_idempotency_key: key, idempotency_key: keyFor(key), operation_id: "op-7", status, record_found: true, safe_to_retry: false, stages: [], ...extra });

async function sendUncertain(page: Page, reconcile: Reconcile, historical: Record<string, unknown> | null) {
  const keys: string[] = [];
  const lookups: string[] = [];
  await mount(page, (device, action, route) => {
    if (action === "status") return route.fulfill({ json: historical ?? { ...scope, status: "not_started", idempotency_key: null, operation_id: null } });
    if (action === "preview") return route.fulfill({ json: preview(device) });
    if (action === "reconcile") {
      const key = new URL(route.request().url()).searchParams.get("idempotency_key")!;
      lookups.push(key);
      return route.fulfill({ json: reconcile(key) });
    }
    keys.push(route.request().postDataJSON().idempotency_key);
    return route.abort("failed");
  });
  const open = page.getByRole("button", { name: "Review firmware install" });
  if (historical && ["verified", "failed"].includes(String(historical.status))) await expect(open).toBeEnabled();
  await open.click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Confirmation phrase").fill(preview("fixture-server").confirmation_phrase);
  await dialog.getByRole("button", { name: "Install", exact: true }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await page.getByRole("button", { name: "Read recorded status" }).click();
  await expect.poll(() => lookups.length).toBeGreaterThan(0);
  expect(lookups.every(key => key === keys[0])).toBe(true);
  return { keys, lookups };
}

const stillLocked = async (page: Page) => {
  await page.waitForTimeout(300);
  await expect(page.getByText(/A request was sent and its outcome is unknown/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeDisabled();
  await page.reload();
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeDisabled();
};

test("reconcile with no recorded row keeps the attempt locked", async ({ page }) => {
  await sendUncertain(page, missing, null);
  await stillLocked(page);
});

test("a recorded row with a different key does not unlock, even though the echo matches", async ({ page }) => {
  await sendUncertain(page, recorded("running", () => "some-other-key"), null);
  await stillLocked(page);
});

test("a recorded row with a null key does not unlock", async ({ page }) => {
  await sendUncertain(page, recorded("running", () => null), null);
  await stillLocked(page);
});

test("a recorded row for another device does not unlock", async ({ page }) => {
  await sendUncertain(page, recorded("running", key => key, { device_id: "fixture-other" }), null);
  await stillLocked(page);
});

for (const status of ["verified", "failed"]) {
  test(`a historical ${status} operation from before the attempt does not unlock`, async ({ page }) => {
    const historical = { ...scope, status, operation_id: "op-old", idempotency_key: "older-key", record_found: true, evidence_at: new Date().toISOString() };
    await sendUncertain(page, key => ({ ...missing(key) }), historical);
    await stillLocked(page);
    await expect(page.getByRole("article", { name: "Operation status" })).toContainText("Outcome unknown");
  });
}

test("a recorded row with the same key, kit, device and resource unlocks", async ({ page }) => {
  await sendUncertain(page, recorded("running", key => key), null);
  await expect(page.getByText(/A request was sent and its outcome is unknown/)).toHaveCount(0);
  const stored = await page.evaluate(() => Object.keys(localStorage).filter(key => key.startsWith("lab-builder-guarded-attempt:")));
  expect(stored).toHaveLength(0);
});

test("a slow status for one server never lands on another", async ({ page }) => {
  let releaseA = () => {};
  const heldA = new Promise<void>(resolve => { releaseA = resolve; });
  let firstA = true;
  await mount(page, async (device, action, route) => {
    if (action !== "status") return route.fulfill({ json: preview(device) });
    if (device === "fixture-server" && firstA) { firstA = false; await heldA; return route.fulfill({ json: { status: "verified", operation_id: "op-a", evidence_at: new Date().toISOString() } }); }
    return route.fulfill({ json: { status: "not_started" } });
  });
  await page.getByRole("button", { name: "Switch fixture server" }).click();
  await expect(page.getByTestId("device")).toHaveText("fixture-other");
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeEnabled();
  releaseA();
  await page.waitForTimeout(500);
  await expect(page.getByRole("article", { name: "Operation status" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeEnabled();
});

test("changing the target closes the open confirmation and starts a fresh review", async ({ page }) => {
  const calls = await mount(page, (device, action, route) => {
    if (action === "status") return route.fulfill({ json: { status: "not_started" } });
    if (action === "preview") return route.fulfill({ json: preview(device) });
    throw new Error("apply must not be sent");
  });
  await page.getByRole("button", { name: "Review firmware install" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByText("Technical details").click();
  await expect(dialog.getByText("SERIAL-fixture-server")).toBeVisible();
  await dialog.getByLabel("Confirmation phrase").fill(preview("fixture-server").confirmation_phrase);
  // The target changes from elsewhere (for example the rail) while the modal is open.
  await page.evaluate(() => Array.from(document.querySelectorAll("button")).find(button => button.textContent === "Switch fixture server")!.click());
  await expect(page.getByTestId("device")).toHaveText("fixture-other");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Review firmware install" }).click();
  const next = page.getByRole("dialog");
  await next.getByText("Technical details").click();
  await expect(next.getByText("SERIAL-fixture-other")).toBeVisible();
  await expect(next.getByText("SERIAL-fixture-server")).toHaveCount(0);
  await expect(next.getByLabel("Confirmation phrase")).toHaveValue("");
  await expect(next.getByRole("button", { name: "Install", exact: true })).toBeDisabled();
  expect(calls.filter(call => call.startsWith("apply"))).toHaveLength(0);
});
