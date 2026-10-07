import { test, expect, type Page } from "@playwright/test";

const html = `<html><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/studioRailHarness.tsx');</script></body></html>`;

async function mount(page: Page, storage: Record<string, unknown>) {
  const stamp = new Date().toISOString();
  await page.route("**/api/**", route => {
    if (route.request().method() !== "GET") { void route.abort(); throw new Error("Unexpected write"); }
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/rack-plans/fixture-r")) return route.fulfill({ json: { revision: 1, rack_units: 4, equipment: [{
      id: "s", device_id: "s", name: "Server S", kind: "server", model: "HPE DL360", position: 1, height: 1, mount: "rack", ports: 0, bay_count: 0, occupied_bays: [] }] } });
    if (path.endsWith("/access-settings")) return route.fulfill({ json: { device_id: "s", host: "192.0.2.10", last_probe_time: stamp,
      last_probe_status: "ok", last_probe_is_current: true, last_probe_target_matches_access_host: true, verify_tls: false } });
    if (path.endsWith("/raid-rebuild/status")) return route.fulfill({ json: storage });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.route("**/studio-rail-fixture", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto("/studio-rail-fixture");
  const connect = page.getByRole("link", { name: /Connect equipment/ });
  await expect(connect).toContainText("1 of 1 server answered");
  return connect;
}

test("a current connection completes Connect; firmware is now and RAID is not built", async ({ page }) => {
  const connect = await mount(page, { status: "not_started", active: false, message: "No operation" });
  await expect(connect).toContainText("Done");
  await expect(connect).toHaveClass(/\bdone\b/);
  // Firmware review does not wait for disks or RAID.
  await expect(page.getByRole("link", { name: /Check firmware/ })).toHaveClass(/\bnow\b/);
  const raid = page.getByRole("link", { name: /^\d*\s*Disks & RAID/ });
  await expect(raid).toContainText("Not built yet");
  await expect(raid).not.toHaveClass(/\bdone\b/);
});

test("a verified erase is not RAID completion", async ({ page }) => {
  await mount(page, { status: "verified", active: false, operation: "sanitize", message: "Erased", verified_at: new Date().toISOString() });
  const raid = page.getByRole("link", { name: /^\d*\s*Disks & RAID/ });
  await expect(raid).toContainText("Not built yet");
  await expect(raid).not.toHaveClass(/\bdone\b/);
});

test("a verified RAID create completes the RAID step", async ({ page }) => {
  await mount(page, { status: "verified", active: false, operation: "create", message: "Created", verified_at: new Date().toISOString() });
  const raid = page.getByRole("link", { name: /^\d*\s*Disks & RAID/ });
  await expect(raid).toContainText("RAID create verified (recorded)");
  await expect(raid).toHaveClass(/\bdone\b/);
});
