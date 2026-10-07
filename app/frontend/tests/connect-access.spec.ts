import { expect, test } from "@playwright/test";

test("saved credentials check directly; edits preserve password; firmware and failures are visible", async ({ page }) => {
  const calls: string[] = [];
  let blocked = false;
  let access = { device_id: "fixture", host: "192.0.2.10", username: "fixture-user", username_configured: true, password_configured: true, verify_tls: true };
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    expect(url.searchParams.get("device_id")).toBe("fixture");
    calls.push(request.method());
    if (url.pathname.endsWith("access-settings")) {
      if (request.method() === "PUT") {
        const body = request.postDataJSON();
        expect(body).not.toHaveProperty("password");
        access = { ...access, ...body };
      }
      return route.fulfill({ json: access });
    }
    expect(url.pathname).toBe("/api/v1/providers/ilo-redfish/probe");
    return route.fulfill({ json: { status: blocked ? "blocked" : "ok", message: blocked ? "Sign-in refused" : "Fixture read completed", checked_at: new Date().toISOString(), warnings: [], blockers: [], firmware: blocked ? [] : [{ Name: "Fixture BIOS", Version: "test-version" }] } });
  });
  await page.route("**/connect-fixture", route => route.fulfill({ contentType: "text/html", body: `<html><body><div id="root"></div><script type="module">
    import RefreshRuntime from '/@react-refresh'; RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$=()=>{}; window.$RefreshSig$=()=>(type)=>type; window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/connectAccessHarness.tsx');
    </script></body></html>` }));
  await page.goto("/connect-fixture");
  await expect(page.getByText("Password saved securely")).toBeVisible();
  expect(calls).toEqual(["GET"]);
  await expect(page.getByLabel("iLO password", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Check connection", exact: true }).click();
  await expect(page.getByText("test-version")).toBeVisible();
  expect(calls).toEqual(["GET", "POST"]);
  await page.getByLabel("Current iLO address").fill("192.0.2.11");
  await expect(page.getByText("test-version")).toHaveCount(0);
  blocked = true;
  await page.getByRole("button", { name: "Save and check connection" }).click();
  await expect(page.getByText("Sign-in refused")).toBeVisible();
  expect(calls).toEqual(["GET", "POST", "PUT", "POST"]);
  await expect(page.getByText("No firmware versions returned.")).toBeVisible();
});
