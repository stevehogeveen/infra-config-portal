import {test, expect} from "@playwright/test";

test("missing vendor reference is visible and HPE documentation never auto-approves erasure", async ({page}) => {
  let approvals = 0;
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/preview")) return route.fulfill({json: {
      preview_id:"a".repeat(36), operation:"sanitize", name:"Fixture server", host:"192.0.2.20",
      controller:"Fixture SR controller", capability_context:{controller_firmware:"1.00"},
      power:"Off", arrays_present:false, authorization_expires_at:approvals?new Date(Date.now()+86400000).toISOString():null,
      preparation:{raw_bays:[], assigned_bays:[], support_review_bays:approvals?[]:["1","2"]},
      drives:[1,2].map(i=>({bay:String(i),identity:`disk-${i}`,model:"Fixture HDD",firmware:"TEST1",media:"HDD",capacity_bytes:300e9,erase_pattern:"OnePass",blockers:[]})),
      blockers:approvals?[]:["Method support review required."], warnings:[], volumes:[], empty_bays:[],
      apply_enabled:!!approvals, expires_at:new Date(Date.now()+300000).toISOString(),
      confirmation:"ERASE ALL 2 DISKS Fixture server", method:"PATCH", path:"/settings", payload:{}
    }});
    if (path.endsWith("/sanitize-authorization")) {
      approvals++;
      const body = route.request().postDataJSON();
      expect(body).toMatchObject({confirmation:"AUTHORIZE ERASURE Fixture server", vendor_support_reviewed:true});
      expect(Object.keys(body.sources)).toEqual(["disk-1","disk-2"]);
      for (const value of Object.values(body.sources)) {
        expect(value).toContain("Existing fixture support case: exact disk/controller firmware reviewed.");
        expect(value).toContain("https://developer.hpe.com/blog/storage-management-with-redfish/");
      }
      return route.fulfill({json:{message:"Support review recorded. No hardware changed."}});
    }
    throw new Error(`Unexpected request (no hardware writes permitted): ${path}`);
  });
  await page.route("**/support-fixture", r=>r.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh'; R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/diskSanitizationHarness.tsx');</script></body></html>`}));
  await page.goto("/support-fixture");
  await page.getByRole("button",{name:"Review all disks for erasure"}).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button",{name:"Next",exact:true}).click();
  await dialog.getByRole("button",{name:"Next",exact:true}).click();
  const save = dialog.getByRole("button",{name:"Save and Next"});
  const reference = dialog.getByLabel("Vendor reference and applicability notes for all listed disks (required)");
  const consent = dialog.getByLabel(/I reviewed vendor support/);
  const referenceBox = await reference.boundingBox();
  const footerBox = await dialog.locator(".erase-wizard-footer").boundingBox();
  expect(referenceBox!.y+referenceBox!.height).toBeLessThanOrEqual(footerBox!.y);
  await consent.check();
  await dialog.getByLabel("Type AUTHORIZE ERASURE Fixture server").fill("AUTHORIZE ERASURE Fixture server");
  await expect(save).toBeDisabled();
  await expect(save).toHaveAttribute("aria-describedby","erase-approval-problem");
  await expect(reference).toHaveAttribute("aria-invalid","true");
  await expect(dialog.getByText(/Required: add a vendor reference/)).toBeVisible();
  await expect(dialog.getByRole("link",{name:/Read HPE documentation/})).toHaveAttribute("href","https://developer.hpe.com/blog/storage-management-with-redfish/");
  await expect(dialog.getByText(/It does not certify support/)).toBeVisible();
  for (const width of [1440,768,390,320]) {
    await page.setViewportSize({width,height:950});
    await page.screenshot({path:`test-results/erase-support-${width}.png`});
    expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    const hint = await dialog.locator("#erase-approval-problem").boundingBox();
    const button = await save.boundingBox();
    expect(hint!.y+hint!.height).toBeLessThanOrEqual(button!.y);
  }
  await reference.fill("Existing fixture support case: exact disk/controller firmware reviewed.");
  await expect(consent).not.toBeChecked();
  await consent.check();
  await expect(save).toBeEnabled();
  await dialog.getByRole("button",{name:"Add HPE reference"}).click();
  await expect(reference).toHaveValue(/Existing fixture support case:[\s\S]*https:\/\/developer.hpe.com/);
  await expect(consent).not.toBeChecked();
  await expect(save).toBeDisabled();
  await expect(dialog.getByRole("button",{name:"Add HPE reference"})).toBeDisabled();
  expect(approvals).toBe(0);
  await dialog.getByLabel("Use a different reference for each disk").check();
  await expect(save).toBeDisabled();
  await expect(dialog.getByText("Add a vendor reference and applicability notes for 2 disks.")).toBeVisible();
  await dialog.getByLabel("Use a different reference for each disk").uncheck();
  await expect(reference).toHaveValue(/Existing fixture support case/);
  await consent.check();
  await save.click();
  await expect(dialog.getByText("Support review recorded. No hardware changed.")).toBeVisible();
  expect(approvals).toBe(1);
  await dialog.getByRole("button",{name:"Next",exact:true}).click();
  await expect(dialog.getByRole("heading",{name:"Step 3 of 4: Confirm drive wipe"})).toBeVisible();
  await expect(dialog.getByRole("button",{name:"Confirm wipe request"})).toBeDisabled();
});
