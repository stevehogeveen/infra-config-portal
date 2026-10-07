import { expect, test } from "@playwright/test";
import { saveRack } from "./fixtures/saveRack";

test("photographic fronts preserve exact configuration and fit small screens", async ({ page }) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  let plan: any = { revision: 1, rack_units: 12, equipment: [
    { id: "s1", device_id: "d1", name: "DL360", kind: "server", model: "HPE DL360 Gen11", position: 12, height: 1, ports: 0, bay_count: 10, occupied_bays: [1, 2] },
    { id: "s2", device_id: "d2", name: "DL380", kind: "server", model: "HPE DL380 Gen11", position: 10, height: 2, ports: 0, bay_count: 24, occupied_bays: [1, 2, 24] },
    { id: "sw", device_id: "d3", name: "Catalyst", kind: "switch", model: "Catalyst 9300", position: 9, height: 1, ports: 24, uplink_ports: 4, bay_count: 0, occupied_bays: [] },
    { id: "ups", device_id: "d4", name: "UPS", kind: "ups", model: "Rackmount UPS", position: 7, height: 2, ports: 0, bay_count: 0, occupied_bays: [] },
    { id: "eaton", device_id: "d5", name: "Eaton", kind: "ups", model: "Eaton 5P 1550", position: 6, height: 1, ports: 0, bay_count: 0, occupied_bays: [] },
    { id: "pdu", device_id: "d6", name: "PDU", kind: "pdu", model: "", position: 5, height: 1, ports: 0, bay_count: 0, occupied_bays: [] },
    { id: "netapp", device_id: "d7", name: "NetApp", kind: "storage", model: "NetApp 24 SFF", position: 3, height: 2, ports: 0, bay_count: 24, occupied_bays: Array.from({ length: 24 }, (_, i) => i + 1) },
    { id: "unknown", device_id: "d8", name: "Unknown server", kind: "server", model: "", position: 1, height: 2, ports: 0, bay_count: 0, occupied_bays: [] }
  ].map(item => ({ mount: "rack", ...item })) };
  await page.route("**/api/**", route => {
    expect(new URL(route.request().url()).pathname).toBe("/api/v1/rack-plans/art");
    if (route.request().method() === "PUT") plan = { ...route.request().postDataJSON(), revision: plan.revision + 1 };
    return route.fulfill({ json: plan });
  });
  await page.route("**/hardware-art-test", route => route.fulfill({ contentType: "text/html", body: `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
    import RefreshRuntime from "/@react-refresh";
    RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;window.__vite_plugin_react_preamble_installed__=true;
    const {default:React}=await import("/node_modules/.vite/deps/react.js");
    const {default:ReactDOM}=await import("/node_modules/.vite/deps/react-dom_client.js");
    const {RackPlanner}=await import("/src/components/RackPlanner.tsx");
    ReactDOM.createRoot(document.getElementById("root")).render(React.createElement("div",{className:"rack-workbench"},React.createElement(RackPlanner,{profileId:"art",devices:[{id:"outside-rack",display_name:"Legacy outside server",device_type:"ilo"}]})));
    </script></body></html>` }));
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/hardware-art-test");
  await expect(page.getByText("Saved equipment outside this rack", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Legacy outside server", exact: true })).toHaveCount(0);
  await expect(page.getByTestId("bays-s1").locator(".hw-bay")).toHaveCount(10);
  await expect(page.getByTestId("bays-s2").locator(".hw-bay")).toHaveCount(24);
  await expect(page.getByTestId("bays-netapp").locator(".occupied")).toHaveCount(24);
  await expect(page.getByRole("button", { name: "Select Unknown server", exact: true }).locator(".hw-bay")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Place HPE DL380", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Place Eaton 1550", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Select DL360", exact: true }).click();
  await page.getByRole("tab", { name: "Drives", exact: true }).click();
  await page.getByLabel("Drive bay capacity", { exact: true }).fill("11");
  await expect(page.getByRole("alert")).toContainText("DL360 supports up to 10");
  await expect(page.getByRole("button", { name: "Save a copy", exact: true })).toBeDisabled();
  await page.getByLabel("Drive bay capacity", { exact: true }).fill("10");
  await page.getByRole("button", { name: "Select DL380", exact: true }).click();
  await page.getByRole("button", { name: "Bay 24", exact: true }).click();
  await expect(page.getByTestId("bays-s2").locator(".occupied")).toHaveCount(2);
  await page.getByRole("button", { name: "Select NetApp", exact: true }).click();
  await page.getByRole("button", { name: "Bay 24", exact: true }).click();
  await expect(page.getByTestId("bays-netapp").locator(".occupied")).toHaveCount(23);
  await page.getByRole("button", { name: "Select Catalyst", exact: true }).click();
  await page.getByRole("tab", { name: "Edit equipment", exact: true }).click();
  await page.getByLabel("Switch ports", { exact: true }).selectOption("48");
  await expect(page.getByTestId("ports-sw").locator(".hw-port")).toHaveCount(48);
  await expect(page.getByRole("button", { name: "Select Catalyst", exact: true }).locator(".hw-sfp-port")).toHaveCount(4);
  await page.getByLabel("SFP uplink slots", { exact: true }).selectOption("0");
  await expect(page.getByRole("button", { name: "Select Catalyst", exact: true }).locator(".hw-sfp-port")).toHaveCount(0);
  await page.getByLabel("SFP uplink slots", { exact: true }).selectOption("4");
  await page.getByLabel("Switch ports", { exact: true }).selectOption("24");
  await saveRack(page);
  await page.reload();
  expect(plan.equipment.find((item: any) => item.id === "sw").uplink_ports).toBe(4);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1100 });
    await expect.poll(() => page.locator(".hw-art img").evaluateAll(images => images.every(img => (img as HTMLImageElement).complete && (img as HTMLImageElement).naturalWidth > 0))).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const name of ["DL360", "DL380", "Catalyst", "UPS", "Eaton", "PDU", "NetApp", "Unknown server"]) {
      const device = page.getByRole("button", { name: `Select ${name}`, exact: true });
      await device.click();
      const face = (await device.locator(".hw-art").boundingBox())!;
      expect(face.width / face.height).toBeGreaterThan(["DL360", "Catalyst", "Eaton", "PDU"].includes(name) ? 7 : 4);
      await device.screenshot({ path: `test-results/hardware-${name.replaceAll(" ", "-")}-${width}.png` });
    }
    await page.getByRole("button", { name: "Select DL380", exact: true }).click();
    await page.getByRole("tab", { name: "Overview", exact: true }).click();
    await page.getByRole("button", { name: "Enlarge equipment image" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(await page.getByRole("dialog").evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await page.screenshot({ path: `test-results/hardware-detail-${width}.png`, fullPage: true });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByRole("button", { name: "Enlarge equipment image" })).toBeFocused();
  }
  plan = { revision: 2, rack_units: 24, equipment: [] };
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.evaluate(() => localStorage.removeItem("rack-workbench-draft-v1:art"));
  await page.reload();
  const presets = [
    { name: "HPE DL360", slot: 24, height: 1, bays: 10 },
    { name: "HPE DL380", slot: 23, height: 2, bays: 24 },
    { name: "Cisco switch", slot: 21, height: 1, bays: 0 },
    { name: "UPS", slot: 20, height: 2, bays: 0 },
    { name: "Eaton 1550", slot: 18, height: 1, bays: 0 },
    { name: "PDU", slot: 17, height: 1, bays: 0 },
    { name: "NetApp storage", slot: 16, height: 2, bays: 24 }
  ];
  for (const [index, preset] of presets.entries()) {
    await page.getByRole("button", { name: `Place ${preset.name}`, exact: true }).click();
    await page.getByRole("button", { name: `Place at U${preset.slot}`, exact: true }).click();
    await expect(page.getByLabel("Equipment height", { exact: true })).toHaveValue(String(preset.height));
    const item = page.getByRole("button", { name: `Select ${preset.name} ${index + 1}`, exact: true });
    await expect(item.locator(".hw-bay")).toHaveCount(preset.bays);
    await expect(item.locator(".hw-bay.occupied")).toHaveCount(0);
    if (preset.name === "Cisco switch") {
      await expect(item.locator(".hw-port")).toHaveCount(24);
      await expect(item.locator(".hw-sfp-port")).toHaveCount(4);
    }
  }
  await page.getByRole("button", { name: "Select PDU 6", exact: true }).click();
  await page.getByLabel("PDU mount", { exact: true }).selectOption("left");
  await page.getByLabel("Bottom slot", { exact: true }).fill("1");
  await page.getByLabel("Equipment height", { exact: true }).fill("12");
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1100 });
    const side = page.getByRole("button", { name: "Select PDU 6", exact: true }).locator(".hw-art");
    const bounds = (await side.boundingBox())!;
    expect(bounds.height).toBeGreaterThan(bounds.width * 10);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await saveRack(page);
  await expect(page.getByRole("status")).toContainText("Rack plan saved");
  expect(plan.equipment).toHaveLength(7);
  const beforeResize = await page.locator(".rack-plan-equipment").evaluateAll(items => items.map(item => item.getAttribute("style")));
  await page.getByLabel("Rack height", { exact: true }).fill("8");
  await page.getByLabel("Rack height", { exact: true }).press("Enter");
  await expect(page.getByRole("alert")).toContainText("cannot fit");
  await expect(page.getByLabel("Rack height", { exact: true })).toHaveValue("24");
  expect(await page.locator(".rack-plan-equipment").evaluateAll(items => items.map(item => item.getAttribute("style")))).toEqual(beforeResize);
  expect(errors).toEqual([]);
});
