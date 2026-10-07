import { test, expect } from "@playwright/test";

const html = `<html><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/studioPaletteHarness.tsx');</script></body></html>`;

test("command palette traps focus, closes with Escape from any command and never opens over a dialog", async ({ page }) => {
  await page.route("**/api/**", route => {
    if (route.request().method() !== "GET") throw new Error("Unexpected write");
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/rack-plans/fixture-p")) return route.fulfill({ json: { revision: 1, rack_units: 4, equipment: [] } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.route("**/studio-palette-fixture", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto("/studio-palette-fixture");
  const before = page.getByRole("button", { name: "Before palette" });
  await before.focus();
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Command" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(palette.getByRole("option").last()).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("textbox", { name: "Command" })).toBeFocused();
  await palette.getByRole("option").first().focus();
  await page.keyboard.press("Escape");
  await expect(palette).toHaveCount(0);
  await expect(before).toBeFocused();
  await page.getByRole("button", { name: "Open confirmation" }).click();
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toHaveCount(0);
});
