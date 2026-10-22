import { expect, test, type Page } from "@playwright/test";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

// Serve only a bundled test fixture through browser interception. No app server.
const fixture = build({
  entryPoints: [fileURLToPath(new URL("./fixtures/kitContractHarness.tsx", import.meta.url))],
  bundle: true, write: false, outfile: "kit-contract-fixture.js", format: "esm", jsx: "automatic",
  loader: { ".png": "dataurl", ".svg": "dataurl" },
  define: { "import.meta.env": "{}", "process.env.NODE_ENV": '"development"' }
});

async function open(page: Page) {
  const { outputFiles = [] } = await fixture;
  await page.route("**/kit-contract-fixture.*", route => {
    const css = new URL(route.request().url()).pathname.endsWith(".css");
    return route.fulfill({ contentType: css ? "text/css" : "text/javascript", body: outputFiles.find(file => file.path.endsWith(css ? ".css" : ".js"))!.text });
  });
  await page.route("**/kit-contract-fixture", route => route.fulfill({ contentType: "text/html", body: `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/kit-contract-fixture.css"></head><body><div id="root"></div><script type="module" src="/kit-contract-fixture.js"></script></body></html>` }));
  await page.goto("/kit-contract-fixture");
}

async function mock(page: Page, blocked = false) {
  const state = { approvals: 0, ticks: 0, certificates: 0, unexpected: [] as string[] };
  const digest = "a".repeat(64);
  const item = { id: "windows:fixture", title: "Fixture server — Windows", step: "windows", device_id: "fixture", href: "/setup/install-windows", desired: { vm_name: "fixture-vm", image: "fixture.ova", datastore: "fixture-data" } };
  await page.route("**/api/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method();
    const base = "/api/v1/rack-plans/fixture/contract";
    if (path === base && method === "GET") return route.fulfill({ json: { profile_id: "fixture", kit: "Fixture kit", digest, network: { gateway: "192.0.2.1", dns: ["192.0.2.53"] }, items: [item] } });
    if (path === base + "/approve" && method === "POST") {
      expect(request.postDataJSON()).toEqual({ digest }); state.approvals++;
      return route.fulfill({ json: { state: "converging", digest } });
    }
    if (path === base + "/reconcile" && method === "POST") {
      expect(state.approvals).toBeGreaterThan(0); state.ticks++;
      return route.fulfill({ json: { state: blocked ? "blocked" : state.ticks > 1 ? "converged" : "converging", item: item.id,
        message: blocked ? "Save the Windows administrator sign-in before testing." : state.ticks > 1 ? "Every item verified." : "Importing Windows once.",
        href: blocked ? item.href : undefined, items: [{ ...item, state: state.ticks > 1 ? "verified" : "running", observed: { vm_name: "fixture-vm" } }] } });
    }
    if (path === base + "/certificate" && method === "GET") {
      state.certificates++;
      return route.fulfill({ json: { digest, state: "converged", generated_at: "2026-10-16T00:00:00Z", items: [{ ...item, verified: { vm_name: "fixture-vm" }, verified_at: "2026-10-16T00:00:00Z" }] } });
    }
    if (path === "/api/v1/rack-plans/fixture/handover" && method === "GET") return route.fulfill({ json: { kit: "Fixture kit", generated_at: "2026-10-16T00:00:00Z", network: { dns: [] }, servers: [], switches: [], cables: null, verified: [] } });
    state.unexpected.push(`${method} ${path}`);
    return route.fulfill({ status: 404, json: { detail: "Unexpected " + path } });
  });
  return state;
}

test("approve then converge on ten-second polls and show certificate and handover", async ({ page }) => {
  const state = await mock(page);
  await page.clock.install();
  await open(page);
  await expect(page.getByRole("heading", { name: "Kit contract", exact: true })).toBeVisible();
  await expect(page.getByText("fixture-vm", { exact: true })).toBeVisible();
  expect(state.ticks).toBe(0);
  await page.getByRole("button", { name: "Approve contract", exact: true }).click();
  await page.clock.runFor(100);
  await expect(page.getByText("Importing Windows once.")).toBeVisible();
  expect(state.approvals).toBe(1);
  expect(state.ticks).toBe(1);
  await page.clock.runFor(10000);
  await expect(page.getByRole("heading", { name: "As-built certificate" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hand-over pack" })).toBeVisible();
  await page.clock.runFor(30000);
  expect(state.ticks).toBe(2); expect(state.certificates).toBe(1);
  expect(state.unexpected).toEqual([]);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  }
});

test("compact firmware and ESXi desired values render without repeated detail", async ({ page }) => {
  await page.route("**/api/**", route => route.fulfill({ json: {
    profile_id: "fixture", kit: "Fixture kit", digest: "b".repeat(64), network: {}, items: [
      { id: "firmware:fixture", title: "Firmware", href: "/setup/check-firmware", desired: { file_name: "spp.iso", release_hint: "Fixture release", size_bytes: 42 } },
      { id: "esxi:fixture", title: "ESXi", href: "/setup/prepare-esxi", desired: { hostname: "fixture.example", media: "esxi.iso", network_summary: "192.0.2.0/24 via 192.0.2.1" } }
    ]
  } }));
  await open(page);
  await expect(page.getByText("spp.iso", { exact: true })).toBeVisible();
  await expect(page.getByText("esxi.iso", { exact: true })).toBeVisible();
  await expect(page.getByText("192.0.2.0/24 via 192.0.2.1", { exact: true })).toBeVisible();
  await expect(page.getByText("manifest files", { exact: true })).toHaveCount(0);
  await expect(page.getByText("volumes", { exact: true })).toHaveCount(0);
});

test("a blocker shows its message and fix link and stops polling", async ({ page }) => {
  const state = await mock(page, true);
  await page.clock.install();
  await open(page);
  await page.getByRole("button", { name: "Approve contract", exact: true }).click();
  await page.clock.runFor(100);
  await expect(page.getByRole("alert")).toContainText("Save the Windows administrator sign-in before testing.");
  await expect(page.getByRole("link", { name: "Open settings to resolve this" })).toHaveAttribute("href", "/setup/install-windows");
  await page.clock.runFor(60000);
  expect(state.ticks).toBe(1); expect(state.certificates).toBe(0);
  expect(state.unexpected).toEqual([]);
});

test("reload never approves or resumes automatically", async ({ page }) => {
  const state = await mock(page);
  await page.clock.install();
  await open(page);
  await page.getByRole("button", { name: "Approve contract", exact: true }).click();
  await page.clock.runFor(100);
  await expect(page.getByText("Importing Windows once.")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Approve contract", exact: true })).toBeVisible();
  await page.clock.runFor(30000);
  expect(state.approvals).toBe(1); expect(state.ticks).toBe(1);
  expect(state.unexpected).toEqual([]);
});
