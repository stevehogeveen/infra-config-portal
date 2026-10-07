import { expect, test } from "@playwright/test";

test("inventory is queued explicitly and mock results are never hardware proof", async ({ page }) => {
  let queued = false;
  let posts = 0;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    expect(new URL(request.url()).pathname).toBe("/api/v1/devices/fixture-a/inventory-jobs");
    if (request.method() === "POST") {
      posts++;
      queued = true;
      expect(request.postDataJSON()).toEqual({});
      return route.fulfill({ status: 202, json: {
        version: 1, job_id: "fixture-job", device_id: "fixture-a", status: "queued", current: false, result: null,
      } });
    }
    return route.fulfill({ json: queued ? {
      version: 1, job_id: "fixture-job", device_id: "fixture-a", status: "completed", current: false,
      result: {
        version: 1, device_id: "fixture-a", status: "completed", source: "mock",
        checked_at: "2026-09-10T12:00:00Z", systems: [],
        summary: "Mock job completed. No hardware was contacted and no inventory is proven.",
      },
    } : null });
  });
  await page.route("**/inventory-test", (route) => route.fulfill({
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
        const { InventoryWorkflowPanel } = await import("/src/components/InventoryWorkflowPanel.tsx");
        await import("/src/styles.css");
        ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(InventoryWorkflowPanel, {
          deviceId: "fixture-a", currentHost: "ilo-a.example.test"
        }));
      </script></body></html>`
  }));
  await page.goto("/inventory-test");
  const read = page.getByRole("button", { name: "Read inventory" });
  await expect(read).toBeEnabled();
  expect(posts).toBe(0);
  await read.click();
  await expect(page.getByRole("button", { name: "Inventory pending" })).toBeDisabled();
  await expect(page.getByText("Mock result", { exact: false })).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("Current observation", { exact: false })).toHaveCount(0);
  expect(posts).toBe(1);
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: `test-results/inventory-workflow-${width}.png`, fullPage: true });
  }
  await page.route("**/api/**", (route) => route.fulfill({
    status: 503, json: { detail: "Automation queue is unavailable." },
  }));
  await read.click();
  await expect(page.getByRole("alert")).toContainText("Automation queue is unavailable.");
});
