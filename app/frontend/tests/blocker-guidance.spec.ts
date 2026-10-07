import { test, expect } from "@playwright/test";

// Contract: backend app/services/blocker_guidance.py (blocker_details beside plain blockers).
const html = `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/blockerGuidanceHarness.tsx');</script></body></html>`;

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", route => route.fulfill({ status: 404, json: {} }));
  await page.route("**/guidance-fixture", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto("/guidance-fixture");
});

test("each blocker shows what's wrong, how to fix it, and who fixes it", async ({ page }) => {
  const box = page.getByRole("note", { name: "Fix this first" });
  await expect(box).toContainText("At least one enabled healthy power supply with input voltage is required.");
  await expect(box).toContainText("How to fix: Connect at least one healthy power supply to a working outlet.");
  await expect(box.getByText("Needs a hands-on fix")).toBeVisible();
  await expect(box.getByText("The app can fix this").first()).toBeVisible();
});

test("an unknown blocker is still shown, without invented guidance", async ({ page }) => {
  const item = page.getByRole("note", { name: "Fix this first" }).getByRole("listitem").filter({ hasText: "Some brand-new backend message." });
  await expect(item).toBeVisible();
  await expect(item).not.toContainText("How to fix");
  await expect(item.getByRole("button")).toHaveCount(0);
});

test("a shared fix gets one button, and the button runs the app's own fix", async ({ page }) => {
  const box = page.getByRole("note", { name: "Fix this first" });
  await expect(box.getByRole("button", { name: "Read again" })).toHaveCount(1);
  await box.getByRole("button", { name: "Read again" }).click();
  expect(await page.evaluate(() => (window as unknown as { clicks: string[] }).clicks)).toEqual(["read_again"]);
});

test("connection fixes link to this server's connection settings", async ({ page }) => {
  await expect(page.getByRole("link", { name: "Open connection settings" })).toHaveAttribute("href", "/setup/connect?device=srv-1");
});

test("no blockers renders nothing, and no handler means no button", async ({ page }) => {
  await expect(page.getByTestId("empty")).toBeEmpty();
  const plain = page.getByRole("note", { name: "Plain" });
  await expect(plain).toContainText("How to fix: Read the iLO again.");
  await expect(plain.getByRole("button")).toHaveCount(0);
});

test("fits a phone", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
