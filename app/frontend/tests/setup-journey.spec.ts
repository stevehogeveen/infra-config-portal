import { expect, test, type Locator, type Page } from "@playwright/test";
import { saveRack } from "./fixtures/saveRack";

const harnessHtml = `<html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script type="module">
  import RefreshRuntime from '/@react-refresh';
  RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;window.__vite_plugin_react_preamble_installed__=true;
  await import('/tests/fixtures/setupJourneyHarness.tsx');
  </script></body></html>`;

test("My Rack opens as saved status and never contacts equipment until Edit rack is chosen", async ({ page }) => {
  let current = true;
  await page.route("**/api/**", route => {
    { const u = new URL(route.request().url()).pathname; if (/\/devices\/[^/]+\/health$|\/cable-map$|^\/api\/v1\/jobs$/.test(u)) return route.fulfill({ json: u.endsWith("/jobs") ? { running: [], attention: [], recent: [] } : u.endsWith("cable-map") ? { state: "not_read", cables: [], unmatched_server_ports: [], other_switch_ports: [] } : { overall: null, problems: [], checked_at: null } }); }
    expect(route.request().method()).toBe("GET");
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/jobs") return route.fulfill({ json: { running: [], attention: [], recent: [], now: new Date().toISOString() } });
    if (url.pathname === "/api/v1/rack-plans/fixture") return route.fulfill({ json: {
      revision: 1, rack_units: 4, equipment: [{
        id: "server", device_id: "server", name: "Server Alpha", kind: "server",
        model: "HPE DL360 Gen11", position: 1, height: 1, mount: "rack",
        ports: 0, bay_count: 10, occupied_bays: [],
      }],
    } });
    expect(url.pathname).toBe("/api/v1/providers/ilo-redfish/access-settings");
    expect(url.searchParams.get("device_id")).toBe("server");
    return route.fulfill({ json: { device_id: "server", host: "192.0.2.10",
      last_probe_time: new Date().toISOString(), last_probe_status: "ok",
      last_probe_is_current: current, last_probe_target_matches_access_host: current,
      observed_ilo_firmware: "iLO 5 v1.37", observed_bios_version: "U32 v1.46 (10/02/2018)",
    } });
  });
  await page.route("**/simple", route => route.fulfill({ contentType: "text/html", body: harnessHtml }));
  await page.goto("/simple");
  await expect(page.getByText("Connected at last check", { exact: true })).toBeVisible();
  await expect(page.getByText("192.0.2.10", { exact: false })).toBeVisible();
  for (const name of ["Edit equipment", "Review details", "Connect server", "Save a copy", "Load plan", "Move equipment", "Save changes"]) {
    await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
  }
  await expect(page.getByRole("group", { name: "Choose hardware" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Edit rack", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Continue setup" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Equipment status" }).locator("input, select, textarea")).toHaveCount(0);
  await expect(page.getByText("ESXi version", { exact: true })).toBeVisible();
  await expect(page.getByText("iLO 5 v1.37", { exact: true })).toBeVisible();
  await expect(page.getByText("U32 v1.46 (10/02/2018)", { exact: true })).toBeVisible();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 950 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/rack-status-${width}.png`, fullPage: true });
  }
  current = false;
  await page.reload();
  await expect(page.getByText("Needs recheck", { exact: true })).toBeVisible();
  await expect(page.getByText("Connected at last check", { exact: true })).toHaveCount(0);
  await expect(page.getByText("iLO 5 v1.37", { exact: true })).toHaveCount(0);
});

test("My Rack: Edit rack brings back the shelf, placing, moving and saving the plan", async ({ page }) => {
  let savedPlan: any = null;
  const plan = { revision: 1, rack_units: 6, equipment: [{ id: "server", device_id: "server", name: "Server Alpha", kind: "server",
    model: "HPE DL360 Gen10", position: 1, height: 1, mount: "rack", ports: 0, bay_count: 10, occupied_bays: [] }] };
  await page.route("**/api/**", route => {
    { const u = new URL(route.request().url()).pathname; if (/\/devices\/[^/]+\/health$|\/cable-map$|^\/api\/v1\/jobs$/.test(u)) return route.fulfill({ json: u.endsWith("/jobs") ? { running: [], attention: [], recent: [] } : u.endsWith("cable-map") ? { state: "not_read", cables: [], unmatched_server_ports: [], other_switch_ports: [] } : { overall: null, problems: [], checked_at: null } }); }
    const req = route.request(), url = new URL(req.url());
    if (url.pathname === "/api/v1/rack-plans/fixture" && req.method() === "PUT") {
      savedPlan = req.postDataJSON();
      return route.fulfill({ json: { ...savedPlan, revision: 2, equipment: savedPlan.equipment.map((item: any) => ({ ...item, device_id: item.device_id ?? item.id })) } });
    }
    expect(req.method()).toBe("GET");
    if (url.pathname === "/api/v1/rack-plans/fixture") return route.fulfill({ json: plan });
    return route.fulfill({ json: { device_id: "server", host: "192.0.2.10", last_probe_status: "never" } });
  });
  await page.route("**/simple", route => route.fulfill({ contentType: "text/html", body: harnessHtml }));
  await page.goto("/simple");
  await page.evaluate(() => localStorage.clear());
  await page.getByRole("button", { name: "Edit rack", exact: true }).click();
  await expect(page.getByRole("group", { name: "Choose hardware" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Your guide" }).locator("[title^=\"Editing changes your plan only\"]")).toHaveCount(1);
  // Add from the shelf: tap a card, then a slot.
  await page.getByRole("button", { name: "Place Cisco switch" }).click();
  await page.getByRole("button", { name: "Place at U4" }).click();
  await expect(page.getByRole("status")).toContainText("placed at U4");
  // Move a piece that is already in the rack.
  await page.getByRole("button", { name: "Select Server Alpha" }).click();
  await page.getByRole("button", { name: "Move equipment", exact: true }).click();
  await page.getByRole("button", { name: "Place at U6" }).click();
  await expect(page.getByRole("status")).toContainText("Server Alpha placed at U6");
  // And a real mouse drag: the switch from U4 up to U5.
  await dragEquipment(page, page.getByRole("button", { name: "Select Cisco switch 2", exact: true }), page.locator(".rack-plan-frame .rack-plan-unit").nth(1), { x: 100, y: 10 });
  await expect(page.getByRole("status")).toContainText("Cisco switch 2 placed at U5");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect.poll(() => savedPlan).not.toBeNull();
  const byName = Object.fromEntries(savedPlan.equipment.map((item: any) => [item.kind, item.position]));
  expect(byName).toEqual({ server: 6, switch: 5 });
  await expect(page.getByText("Rack plan saved. No hardware changed.")).toBeVisible();
  await page.getByRole("button", { name: "Done editing" }).click();
  await expect(page.getByRole("group", { name: "Choose hardware" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Edit rack", exact: true })).toBeVisible();
});

async function dragEquipment(page: Page, source: Locator, target: Locator, position?: { x: number; y: number }) {
  await source.hover();
  const box = (await source.boundingBox())!;
  await page.mouse.down();
  // Pick it up (a short move starts the drag), then glide to the target like a user would.
  await page.mouse.move(box.x + box.width / 2 + 12, box.y + box.height / 2, { steps: 4 });
  await target.scrollIntoViewIfNeeded();
  const goal = (await target.boundingBox())!;
  await page.mouse.move(goal.x + (position?.x ?? goal.width / 2), goal.y + (position?.y ?? goal.height / 2), { steps: 6 });
  await page.mouse.up();
}

test("guided setup shares the rack, keeps later stages unverified and fits desktop/mobile", async ({ page }) => {
  test.setTimeout(90000);
  page.on("pageerror", error => { throw error; });
  let plan: any = { revision: 0, rack_units: 8, equipment: [] };
  let writes = 0;
  await page.route("**/api/**", async route => {
    { const u = new URL(route.request().url()).pathname; if (/\/devices\/[^/]+\/health$|\/cable-map$|^\/api\/v1\/jobs$/.test(u)) return route.fulfill({ json: u.endsWith("/jobs") ? { running: [], attention: [], recent: [] } : u.endsWith("cable-map") ? { state: "not_read", cables: [], unmatched_server_ports: [], other_switch_ports: [] } : { overall: null, problems: [], checked_at: null } }); }
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/rack-plans/fixture") {
      if (route.request().method() === "PUT") {
        writes++;
        plan = { ...route.request().postDataJSON(), revision: plan.revision + 1 };
        plan.equipment = plan.equipment.map((item: any, index: number) => ({ ...item, device_id: `fixture-${index}` }));
      }
      return route.fulfill({ json: plan });
    }
    if (path === "/api/v1/jobs") return route.fulfill({ json: { running: [], attention: [], recent: [], now: new Date().toISOString() } });
    if (path === "/api/v1/providers/ilo-redfish/access-settings") return route.fulfill({ json: { host: "", username: "", verify_tls: false, username_configured: false, password_configured: false } });
    if (path.endsWith("/firmware-execution/status")) return route.fulfill({ json: { status: "not_started", blockers: [], stages: [] } });
    if (path.includes("/firmware-update/")) return route.fulfill({ status: 404, json: { detail: "Not Found" } });
    if (path.endsWith("/parts-update/status")) return route.fulfill({ json: { state: "not_started", active: false, phases: [], parts: [], message: "" } });
    if (path.endsWith("/raid-rebuild/status")) return route.fulfill({json:{status:"not_started",active:false,message:"No RAID operation submitted."}});
    if (path.endsWith("/disk-preparation")) return route.fulfill({json:{current:false,drives:[],volumes:[],blockers:[],health_issues:[],saved_intent:{volumes:[],wipe_existing_logical_drives:false}}});
    if (path.endsWith("/firmware-package")) return route.fulfill({json:{root:"/media",host_root:null,folder:"",folders:[],files:[],warning:null,selected:null,selection_current:false}});
    if (path.endsWith("/firmware-assessment")) return route.fulfill({json:{status:"Cannot determine",reason:"Select an SPP above to compare installed firmware.",rows:[]}});
    throw new Error(`Unexpected API request ${route.request().method()} ${path}`);
  });
  await page.route(/\/(simple|equipment|setup\/(guide|defaults|connect|check-firmware|disks|raid|prepare-esxi|install-windows))(\?.*)?$/, route => route.fulfill({ contentType: "text/html", body: harnessHtml }));
  await page.goto("/setup/guide");
  await expect(page.getByLabel("Equipment to add", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Place HPE DL360", exact: true }).click();
  await page.getByRole("button", { name: "Place at U2", exact: true }).click();
  await page.getByLabel("Equipment name", { exact: true }).fill("Server Alpha");
  await saveRack(page);
  await page.getByRole("link", { name: "Next: Network settings" }).click();
  await expect(page.getByRole("heading", { name: "Network settings", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Your guide" })).toContainText("Step 2 of 7");
  await page.getByRole("link", { name: "Next: Connect equipment" }).click();
  await expect(page.getByRole("heading", { name: "Connect Server Alpha" })).toBeVisible();
  await expect(page.getByLabel("Current iLO address", { exact: true })).toHaveValue("");
  expect(writes).toBe(1);
  for (const [path, heading] of [["check-firmware", "Check firmware"], ["disks", "Disks & RAID"], ["raid", "Disks & RAID"], ["prepare-esxi", "Prepare ESXi"], ["install-windows", "Install Windows"]]) {
    await page.goto(`/setup/${path}`);
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    if (path === "check-firmware") {
      await expect(page.getByText("Readiness not yet confirmed", { exact: true })).toHaveCount(0);
      await expect(page.getByRole("region", { name: "Server Alpha" })).toBeVisible();
      await expect(page.getByText("NetApp firmware", { exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Check again", exact: true })).toBeDisabled();
      await expect(page.getByRole("button", { name: /^Update to/ })).toHaveCount(0);
      continue;
    }
    if (path === "disks" || path === "raid") {
      await expect(page.getByRole("article", { name: "Server Alpha" })).toContainText(/Disks not read yet|Not connected/);
      continue;
    }
    if (path === "prepare-esxi") {
      await expect(page.getByText("Existing guarded tools")).toBeVisible();
      continue;
    }
    await expect(page.getByText("Readiness not yet confirmed", { exact: true })).toBeVisible();
    await expect(page.locator(".journey-prerequisites")).not.toHaveAttribute("open");
    await page.locator(".journey-prerequisites > summary").click();
    await expect(page.locator(".journey-checks")).toBeVisible();
    await expect(page.getByText("Existing guarded tools")).toBeVisible();
  }
  expect(writes).toBe(1);
  for (const path of ["/simple", "/equipment", "/setup/guide", "/setup/connect", "/setup/check-firmware", "/setup/disks", "/setup/raid", "/setup/prepare-esxi", "/setup/install-windows"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    if (["/simple", "/equipment", "/setup/guide"].includes(path)) await expect(page.locator(".rack-plan-inspector > h2")).toHaveText("Server Alpha");
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 950 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      await page.screenshot({ path: `test-results/journey-${path.replaceAll("/", "-")}-${width}.png`, fullPage: true });
    }
  }
  await page.goto("/simple");
  await expect(page.getByRole("button", { name: "Place HPE DL360", exact: true })).toBeHidden();
  await page.getByRole("link", { name: "Continue setup", exact: true }).click();
  await page.getByRole("button", { name: "Add equipment", exact: true }).click();
  await expect(page.getByRole("button", { name: "Place HPE DL360", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1200 });
  const frame = page.locator(".rack-plan-frame");
  await dragEquipment(page, page.getByRole("button", { name: "Place UPS", exact: true }), frame.locator(".rack-plan-unit").first(), { x: 100, y: 10 });
  await expect(page.locator(".rack-plan-equipment")).toHaveCount(2);
  const ups = page.getByRole("button", { name: "Select UPS 2", exact: true });
  await dragEquipment(page, ups, frame.locator(".rack-plan-unit").nth(3), { x: 100, y: 10 });
  await expect(page.getByLabel("Bottom slot", { exact: true })).toHaveValue("9");
  await page.getByRole("button", { name: "Place Cisco switch", exact: true }).click();
  await page.getByRole("button", { name: "Place at U9", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Moved UPS 2 to U7");
  await expect(page.locator(".rack-plan-equipment")).toHaveCount(3);
  await saveRack(page);
  await expect(page.getByRole("status")).toContainText("Rack plan saved");
  expect(plan.equipment.find((item: any) => item.name === "UPS 2").position).toBe(7);
  await page.reload();
  await dragEquipment(page, ups, frame.locator(".rack-plan-unit").nth(3), { x: 100, y: 10 });
  await expect(page.getByRole("status")).toContainText("Moved Cisco switch 3 to U8");
  page.once("dialog", dialog => dialog.accept());
  await dragEquipment(page, page.getByRole("button", { name: "Select Cisco switch 3", exact: true }), page.getByRole("button", { name: "Remove from rack", exact: true }));
  page.once("dialog", dialog => dialog.accept());
  await dragEquipment(page, ups, page.getByRole("button", { name: "Remove from rack", exact: true }));
  await expect(page.locator(".rack-plan-equipment")).toHaveCount(1);
  await page.reload();
  await expect(page.locator(".rack-plan-equipment")).toHaveCount(1);
  const server = page.getByRole("button", { name: "Select Server Alpha", exact: true });
  const topSlot = frame.locator(".rack-plan-unit").first();
  await dragEquipment(page, server, topSlot, { x: 100, y: 10 });
  await expect(page.getByLabel("Bottom slot", { exact: true })).toHaveValue("12");
  await expect(page.locator(".rack-plan-equipment .hw-bays > .hw-bay")).toHaveCount(10);
  await saveRack(page);
  await expect(page.getByRole("status")).toContainText("Rack plan saved");
  expect(plan.equipment[0]).toMatchObject({ position: 12, device_id: "fixture-0", name: "Server Alpha" });
  await page.getByLabel("Rack height", { exact: true }).fill("4");
  await saveRack(page);
  await expect(page.getByRole("status")).toContainText("Rack plan saved");
  expect(plan.rack_units).toBe(4);
  expect(plan.equipment[0]).toMatchObject({ position: 4, device_id: "fixture-0", name: "Server Alpha" });
  await page.reload();
  await expect(page.getByLabel("Rack height", { exact: true })).toHaveValue("4");
  await expect(page.getByLabel("Bottom slot", { exact: true })).toHaveValue("4");
});

test("run history is read-only, groups the app's records, filters attention and reports refresh failures", async ({ page }) => {
  let fail = false;
  await page.route("**/api/**", async route => {
    expect(route.request().method()).toBe("GET");
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/build-history") return route.fulfill({ status: fail ? 503 : 200, json: fail ? { detail: "Fixture unavailable" } : [
      { id: "e1", at: "2026-09-10T12:00:00Z", area: "Windows", message: "windows01 is running Windows.", outcome: "ok", actor: "op" },
      { id: "e2", at: "2026-09-10T11:00:00Z", area: "Disks & RAID", message: "The RAID create was not confirmed.", outcome: "failed", actor: "op" }] });
    throw new Error(`Unexpected API request ${path}`);
  });
  await page.route("**/activity-test", route => route.fulfill({ contentType: "text/html", body: harnessHtml }));
  await page.goto("/activity-test");
  await expect(page.locator(".history-list > li")).toHaveCount(2);
  await page.getByRole("button", { name: "Needs attention (1)" }).click();
  await expect(page.locator(".history-list > li")).toHaveCount(1);
  await expect(page.locator(".history-list")).toContainText("The RAID create was not confirmed.");
  fail = true;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("History could not be loaded");
  await expect(page.locator(".history-list > li")).toHaveCount(1);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  }
});
