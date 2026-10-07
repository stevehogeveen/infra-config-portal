import { test, expect, type Page, type Route } from "@playwright/test";

// Shapes follow backend/app/api/firmware_execution.py, services/firmware_flow.py,
// services/firmware_reconcile.py and guarded_operation_ledger.recorded_result.
const html = `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
await import('/tests/fixtures/firmwareBridgeHarness.tsx');</script></body></html>`;

const scope = { profile_id: "kit", device_id: "srv", resource: "firmware-execution" };
const PHRASE = "INSTALL ILO 1.48 ON srv; ILO WILL RESET; KEEP POWER CONNECTED";
const WARNINGS = [
  { group: "Power", health: "Warning", title: "One healthy powered supply observed. Keep its power feed connected throughout the update." },
  { group: "Storage", health: "Warning", title: "Erased physical drives report EraseCompleted.", details: "6 drives on the embedded controller." },
];
const notStarted = { ...scope, status: "not_started", operation_id: null, idempotency_key: null, stages: [], blockers: [], execution_available: false };
const recorded = (status: string, key: string, extra: Record<string, unknown> = {}) =>
  ({ ...scope, operation_id: "op-1", idempotency_key: key, status, record_found: true, safe_to_retry: false, evidence_at: null, stages: [], ...extra });
const preview = (blockers: string[] = [], warnings: typeof WARNINGS = []) => ({
  warnings,
  ...scope, review_token: `review-${Math.random().toString(36).slice(2)}`, expires_at: new Date(Date.now() + 5 * 60000).toISOString(),
  target: { device_id: "srv", name: "HPE DL360 3" }, target_provenance: "live-ilo-firmware-capabilities", evidence_at: new Date().toISOString(),
  component_hash: "59419c9b3f34d4cee7730f836ebcd61b6ad7c4843476551746781947a6437664", drive_identities: [], blockers, can_apply: blockers.length === 0,
  confirmation_phrase: blockers.length ? "" : PHRASE,
  operations: blockers.length ? [] : [{ order: 1, component: "iLO 5", current_version: "1.37", package_version: "1.48", file: "ilo5_148.bin", action: "POST /cgi-bin/uploadFile; automatic iLO reset; no host reboot" }],
  message: "Install only the authenticated 1.48 bridge. iLO will reset and temporarily disconnect. No host reboot or storage change is authorized.",
});

type Handler = (action: string, route: Route, body: any) => unknown;
async function mount(page: Page, handler: Handler) {
  const calls: Array<{ action: string; body: any }> = [];
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/v1/rack-plans/kit/firmware-execution/") || url.searchParams.get("device_id") !== "srv") {
      await route.fulfill({ status: 404, json: {} }); throw new Error(`Unexpected ${url.pathname}`);
    }
    const action = url.pathname.split("/").pop()!;
    const body = route.request().method() === "POST" ? route.request().postDataJSON() : null;
    calls.push({ action, body });
    const result = await handler(action, route, body);
    if (result === "abort") return route.abort("failed");
    if (result && typeof result === "object" && "__status" in (result as any)) return route.fulfill({ status: (result as any).__status, json: { detail: (result as any).detail } });
    return route.fulfill({ json: result });
  });
  await page.route("**/bridge-fixture", route => route.fulfill({ contentType: "text/html", body: html }));
  await page.goto("/bridge-fixture");
  return calls;
}
const count = (calls: Array<{ action: string }>, action: string) => calls.filter(call => call.action === action).length;

test("1a capabilities are read only after explicit confirmation and show versions with their time", async ({ page }) => {
  const checkedAt = new Date().toISOString();
  const calls = await mount(page, action => {
    if (action === "status") return notStarted;
    if (action === "capabilities") return { device_id: "srv", profile_id: "kit", checked_at: checkedAt, manager_firmware_version: "1.37 Feb 20 2019", system_health: "Warning", state: "Idle", errors: [],
      health_issues: [{ group: "Storage", health: "Warning" }], inventory: [{ resource_path: "/redfish/v1/UpdateService/FirmwareInventory/1", name: "iLO 5", version: "1.37 Feb 20 2019", updateable: true }], can_apply: false,
      message: "Read-only capabilities recorded; package prerequisites and approval remain separate." };
    throw new Error(`unexpected ${action}`);
  });
  const read = page.getByRole("button", { name: "Read firmware capabilities (read-only)" });
  await expect(read).toBeDisabled();
  await page.waitForTimeout(400);
  expect(count(calls, "capabilities")).toBe(0);
  await page.getByLabel(/I confirm a read-only check/).check();
  await read.click();
  const result = page.getByLabel("Firmware capabilities");
  await expect(result).toContainText("1.37 Feb 20 2019");
  await expect(result).toContainText("Storage: Warning");
  await result.getByText("Details from this read").click();
  await expect(result.getByRole("rowheader", { name: "iLO 5" })).toBeVisible();
  await expect(result.locator("[data-provenance=proven]")).toBeVisible();
  expect(calls.find(call => call.action === "capabilities")!.body).toEqual({ confirm_read_only: true });
});

test("1b bridge preparation is shown as prepared and authenticated, not install-ready", async ({ page }) => {
  const calls = await mount(page, action => {
    if (action === "status") return notStarted;
    if (action === "prepare-spp-bridge") return { profile_id: "kit", device_id: "srv", package_selection_id: 41, preparation_id: 77,
      bridge: { source_kind: "spp-prerequisite", path: "prerequisite/ilo5_148.fwpkg", sha256: "abc", size_bytes: 33556514, can_apply: false },
      authentication: { binary_authenticated: true, authentication_method: "hpe_signed_rpm_exact_binary_match", signing_key_id: "74c3a4a2",
        binary: { sha256: "59419c9b3f34d4cee7730f836ebcd61b6ad7c4843476551746781947a6437664", size_bytes: 33556514 }, fwpkg_signature_verified: false, applicability_verified: false, can_apply: false },
      can_apply: false, blockers: ["Fresh target applicability and prerequisites require review.", "No production installation adapter is enabled."] };
    throw new Error(`unexpected ${action}`);
  });
  await page.getByRole("button", { name: "Prepare the iLO 1.48 bridge from your SPP" }).click();
  const result = page.getByLabel("Bridge preparation", { exact: true });
  await expect(result).toContainText("Done: the 1.48 file in your package is genuine.");
  await expect(result).toContainText("install needs its own review");
  await result.getByText("Technical details").click();
  await expect(result).toContainText("77");
  await expect(result).toContainText("41");
  await expect(result).toContainText("verified (hpe_signed_rpm_exact_binary_match, key 74c3a4a2)");
  await expect(result).toContainText("yes · 33556514 bytes · 59419c9b");
  await expect(result).toContainText("No production installation adapter is enabled.");
  await expect(result.getByText("can apply")).toBeVisible();
  await expect(page.getByText(/install-ready/).filter({ hasNotText: "install needs its own review" })).toHaveCount(0);
  expect(calls.find(call => call.action === "prepare-spp-bridge")!.body).toEqual({});
});

test("1c review shows the server phrase with the iLO reset disclosure and persists token and key before one apply", async ({ page }) => {
  let issued = preview();
  let storedBeforeApply: any[] = [];
  const calls = await mount(page, async (action, _route, body) => {
    if (action === "status") return notStarted;
    if (action === "preview") { issued = preview(); return issued; }
    if (action === "apply") {
      storedBeforeApply = await page.evaluate(() => Object.keys(localStorage).filter(key => key.includes(":firmware-execution:srv")).map(key => JSON.parse(localStorage.getItem(key)!)));
      return recorded("running", body.idempotency_key);
    }
    if (action === "reconcile") return recorded("running", new URL(_route.request().url()).searchParams.get("idempotency_key")!);
    throw new Error(`unexpected ${action}`);
  });
  await page.getByRole("button", { name: "Review firmware install" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(PHRASE, { exact: true })).toBeVisible();
  await expect(dialog.getByText(/The iLO restarts by itself when it.s done/)).toBeVisible();
  await expect(dialog.getByText(/The server stays on; keep its power connected/)).toBeVisible();
  await dialog.getByText("Technical details").click();
  await expect(dialog.getByText("POST /cgi-bin/uploadFile; automatic iLO reset; no host reboot")).toBeVisible();
  await dialog.getByLabel("Confirmation phrase").fill(PHRASE);
  await dialog.getByRole("button", { name: "Install", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const apply = calls.filter(call => call.action === "apply");
  expect(apply).toHaveLength(1);
  expect(Object.keys(apply[0].body).sort()).toEqual(["confirmation_phrase", "idempotency_key", "review_token"]);
  expect(apply[0].body).toMatchObject({ review_token: issued.review_token, confirmation_phrase: PHRASE });
  expect(storedBeforeApply).toHaveLength(1);
  expect(storedBeforeApply[0]).toMatchObject({ reviewToken: issued.review_token, idempotencyKey: apply[0].body.idempotency_key, profileId: "kit", deviceId: "srv", resource: "firmware-execution" });
});

test("1d completion needs the explicit read-only verify; status is never polled", async ({ page }) => {
  let state: Record<string, unknown> = recorded("running", "key-1");
  const calls = await mount(page, (action, _route, body) => {
    if (action === "status") return state;
    if (action === "verify") { state = recorded("verified", "key-1", { evidence_at: new Date().toISOString(), stages: [{ name: "Verification", status: "verified" }] }); return state; }
    throw new Error(`unexpected ${action} ${JSON.stringify(body)}`);
  });
  const verify = page.getByRole("button", { name: "Verify iLO version (read-only)" });
  await expect(verify).toBeVisible();
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeDisabled();
  await page.waitForTimeout(1500);
  expect(count(calls, "status")).toBe(1);
  expect(count(calls, "verify")).toBe(0);
  await verify.click();
  await expect(page.getByRole("article", { name: "Operation status" })).toContainText("Verified");
  expect(calls.find(call => call.action === "verify")!.body).toEqual({ operation_id: "op-1", confirm_read_only: true });
});

test("1d a failed readback keeps the operation locked and says not to resend", async ({ page }) => {
  await mount(page, action => {
    if (action === "status") return recorded("uncertain", "key-1");
    if (action === "verify") return { __status: 409, detail: "Firmware readback is not proven. The operation remains blocked; do not resend." };
    throw new Error(`unexpected ${action}`);
  });
  await page.getByRole("button", { name: "Verify iLO version (read-only)" }).click();
  await expect(page.getByRole("alert")).toContainText("do not resend");
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeDisabled();
});

async function sendAndLose(page: Page, apply: (body: any) => unknown, extra: Handler = () => { throw new Error("unexpected"); }) {
  let issued = preview();
  const calls = await mount(page, (action, route, body) => {
    if (action === "status") return notStarted;
    if (action === "preview") { issued = preview(); return issued; }
    if (action === "apply") return apply(body);
    if (action === "reconcile") return { ...scope, requested_idempotency_key: new URL(route.request().url()).searchParams.get("idempotency_key"), idempotency_key: null, operation_id: null, status: "uncertain", record_found: false, safe_to_retry: false };
    return extra(action, route, body);
  });
  await page.getByRole("button", { name: "Review firmware install" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Confirmation phrase").fill(PHRASE);
  await dialog.getByRole("button", { name: "Install", exact: true }).click();
  await expect.poll(async () => (await dialog.count()) === 0 || await dialog.getByRole("alert").isVisible()).toBe(true);
  if (await dialog.count()) await dialog.getByRole("button", { name: "Cancel" }).click();
  return { calls, issued: () => issued };
}

test("1e a lost send is closed only when the server proves dispatch was prevented, then needs a new review", async ({ page }) => {
  let key = "";
  const { calls, issued } = await sendAndLose(page, body => { key = body.idempotency_key; return "abort"; }, (action, _route, body) => {
    if (action === "reconcile-unsent") return recorded("failed", body.idempotency_key, { operation_id: "op-fence", dispatch_prevented: true, next_action: "Create a fresh firmware review; this attempt cannot be sent." });
    throw new Error(`unexpected ${action}`);
  });
  const firstToken = issued().review_token;
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeDisabled();
  await page.getByRole("button", { name: "Close this attempt safely" }).click();
  const fence = calls.find(call => call.action === "reconcile-unsent")!;
  expect(fence.body).toEqual({ review_token: firstToken, idempotency_key: key, prevent_late_dispatch: true });
  await expect(page.getByRole("article", { name: "Operation status" })).toContainText("Closed before sending");
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeEnabled();
  await page.getByRole("button", { name: "Review firmware install" }).click();
  await expect(page.getByRole("dialog").getByLabel("Confirmation phrase")).toHaveValue("");
  expect(count(calls, "preview")).toBe(2);
  expect(count(calls, "apply")).toBe(1);
});

test("1e a fence that finds the send already running stays locked", async ({ page }) => {
  await sendAndLose(page, () => "abort", (action, _route, body) => {
    if (action === "reconcile-unsent") return recorded("running", body.idempotency_key);
    if (action === "status") return recorded("running", body?.idempotency_key ?? "k");
    throw new Error(`unexpected ${action}`);
  });
  await page.getByRole("button", { name: "Close this attempt safely" }).click();
  await expect(page.getByText(/could not be closed/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Verify iLO version (read-only)" })).toBeVisible();
});

test("1e accepted but not sent offers only the safe close; a fence without dispatch_prevented stays locked", async ({ page }) => {
  await sendAndLose(page, body => recorded("accepted", body.idempotency_key), (action, _route, body) => {
    if (action === "reconcile-unsent") return recorded("failed", body.idempotency_key);
    throw new Error(`unexpected ${action}`);
  });
  await expect(page.getByRole("article", { name: "Operation status" })).toContainText("Accepted, not verified");
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeDisabled();
  await expect(page.getByRole("button", { name: /retry|send again/i })).toHaveCount(0);
  await page.getByRole("button", { name: "Close this attempt safely" }).click();
  await expect(page.getByText("The attempt could not be proven closed. It stays locked.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeDisabled();
});

test("1e a legacy attempt without a server-issued review stays blocked", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lab-builder-guarded-attempt:kit:firmware-execution:srv",
    JSON.stringify({ idempotencyKey: "legacy-key", reviewToken: "", sentAt: "2026-09-28T10:00:00Z", state: "uncertain" })));
  const calls = await mount(page, (action, route) => {
    if (action === "status") return notStarted;
    if (action === "reconcile") return { ...scope, requested_idempotency_key: "legacy-key", idempotency_key: null, operation_id: null, status: "uncertain", record_found: false };
    throw new Error(`unexpected ${action} ${route.request().url()}`);
  });
  await expect(page.getByRole("button", { name: "Close this attempt safely" })).toBeDisabled();
  await expect(page.getByText(/has no server-issued review/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Review firmware install" })).toBeDisabled();
  expect(count(calls, "reconcile-unsent")).toBe(0);
});

test("1f backend gates are shown with the server's exact reasons and no bypass", async ({ page }) => {
  const gates = ["Hardware health must be OK for the components this update touches.", "Exclusive firmware maintenance scope is required; competing hardware writes must be disabled."];
  await mount(page, action => {
    if (action === "status") return { ...notStarted, blockers: gates };
    if (action === "preview") return preview(gates);
    throw new Error(`unexpected ${action}`);
  });
  for (const gate of gates) await expect(page.getByRole("note").filter({ hasText: "What the server says blocks this" })).toContainText(gate);
  await page.getByRole("button", { name: "Review firmware install" }).click();
  const dialog = page.getByRole("dialog");
  for (const gate of gates) await expect(dialog.getByText(gate)).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Install", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: /bypass|override|ignore/i })).toHaveCount(0);
});

test("delta 1+3: known warnings are listed without blocking apply, and power must stay connected", async ({ page }) => {
  let issued = preview([], WARNINGS);
  const calls = await mount(page, (action, route, body) => {
    if (action === "status") return notStarted;
    if (action === "preview") { issued = preview([], WARNINGS); return issued; }
    if (action === "apply") return recorded("running", body.idempotency_key);
    if (action === "reconcile") return recorded("running", new URL(route.request().url()).searchParams.get("idempotency_key")!);
    throw new Error(`unexpected ${action}`);
  });
  await page.getByRole("button", { name: "Review firmware install" }).click();
  const dialog = page.getByRole("dialog");
  const warnings = dialog.getByLabel("Known warnings");
  await expect(warnings).toContainText("known warnings (don't block this)");
  for (const item of WARNINGS) await expect(warnings).toContainText(item.title);
  await expect(warnings).toContainText("6 drives on the embedded controller.");
  await expect(dialog.getByText(/^Blocked$/)).toHaveCount(0);
  await expect(dialog.getByText(PHRASE, { exact: true })).toBeVisible();
  await expect(dialog.getByText(/The server stays on; keep its power connected/)).toBeVisible();
  await expect(dialog.getByText(/health (is )?cleared|all clear|hardware is healthy|warnings cleared/i)).toHaveCount(0);
  await dialog.getByLabel("Confirmation phrase").fill(PHRASE);
  const apply = dialog.getByRole("button", { name: "Install", exact: true });
  await expect(apply).toBeEnabled();
  await apply.click();
  expect(count(calls, "apply")).toBe(1);
});

test("delta 1: warnings stay separate from real blockers", async ({ page }) => {
  await mount(page, action => {
    if (action === "status") return notStarted;
    if (action === "preview") return preview(["An energized power supply reports a fault or unknown state."], WARNINGS);
    throw new Error(`unexpected ${action}`);
  });
  await page.getByRole("button", { name: "Review firmware install" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Known warnings")).toContainText(WARNINGS[1].title);
  await expect(dialog.getByLabel("Known warnings")).not.toContainText("energized power supply");
  await expect(dialog.getByText("An energized power supply reports a fault or unknown state.")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Install", exact: true })).toBeDisabled();
});

test("delta 2: capabilities show iLO update health; older results ask for an explicit fresh read", async ({ page }) => {
  let withHealth = false;
  const calls = await mount(page, action => {
    if (action === "status") return notStarted;
    if (action === "capabilities") {
      const base = { device_id: "srv", profile_id: "kit", checked_at: new Date().toISOString(), manager_firmware_version: "1.37", inventory: [], errors: [], health_issues: [] };
      return withHealth ? { ...base, ilo_update_health: { scope: "ilo-only-v1", warnings: WARNINGS, blockers: [], assessment_sha256: "0123456789abcdef0123" } } : base;
    }
    throw new Error(`unexpected ${action}`);
  });
  await page.getByLabel(/I confirm a read-only check/).check();
  await page.getByRole("button", { name: "Read firmware capabilities (read-only)" }).click();
  await expect(page.getByText("Read capabilities again to assess iLO update health")).toBeVisible();
  await page.waitForTimeout(500);
  expect(count(calls, "capabilities")).toBe(1);
  withHealth = true;
  await page.getByRole("button", { name: "Read capabilities again (read-only)" }).click();
  const health = page.getByLabel("iLO update health");
  await expect(health).toContainText("Nothing in this read blocks the iLO update.");
  await expect(health).toContainText("other warnings (don't block this update)");
  await expect(health).toContainText(WARNINGS[1].title);
  expect(count(calls, "capabilities")).toBe(2);
});

test("delta 2: iLO update health blockers are shown as blockers", async ({ page }) => {
  await mount(page, action => {
    if (action === "status") return notStarted;
    if (action === "capabilities") return { device_id: "srv", checked_at: new Date().toISOString(), manager_firmware_version: "1.37",
      ilo_update_health: { scope: "ilo-only-v1", warnings: [], blockers: ["Fresh cooling and temperature inventory is required."], assessment_sha256: "ffff0000ffff0000" } };
    throw new Error(`unexpected ${action}`);
  });
  await page.getByLabel(/I confirm a read-only check/).check();
  await page.getByRole("button", { name: "Read firmware capabilities (read-only)" }).click();
  await expect(page.getByLabel("iLO update health")).toContainText("Blocks the iLO update");
  await expect(page.getByLabel("iLO update health")).toContainText("Fresh cooling and temperature inventory is required.");
});

test("the read-only confirm checkbox is normal size with its label inline, at desktop and phone widths", async ({ page }) => {
  await mount(page, action => { if (action === "status") return notStarted; throw new Error(`unexpected ${action}`); });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const box = await page.getByLabel(/I confirm a read-only check/).boundingBox();
    expect(box!.width).toBeLessThanOrEqual(20);
    expect(box!.height).toBeLessThanOrEqual(20);
    const fits = await page.evaluate(() => {
      const label = document.querySelector(".sd-bridge .workflow-checkbox")!.getBoundingClientRect();
      const card = document.querySelector(".sd-bridge")!.getBoundingClientRect();
      const text = document.querySelector(".sd-bridge .workflow-checkbox")!;
      return { ok: label.right <= card.right + 0.5 && label.width >= card.width - 60 && label.height < 90, label: label.width, right: label.right, cardRight: card.right, h: label.height };
    });
    expect(fits, JSON.stringify(fits)).toMatchObject({ ok: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});
