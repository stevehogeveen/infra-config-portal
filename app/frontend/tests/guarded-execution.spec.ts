import { test, expect, type Page } from "@playwright/test";

const html = `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/guardedExecutionHarness.tsx');</script></body></html>`;

type Kind = "firmware" | "drives";
const resource = { firmware: "firmware-execution", drives: "drive-return-to-service" };
const openName = { firmware: "Review firmware install", drives: "Return erased disks to service" };
const applyName = { firmware: "Install", drives: "Confirm and re-enable disks" };
const unavailable = {
  firmware: "Not available yet: the app cannot install firmware on this server yet.",
  drives: "Not available yet: the app cannot re-enable erased disks on this server yet.",
};

function preview(kind: Kind, blockers: string[] = [], can_apply = true) {
  return {
    review_token: "token-1", expires_at: new Date(Date.now() + 10 * 60000).toISOString(),
    target: { device_id: "fixture-server", name: "Server Alpha", host: "192.0.2.10", model: "ProLiant DL360 Gen10", serial: "FIXTURE01", controller: "Smart Array P408i-a SR Gen10" },
    component_hash: kind === "firmware" ? "sha256:fixture" : null,
    operations: kind === "firmware"
      ? [{ order: 1, component: "iLO 5", current_version: "1.37", package_version: "3.19" }, { order: 2, component: "System ROM", current_version: "U32 v1.46", package_version: "U32 v3.40" },
         { order: 3, component: "Smart Array P408i-a", current_version: "1.66", package_version: "7.43" }, { order: 4, component: "Drive EG000300JWEBF", current_version: "HPD2", package_version: "HPD4" }]
      : [{ order: 1, location: "1I:1:1", model: "EG000300JWEBF", current_status: "Warning", status_reasons: ["EraseCompleted"] }, { order: 2, location: "1I:1:2", model: "EG000300JWEBF", current_status: "Warning", status_reasons: ["EraseCompleted"] }],
    blockers, can_apply, confirmation_phrase: kind === "firmware" ? "INSTALL FIRMWARE ON SERVER ALPHA" : "ENABLE 2 ERASED DISKS",
  };
}

type Result = Record<string, unknown> | "abort" | { __status: number };
async function mount(page: Page, kind: Kind, handlers: { status?: () => Result; preview?: () => Result; apply?: () => Result }) {
  const calls: string[] = [];
  const applied: Record<string, unknown>[] = [];
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    calls.push(`${request.method()} ${url.pathname}`);
    if (!url.pathname.includes(`/${resource[kind]}/`) || url.searchParams.get("device_id") !== "fixture-server") {
      await route.fulfill({ status: 404, json: {} });
      throw new Error(`Unexpected ${url.pathname}`);
    }
    const action = url.pathname.split("/").pop();
    if (action === "apply") applied.push(request.postDataJSON());
    const make = action === "status" ? handlers.status : action === "preview" ? handlers.preview : handlers.apply;
    const result = make ? make() : { __status: 404 };
    if (result === "abort") return route.abort("failed");
    if ("__status" in result) return route.fulfill({ status: result.__status as number, json: { detail: "Fixture" } });
    return route.fulfill({ json: result });
  });
  await page.route("**/guarded-fixture*", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto(`/guarded-fixture?kind=${kind}`);
  return { calls, applied };
}

for (const kind of ["firmware", "drives"] as Kind[]) {
  test(`${kind}: missing endpoint is shown disabled as not available yet`, async ({ page }) => {
    await mount(page, kind, { status: () => ({ __status: 404 }) });
    await expect(page.getByText(unavailable[kind], { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: openName[kind] })).toBeDisabled();
  });

  test(`${kind}: 501 and unreachable are also not available yet, never hidden`, async ({ page }) => {
    let first = true;
    await mount(page, kind, { status: () => { const result: Result = first ? { __status: 501 } : "abort"; first = false; return result; } });
    await expect(page.getByText(unavailable[kind], { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByText(unavailable[kind], { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: openName[kind] })).toBeDisabled();
  });

  test(`${kind}: blockers are listed and apply stays disabled`, async ({ page }) => {
    const { applied } = await mount(page, kind, { status: () => ({ status: "not_started" }), preview: () => preview(kind, ["Package prerequisites for iLO 5 are missing from the manifest."], false) });
    await page.getByRole("region", { name: "Your guide" }).getByRole("button", { name: openName[kind] }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("Package prerequisites for iLO 5 are missing from the manifest.")).toBeVisible();
    await expect(dialog.getByRole("button", { name: applyName[kind] })).toBeDisabled();
    // Blocked reviews show no phrase box at all.
    await expect(dialog.getByLabel("Confirmation phrase")).toHaveCount(0);
    expect(applied).toHaveLength(0);
  });

  test(`${kind}: preview, typed confirmation, one apply, then recorded status`, async ({ page }) => {
    let stage = "not_started";
    const { applied, calls } = await mount(page, kind, {
      status: () => ({ status: stage, evidence_at: new Date().toISOString(), stages: stage === "not_started" ? [] : [{ name: "Request accepted", status: "done" }], next_action: stage === "accepted" ? "Wait for the verification read." : null }),
      preview: () => preview(kind),
      apply: () => { stage = "accepted"; return { status: "accepted", operation_id: "op-1", evidence_at: new Date().toISOString(), next_action: "Wait for the verification read." }; },
    });
    await page.getByRole("region", { name: "Your guide" }).getByRole("button", { name: openName[kind] }).click();
    const dialog = page.getByRole("dialog");
    if (kind === "firmware") for (const component of ["iLO 5", "System ROM", "Smart Array P408i-a", "Drive EG000300JWEBF"]) await expect(dialog.getByRole("listitem").filter({ hasText: component }).first()).toBeVisible();
    // Identity and per-disk status sit under Technical details.
    await dialog.getByText("Technical details").click();
    if (kind !== "firmware") await expect(dialog.getByText("EraseCompleted").first()).toBeVisible();
    await expect(dialog.getByText("FIXTURE01")).toBeVisible();
    const apply = dialog.getByRole("button", { name: applyName[kind] });
    await expect(apply).toBeDisabled();
    const phrase = preview(kind).confirmation_phrase;
    await dialog.getByLabel("Confirmation phrase").fill(phrase.toLowerCase());
    await expect(apply).toBeDisabled();
    await dialog.getByLabel("Confirmation phrase").fill(phrase);
    await apply.click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("article", { name: "Operation status" })).toContainText("Accepted, not verified");
    expect(applied).toHaveLength(1);
    expect(Object.keys(applied[0]).sort()).toEqual(["confirmation_phrase", "idempotency_key", "review_token"]);
    expect(applied[0]).toMatchObject({ review_token: "token-1", confirmation_phrase: phrase });
    expect(calls.filter(call => call.endsWith("/apply"))).toHaveLength(1);
    // In progress: no second review is offered.
    await expect(page.getByRole("button", { name: openName[kind] })).toBeDisabled();
  });

  test(`${kind}: uncertain outcome offers no retry`, async ({ page }) => {
    const { calls } = await mount(page, kind, { status: () => ({ status: "uncertain", operation_id: "op-2", evidence_at: new Date().toISOString(), next_action: "Read the recorded status before deciding." }) });
    await expect(page.getByRole("article", { name: "Operation status" })).toContainText("Outcome unknown");
    await expect(page.getByText("Do not retry automatically. No retry is offered here.")).toBeVisible();
    await expect(page.getByRole("button", { name: openName[kind] })).toBeDisabled();
    await expect(page.getByRole("button", { name: /retry/i })).toHaveCount(0);
    await page.waitForTimeout(500);
    expect(calls.filter(call => !call.endsWith("/status"))).toHaveLength(0);
  });

  test(`${kind}: verified is a recorded result`, async ({ page }) => {
    await mount(page, kind, { status: () => ({ status: "verified", operation_id: "op-3", evidence_at: new Date().toISOString(), stages: [{ name: "Result verified", status: "done" }] }) });
    const card = page.getByRole("article", { name: "Operation status" });
    await expect(card).toContainText("Verified");
    await expect(card).toContainText("Recorded result, not a live check.");
  });
}
