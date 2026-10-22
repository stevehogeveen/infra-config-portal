import { expect, test, type Page } from "@playwright/test";

// Rehearsal rack: the whole build on pretend equipment. It must never call the app's API.
async function open(page: Page) {
  const calls: string[] = [];
  await page.route("**/api/**", route => { calls.push(route.request().url()); return route.fulfill({ status: 500, json: { detail: "no API in rehearsal" } }); });
  await page.route("**/rehearsal-fixture", r => r.fulfill({ contentType: "text/html", body: `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/rehearsalHarness.tsx');</script></body></html>` }));
  await page.goto("/rehearsal-fixture");
  return calls;
}

async function nextOrDone(page: Page) {
  const next = page.getByRole("button", { name: /^Next: / });
  const done = page.getByRole("heading", { name: /Kit built/ });
  await expect(next.or(done)).toBeVisible({ timeout: 20000 });
  if (await next.isVisible()) await next.click();
}

test("a smooth practice run builds all seven steps and the pretend rack goes green", async ({ page }) => {
  const calls = await open(page);
  await page.getByRole("checkbox", { name: "With surprises" }).uncheck();
  await page.getByRole("button", { name: "Start practice" }).click();
  for (let i = 0; i < 7; i++) await nextOrDone(page);
  await expect(page.getByRole("heading", { name: /Kit built/ })).toBeVisible();
  for (const device of ["server", "vm", "switch"]) await expect(page.getByTestId(`rh-${device}`)).toHaveClass(/rh-ok/);
  expect(calls).toEqual([]);
});

test("a surprise stops the step; the wrong fix explains why, the right one carries on", async ({ page }) => {
  const calls = await open(page);
  const pick = page.getByRole("group", { name: "Problems to practise" });
  for (const name of ["Update firmware", "Build RAID", "Set up the switch"]) await pick.getByRole("checkbox", { name }).uncheck();
  await pick.getByRole("checkbox", { name: "Connect the server" }).check();
  await page.getByRole("button", { name: "Start practice" }).click();
  const problem = page.getByRole("alert");
  await expect(problem).toContainText("Nothing answered at 192.0.2.10.");
  await expect(page.getByTestId("rh-server")).toHaveClass(/rh-bad/);
  await problem.getByRole("button", { name: "Restart the server" }).click();
  await expect(problem).toContainText("Check the cable first");
  await problem.getByRole("button", { name: /Check the cable is in the iLO port/ }).click();
  for (let i = 0; i < 7; i++) await nextOrDone(page);
  await expect(page.getByRole("status")).toContainText("Problems handled: Connect the server. Wrong first tries: 1.");
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  }
  expect(calls).toEqual([]);
});
