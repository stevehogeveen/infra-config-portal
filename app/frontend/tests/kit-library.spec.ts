import { test, expect } from "@playwright/test";

test("named kit copies and saved reports stay separate and fit narrow screens", async ({ page }) => {
  const profiles = [{ id: "kit-a", name: "Kit Alpha" }];
  const reports: any[] = [];
  const writes: string[] = [];
  page.on("pageerror", error => { throw error; });
  await page.route("**/api/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== "GET") writes.push(path);
    if (path === "/api/v1/lab/profiles") return route.fulfill({ json: { active_profile: profiles[0], profiles } });
    if (path.endsWith("/save-as")) { profiles.push({id: "kit-b", name: request.postDataJSON().name}); return route.fulfill({status:201, json: profiles[1]}); }
    if (path.endsWith("/reports")) {
      if (request.method() === "POST") {
        const report = {id: "report-1", name: "Kit Alpha", profile_id: "kit-a", captured_at: "2026-09-14T12:00:00Z", rack_revision: 2, limitations: "Snapshot, not build completion proof.", equipment: [{ name: "Server Alpha", model: "HPE DL360", position:2, device_id:"device-a", host:null, connection:"Not checked", checked_at:null, versions:[] }], activity: []};
        reports.push(report); return route.fulfill({status:201, json:report});
      }
      return route.fulfill({json: reports});
    }
    throw new Error(`Unexpected API ${path}`);
  });
  await page.route("**/setup/guide*", route => route.fulfill({contentType:"text/html", body:`<html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script type="module">
    import RefreshRuntime from '/@react-refresh'; RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$=()=>{}; window.$RefreshSig$=()=>(type)=>type; window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/kitLibraryHarness.tsx');
    </script></body></html>`}));
  await page.goto("/setup/guide");
  await page.getByRole("button", {name:"Save as new kit"}).click();
  await page.getByLabel("Kit name").fill("Kit Beta");
  await page.getByRole("button", {name:"Save", exact:true}).click();
  await expect(page.getByRole("status")).toContainText('Saved "Kit Beta"');
  await expect(page.getByLabel("Kit", {exact:true})).toHaveValue("kit-a");
  expect(writes).toEqual(["/api/v1/rack-plans/kit-a/save-as"]);
  await page.getByRole("button", {name:"Build reports"}).click();
  await expect(page.getByText("No reports saved for this kit yet.")).toBeVisible();
  await page.getByRole("button", {name:"Save report snapshot"}).click();
  await expect(page.getByRole("heading", {name:"Kit Alpha", exact:true})).toBeVisible();
  for (const width of [1440, 390]) {
    await page.setViewportSize({width, height:900});
    expect(await page.locator("dialog").evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await page.screenshot({path:`test-results/kit-report-${width}.png`, fullPage:true});
  }
  await page.getByRole("button", {name:"Close", exact:true}).click();
  await page.getByRole("button", {name:"Build reports"}).click();
  await expect(page.getByRole("heading", {name:"Kit Alpha", exact:true})).toBeVisible();
  expect(writes).toHaveLength(2);
  await page.goto("/setup/guide?report=1");
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("heading", {name:"Kit Alpha", exact:true})).toBeVisible();
  expect(writes).toHaveLength(2);
});
