import { test, expect, type Page } from "@playwright/test";

const html = `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/firmwareOverviewHarness.tsx');</script></body></html>`;

async function mount(page: Page, installed = "iLO 5 1.48", target = "3.19", model = "ProLiant DL360 Gen10") {
  const writes: string[] = [];
  await page.route("**/api/**", route => {
    const url = new URL(route.request().url());
    if (route.request().method() !== "GET") writes.push(url.pathname);
    if (url.pathname.endsWith("/access-settings")) return route.fulfill({ json: { host: "192.0.2.10", username_configured: true, password_configured: true } });
    if (url.pathname.endsWith("/firmware-assessment")) return route.fulfill({ json: { detected_model: model, checked_at: "2026-09-29T10:00:00Z", rows: [{ component: "iLO", installed, target, status: "Update available" }] } });
    if (url.pathname.includes("/firmware-update/")) return route.fulfill({ status: 404, json: { detail: "Not Found" } });
    if (url.pathname.endsWith("/status")) return route.fulfill({ json: { status: "not_started", blockers: [], stages: [] } });
    if (url.pathname.endsWith("/runtime/write-scope")) return route.fulfill({ json: { scope: "read_only", active_operations: [], blockers: [] } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.route("**/overview-fixture", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto("/overview-fixture");
  return writes;
}

for (const width of [1440, 390, 320]) {
  test(`3.19 entry is usable at ${width}px without implicit hardware calls`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const writes = await mount(page);
    const update = page.getByRole("button", { name: "Update to 3.19", exact: true });
    await expect(update).toBeVisible();
    await update.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog", { name: "iLO firmware update on Fixture server" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Yes", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`ilo319-${width}.png`), fullPage: true });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).not.toBeVisible();
    expect(writes).toEqual([]);
  });
}

test("older iLO5 still starts with 1.48, without a 2.78 hop", async ({ page }) => {
  await mount(page, "iLO 5 1.37");
  await expect(page.getByRole("button", { name: "Update to 1.48", exact: true })).toBeVisible();
  await expect(page.getByText("2.78", { exact: true })).toHaveCount(0);
});

test("Gen11 iLO6 does not inherit the legacy iLO5 bridge", async ({ page }) => {
  await mount(page, "iLO 6 1.20", "1.68", "ProLiant DL360 Gen11");
  await expect(page.getByText("Requires an adapter for the detected iLO generation")).toBeVisible();
  await expect(page.getByRole("button", { name: /Update to/ })).toHaveCount(0);
  await expect(page.getByText("Needs 1.48 first")).toHaveCount(0);
});

test("future SPP target is not silently replaced by today's install version", async ({ page }) => {
  await mount(page, "iLO 5 3.19", "3.20");
  await expect(page.getByText("Step to 3.20 not in the app yet")).toBeVisible();
  await expect(page.getByRole("button", { name: /Update to/ })).toHaveCount(0);
});
