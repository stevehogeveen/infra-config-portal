import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { saveRack } from "./fixtures/saveRack";

test("named rack copies load safely and persist without exporting connections", async ({ page }) => {
  await page.addInitScript(() => {
    (window as any).pickerMode = "cancel";
    (window as any).showSaveFilePicker = async (options: unknown) => {
      (window as any).pickerOptions = options;
      if ((window as any).pickerMode === "cancel") throw new DOMException("Cancelled", "AbortError");
      return { name: "chosen.rack-plan.json", createWritable: async () => ({
        write: async (data: Blob) => {
          if ((window as any).pickerMode === "fail") throw new Error("Disk unavailable");
          (window as any).savedCopy = await data.text();
        }, close: async () => {}, abort: async () => {}
      }) };
    };
  });
  let writes = 0;
  let plan: any = { revision: 1, rack_units: 8, equipment: [{ id: "server", device_id: "connection", name: "Original server", kind: "server", model: "HPE DL360 Gen11", position: 8, height: 1, mount: "rack", ports: 0, bay_count: 10, occupied_bays: [1, 2] }] };
  await page.route("**/api/**", route => {
    expect(new URL(route.request().url()).pathname).toBe("/api/v1/rack-plans/fixture");
    if (route.request().method() === "PUT") { writes++; plan = { ...route.request().postDataJSON(), revision: plan.revision + 1 }; }
    return route.fulfill({ json: plan });
  });
  await page.route("**/setup/guide", route => route.fulfill({ contentType: "text/html", body: `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
    import RefreshRuntime from '/@react-refresh';
    RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/setupJourneyHarness.tsx');
    </script></body></html>` }));
  await page.goto("/setup/guide");
  await expect(page.getByRole("button", { name: "Reload", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Save rack plan", exact: true })).toHaveCount(0);
  await expect(page.locator(".rack-plan-toolbar").getByRole("button", { name: "Save a copy", exact: true })).toHaveCount(0);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 950 });
    const footer = page.locator(".rack-plan-footer");
    await footer.scrollIntoViewIfNeeded();
    const controls = (await footer.boundingBox())!;
    const workspace = (await page.locator(".rack-plan-workspace").boundingBox())!;
    expect(controls.y).toBeGreaterThanOrEqual(workspace.y + workspace.height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await footer.screenshot({ path: `test-results/rack-footer-${width}.png` });
  }
  await page.getByRole("button", { name: "Save a copy", exact: true }).click();
  await page.getByLabel("Plan name", { exact: true }).fill("Windows kit");
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 950 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await page.getByLabel("Plan name", { exact: true }).boundingBox())!.width).toBeGreaterThan(250);
    await page.screenshot({ path: `test-results/rack-copy-${width}.png`, fullPage: true });
  }
  const downloadEvent = page.waitForEvent("download");
  await page.getByLabel("Save location", { exact: true }).selectOption("browser");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("rack-Windows-kit.rack-plan.json");
  const file = JSON.parse(await readFile((await download.path())!, "utf8"));
  expect(file.equipment[0].device_id).toBeUndefined();
  expect(file.name).toBe("Windows kit");
  expect(writes).toBe(1);
  await page.getByLabel("Equipment name", { exact: true }).fill("Unsaved change");
  const upload = () => page.getByLabel("Rack plan file", { exact: true }).setInputFiles({ name: "kit.rack-plan.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(file)) });
  page.once("dialog", dialog => dialog.dismiss());
  await upload();
  await expect(page.getByLabel("Equipment name", { exact: true })).toHaveValue("Unsaved change");
  page.once("dialog", dialog => dialog.accept());
  await upload();
  await expect(page.getByRole("status")).toContainText("Loaded Windows kit");
  await expect(page.getByLabel("Equipment name", { exact: true })).toHaveValue("Original server");
  expect(writes).toBe(1);
  // Change one field so the imported copy is explicitly committed to the active kit.
  await page.getByLabel("Equipment name", { exact: true }).fill("Loaded server");
  await saveRack(page);
  await expect(page.getByRole("status")).toContainText("Rack plan saved");
  expect(plan.equipment[0].device_id).toBe("connection");
  await page.reload();
  await expect(page.getByLabel("Equipment name", { exact: true })).toHaveValue("Loaded server");
  file.equipment[0].position = 99;
  await upload();
  await expect(page.getByRole("alert")).toContainText("must fit inside");
  await expect(page.getByLabel("Equipment name", { exact: true })).toHaveValue("Loaded server");
  expect(writes).toBe(2);
  // A bad import does not invalidate the current layout or prevent a fresh save.
  await page.getByRole("button", { name: "Save a copy", exact: true }).click();
  await page.getByLabel("Save location", { exact: true }).selectOption("choose");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeEnabled();
  expect(writes).toBe(2);
  await page.evaluate(() => { (window as any).pickerMode = "fail"; });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Disk unavailable");
  expect(writes).toBe(2);
  await page.evaluate(() => { (window as any).pickerMode = "save"; });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByRole("status")).toContainText("chosen location");
  expect(writes).toBe(3);
  const stored = await page.evaluate(() => JSON.parse((window as any).savedCopy));
  expect(stored.equipment[0].name).toBe("Loaded server");
  expect(stored.equipment[0].device_id).toBeUndefined();
});
