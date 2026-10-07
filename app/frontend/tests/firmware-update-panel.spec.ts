import { test, expect, type Page } from "@playwright/test";

// One button at a time: Prepare update -> Upgrade (scope first when needed) -> Lock.
const html = `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/firmwareUpdatePanelHarness.tsx');</script></body></html>`;

type Opts = { scope?: string; blockers?: string[]; details?: unknown[]; genuine?: boolean; status?: string; target?: string };
async function mount(page: Page, opts: Opts = {}) {
  const calls: string[] = [];
  await page.route("**/api/**", route => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    calls.push(`${method} ${url.pathname.replace(/^.*\/(firmware-execution|runtime)\//, "")}`);
    if (url.pathname.endsWith("/runtime/write-scope")) return route.fulfill({ json: { scope: opts.scope ?? "mixed", source: "server_configuration", active_operations: [], blockers: [] } });
    if (url.pathname.endsWith("/runtime/write-scope/preview")) return route.fulfill({ json: { review_token: "t", current_scope: opts.scope ?? "mixed", target_scope: route.request().postDataJSON().target_scope,
      expires_at: new Date(Date.now() + 600000).toISOString(), effects: [], blockers: [], confirmation_phrase: "ALLOW ILO FIRMWARE WRITES ONLY" } });
    if (url.pathname.endsWith("/firmware-execution/status")) return route.fulfill({ json: { status: opts.status ?? "not_started", blockers: ["recorded generic blocker"], stages: [] } });
    if (url.pathname.endsWith("/firmware-execution/capabilities")) return route.fulfill({ json: { device_id: "srv", checked_at: new Date().toISOString(), manager_firmware_version: "1.37",
      ilo_update_health: { scope: "ilo-only-v1", blockers: opts.blockers ?? [], blocker_details: opts.details ?? [], warnings: [{ group: "Storage", health: "Warning", title: "Erased drives" }], assessment_sha256: "abc" } } });
    if (url.pathname.endsWith("/firmware-execution/prepare-spp-bridge")) return route.fulfill({ json: { preparation_id: 1, profile_id: "kit", device_id: "srv", package_selection_id: 2,
      target_version: opts.target ?? "1.48", bridge: {}, authentication: { binary_authenticated: opts.genuine ?? true }, can_apply: false, blockers: ["Preparation does not authorize installation."] } });
    if (url.pathname.endsWith("/firmware-execution/preview")) return route.fulfill({ status: 404, json: {} });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.route("**/update-panel-fixture", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto("/update-panel-fixture");
  return calls;
}

test("only Prepare update is offered first, and nothing is read until it is pressed", async ({ page }) => {
  const calls = await mount(page);
  await expect(page.getByRole("button", { name: "Prepare update" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Upgrade iLO/ })).toHaveCount(0);
  await expect(page.getByText("recorded generic blocker")).toHaveCount(0);
  await page.waitForTimeout(300);
  expect(calls.filter(call => call.startsWith("POST"))).toEqual([]);
});

test("after a clean prepare the next button is Upgrade, with no details on screen", async ({ page }) => {
  const calls = await mount(page);
  await page.getByRole("button", { name: "Prepare update" }).click();
  await expect(page.getByText("Ready. The iLO answered and the 1.48 file is genuine.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Upgrade iLO to 1.48" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Prepare update" })).toHaveCount(0);
  await expect(page.getByText("Erased drives")).toHaveCount(0);
  expect(calls.filter(call => call.startsWith("POST"))).toEqual(["POST capabilities", "POST prepare-spp-bridge"]);
});

test("Upgrade asks to limit changes to firmware first when the scope is wider", async ({ page }) => {
  await mount(page, { scope: "mixed" });
  await page.getByRole("button", { name: "Prepare update" }).click();
  await page.getByRole("button", { name: "Upgrade iLO to 1.48" }).click();
  await expect(page.getByRole("dialog", { name: "Only update the iLO firmware" })).toBeVisible();
});

test("Upgrade goes straight to the install review when already firmware only", async ({ page }) => {
  const calls = await mount(page, { scope: "firmware_only" });
  await page.getByRole("button", { name: "Prepare update" }).click();
  await page.getByRole("button", { name: "Upgrade iLO to 1.48" }).click();
  await expect(page.getByRole("dialog", { name: "Only update the iLO firmware" })).toHaveCount(0);
  await expect.poll(() => calls.includes("POST preview")).toBe(true);
});

test("a real blocker stops at Prepare and is shown in plain words", async ({ page }) => {
  await mount(page, { blockers: ["Fresh cooling and temperature inventory is required."] });
  await page.getByRole("button", { name: "Prepare update" }).click();
  await expect(page.getByText("Fix this first", { exact: true })).toBeVisible();
  await expect(page.getByText("Fresh cooling and temperature inventory is required.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Upgrade iLO/ })).toHaveCount(0);
});

test("an unverified file is never offered for install", async ({ page }) => {
  await mount(page, { genuine: false });
  await page.getByRole("button", { name: "Prepare update" }).click();
  await expect(page.getByText(/could not be verified as HPE's/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Upgrade iLO/ })).toHaveCount(0);
});

test("a verified update offers only Lock to read-only", async ({ page }) => {
  await mount(page, { status: "verified" });
  await expect(page.getByRole("button", { name: "Lock to read-only" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Prepare update|Upgrade iLO/ })).toHaveCount(0);
});

test("server-selected 3.19 replaces the old bridge label and opens a separate review", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const calls = await mount(page, { target: "3.19", scope: "firmware_only" });
  await page.getByRole("button", { name: "Prepare update" }).click();
  await expect(page.getByText("Ready. The iLO answered and the 3.19 file is genuine.")).toBeVisible();
  const upgrade = page.getByRole("button", { name: "Upgrade iLO to 3.19" });
  await expect(upgrade).toBeEnabled();
  await upgrade.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => calls.includes("POST preview")).toBe(true);
  expect(calls.some(call => call === "POST apply")).toBe(false);
});

test("verified bridge does not trap the next separately prepared update", async ({ page }) => {
  const calls = await mount(page, { status: "verified", scope: "read_only", target: "3.19" });
  await expect(page.getByRole("button", { name: "Prepare next update" })).toBeVisible();
  expect(calls.filter(call => call.startsWith("POST"))).toEqual([]);
  await page.getByRole("button", { name: "Prepare next update" }).click();
  await expect(page.getByRole("button", { name: "Upgrade iLO to 3.19" })).toBeEnabled();
  expect(calls.filter(call => call.startsWith("POST"))).toEqual(["POST capabilities", "POST prepare-spp-bridge"]);
});

test("unsupported server-selected version does not enable an install", async ({ page }) => {
  await mount(page, { target: "2.78" });
  await page.getByRole("button", { name: "Prepare update" }).click();
  await expect(page.getByText("This firmware version has no installation adapter.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Upgrade iLO/ })).toHaveCount(0);
});

test("a blocker shows how to fix it, and Read again re-runs Prepare", async ({ page }) => {
  const text = "Fresh cooling and temperature inventory is required.";
  const calls = await mount(page, { blockers: [text], details: [{ code: "thermal_incomplete", text, fix_kind: "app", fix: "Read the iLO again to collect complete cooling evidence.", action: "read_again" }] });
  await page.getByRole("button", { name: "Prepare update" }).click();
  const box = page.getByRole("note", { name: "Fix this first" });
  await expect(box).toContainText("How to fix: Read the iLO again to collect complete cooling evidence.");
  await box.getByRole("button", { name: "Read again" }).click();
  await expect.poll(() => calls.filter(call => call === "POST capabilities").length).toBe(2);
  await expect(page.getByRole("button", { name: /Upgrade iLO/ })).toHaveCount(0);
});
