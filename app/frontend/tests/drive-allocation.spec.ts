import { expect, test } from "@playwright/test";

test("saved preview is target-bound, invalidated by edits, and never applies", async ({ page }) => {
  test.setTimeout(60000);
  page.on("pageerror", (error) => { throw error; });
  const bayIds = ["1I:1:1", "1I:1:2", "1I:1:3", "2I:1:4"];
  const discovery = {
    provider_id: "ilo-redfish", source: "mock", last_probe_time: null,
    storage_inventory_available: true, server: {}, controllers: [],
    physical_drives: bayIds.map((bay_id) => ({ bay_id, capacity_label: "480 GB", media_type: "SSD" })),
    logical_drives: [], warnings: [], blockers: [], next_safe_action: "Review inventory."
  };
  let intent = {
    device_id: "fixture-a", controller_ref: "SmartArray", wipe_existing_logical_drives: false,
    volumes: [{
      name: "ESXi-OS", purpose: "ESXi boot", raid_level: "RAID1", drive_bays: bayIds.slice(0, 2),
      spare_bays: ["2I:1:4"], spare_rebuild_mode: null, size_policy: "max", bootable: true
    }], notes: null
  };
  let wrongTarget = false;
  let currentHost = "ilo-a.example.test";
  const requests: string[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    requests.push(route.request().method() + " " + url.pathname);
    expect(url.searchParams.get("device_id")).toBe("fixture-a");
    if (url.pathname.endsWith("/access-settings")) return route.fulfill({ json: {
      device_id: "fixture-a", host: currentHost, updated_at: null, verify_tls: true
    } });
    if (url.pathname.endsWith("/hpe-storage-discovery")) return route.fulfill({ json: discovery });
    if (url.pathname.endsWith("/hpe-raid-intent")) {
      if (route.request().method() === "PUT") intent = { ...intent, ...route.request().postDataJSON() };
      return route.fulfill({ json: intent });
    }
    if (url.pathname.endsWith("/hpe-raid-plan-preview")) return route.fulfill({ json: {
      provider_id: "ilo-redfish", status: "planned", apply_enabled: false,
      destructive_actions_requested: true, destructive_actions_enabled: false,
      current_layout: discovery, desired_intent: { ...intent, device_id: wrongTarget ? "fixture-b" : "fixture-a" },
      planned_layout: {}, impact: {
        logical_drives_to_delete: 0,
        physical_drives_not_selected: bayIds.filter((bay) => !intent.volumes.some((volume) => volume.drive_bays.includes(bay)))
      },
      blockers: [], warnings: ["Creating a mirror is destructive."], disabled_actions: [],
      next_safe_action: "Review the saved plan."
    } });
    throw new Error("Unexpected API request: " + url.pathname);
  });
  await page.route("**/drive-panel-test", (route) => route.fulfill({
    contentType: "text/html",
    body: `<html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body>
      <div id="root" style="max-width:520px;padding:16px"></div>
      <script type="module">
        import RefreshRuntime from "/@react-refresh";
        RefreshRuntime.injectIntoGlobalHook(window);
        window.$RefreshReg$ = () => {};
        window.$RefreshSig$ = () => (type) => type;
        window.__vite_plugin_react_preamble_installed__ = true;
        const { default: React } = await import("/node_modules/.vite/deps/react.js");
        const { default: ReactDOM } = await import("/node_modules/.vite/deps/react-dom_client.js");
        const { DriveAllocationPanel } = await import("/src/components/DriveAllocationPanel.tsx");
        await import("/src/styles.css");
        ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(DriveAllocationPanel, {
          deviceId: "fixture-a", deviceName: "Fixture A"
        }));
      </script></body></html>`
  }));
  await page.goto("/drive-panel-test");
  const previewButton = page.getByRole("button", { name: "Preview saved plan" });
  await expect(previewButton).toBeEnabled({ timeout: 30000 });
  await previewButton.click();
  const preview = page.getByRole("region", { name: "RAID plan preview" });
  await expect(preview).toContainText("1I:1:1, 1I:1:2");
  await expect(preview.getByRole("button", { name: "Apply RAID plan" })).toBeDisabled();
  await expect(preview).toContainText("default lab target");
  await page.getByRole("radio", { name: "Local" }).click();
  await page.getByRole("button", { name: /Bay 3/ }).click();
  await expect(preview).toHaveCount(0);
  await expect(previewButton).toBeDisabled();
  await page.getByRole("button", { name: "Save this plan" }).click();
  await expect(previewButton).toBeEnabled();
  expect(intent.volumes.flatMap((volume) => volume.drive_bays)).toEqual(bayIds.slice(0, 3));
  expect(intent.volumes.flatMap((volume) => volume.spare_bays)).toEqual([]);
  wrongTarget = true;
  await previewButton.click();
  await expect(page.getByText("The saved plan changed. Reload it before reviewing the impact.")).toBeVisible();
  await expect(preview).toHaveCount(0);
  wrongTarget = false;
  await previewButton.click();
  await expect(preview).toBeVisible();
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    await page.screenshot({ path: `test-results/drive-allocation-${width}.png`, fullPage: true });
  }
  currentHost = "ilo-a-moved.example.test";
  await previewButton.click();
  await expect(page.getByText("Device access changed. Reload inventory from the current address before continuing.")).toBeVisible();
  await expect(preview).toHaveCount(0);
  await page.getByRole("button", { name: "Retry inventory" }).click();
  await expect(page.getByText("Current saved address: ilo-a-moved.example.test")).toBeVisible();
  await expect(previewButton).toBeEnabled();
  discovery.physical_drives[3].bay_id = "";
  await page.getByRole("button", { name: "Reload saved allocation" }).click();
  await expect(page.getByText("Some drives have missing or duplicate bay IDs.", { exact: false })).toBeVisible();
  await expect(previewButton).toBeDisabled();
  await expect(page.getByRole("button", { name: /Bay 4/ })).toHaveCount(0);
  expect(requests.filter((request) => request.startsWith("POST"))).toEqual([]);
});
