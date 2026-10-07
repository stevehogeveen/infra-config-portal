import { test, expect } from "@playwright/test";

// Visual regression for the Studio My Rack home (rack, guide banner, rail and evidence drawer).
// Replaces the retired "overview design mode map surface stays stable and scalable" map test.
// Deterministic: fixed clock and timezone, no web fonts (fallback stack), animations disabled.
test.use({ timezoneId: "UTC", locale: "en-GB", colorScheme: "light" });

const html = `<html data-theme="light"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/studioHomeHarness.tsx');</script></body></html>`;

const NOW = new Date("2026-09-28T12:00:00Z");
const CHECKED = "2026-09-28T08:35:00Z";

test("studio my rack home stays stable and scalable at desktop and phone widths", async ({ page }) => {
  await page.clock.setFixedTime(NOW);
  await page.route(/fonts\.(googleapis|gstatic)\.com/, route => route.abort());
  await page.route("**/api/**", route => {
    if (route.request().method() !== "GET") throw new Error("Unexpected write");
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/rack-plans/fixture") return route.fulfill({ json: { revision: 3, rack_units: 8, equipment: [
      { id: "pdu5", device_id: "pdu5", name: "PDU 5", kind: "pdu", model: "", position: 4, height: 1, mount: "rack", ports: 0, bay_count: 0, occupied_bays: [] },
      { id: "sw6", device_id: "sw6", name: "Cisco switch 6", kind: "switch", model: "Catalyst 9300", position: 3, height: 1, mount: "rack", ports: 24, uplink_ports: 4, bay_count: 0, occupied_bays: [] },
      { id: "pdu4", device_id: "pdu4", name: "PDU 4", kind: "pdu", model: "", position: 2, height: 1, mount: "rack", ports: 0, bay_count: 0, occupied_bays: [] },
      { id: "dl3", device_id: "dl3", name: "HPE DL360 3", kind: "server", model: "HPE DL360 Gen10", position: 1, height: 1, mount: "rack", ports: 0, bay_count: 10, occupied_bays: [1, 2, 3, 4, 6, 7, 8, 9] },
    ] } });
    if (url.pathname.endsWith("/access-settings")) return route.fulfill({ json: { device_id: "dl3", host: "192.0.2.27", username: "fixture", username_configured: true, password_configured: true,
      verify_tls: false, last_probe_time: CHECKED, last_probe_status: "ok", last_probe_is_current: true, last_probe_target_matches_access_host: true,
      last_probe_message: "Read-only Redfish probe completed.", observed_ilo_firmware: "iLO 5 v1.37", observed_bios_version: "U32 v1.46" } });
    if (url.pathname.endsWith("/raid-rebuild/status")) return route.fulfill({ json: { status: "verified", active: false, operation: "sanitize", message: "Recorded",
      submitted_at: "2026-09-24T14:34:02Z", boot_started_at: "2026-09-24T14:35:21Z", verified_at: "2026-09-24T16:22:23Z", sanitization: { checked_at: "2026-09-25T08:35:50Z", message: "", drives: [] } } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.route("**/studio-home-fixture*", route => route.fulfill({ contentType: "text/html", body: html }));
  for (const [width, height, name] of [[1440, 900, "studio-home-1440.png"], [390, 844, "studio-home-390.png"]] as const) {
    await page.setViewportSize({ width, height });
    await page.goto("/studio-home-fixture?device=dl3");
    await expect(page.getByRole("region", { name: "Your guide" })).toContainText("HPE DL360 3");
    await expect(page.locator(".sd-uled.ok")).toHaveCount(1);
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page).toHaveScreenshot(name, { fullPage: true, animations: "disabled", caret: "hide", maxDiffPixelRatio: 0.01 });
  }
});
