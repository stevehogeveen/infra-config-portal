import { test, expect, type Page, type Route } from "@playwright/test";

// Contract: Claude 14:32 / Codex reply / "write-scope answers accepted" in app/docs/agent-chat.md.
const html = (entry: string) => `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/${entry}');</script></body></html>`;

type Handler = (path: string, route: Route, body: any) => unknown;
async function mount(page: Page, handler: Handler) {
  const calls: Array<{ path: string; body: any }> = [];
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/v1/runtime/write-scope")) { await route.fulfill({ status: 404, json: {} }); throw new Error(`Unexpected ${url.pathname}`); }
    const path = url.pathname.replace("/api/v1/runtime/write-scope", "") || "/";
    const body = route.request().method() === "POST" ? route.request().postDataJSON() : null;
    calls.push({ path, body });
    const result = await handler(path, route, body);
    if (result === "abort") return route.abort("failed");
    if (result && typeof result === "object" && "__status" in (result as any)) return route.fulfill({ status: (result as any).__status, json: { detail: "Fixture" } });
    return route.fulfill({ json: result });
  });
  await page.route("**/scope-fixture", route => route.fulfill({ contentType: "text/html", body: html("writeScopeHarness.tsx") }));
  await page.goto("/scope-fixture");
  return calls;
}
const pill = (page: Page) => page.locator(".sd-scope-pill");
const section = (page: Page) => page.getByRole("region", { name: "Write scope" });

test("not available: a missing service is neutral and the entry is disabled, never hidden", async ({ page }) => {
  await mount(page, () => ({ __status: 404 }));
  await expect(pill(page)).toHaveText("Changes allowed: set by server configuration");
  await expect(pill(page)).not.toHaveClass(/grant/);
  await expect(section(page).getByRole("button", { name: "Limit to firmware only" })).toBeDisabled();
  await expect(section(page).getByText("Not available yet: the app cannot change write scope on this server yet.")).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("not available: GET answers but preview does not", async ({ page }) => {
  await mount(page, path => path === "/" ? { scope: "read_only", source: "env", active_operations: [], blockers: [] } : { __status: 501 });
  await expect(pill(page)).toHaveText("Read-only mode");
  await section(page).getByRole("button", { name: "Limit to firmware only" }).click();
  await expect(section(page).getByText("Not available yet: the app cannot change write scope on this server yet.")).toBeVisible();
  await expect(section(page).getByRole("button", { name: "Limit to firmware only" })).toBeDisabled();
});

test("blocked by an active operation: the operation is named and nothing can be applied", async ({ page }) => {
  const refusal = "Refused: legacy storage operation op-3 (ilo-redfish.hpe-raid-apply) is running on srv.";
  const calls = await mount(page, path => {
    if (path === "/") return { scope: "read_only", source: "env", active_operations: [{ description: "Legacy RAID apply", device_id: "srv", status: "running", operation_id: "op-3" }], blockers: [] };
    if (path === "/preview") return { review_token: "t1", expires_at: new Date(Date.now() + 300000).toISOString(), current_scope: "read_only", target_scope: "firmware_only",
      effects: ["Only ilo.firmware-update writes would be allowed."], blockers: [refusal], confirmation_phrase: "ALLOW FIRMWARE WRITES ONLY" };
    throw new Error(`unexpected ${path}`);
  });
  await expect(section(page).getByLabel("Unresolved operation locks")).toContainText("Legacy RAID apply on srv (running) · op-3");
  await section(page).getByRole("button", { name: "Limit to firmware only" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(refusal, { exact: true })).toBeVisible();
  await expect(dialog.getByLabel("Confirmation phrase")).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Confirm", exact: true })).toBeDisabled();
  expect(calls.filter(call => call.path === "/apply")).toHaveLength(0);
});

test("firmware_only: preview, typed phrase, one apply, then the server's re-read decides the pill", async ({ page }) => {
  let scope = "read_only";
  const calls = await mount(page, (path, _route, body) => {
    if (path === "/") return { scope, source: scope === "read_only" ? "env" : "database", changed_at: "2026-09-28T15:00:00Z", changed_by: "local-operator", active_operations: [], blockers: [] };
    if (path === "/preview") return { review_token: "scope-token", expires_at: new Date(Date.now() + 300000).toISOString(), current_scope: "read_only", target_scope: body.target_scope,
      effects: ["Only ilo.firmware-update writes would be allowed.", "Storage and power writes stay refused."], blockers: [], confirmation_phrase: "ALLOW FIRMWARE WRITES ONLY" };
    if (path === "/apply") { scope = "firmware_only"; return { scope, source: "database", active_operations: [], blockers: [] }; }
    throw new Error(`unexpected ${path}`);
  });
  await expect(pill(page)).toHaveText("Read-only mode");
  await section(page).getByRole("button", { name: "Limit to firmware only" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Storage and power writes stay refused.")).toBeVisible();
  const confirm = dialog.getByRole("button", { name: "Confirm", exact: true });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel("Confirmation phrase").fill("allow firmware writes only");
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel("Confirmation phrase").fill("ALLOW FIRMWARE WRITES ONLY");
  await confirm.click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(pill(page)).toHaveText("Changes allowed: firmware only");
  await expect(section(page)).toContainText("firmware only");
  const previews = calls.filter(call => call.path === "/preview");
  const applies = calls.filter(call => call.path === "/apply");
  expect(previews[0].body).toEqual({ target_scope: "firmware_only" });
  expect(applies).toHaveLength(1);
  expect(applies[0].body).toEqual({ review_token: "scope-token", confirmation_phrase: "ALLOW FIRMWARE WRITES ONLY" });
  expect(calls.filter(call => call.path === "/").length).toBeGreaterThanOrEqual(3);
});

test("read_only revoke previews, needs no phrase, and keeps unresolved locks visible", async ({ page }) => {
  let scope = "firmware_only";
  const lock = { description: "iLO 1.48 bridge install", device_id: "srv", status: "uncertain", operation_id: "op-9" };
  const calls = await mount(page, (path, _route, body) => {
    if (path === "/") return { scope, source: "database", active_operations: [lock], blockers: [] };
    if (path === "/preview") return { review_token: "ro-token", expires_at: new Date(Date.now() + 300000).toISOString(), current_scope: "firmware_only", target_scope: body.target_scope,
      effects: ["All hardware writes will be refused."], blockers: [], confirmation_phrase: "" };
    if (path === "/apply") { scope = "read_only"; return { scope, source: "database", active_operations: [lock], blockers: [] }; }
    throw new Error(`unexpected ${path}`);
  });
  await expect(pill(page)).toHaveText("Changes allowed: firmware only");
  await section(page).getByRole("button", { name: "Lock to read-only" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("All hardware writes will be refused.")).toBeVisible();
  await expect(dialog.getByLabel("Confirmation phrase")).toHaveCount(0);
  await dialog.getByRole("button", { name: "Lock", exact: true }).click();
  await expect(pill(page)).toHaveText("Read-only mode");
  await expect(section(page).getByLabel("Unresolved operation locks")).toContainText("iLO 1.48 bridge install on srv (uncertain) · op-9");
  expect(calls.find(call => call.path === "/preview")!.body).toEqual({ target_scope: "read_only" });
  expect(calls.filter(call => call.path === "/apply")).toHaveLength(1);
});

test("storage, power and mixed scopes are shown as reported and never offered", async ({ page }) => {
  await mount(page, () => ({ scope: "mixed", source: "env", active_operations: [], blockers: [] }));
  await expect(pill(page)).toHaveText("Changes allowed: several kinds");
  await expect(section(page)).toContainText("The app can only narrow what's allowed, never widen it.");
  await expect(page.getByRole("button", { name: /storage|power|mixed/i })).toHaveCount(0);
  await expect(section(page).getByRole("button", { name: "Limit to firmware only" })).toBeEnabled();
});

test("the firmware bridge's scope blocker links to the write-scope entry", async ({ page }) => {
  await page.route("**/api/**", route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/firmware-execution/status")) return route.fulfill({ json: { profile_id: "kit", device_id: "srv", resource: "firmware-execution", status: "not_started",
      blockers: ["Exclusive firmware maintenance scope is required; competing hardware writes must be disabled."] } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.route("**/bridge-fixture", route => route.fulfill({ contentType: "text/html", body: html("firmwareBridgeHarness.tsx") }));
  await page.goto("/bridge-fixture");
  await expect(page.getByRole("link", { name: "Limit to firmware only" })).toHaveAttribute("href", "#write-scope");
});
