import { expect, test } from "@playwright/test";

test("running firmware page labels saved evidence and has honest button cursors", async ({page}) => {
  test.skip(!process.env.WORKBENCH_URL, "Optional read-only running-app check");
  test.setTimeout(120000);
  await page.route("**/api/**", route => ["GET","HEAD"].includes(route.request().method()) ? route.continue() : route.abort());
  await page.goto(process.env.WORKBENCH_URL + "/setup/check-firmware");
  await expect(page.getByText("Connection not checked on this visit",{exact:true}).first()).toBeVisible({timeout:60000});
  for (const width of [1440,390]) {
    await page.setViewportSize({width,height:950});
    for (const button of await page.locator("button:visible:enabled").all()) {
      await button.hover();
      await expect(button).not.toHaveCSS("cursor", "not-allowed");
    }
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:`test-results/firmware-saved-live-${width}.png`,fullPage:true});
  }
});

test("firmware reads only the selected server on click and does not imply compliance", async ({ page }) => {
  let reads = 0;
  let configured = true;
  await page.route("**/api/**", route => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get("device_id")).toBe("fixture-server");
    if (url.pathname.endsWith("access-settings")) return route.fulfill({json:{host:"192.0.2.10", username_configured:true, password_configured:configured}});
    if (url.pathname.endsWith("firmware-assessment")) return route.fulfill({json: reads ? {
      status:"Updates available", reason:"Matched firmware", checked_at:"2026-09-14T12:00:00Z", detected_model:"ProLiant DL360 Gen10", planned_model:"HPE DL360 Gen11", identity_mismatch:true,
      rows:[{component:"iLO",installed:"1.37",target:"3.19",status:"Update available",reason:"Prerequisites require approval",files:["ilo5_319.fwpkg"]}],
      limitations:"Not upgrade approval"
    } : {status:"Cannot determine",reason:"Run a connection check",rows:[]}});
    expect(url.pathname).toBe("/api/v1/providers/ilo-redfish/probe");
    expect(route.request().method()).toBe("POST");
    reads++;
    return route.fulfill({json:{status:"ok", message:"Fixture inventory read", checked_at:"2026-09-14T12:00:00Z", blockers:[], warnings:[], firmware:[{Name:"Fixture ROM", Version:"fixture-version"}]}});
  });
  await page.route("**/firmware-fixture", route => route.fulfill({contentType:"text/html", body:`<html><body><div id="root"></div><script type="module">
    import RefreshRuntime from '/@react-refresh'; RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$=()=>{}; window.$RefreshSig$=()=>(type)=>type; window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/firmwareReadHarness.tsx');</script></body></html>`}));
  await page.goto("/firmware-fixture");
  await expect(page.getByRole("button",{name:"Check firmware against SPP"})).toBeEnabled();
  await page.getByRole("button",{name:"Check firmware against SPP"}).hover();
  await expect(page.getByRole("button",{name:"Check firmware against SPP"})).toHaveCSS("cursor", "pointer");
  await expect(page.getByRole("button",{name:"Review upgrades",exact:true})).toHaveCSS("cursor", "pointer");
  expect(reads).toBe(0);
  await page.getByRole("button",{name:"Check firmware against SPP"}).click();
  await expect(page.getByText("3.19",{exact:true})).toBeVisible();
  await expect(page.getByText(/Comparison uses the detected ProLiant DL360 Gen10/)).toBeVisible();
  await expect(page.getByText("Not upgrade approval")).toBeVisible();
  await expect(page.getByText("Hardware check completed",{exact:true})).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(reads).toBe(1);
  configured = false;
  await page.reload();
  await expect(page.getByRole("button",{name:"Check firmware against SPP"})).toBeDisabled();
  await expect(page.getByRole("button",{name:"Check firmware against SPP"})).toHaveCSS("cursor", "not-allowed");
  await expect(page.getByText("Connection not checked on this visit",{exact:true})).toBeVisible();
  await expect(page.getByText("3.19",{exact:true})).not.toBeVisible();
  await expect(page.getByRole("link",{name:"Open connection settings"})).toBeVisible();
  expect(reads).toBe(1);
});

for (const failure of ["offline", "blocked", "transport", "mismatched reading"]) {
  test(`saved firmware is not live and ${failure} cannot leave a successful comparison`, async ({page}) => {
    let probes = 0;
    let assessments = 0;
    let releaseProbe!: () => void;
    const pending = new Promise<void>(resolve => { releaseProbe = resolve; });
    await page.route("**/api/**", async route => {
      const url = new URL(route.request().url());
      expect(url.searchParams.get("device_id")).toBe("fixture-server");
      if (url.pathname.endsWith("access-settings")) return route.fulfill({json:{host:"192.0.2.10", username_configured:true, password_configured:true}});
      if (url.pathname.endsWith("firmware-assessment")) {
        assessments++;
        return route.fulfill({json:{status:"Updates available", reason:"Saved comparison",checked_at:"2026-09-14T12:00:00Z",rows:[{component:"iLO",installed:"1.37",target:"3.19",status:"Update available",reason:"Matched firmware",files:[]}]}});
      }
      expect(url.pathname).toBe("/api/v1/providers/ilo-redfish/probe");
      expect(route.request().method()).toBe("POST");
      probes++;
      await pending;
      if (failure === "transport") return route.abort("failed");
      return route.fulfill({json:{status: failure === "mismatched reading" ? "ok" : failure === "blocked" ? "blocked" : "error",message:"Fixture check failed",checked_at:"2026-09-15T12:00:00Z"}});
    });
    await page.route("**/firmware-fixture", route => route.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/firmwareReadHarness.tsx');</script></body></html>`}));
    await page.goto("/firmware-fixture");
    await expect(page.getByText("Connection not checked on this visit",{exact:true})).toBeVisible();
    await expect(page.getByText("3.19",{exact:true})).not.toBeVisible();
    expect(probes).toBe(0);
    await page.locator(".firmware-saved-readings > summary").click();
    await expect(page.getByText("3.19",{exact:true})).toBeVisible();
    await page.getByRole("button",{name:"Check firmware against SPP"}).click();
    await expect(page.getByText("Contacting iLO and reading firmware...",{exact:true})).toBeVisible();
    await expect(page.getByText("3.19",{exact:true})).not.toBeVisible();
    await expect(page.getByRole("button",{name:"Working...",exact:true})).toBeDisabled();
    releaseProbe();
    await expect(page.getByRole("alert")).toContainText("Check unsuccessful. Connection not verified.");
    await expect(page.getByRole("button",{name:"Check firmware against SPP"})).toBeEnabled();
    await expect(page.getByRole("region",{name:"Firmware assessment"})).toHaveCount(0);
    expect(probes).toBe(1);
    expect(assessments).toBe(failure === "mismatched reading" ? 2 : 1);
    for (const width of [1440,390]) {
      await page.setViewportSize({width,height:950});
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      if (failure === "offline") await page.screenshot({path:`test-results/firmware-offline-${width}.png`,fullPage:true});
    }
    await page.reload();
    await expect(page.getByText("Connection not checked on this visit",{exact:true})).toBeVisible();
    await expect(page.getByText("3.19",{exact:true})).not.toBeVisible();
    expect(probes).toBe(1);
  });
}
