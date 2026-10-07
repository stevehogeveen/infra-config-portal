import {test,expect} from "@playwright/test";

test("missing bay is a warning and RAID writes need reviewed, explicit confirmation",async({page})=>{
  let plans=0,previews=0,writes=0;
  const drives=[1,2,3,4,5,6,7].map(i=>({id:`drive-${i}`,location:`1I:1:${i}`,model:i===7?"Not identified":"Fixture drive",capacity_bytes:i===7?0:300e9,health:i===7?"Warning":"OK",label:i===7?"Missing or unidentified":"OK",presence:i===7?"unidentified":"identified",firmware:"HPD1",eligible:i!==7}));
  await page.route("**/api/**",route=>{
    const request=route.request(),url=new URL(request.url());
    const path=url.pathname;
    if(path.endsWith('/raid-rebuild/status'))return route.fulfill({json:{status:writes?'staged':'not_started',active:!!writes,message:writes?'Staged, not completed':'No operation'}});
    if(path.endsWith('/boot-preview'))return route.fulfill({json:{preview_id:'c'.repeat(36),operation:'clear',name:'Test server',blockers:[],apply_enabled:true,confirmation:'START RAID Test server',payload:{ResetType:'On'},pending_payload:{LogicalDrives:[]},method:'POST',path:'/reset'}});
    if(path.endsWith("/preview")){
      previews++;expect(request.postDataJSON()).toEqual({operation:"clear"});
      return route.fulfill({json:{preview_id:"a".repeat(36),operation:"clear",name:"Test server",host:"192.0.2.10",controller:"HPE Smart Array P408i-a SR Gen10",method:"PUT",path:"/redfish/v1/Systems/1/SmartStorageConfig/Settings/",payload:{DataGuard:"Disabled",LogicalDrives:[],Actions:[{Action:"ClearConfigurationMetadata"}]},volumes:[{id:"v",name:"Old RAID",raid:"RAID1",capacity_bytes:300e9}],empty_bays:["1I:1:7"],warnings:["Missing spare record: inspect the bay"],blockers:[],apply_enabled:true,confirmation:"CLEAR RAID Test server",expires_at:new Date(Date.now()+300000).toISOString()}});
    }
    if(path.endsWith("/apply")){
      writes++;expect(request.postDataJSON()).toEqual({preview_id:"a".repeat(36),confirmation:"CLEAR RAID Test server",data_loss_confirmed:true,backups_confirmed:true,health_reviewed:true,firmware_reviewed:true,empty_bays_confirmed:["1I:1:7"]});
      return new Promise<void>(resolve=>setTimeout(()=>{void route.fulfill({json:{status:"pending",message:"Configuration staged. Verify after the next server boot.",verified:false}}).then(resolve);},1000));
    }
    if(path.endsWith("/disk-preparation")){
      if(request.method()==="POST"){
        plans++;expect(request.postDataJSON()).toMatchObject({boot_drive_ids:["drive-1","drive-2"],data_drive_ids:["drive-3","drive-4","drive-5","drive-6"],data_raid:"RAID5"});
        return route.fulfill({json:{status:"Plan saved",message:"No disks changed."}});
      }
      return route.fulfill({json:{name:"Test server",model:"HPE DL360",host:"192.0.2.10",current:true,checked_at:new Date().toISOString(),inventory_token:"a".repeat(64),controllers:[{id:"c",model:"Smart Array",health:"Warning",firmware:"1.66"}],drives,volumes:[{id:"v",name:"Old RAID",raid:"RAID1",capacity_bytes:300e9}],blockers:[],health_issues:["Missing spare"],saved_intent:{volumes:plans?[{bootable:true,raid_level:"RAID1",drive_bays:["1I:1:1","1I:1:2"]},{bootable:false,raid_level:"RAID5",drive_bays:["1I:1:3","1I:1:4","1I:1:5","1I:1:6"]}]:[],wipe_existing_logical_drives:!!plans}}});
    }
    expect(request.method()).toBe("GET");expect(path).toBe("/api/v1/rack-plans/fixture");
    return route.fulfill({json:{equipment:[{id:"s",device_id:"s",kind:"server",name:"Test server"}]}});
  });
  await page.route("**/raid-fixture",r=>r.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh'; R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/diskPreparationHarness.tsx');</script></body></html>`}));
  await page.clock.install();
  await page.goto("/raid-fixture");
  const missing=page.locator('.storage-assignment-table tbody tr').filter({hasText:"Missing or unidentified"});
  await expect(missing.locator('.state-warning')).toBeVisible();
  await expect(missing.getByRole('combobox')).toBeDisabled();
  expect(previews).toBe(0);expect(writes).toBe(0);
  await page.getByLabel("Role for drive 1I:1:1",{exact:true}).selectOption("boot");await page.getByLabel("Role for drive 1I:1:2",{exact:true}).selectOption("boot");
  for(const i of [3,4,5,6])await page.getByLabel(`Role for drive 1I:1:${i}`,{exact:true}).selectOption("data");
  await page.getByText(/Existing configuration \(1 volume\)/).click();
  await page.getByLabel("Replace the existing RAID volumes").check();await page.getByLabel(/I have reviewed the backups/).check();
  await page.getByRole("button",{name:"Save proposed layout"}).click();
  await expect(page.getByText("No disks changed.",{exact:true})).toBeVisible();
  // Aging display evidence must not prevent opening a fresh, guarded preview.
  await page.clock.fastForward(6 * 60 * 1000);
  await expect(page.getByText(/Inventory is over five minutes old/)).toBeVisible();
  await expect(page.getByRole('button',{name:'Delete old RAID',exact:true})).toBeEnabled();
  expect(writes).toBe(0);
  await page.getByRole("button",{name:"Delete old RAID",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"Review RAID rebuild"});
  await expect(dialog.getByRole("heading",{name:"Confirm RAID deletion",exact:true})).toBeVisible();
  await expect(dialog.getByText(/Nothing has been changed/)).toBeVisible();
  const apply=dialog.getByRole("button",{name:"Confirm and stage RAID deletion",exact:true});
  await expect(apply).toBeDisabled();
  await expect(dialog.locator('.raid-payload')).toHaveCSS('color','rgb(36, 62, 68)');
  expect(writes).toBe(0);
  for(const width of [1440,390]){await page.setViewportSize({width,height:950});expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);await page.screenshot({path:`test-results/raid-rebuild-${width}.png`});}
  await dialog.getByLabel("RAID confirmation phrase").fill("CLEAR RAID Test server");
  await expect(apply).toBeDisabled();
  for(const checkbox of await dialog.getByRole("checkbox").all())await checkbox.check();
  await expect(apply).toBeEnabled();await apply.click();
  await expect(dialog.getByRole('heading',{name:'Sending storage request...'})).toBeVisible();
  await expect(dialog.getByText("Configuration staged. Verify after the next server boot.")).toBeVisible();
  await expect(apply).toHaveCount(0);
  await expect(dialog.getByRole('heading',{name:'Request accepted: waiting for server power-on'})).toBeVisible();
  await expect(dialog.getByRole('button',{name:'Start server and verify RAID'})).toBeVisible();
  for(const width of [1440,320]){
    await page.setViewportSize({width,height:950});
    expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    await page.screenshot({path:`test-results/raid-staged-${width}.png`});
  }
  await dialog.getByRole('button',{name:'Start server and verify RAID'}).click();
  const boot=page.getByRole('dialog',{name:'Start server for RAID'});
  await expect(boot.getByRole('button',{name:'Confirm power-on and apply RAID'})).toBeDisabled();
  await boot.getByRole('button',{name:'Close power-on review'}).click();
  expect(previews).toBe(1);expect(writes).toBe(1);
  await dialog.getByRole('button', {name: 'Close RAID review'}).click();
  const eraseSection=page.getByRole('region',{name:'Physical-disk sanitization'});
  await expect(eraseSection.getByRole('button',{name:'Review all disks for erasure'})).toBeDisabled();
  await eraseSection.getByRole('button',{name:'Go to current storage operation'}).click();
  const currentOperation=page.getByRole('region',{name:'RAID operation progress'});
  await expect(currentOperation.getByRole('button',{name:'Start server and verify RAID'})).toBeEnabled();
  await currentOperation.getByRole('button',{name:'Start server and verify RAID'}).click();
  await expect(page.getByRole('dialog',{name:'Start server for RAID'})).toBeVisible();
  await page.getByRole('button',{name:'Close power-on review'}).click();
  expect(writes).toBe(1);
  await page.route('**/raid-rebuild/preview?*', route => {
    expect(route.request().postDataJSON()).toEqual({operation:'reset'});
    return route.fulfill({json:{preview_id:'b'.repeat(36),operation:'reset',name:'Test server',host:'192.0.2.10',controller:'Smart Array',method:'PUT',path:'/redfish/v1/Systems/1/SmartStorageConfig/Settings/',payload:{Actions:[{Action:'FactoryReset'}],DataGuard:'Disabled'},volumes:[],empty_bays:[],warnings:[],blockers:['A previous storage request has not been verified.'],apply_enabled:false,confirmation:'RESET STORAGE CONTROLLER Test server'}});
  });
  await page.getByText('Advanced storage recovery', {exact:true}).click();
  await page.getByRole('button', {name:'Review controller reset',exact:true}).click();
  await expect(dialog.getByRole('heading', {name:'Confirm storage controller reset'})).toBeVisible();
  await expect(dialog.getByText('A previous storage request has not been verified.')).toBeVisible();
  await expect(dialog.getByRole('button', {name:'Confirm and stage controller reset'})).toBeDisabled();
  await expect(dialog.locator('.raid-payload')).toContainText('FactoryReset');
  await dialog.getByRole('button',{name:'Open guided storage recovery'}).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('button',{name:'Shut down server...',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Shut down server...',exact:true})).toBeEnabled();
  expect(writes).toBe(1);
});

test("verified deletion opens erase preparation without sending a hardware write",async({page})=>{
  let previews=0;
  await page.route("**/api/**",route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    if(path.endsWith("/raid-rebuild/status"))return route.fulfill({json:{status:"verified",operation:"clear",active:false,message:"Old layout cleared",verified_at:new Date().toISOString()}});
    if(path.endsWith("/sanitization-report"))return route.fulfill({json:{status:"not_started",message:"No physical-disk erasure has been submitted."}});
    if(path.endsWith("/disk-preparation"))return route.fulfill({json:{name:"Test server",current:false,checked_at:null,controllers:[],drives:[],volumes:[],blockers:[],health_issues:[],saved_intent:{volumes:[],wipe_existing_logical_drives:false}}});
    if(path.endsWith("/preview")){
      previews++;expect(request.postDataJSON()).toEqual({operation:"sanitize",erase_pattern:"auto"});
      return route.fulfill({json:{preview_id:"a".repeat(36),operation:"sanitize",name:"Test server",host:"192.0.2.10",controller:"Fixture controller",method:"PATCH",path:"/settings",payload:{},drives:[],blockers:["Fresh drive evidence required"],warnings:[],empty_bays:[],volumes:[],apply_enabled:false,confirmation:"ERASE ALL 0 DISKS Test server"}});
    }
    expect(request.method()).toBe("GET");
    return route.fulfill({json:{equipment:[]}});
  });
  await page.route("**/raid-fixture",r=>r.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh'; R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/diskPreparationHarness.tsx');</script></body></html>`}));
  await page.goto("/raid-fixture");
  await expect(page.getByRole("button",{name:"Prepare disk erasure",exact:true})).toHaveCount(1);
  await expect(page.getByRole("region",{name:"Physical-disk sanitization"})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Review all disks for erasure"})).toHaveCount(0);
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:1000});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    await page.screenshot({path:`test-results/storage-single-entry-${width}.png`,fullPage:true});
  }
  await page.getByRole("button",{name:"Prepare disk erasure",exact:true}).click();
  const eraseDialog=page.getByRole("dialog",{name:"Confirm physical-disk erasure"});
  await expect(eraseDialog).toBeVisible();
  await eraseDialog.getByRole("button",{name:"Next",exact:true}).click();
  await expect(eraseDialog.getByText(/Physical erasure is irreversible/)).toBeVisible();
  await expect(eraseDialog.getByRole("button",{name:"Wipe drives...",exact:true})).toHaveCount(0);
  await expect(eraseDialog.getByRole("button",{name:"Erasure report"})).toHaveCount(0);
  await expect(eraseDialog.getByRole("heading",{name:"Preparation required: erasure has not started"})).toBeVisible();
  await eraseDialog.getByRole("button",{name:"Close erase review"}).click();
  await expect(page.getByRole("button",{name:"Prepare disk erasure",exact:true})).toBeEnabled();
  await expect(page.getByRole("region",{name:"Physical-disk sanitization"})).toHaveCount(0);
  expect(previews).toBe(1);
});
