import { test, expect } from "@playwright/test";

test("pending RAID remains visible with stale inventory and power-on needs separate confirmation", async ({ page }) => {
  let boots = 0, verifies = 0;
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/disk-preparation')) return route.fulfill({ json: { current:false, blockers:['Refresh inventory before editing the plan.'], drives:[], volumes:[], health_issues:[], saved_intent:{volumes:[],wipe_existing_logical_drives:true} } });
    if (path.endsWith('/status')) return route.fulfill({ json: { status: boots ? verifies ? 'verified' : 'waiting' : 'staged', active: !verifies, operation:'clear', message:boots ? 'Power-on accepted; waiting for verification' : 'RAID changes are staged, not completed.', submitted_at:new Date().toISOString(), boot_started_at:boots ? new Date().toISOString() : null, boot_blockers:[] } });
    if (path.endsWith('/boot-preview')) return route.fulfill({ json: { preview_id:'p'.repeat(36), name:'Test server', operation:'clear', confirmation:'START RAID Test server', pending_payload:{LogicalDrives:[]}, method:'POST',path:'/redfish/v1/Systems/1/Actions/ComputerSystem.Reset/',payload:{ResetType:'On'}, blockers:[],apply_enabled:true,expires_at:new Date(Date.now()+300000).toISOString() } });
    if (path.endsWith('/boot')) {
      boots++; expect(route.request().postDataJSON()).toMatchObject({confirmation:'START RAID Test server',data_loss_confirmed:true,pending_changes_reviewed:true,maintenance_confirmed:true});
      return route.fulfill({json:{status:'waiting',message:'Power-on accepted. Waiting for POST.'}});
    }
    if (path.endsWith('/verify')) { verifies++; return route.fulfill({json:{status:'verified',verified:true,message:'Verified: the old RAID layout is cleared.'}}); }
    throw Error(`Unexpected request ${path}`);
  });
  await page.route('**/boot-fixture', r => r.fulfill({contentType:'text/html',body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/diskPreparationHarness.tsx');</script></body></html>`}));
  await page.goto('/boot-fixture');
  await expect(page.getByRole('heading',{name:'Ready to start the server'})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button',{name:'Start server and verify RAID'})).toBeEnabled();
  expect(boots).toBe(0); expect(verifies).toBe(0);
  await page.getByRole('button',{name:'Start server and verify RAID'}).click();
  const dialog = page.getByRole('dialog',{name:'Start server for RAID'});
  const start = dialog.getByRole('button',{name:'Confirm power-on and apply RAID'});
  await expect(start).toBeDisabled();
  await dialog.getByLabel('Power-on confirmation phrase').fill('START RAID Test server');
  await expect(start).toBeDisabled();
  for (const c of await dialog.getByRole('checkbox').all()) await c.check();
  await expect(start).toBeEnabled();
  for (const width of [1440,390]) {
    await page.setViewportSize({width,height:950});
    expect(await dialog.evaluate(e => e.scrollWidth <= e.clientWidth + 1)).toBe(true);
    await page.screenshot({path:`test-results/raid-boot-${width}.png`});
  }
  await start.click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('heading',{name:'RAID arrays removed',exact:true})).toBeVisible({timeout:15000});
  expect(boots).toBe(1); expect(verifies).toBe(1);
  await page.reload();
  await expect(page.getByRole('heading',{name:'RAID arrays removed',exact:true})).toBeVisible();
  expect(boots).toBe(1);
});
