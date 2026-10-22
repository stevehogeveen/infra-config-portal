import { expect, test } from "@playwright/test";
import { saveRack } from "./fixtures/saveRack";

test("rack plans render exact ports and bays, reject overlap and retain occupancy", async ({ page }) => {
  let saved = { revision: 0, rack_units: 12, equipment: [] as any[] };
  let accessSaves = 0;
  await page.route("**/api/**", async (route) => {
    { const u = new URL(route.request().url()).pathname; if (/\/devices\/[^/]+\/health$|\/cable-map$|^\/api\/v1\/jobs$/.test(u)) return route.fulfill({ json: u.endsWith("/jobs") ? { running: [], attention: [], recent: [] } : u.endsWith("cable-map") ? { state: "not_read", cables: [], unmatched_server_ports: [], other_switch_ports: [] } : { overall: null, problems: [], checked_at: null } }); }
    if (new URL(route.request().url()).pathname === "/api/v1/providers/ilo-redfish/access-settings") {
      expect(new URL(route.request().url()).searchParams.get("device_id")).toBe("device-0");
      if (route.request().method() === "PUT") {
        accessSaves++;
        expect(route.request().postDataJSON()).toMatchObject({ host: "ilo.example.test", username: "fixture-user", password: "fixture-password" });
      }
      return route.fulfill({ json: { host: "", username: "", verify_tls: false, username_configured: false, password_configured: false } });
    }
    expect(new URL(route.request().url()).pathname).toBe("/api/v1/rack-plans/fixture");
    if (route.request().method() === "PUT") { saved = { ...route.request().postDataJSON(), revision: saved.revision + 1 }; saved.equipment = saved.equipment.map((item, index) => ({ ...item, device_id: `device-${index}` })); }
    await route.fulfill({ json: saved });
  });
  await page.route("**/rack-plan-test", (route) => route.fulfill({ contentType: "text/html", body: `<html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script type="module">
    import RefreshRuntime from "/@react-refresh";
    RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$=()=>{}; window.$RefreshSig$=()=>(type)=>type; window.__vite_plugin_react_preamble_installed__=true;
    const {default:React}=await import("/node_modules/.vite/deps/react.js");
    const {default:ReactDOM}=await import("/node_modules/.vite/deps/react-dom_client.js");
    const {RackPlanner}=await import("/src/components/RackPlanner.tsx");
    ReactDOM.createRoot(document.getElementById("root")).render(React.createElement("div",{className:"rack-workbench"},React.createElement(RackPlanner,{profileId:"fixture"})));
    </script></body></html>` }));
  await page.goto("/rack-plan-test");
  await page.getByRole("button", { name: "Place HPE DL360", exact: true }).click();
  await page.getByRole("button", { name: "Place at U2", exact: true }).click();
  // A server model comes only from first contact (lab-build-rules §3), so the field is read-only here.
  await expect(page.getByLabel("Equipment model", { exact: true })).toHaveAttribute("readonly", "");
  await page.getByRole("tab", { name: "Drives", exact: true }).click();
  await expect(page.getByLabel("Drive bay capacity", { exact: true })).toHaveValue("10");
  await expect(page.locator(".rack-plan-equipment .hw-bays > .hw-bay")).toHaveCount(10);
  for (const bay of [1, 2, 3, 4, 5, 6, 10]) await page.getByRole("button", { name: `Bay ${bay}`, exact: true }).click();
  await expect(page.getByRole("heading", { name: "7 drives / 10 bays" })).toBeVisible();
  await page.getByRole("button", { name: "Bay 3", exact: true }).click();
  await page.getByRole("button", { name: "Place Cisco switch", exact: true }).click();
  await page.getByRole("button", { name: "Place at U3", exact: true }).click();
  await expect(page.locator(".rack-plan-equipment .hw-port")).toHaveCount(24);
  await page.getByLabel("Switch ports", { exact: true }).selectOption("48");
  await expect(page.locator(".rack-plan-equipment .hw-port")).toHaveCount(48);
  await page.getByLabel("Bottom slot", { exact: true }).fill("2");
  await expect(page.getByRole("alert")).toContainText("overlaps");
  await expect(page.getByRole("button", { name: "Save a copy", exact: true })).toBeDisabled();
  await page.getByLabel("Bottom slot", { exact: true }).fill("8");
  await page.getByRole("button", { name: "Place PDU", exact: true }).click();
  await page.getByRole("button", { name: "Place at U3", exact: true }).click();
  await page.getByLabel("PDU mount", { exact: true }).selectOption("right");
  await page.goto("about:blank");
  await page.goto("/rack-plan-test");
  await expect(page.getByRole("status")).toContainText("Recovered your rack draft");
  await expect(page.locator(".rack-plan-equipment")).toHaveCount(3);
  await expect(page.locator(".rack-plan-equipment .hw-port")).toHaveCount(48);
  await expect(page.locator(".rack-plan-equipment .hw-bay.occupied")).toHaveCount(6);
  await page.reload();
  await expect(page.getByRole("status")).toContainText("Recovered your rack draft");
  await saveRack(page);
  await expect(page.getByRole("status")).toContainText("Rack plan saved");
  expect(saved.equipment[0].occupied_bays).toEqual([1, 2, 4, 5, 6, 10]);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("rack-workbench-draft-v1:fixture"))).toBeNull();
  await page.reload();
  await expect(page.locator(".rack-plan-equipment .hw-port")).toHaveCount(48);
  await expect(page.locator(".rack-plan-equipment .hw-bays > .hw-bay")).toHaveCount(10);
  await page.getByRole("button", { name: "List", exact: true }).click();
  await expect(page.getByLabel("Equipment checklist").getByRole("button")).toHaveCount(3);
  await page.getByLabel("Equipment checklist").getByRole("button").first().click();
  await expect(page.getByRole("tab", { name: "Overview", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".equipment-readiness dd")).toHaveText(["Not checked", "Not checked", "Not checked", "Not checked"]);
  await page.getByRole("button", { name: "Connect server", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Access", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("button", { name: "Rack", exact: true }).click();
  await page.getByLabel("Current iLO address", { exact: true }).fill("ilo.example.test");
  await page.getByLabel("iLO username", { exact: true }).fill("fixture-user");
  await page.getByLabel("iLO password", { exact: true }).fill("fixture-password");
  await page.getByRole("button", { name: "Save iLO connection" }).click();
  await expect(page.getByText("Connection saved. No hardware check has run.", { exact: true })).toBeVisible();
  expect(accessSaves).toBe(1);
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 850 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: `test-results/rack-plan-${width}.png`, fullPage: true });
    await page.getByRole("button", { name: "List", exact: true }).click();
    await page.getByRole("tab", { name: "Overview", exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: `test-results/checklist-${width}.png`, fullPage: true });
    await page.getByRole("button", { name: "Rack", exact: true }).click();
  }
});
