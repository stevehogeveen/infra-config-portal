import {test, expect} from "@playwright/test";

test('physical erasure has explicit scope, blocked reasons and single-use confirmation', async ({page}) => {
  let blocked = true, writes = 0, authorizations = 0, shutdowns = 0, power = 'On';
  let releasePower: (()=>void)|undefined;
  let boots=0, verified=false;
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/preview')) return route.fulfill({json:{
      preview_id:'a'.repeat(36), operation:'sanitize', name:'Test server',host:'192.0.2.10',controller:'HPE test controller',
      power, arrays_present:false, authorization_expires_at:authorizations?new Date(Date.now()+86400000).toISOString():null,
      preparation:{raw_bays:['1I:1:1','1I:1:2'],assigned_bays:[],support_review_bays:[]},
      raw_preparation:{assignment_verified:!blocked,controller_mode:'Mixed',blockers:blocked?['Array membership could not be confirmed.']:[],reference:'https://example.invalid/vendor'},
      method:'PATCH',path:'/redfish/v1/Systems/1/SmartStorageConfig/Settings/',
      payload:{Actions:[{Action:'PhysicalDriveErase',ErasePattern:'SanitizeRestrictedOverwrite',PhysicalDriveList:['1I:1:1','1I:1:2']}]},
      drives:[1,2].map(i=>({path:`/drives/${i}`,bay:`1I:1:${i}`,identity:String(i).repeat(64),model:'Fixture SAS disk',capacity_bytes:300e9,media:i===1?'HDD':'SSD',erase_pattern:i===1?'SanitizeRestrictedOverwrite':'SanitizeRestrictedBlockErase',role:'Raw',blockers:blocked?['Method support not approved for this drive.']:[]})),
      blockers:blocked?['Delete and verify existing arrays first.']:[],warnings:[],volumes:[],empty_bays:[],
      scope_note:'All physical drives on this controller, including former hot spares.',assurance:'Not a compliance certificate.',
      apply_enabled:!blocked,confirmation:'ERASE ALL 2 DISKS Test server',expires_at:new Date(Date.now()+300000).toISOString(),
    }});
    if (path.endsWith('/shutdown-preview')) return route.fulfill({json:{
      preview_id:'b'.repeat(36),name:'Test server',force:false,confirmation:'SHUT DOWN Test server',
      blockers:[],apply_enabled:true,payload:{ResetType:'PushPowerButton'},
    }});
    if (path.endsWith('/shutdown')) {
      shutdowns++; power='Off';
      expect(route.request().postDataJSON()).toMatchObject({confirmation:'SHUT DOWN Test server',downtime_confirmed:true});
      return route.fulfill({json:{message:'Shutdown requested.'}});
    }
    if (path.endsWith('/power-state')) return new Promise<void>(resolve=>{
      releasePower=()=>{void route.fulfill({json:{power,pending_changes:false}}).then(()=>resolve());};
    });
    if (path.endsWith('/sanitize-authorization')) {
      authorizations++;
      expect(route.request().postDataJSON()).toMatchObject({
        confirmation:'AUTHORIZE ERASURE Test server',vendor_support_reviewed:true,
      });
      expect(Object.keys(route.request().postDataJSON().sources)).toHaveLength(2);
      expect(new Set(Object.values(route.request().postDataJSON().sources)).size).toBe(1);
      return route.fulfill({json:{expires_at:new Date(Date.now()+86400000).toISOString(),message:'Authorization saved. No disks changed.'}});
    }
    if (path.endsWith('/apply')) {
      writes++;
      expect(route.request().postDataJSON()).toMatchObject({physical_erase_confirmed:true,confirmation:'ERASE ALL 2 DISKS Test server'});
      return route.fulfill({json:{status:'pending',message:'Staged'}});
    }
    if(path.endsWith('/boot-preview'))return route.fulfill({json:{preview_id:'c'.repeat(36),operation:'sanitize',name:'Test server',apply_enabled:true,blockers:[],confirmation:'START Test server',method:'POST',path:'/reset',payload:{ResetType:'On'},pending_payload:{}}});
    if(path.endsWith('/boot')){
      boots++;
      expect(route.request().postDataJSON()).toMatchObject({confirmation:'START Test server',pending_changes_reviewed:true,data_loss_confirmed:true,maintenance_confirmed:true});
      return route.fulfill({json:{status:'waiting',message:'Power-on accepted.'}});
    }
    if(path.endsWith('/verify')){verified=true;return route.fulfill({json:{status:'verified',verified:true,message:'All disks verified.'}});}
    if (path.endsWith('/sanitization-report')) return route.fulfill({json:{status:'not_started',message:'No erasure submitted.'}});
    if (path.endsWith('/raid-rebuild/status')) return route.fulfill({json:{status:verified?'verified':boots?'waiting':'staged',operation:'sanitize',active:!verified,message:verified?'All disks verified.':'Erasure staged, not started.',boot_blockers:[],boot_started_at:boots?new Date().toISOString():null}});
    throw Error('Unexpected API: '+path);
  });
  await page.route('**/sanitize-fixture', r=>r.fulfill({contentType:'text/html',body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh'; R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/diskSanitizationHarness.tsx');</script></body></html>`}));
  await page.goto('/sanitize-fixture');
  await page.getByRole('button',{name:'Review all disks for erasure'}).click();
  const dialog=page.getByRole('dialog',{name:'Confirm physical-disk erasure'});
  const apply=dialog.getByRole('button',{name:'Confirm wipe request'});
  await expect(dialog.getByRole('heading',{name:'Step 1 of 4: Choose an erase method',exact:true})).toBeVisible();
  await expect(dialog.getByText('Not ready to wipe',{exact:true})).toHaveCount(0);
  const methodSummary=dialog.getByRole('region',{name:'Selected erase method'});
  await expect(methodSummary.getByText('1 disk: full overwrite',{exact:true})).toBeVisible();
  await expect(methodSummary.getByText(/Can take hours/)).toBeVisible();
  await expect(methodSummary.getByText('1 disk: SSD block erase',{exact:true})).toBeVisible();
  await dialog.getByRole('button',{name:'Next',exact:true}).click();
  await expect(dialog.getByRole('heading',{name:'Step 2 of 4: Prepare the server',exact:true})).toBeVisible();
  await expect(methodSummary).toHaveCount(0);
  await expect(dialog.getByText(/2 Raw disks need their assignment checked/)).toBeVisible();
  await expect(dialog.getByText('Delete and verify existing arrays first.')).not.toBeVisible();
  await dialog.getByText('All readiness issues',{exact:true}).click();
  await expect(dialog.getByText('Delete and verify existing arrays first.')).toBeVisible();
  await expect(dialog.getByText('Method support not approved for this drive.',{exact:true})).toHaveCount(1);
  await dialog.getByText('All readiness issues',{exact:true}).click();
  await expect(dialog.locator('pre')).not.toBeVisible();
  await expect(page.getByRole('combobox')).toHaveCount(0);
  await expect(apply).toHaveCount(0);
  await expect(dialog.getByRole('button',{name:'Wipe drives...',exact:true})).toHaveCount(0);
  await dialog.getByRole('button',{name:'Next',exact:true}).click();
  const shutdown = dialog.getByRole('region',{name:'Shutdown before disk erasure'});
  await expect(shutdown.getByText('Server power: On',{exact:true})).toBeVisible();
  await expect(shutdown.getByRole('button',{name:'Shut down server...',exact:true})).toHaveCount(0);
  await expect(shutdown.getByRole('button',{name:'Check power state',exact:true})).toHaveCount(0);
  const send = shutdown.getByRole('button',{name:'Send shutdown request'});
  await expect(send).toBeDisabled();
  expect(shutdowns).toBe(0);
  await shutdown.getByLabel(/I approve downtime/).check();
  await shutdown.getByLabel('Shutdown confirmation phrase').fill('SHUT DOWN Test server');
  await send.click();
  await expect(shutdown.getByText(/Shutdown requested. Waiting for iLO/)).toBeVisible();
  await expect(send).toHaveCount(0);
  await expect(shutdown.getByRole('button',{name:'Check power state'})).toHaveCount(0);
  await page.screenshot({path:'test-results/shutdown-monitoring.png'});
  await expect.poll(()=>!!releasePower).toBe(true);
  releasePower!();
  await expect(dialog.getByText('Server is off. Disk readiness has been refreshed.',{exact:true})).toBeVisible();
  await expect(shutdown).toHaveCount(0);
  expect(shutdowns).toBe(1);
  expect(writes).toBe(0);
  await expect(dialog.getByRole('button',{name:'Check disk readiness'})).toHaveCount(0);
  await expect(dialog.getByRole('button',{name:'Erasure report'})).toHaveCount(0);
  await dialog.getByRole('button',{name:'Next',exact:true}).click();
  const authorize=dialog.getByRole('button',{name:'Save and Next'});
  await expect(authorize).toBeDisabled();
  await expect(dialog.getByText(/Required: add a vendor reference/)).toBeVisible();
  await expect(dialog.locator('textarea')).toHaveCount(1);
  await dialog.getByLabel('Use a different reference for each disk').check();
  await expect(dialog.locator('textarea')).toHaveCount(2);
  await expect(authorize).toBeDisabled();
  await dialog.getByLabel('Use a different reference for each disk').uncheck();
  for (const input of await dialog.locator('textarea').all()) await input.fill('Vendor support case fixture: exact firmware and method reviewed.');
  await dialog.getByLabel(/I reviewed vendor support/).check();
  await dialog.getByLabel('Type AUTHORIZE ERASURE Test server').fill('AUTHORIZE ERASURE Test server');
  await expect(authorize).toBeEnabled();
  await authorize.click();
  await expect(dialog.getByText('Authorization saved. No disks changed.')).toBeVisible();
  expect(authorizations).toBe(1);
  expect(writes).toBe(0);
  await expect(dialog.getByRole('button',{name:'Retry checks',exact:true})).toBeVisible();
  for (const width of [1440,768,390,320]) {
    await page.setViewportSize({width,height:950});
    await page.screenshot({path:`test-results/sanitization-${width}.png`});
    const overflow = await dialog.evaluate(el => [...el.querySelectorAll('*')].filter(c => c.getBoundingClientRect().right > el.getBoundingClientRect().right + 1).map(c => `${c.tagName}.${c.className}`));
    expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1), `${width}: ${overflow.join(',')}`).toBe(true);
  }
  await dialog.getByRole('button',{name:'Close erase review'}).click();
  blocked=false;
  await page.getByRole('button',{name:'Review all disks for erasure'}).click();
  await dialog.getByRole('button',{name:'Next',exact:true}).click();
  await expect(dialog.getByText('Disk assignment check passed: 2 unassigned disks. No controller-mode conversion is needed.')).toBeVisible();
  await expect(dialog.getByRole('heading',{name:'Ready for wipe confirmation',exact:true})).toBeVisible();
  await expect(dialog.getByText(/must be unconfigured|requires unconfigured RAID-mode/)).toHaveCount(0);
  await dialog.getByRole('button',{name:'Next',exact:true}).click();
  await expect(dialog.getByText('Planned method: Overwrite (device sanitize)')).toBeVisible();
  await expect(apply).toBeDisabled();
  await dialog.getByLabel('Physical erasure confirmation phrase').fill('ERASE ALL 2 DISKS Test server');
  await expect(apply).toBeDisabled();
  for (const checkbox of await dialog.getByRole('checkbox').all()) await checkbox.check();
  await expect(dialog.getByRole('checkbox')).toHaveCount(2);
  await expect(apply).toBeEnabled();
  await page.screenshot({path:'test-results/sanitization-confirm-320.png'});
  await apply.click();
  await expect(dialog.getByText(/Erasure staged, not completed/)).toBeVisible();
  await expect(apply).toHaveCount(0);
  await expect(dialog.getByRole('button',{name:'Start server and begin erasure'})).toBeVisible();
  expect(writes).toBe(1);
  await dialog.getByRole('button',{name:'Start server and begin erasure'}).click();
  const boot=page.getByRole('dialog',{name:'Start server for RAID'});
  const start=boot.getByRole('button',{name:'Confirm power-on and begin erasure'});
  await expect(start).toBeDisabled();
  for(const checkbox of await boot.getByRole('checkbox').all())await checkbox.check();
  await boot.getByLabel('Power-on confirmation phrase').fill('START Test server');
  await start.click();
  await expect(boot).toHaveCount(0);
  await expect(dialog.getByRole('heading',{name:'Disk erasure verified'})).toBeVisible({timeout:10000});
  expect(boots).toBe(1);
  expect(writes).toBe(1);
  await dialog.getByRole('button',{name:'Back to storage setup'}).click();
  await expect(dialog).not.toBeVisible();
});
