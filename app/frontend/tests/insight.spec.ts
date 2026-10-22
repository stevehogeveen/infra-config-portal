import { expect, test, type Page } from "@playwright/test";

// Phase 4: trace the path, ask the lab, time-lapse, camera help. Fixture data only.
async function open(page: Page, view: string) {
  await page.route("**/insight-fixture*", r => r.fulfill({ contentType: "text/html", body: `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/insightHarness.tsx');</script></body></html>` }));
  await page.goto(`/insight-fixture?view=${view}`);
}

test("trace lights each hop and says where the evidence stops", async ({ page }) => {
  await page.route("**/api/v1/rack-plans/fixture/trace", route => route.fulfill({ json: { cables_read_at: null, servers: [{ device_id: "srv", name: "HPE DL360 3", stops_at: 3, hops: [
    { name: "Windows VM", detail: "windows01 at 192.0.2.77", state: "proven", source: "VMware Tools reported its address", at: null, prove: null },
    { name: "VM network", detail: "VM Network", state: "proven", source: "Acceptance test", at: null, prove: null },
    { name: "ESXi host", detail: "esx01 at 192.0.2.20", state: "proven", source: "ESXi answered", at: null, prove: null },
    { name: "Cable", detail: null, state: "unknown", source: "Not read", at: null, prove: "Read the cables (My Rack, Cables)." }] }] } }));
  await open(page, "trace");
  const path = page.getByRole("article", { name: "Path for HPE DL360 3" });
  await expect(path).toContainText("Evidence stops here. Read the cables (My Rack, Cables).");
  await expect(path.locator(".tr-proven")).toHaveCount(3);
});

test("ask the lab shows the summary and the records behind it", async ({ page }) => {
  let asked = "";
  await page.route("**/api/v1/ask*", route => { asked = new URL(route.request().url()).searchParams.get("q") || ""; return route.fulfill({ json: {
    question: asked, terms: ["VLAN 100"], summary: "VLAN 100: planned in switch setup settings; sent by Switch (2026-10-15).",
    plan: [{ where: "Switch setup settings", at: null, message: "Switch lab-sw01: management VLAN 100, dhcp" }],
    changes: [{ where: "Switch", at: "2026-10-15T10:00:00Z", message: "Switch setup over the console starting; outcome unverified." }], checks: [] } }); });
  await open(page, "ask");
  await page.getByRole("button", { name: "Why is VLAN 100 here?" }).click();
  await expect(page.getByRole("status")).toContainText("VLAN 100: planned in switch setup settings");
  await expect(page.getByRole("region", { name: "Planned" })).toContainText("management VLAN 100");
  await expect(page.getByRole("region", { name: "Checked" })).toHaveCount(0);
  expect(asked).toBe("Why is VLAN 100 here?");
});

test("time-lapse scrubs through history and lights the rack", async ({ page }) => {
  await open(page, "lapse");
  await expect(page.getByTestId("tl-switch")).toHaveClass(/tl-bad/);
  await page.getByLabel("Point in time").fill("1");
  await expect(page.getByTestId("tl-server")).toHaveClass(/tl-ok/);
  await expect(page.getByTestId("tl-disks")).not.toHaveClass(/tl-ok/);
  await expect(page.getByText("iLO answered.")).toBeVisible();
  await page.getByRole("button", { name: "Play time-lapse" }).click();
  await expect(page.getByTestId("tl-disks")).toHaveClass(/tl-ok/);
});

test("the tag parser picks out the iLO details; no camera falls back to typing", async ({ page }) => {
  await page.addInitScript(() => { Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia: () => Promise.reject(Object.assign(new Error("denied"), { name: "NotAllowedError" })) } }); });
  await open(page, "camera");
  await expect(page.getByRole("dialog", { name: "Read the iLO tag" }).getByRole("alert")).toContainText("The camera was not allowed");
  const parsed = await page.evaluate(() => (window as any).parseIloTag("iLO Default Network Settings\nSerial Number: MXQ1234ABC\nUser Name: Administrator\nPassword: AB12CD34\nDNS Name: ILOMXQ1234ABC"));
  expect(parsed).toEqual({ host: "ILOMXQ1234ABC", username: "Administrator", password: "AB12CD34", serial: "MXQ1234ABC" });
  const noisy = await page.evaluate(() => (window as any).parseIloTag("User Name\nAdministrator\nPassword:\nXY98ZW76", ["MXQ9999ZZZ"]));
  expect(noisy).toEqual({ username: "Administrator", password: "XY98ZW76", serial: "MXQ9999ZZZ" });
});
