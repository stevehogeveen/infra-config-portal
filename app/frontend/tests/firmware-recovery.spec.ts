import { test, expect, type Page } from "@playwright/test";

const html = `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/guardedExecutionHarness.tsx');</script></body></html>`;
const identity = { profile_id: "fixture-kit", device_id: "fixture-server", operation_id: "op-1", resource: "firmware-execution" };
const closed = { ...identity, status: "failed", resolution: "operator_closed_unverified", dispatch_prevented: false, safe_to_retry: false };
async function mount(page: Page, options: { blocked?: boolean; wrong?: boolean; lost?: boolean; expired?: boolean } = {}) {
  const calls: string[] = [];
  let done = false;
  await page.route("**/api/**", async route => {
    const action = new URL(route.request().url()).pathname.split("/").pop()!;
    calls.push(`${route.request().method()} ${action}`);
    if (action === "status") return route.fulfill({ json: done ? closed : { ...identity, status: "uncertain", stages: [] } });
    if (action === "recovery-preview") return route.fulfill({ json: {
      ...identity, device_id: options.wrong ? "wrong" : identity.device_id,
      can_close: !options.blocked, blockers: options.blocked ? ["Verify the iLO version first."] : [],
      review_token: "review-closure", expires_at: new Date(Date.now() + (options.expired ? -60000 : 300000)).toISOString(),
      confirmation_phrase: "CLOSE UNVERIFIED UPDATE", evidence_at: new Date().toISOString(),
      message: "The previous upload outcome is unknown. Closing this attempt does not prove nothing happened or resend firmware.",
    } });
    if (action === "close-unverified") {
      expect(route.request().postDataJSON()).toEqual({ operation_id: "op-1", review_token: "review-closure", confirmation_phrase: "CLOSE UNVERIFIED UPDATE" });
      done = true;
      return options.lost ? route.abort("failed") : route.fulfill({ json: closed });
    }
    return route.fulfill({ status: 404, json: {} });
  });
  await page.route("**/recovery-fixture", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto("/recovery-fixture");
  return calls;
}
const dialog = (page: Page) => page.getByRole("dialog", { name: "Cancel upgrade" });

test("recovery is explicit, Yes/No, recorded-only, and never claims non-execution", async ({ page }) => {
  const calls = await mount(page);
  await expect(page.getByRole("button", { name: "Verify iLO version (read-only)" })).toBeVisible();
  expect(calls).toEqual(["GET status"]);
  await page.getByRole("button", { name: "Cancel upgrade" }).first().click();
  await expect(dialog(page)).toContainText("Its outcome is unknown");
  await expect(dialog(page).getByRole("button", { name: "Yes" })).toBeEnabled();
  await expect(dialog(page).getByRole("textbox")).toHaveCount(0);
  await dialog(page).getByRole("button", { name: "Yes" }).click();
  await expect(page.getByText("Closed, outcome unverified", { exact: true })).toBeVisible();
  expect(calls.filter(x => x.startsWith("POST"))).toEqual(["POST recovery-preview", "POST close-unverified"]);
});

for (const issue of ["blocked", "wrong", "expired"] as const) {
  test(`${issue} review cannot close an attempt`, async ({ page }) => {
    const calls = await mount(page, { [issue]: true });
    await page.getByRole("button", { name: "Cancel upgrade" }).first().click();
    await expect(dialog(page).getByRole("button", { name: "Yes" })).toBeDisabled();
    expect(calls).not.toContain("POST close-unverified");
  });
}

test("lost close response offers recorded status, never a second close or install", async ({ page }) => {
  const calls = await mount(page, { lost: true });
  await page.getByRole("button", { name: "Cancel upgrade" }).first().click();
  await dialog(page).getByRole("button", { name: "Yes" }).click();
  await expect(dialog(page).getByRole("alert")).toBeVisible();
  await dialog(page).getByRole("button", { name: "Read recorded status" }).click();
  await expect(page.getByText("Closed, outcome unverified", { exact: true })).toBeVisible();
  expect(calls.filter(x => x === "POST close-unverified")).toHaveLength(1);
  expect(calls).not.toContain("POST apply");
});

for (const width of [1440, 320]) {
  test(`recovery keyboard and layout at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await mount(page);
    await page.getByRole("button", { name: "Cancel upgrade" }).first().focus();
    await page.keyboard.press("Enter");
    await expect(dialog(page).getByRole("button", { name: "Yes" })).toBeEnabled();
    await expect(dialog(page).getByRole("textbox")).toHaveCount(0);
    expect(await dialog(page).evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`recovery-${width}.png`), fullPage: true });
    await page.keyboard.press("Escape");
    await expect(dialog(page)).toHaveCount(0);
  });
}
