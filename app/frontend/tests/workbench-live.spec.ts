import { test, expect } from "@playwright/test";

test("workbench pages share navigation and light styling", async ({ page }) => {
  test.skip(!process.env.WORKBENCH_URL, "Optional read-only visual check of the running mock app");
  test.setTimeout(120000);
  await page.route("**/api/**", route => ["GET", "HEAD"].includes(route.request().method()) ? route.continue() : route.abort());
  for (const path of ["/simple", "/setup/guide", "/setup/defaults", "/setup/connect", "/setup/check-firmware", "/setup/prepare-esxi", "/setup/install-windows", "/setup/history"]) {
    await page.goto(process.env.WORKBENCH_URL + path);
    const nav = page.getByRole("navigation", { name: "Main navigation", exact: true });
    await expect(nav.getByRole("link")).toHaveText(["My Rack", "Setup"]);
    if (path.startsWith("/setup/")) {
      // The left build-steps rail was removed (2026-09-29); the guide banner carries the step.
      await expect(nav.getByRole("link", { name: "Setup", exact: true })).toHaveAttribute("aria-current", "page");
    }
    if (path === "/setup/check-firmware") {
      await expect(page.getByRole("heading", { name: "Check firmware", exact: true })).toBeVisible();
      await expect(page.locator(".journey-tools")).toHaveCount(0);
    }
    if (path === "/setup/defaults") {
      await expect(page.getByRole("button", { name: "Initial iLO connection", exact: true })).toHaveCount(0);
    }
    if (path === "/setup/history") await expect(page.getByText("Loading activity...", { exact: true })).toBeHidden({ timeout: 20000 });
    await page.waitForLoadState("networkidle");
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 950 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(await page.locator('.hardware-health-issue dl > div').evaluateAll(facts => facts.every(fact => {
        const label = fact.querySelector('dt')!.getBoundingClientRect();
        const value = fact.querySelector('dd')!.getBoundingClientRect();
        return value.top >= label.bottom && value.right <= fact.getBoundingClientRect().right + 1;
      }))).toBe(true);
      if (path.startsWith("/setup/")) await expect(page.getByRole("link", { name: "Run history", exact: true })).toBeVisible();
      await page.screenshot({ path: `test-results/aligned-${path.replaceAll("/", "-")}-${width}.png`, fullPage: true });
    }
  }
  await page.goto(process.env.WORKBENCH_URL + "/equipment");
  await expect(page).toHaveURL(/\/simple$/);
  await page.goto(process.env.WORKBENCH_URL + "/run-center");
  await expect(page).toHaveURL(/\/setup\/history$/);
});
