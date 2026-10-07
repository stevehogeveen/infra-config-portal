import { test, expect, type Page } from "@playwright/test";

const html = `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/studioEvidenceHarness.tsx');</script></body></html>`;

async function mount(page: Page, options: { failStorage?: boolean; holdKitB?: boolean } = {}) {
  const stamp = new Date().toISOString();
  let release = () => {};
  const held = new Promise<void>(resolve => { release = resolve; });
  // Every API request is fulfilled locally, including unexpected requests.
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (route.request().method() !== "GET") {
      await route.abort();
      throw new Error(`Unexpected write: ${url.pathname}`);
    }
    if (/\/rack-plans\/fixture-[ab]$/.test(url.pathname)) {
      const id = url.pathname.endsWith("fixture-b") ? "b" : "a";
      if (id === "b" && options.holdKitB) await held;
      return route.fulfill({ json: { revision: 1, rack_units: 4, equipment: [{
        id, device_id: id, name: `Server ${id}`, kind: "server", model: "HPE DL360",
        position: 1, height: 1, mount: "rack", ports: 0, bay_count: 0, occupied_bays: [],
      }] } });
    }
    if (url.pathname.endsWith("/access-settings")) return route.fulfill({ json: {
      device_id: url.searchParams.get("device_id"), host: "192.0.2.10",
      last_probe_time: stamp, last_probe_status: "ok", last_probe_is_current: true,
      last_probe_target_matches_access_host: true, verify_tls: false,
    } });
    if (url.pathname.endsWith("/raid-rebuild/status")) return route.fulfill(options.failStorage
      ? { status: 503, json: { detail: "Fixture status unavailable" } }
      : { json: { status: "not_started", active: false, message: "No operation recorded" } });
    // Recorded firmware / ESXi / Windows results: none yet in this fixture.
    if (url.pathname.endsWith("/parts-update/status")) return route.fulfill({ json: { state: "not_started", active: false, phases: [], parts: [], message: "" } });
    if (url.pathname.endsWith("/firmware-update/status")) return route.fulfill({ status: 404, json: { detail: "Not Found" } });
    if (url.pathname.endsWith("/esxi/install")) return route.fulfill({ json: { state: "not_started", active: false, phases: {}, message: "" } });
    if (url.pathname.endsWith("/windows/status")) return route.fulfill({ json: { state: "not_started", active: false, phases: [], message: "" } });
    await route.fulfill({ status: 404, json: { detail: "Unmapped fixture endpoint" } });
    throw new Error(`Unmapped fixture endpoint: ${url.pathname}`);
  });
  await page.route("**/studio-evidence-fixture", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto("/studio-evidence-fixture");
  await expect.poll(async () => JSON.parse(await page.getByTestId("snapshot").innerText()).loading).toBe(false);
  await expect(page.getByTestId("snapshot")).toContainText('"id":"a"');
  return release;
}

test("a failed storage read is unknown, not evidence that none are active", async ({ page }) => {
  await mount(page, { failStorage: true });
  await expect(page.getByText("none active", { exact: true })).toHaveCount(0);
});

test("switching kits removes old device evidence while the new kit loads", async ({ page }) => {
  const release = await mount(page, { holdKitB: true });
  try {
    await page.getByRole("button", { name: "Switch fixture kit" }).click();
    await expect(page.getByTestId("snapshot")).toContainText('"profile":"fixture-b"');
    await expect(page.getByTestId("snapshot")).not.toContainText('"id":"a"');
  } finally { release(); }
});

test("proof ages out while the operator stays on the same page", async ({ page }) => {
  await page.clock.install();
  await mount(page);
  await expect(page.getByTestId("snapshot")).toContainText('"proven":true');
  await page.clock.fastForward(24 * 60 * 60 * 1000);
  await expect(page.getByTestId("snapshot")).not.toContainText('"proven":true');
});
