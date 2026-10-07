import { test, expect, type Page } from "@playwright/test";

// Part by part through the iLO: Check (review, nothing sent) -> one tick, one button -> steps -> Complete.
const html = `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/sppUpdateHarness.tsx');</script></body></html>`;

const part = (id: string, component: string, from: string, to: string, method: "ilo" | "bios", rom = false) =>
  ({ id, component, item: component, from, to, file: `${id}.fwpkg`, method, reset: true, minutes: 5, rom });
const PARTS = [part("rom", "System ROM", "U32 v1.46", "v3.66", "ilo", true), part("sr", "HPE Smart Array P408i-a SR Gen10 (Embedded RAID)", "5.61", "8.00", "ilo"),
  part("ie", "Innovation Engine (IE) Firmware", "0.1.6.1", "0.2.3.0", "bios")];
const LABELS = ["The iLO installs System ROM", "Waiting for the iLO to finish System ROM", "Restart the server", "Waiting for the server to finish starting", "Read the new versions back",
  "Queue Innovation Engine (IE) Firmware for the next start", "Restart the server", "Waiting for the server to finish starting", "Read the new versions back"];
const plan = { review_id: "abcdef0123456789", digest: "d", package: "spp.iso", parts: PARTS, phases: [], restarts: 2, minutes: 35, power: "On", blockers: [],
  expires_at: new Date(Date.now() + 1e6).toISOString(),
  elsewhere: [{ component: "1.2TB 12G SAS HDD", from: "HPD4", to: "HPD9", reason: "Needs HPE's SPP boot disc or the operating system." }] };

function runStatus(done: number, extra: Record<string, unknown> = {}) {
  const finished = done >= LABELS.length;
  return { state: finished ? "verified" : "running", active: !finished, run_id: "run-1",
    message: finished ? "Every listed part was read back at its new version." : LABELS[done] + "…",
    parts: PARTS.map(p => ({ ...p, state: finished ? "done" : "waiting" })),
    phases: LABELS.map((label, index) => ({ index, kind: label.startsWith("Read") ? "check" : "x", label, state: index < done ? "ok" : "todo", message: index < done ? "ok" : null })),
    ...extra };
}

const DRIVE = { step_id: "verify-0", component: "Drive: EG000300JWEBF / 1I:1:1", from: "HPD4", to: "HPD8", order: 1, restarts: "host", est_minutes: null };
const discPlan = { execution_mode: "offline", plan_id: "p", profile_id: "kit", device_id: "srv", review_token: "spp-token", expires_at: new Date(Date.now() + 1e6).toISOString(), can_apply: true,
  confirmation_phrase: "UPDATE srv", server: { name: "Fixture server", model: "ProLiant DL360 Gen10", manager_generation: 5 }, package: { file: "spp.iso", release: "2026.05" },
  updates: [DRIVE], effects: { host_restarts: 1, ilo_restarts: 0, est_total_minutes: 30, power_on_required: false }, not_included: [], blockers: [], warnings: [] };
const discStatus = (state: "running" | "verified") => ({ execution_mode: "offline", profile_id: "kit", device_id: "srv", operation_id: "op-spp", idempotency_key: "k", status: state,
  steps: [{ ...DRIVE, state: state === "verified" ? "done" : "waiting", started_at: state === "verified" ? new Date().toISOString() : null,
    finished_at: state === "verified" ? new Date().toISOString() : null, verified_version: state === "verified" ? "HPD8" : null }],
  current_step: state === "verified" ? null : "verify-0", message: state === "verified" ? "Verified." : "HPE's updater is running.", next_action: null, evidence_at: null, active: state !== "verified" });

async function mount(page: Page, opts: { failAt?: number; disc?: boolean; noParts?: boolean } = {}) {
  const calls: string[] = [];
  let done = -1;
  let discReads = -1;
  let scope = "read_only";
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url()), method = route.request().method(), path = url.pathname;
    if (method !== "GET") calls.push(`${method} ${path.replace(/^.*\/(parts-update|runtime)\//, "$1/")}`);
    if (path.endsWith("/access-settings")) return route.fulfill({ json: { host: "192.0.2.10", username_configured: true, password_configured: true } });
    if (path.endsWith("/firmware-assessment")) return route.fulfill({ json: { detected_model: "ProLiant DL360 Gen10", checked_at: "2026-10-06T10:00:00Z",
      rows: [{ component: "System ROM / BIOS", installed: "U32 v1.46", target: "3.66", status: "Update available" }] } });
    if (method !== "GET" && path.includes("/firmware-update/")) calls.push(`${method} spp/${path.split("/").pop()}`);
    if (path.endsWith("/firmware-update/plan")) return opts.disc ? route.fulfill({ json: discPlan })
      : route.fulfill({ status: 409, json: { detail: "No independently verifiable newer firmware was identified in this package." } });
    if (path.endsWith("/firmware-update/apply")) { discReads = 0; return route.fulfill({ json: discStatus("running") }); }
    if (path.includes("/firmware-update/")) {
      if (discReads >= 0) { discReads += 1; return route.fulfill({ json: discStatus(discReads >= 2 ? "verified" : "running") }); }
      return route.fulfill({ json: { profile_id: "kit", device_id: "srv", operation_id: null, idempotency_key: null, status: "not_started",
        steps: [], current_step: null, message: "", next_action: null, evidence_at: null, active: false } });
    }
    if (path.endsWith("/parts-update/status")) return route.fulfill({ json: done < 0 ? { state: "not_started", active: false, phases: [], parts: [], message: "" } : runStatus(done) });
    if (path.endsWith("/parts-update/review")) return route.fulfill({ json: opts.noParts ? { ...plan, parts: [], restarts: 0, minutes: 0, elsewhere: [] } : plan });
    if (path.endsWith("/parts-update/start")) { done = 1; return route.fulfill({ json: runStatus(done) }); }
    if (path.endsWith("/parts-update/advance")) {
      if (opts.failAt !== undefined && done >= opts.failAt)
        return route.fulfill({ json: runStatus(done, { state: "needs_attention", message: "Not at the new version: System ROM (now U32 v1.46, wanted v3.66). Nothing further was sent." }) });
      done += 1;
      return route.fulfill({ json: runStatus(done) });
    }
    if (path.endsWith("/parts-update/close")) { done = -1; return route.fulfill({ json: { state: "failed", active: false, phases: [], parts: [], message: "Closed." } }); }
    if (path.endsWith("/runtime/write-scope/preview")) {
      const target = route.request().postDataJSON().target_scope;
      return route.fulfill({ json: { review_token: "t", current_scope: scope, target_scope: target, confirmation_phrase: "", blockers: [], expires_at: new Date(Date.now() + 6e5).toISOString() } });
    }
    if (path.endsWith("/runtime/write-scope/apply")) { scope = scope === "read_only" ? "firmware_only" : "read_only"; return route.fulfill({ json: { scope, active_operations: [], blockers: [] } }); }
    if (path.endsWith("/runtime/write-scope")) return route.fulfill({ json: { scope, active_operations: [], blockers: [] } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.route("**/parts-fixture", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto("/parts-fixture");
  return { calls, scope: () => scope };
}
const box = (page: Page) => page.getByRole("dialog", { name: "Update firmware part by part on Fixture server" });

test("review lists the parts in order with who installs them; nothing is sent until the one button", async ({ page }) => {
  const { calls } = await mount(page);
  await page.getByRole("button", { name: "Update firmware" }).click();
  const parts = box(page).getByRole("list", { name: "Parts to update, in order" });
  await expect(parts.getByRole("listitem")).toHaveCount(3);
  await expect(parts.getByRole("listitem").first()).toContainText("System ROM");
  await expect(parts.getByRole("listitem").first()).toContainText("The iLO installs it · first, then read back");
  await expect(parts.getByRole("listitem").nth(2)).toContainText("The BIOS installs it at the next start");
  await expect(box(page)).toContainText("The server restarts 2 times");
  await expect(box(page).getByText("Not installed through the iLO (1)")).toBeVisible();
  await expect(box(page).getByRole("button", { name: "Update firmware" })).toBeDisabled();
  expect(calls).toEqual(["POST parts-update/review"]);
});

test("one tick and one button run every step to Complete, then Done returns to read-only", async ({ page }) => {
  test.setTimeout(150000);
  const env = await mount(page);
  await page.getByRole("button", { name: "Update firmware" }).click();
  await box(page).getByRole("checkbox").check();
  await box(page).getByRole("button", { name: "Update firmware" }).click();
  await expect(box(page).getByRole("heading", { name: "Updating firmware…" })).toBeVisible();
  expect(env.scope()).toBe("firmware_only");
  await expect(box(page).getByRole("heading", { name: "Complete", exact: true })).toBeVisible({ timeout: 120000 });
  await expect(box(page)).toContainText("System ROM: v3.66");
  await box(page).getByRole("button", { name: "Done" }).click();
  await expect(box(page)).toHaveCount(0);
  expect(env.scope()).toBe("read_only");
  expect(env.calls.filter(c => c === "POST parts-update/start")).toHaveLength(1);
});

test("a stopped step says why and can be closed; nothing is retried", async ({ page }) => {
  test.setTimeout(60000);
  const env = await mount(page, { failAt: 2 });
  await page.getByRole("button", { name: "Update firmware" }).click();
  await box(page).getByRole("checkbox").check();
  await box(page).getByRole("button", { name: "Update firmware" }).click();
  await expect(box(page).getByRole("heading", { name: "The update needs attention" })).toBeVisible({ timeout: 40000 });
  await expect(box(page).getByRole("alert")).toContainText("System ROM (now U32 v1.46, wanted v3.66)");
  await box(page).getByRole("button", { name: "Close this run" }).click();
  await expect(box(page).getByRole("heading", { name: "Ready to update" })).toBeVisible();
  expect(env.calls).toContain("POST parts-update/close");
  expect(env.scope()).toBe("read_only");
});

test("one button: after the iLO stage, anything only the boot disc can install runs in the same window", async ({ page }) => {
  test.setTimeout(180000);
  const env = await mount(page, { disc: true });
  await page.getByRole("button", { name: "Update firmware" }).click();
  await box(page).getByRole("checkbox").check();
  await box(page).getByRole("button", { name: "Update firmware" }).click();
  await expect(box(page).getByRole("heading", { name: "HPE's boot disc is updating the rest…" })).toBeVisible({ timeout: 120000 });
  await expect(box(page).getByRole("list", { name: "Boot-disc steps" })).toContainText("EG000300JWEBF");
  expect(env.calls.filter(c => c === "POST spp/apply")).toHaveLength(1);
  await expect(box(page).getByRole("heading", { name: "Complete", exact: true })).toBeVisible({ timeout: 45000 });
  await expect(box(page)).toContainText("Drive: EG000300JWEBF / 1I:1:1: HPD8");
});

test("one button: when nothing is left for the boot disc, it finishes without it", async ({ page }) => {
  test.setTimeout(150000);
  const env = await mount(page);
  await page.getByRole("button", { name: "Update firmware" }).click();
  await box(page).getByRole("checkbox").check();
  await box(page).getByRole("button", { name: "Update firmware" }).click();
  await expect(box(page).getByRole("heading", { name: "Complete", exact: true })).toBeVisible({ timeout: 120000 });
  await expect(box(page)).toContainText("Nothing needed HPE's boot disc.");
  expect(env.calls).toContain("POST spp/plan");
  expect(env.calls).not.toContain("POST spp/apply");
});

test("only boot-disc parts: the review lists them and the one button starts the boot disc", async ({ page }) => {
  const env = await mount(page, { disc: true, noParts: true });
  await page.getByRole("button", { name: "Update firmware" }).click();
  await expect(box(page).getByRole("list", { name: "Parts HPE's boot disc updates" })).toContainText("HPD4");
  await expect(box(page)).toContainText("The server restarts into HPE's boot disc");
  await box(page).getByRole("checkbox").check();
  await box(page).getByRole("button", { name: "Update firmware" }).click();
  await expect(box(page).getByRole("heading", { name: "HPE's boot disc is updating the rest…" })).toBeVisible();
  expect(env.calls).not.toContain("POST parts-update/start");
  expect(env.scope()).toBe("firmware_only");
});
