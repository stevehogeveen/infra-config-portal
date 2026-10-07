import { test, expect } from "@playwright/test";

test("server and iLO panels fit narrow workspace widths", async ({ page }) => {
  test.skip(!process.env.WORKBENCH_URL, "Read-only visual check of the running mock app");
  test.setTimeout(180000);
  await page.route("**/api/**", route => ["GET", "HEAD"].includes(route.request().method()) ? route.continue() : route.abort());
  for (const path of ["/server", "/setup/prepare-esxi"]) {
    await page.goto(process.env.WORKBENCH_URL + path);
    await page.waitForLoadState("networkidle");
    if (path.startsWith("/setup/")) {
      await expect(page.getByRole("heading",{name:"ESXi host settings",exact:true})).toBeVisible();
      await expect(page.getByLabel("Planned iLO IP")).toHaveCount(0);
      await expect(page.getByRole("region",{name:"Drives and RAID"})).toHaveCount(0);
      for (const width of [1024,768,390]) {
        await page.setViewportSize({width,height:950});
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
        for (const field of await page.locator('.guided-esxi .rack-server-input-grid input').all()) {
          const box=await field.boundingBox();expect(box!.width).toBeGreaterThan(180);expect(box!.height).toBeLessThanOrEqual(50);
        }
        await page.screenshot({path:`test-results/esxi-only-${width}.png`,fullPage:true});
      }
      continue;
    }
    const tabs = page.getByRole("tablist", { name: "Server workspace sections" }).getByRole("tab");
    for (const width of [1024, 768, 390]) {
      await page.setViewportSize({ width, height: 950 });
      for (const index of [0, 1, 2]) {
        await tabs.nth(index).click();
        await page.waitForLoadState("networkidle");
        await page.screenshot({ path: `test-results/server-${path.replaceAll("/", "-")}-${width}-${index}.png`, fullPage: true });
        const panel = page.locator(".rack-server-workspace");
        expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      }
    }
  }
});
