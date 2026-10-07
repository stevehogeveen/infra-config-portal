import {test,expect} from '@playwright/test';

test('diagnosis exposes honest SSA recovery, read-only verification and failure without stale success',async({page})=>{
  let reads=0;
  await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/maintenance-diagnostics'))return route.fulfill({json:{job_id:'fixture-ssa'}});
    if(path.endsWith('/maintenance-diagnostics/fixture-ssa'))return route.fulfill({json:{status:'finished',result:{status:'completed',checked_at:new Date().toISOString(),message:'Read-only SSA diagnostics completed.',reports:['Controller Status: Warning','Cache Status: Obsolete Data']}}});
    if(path.endsWith('/diagnose')){
      reads++;
      if(reads===2)return route.fulfill({status:409,json:{detail:'iLO unreachable'}});
      return route.fulfill({json:{name:'Fixture server',checked_at:new Date().toISOString(),status:'needs_attention',summary:'Storage recovery needs attention before the build can continue.',controller:'Fixture controller',controller_health:'Warning',backup_power:'Present',battery_health:'Unknown',detected_drives:6,healthy_drives:6,volume_count:1,pending_changes:false,log_complete:true,log_note:'Historical evidence only.',repair_available:false,raid_verification:'Operation unverified.',volumes:[{raid:'Raid1',members:['1I:1:1','Unknown:0:Unknown'],spares:['1I:1:2']}],findings:[{id:'missing',title:'The old RAID references an unavailable member',source:'Current RAID membership',detail:'Not proof of a failed installed drive.',evidence:['Unknown:0:Unknown'],action:'Inspect the old array in SSA.'},{id:'cache',title:'Cached data may belong to the previous array',source:'Historical IML evidence',detail:'Confirm current cache condition in SSA.',evidence:['1795 mismatch'],action:'Discard only after a separate destructive confirmation.'}],recovery_steps:['Inspect controller status in HPE SSA.','Review any destructive discard separately.','Return here and verify.']}});
    }
    if(path.endsWith('/status'))return route.fulfill({json:{status:'not_started',active:false,message:'No operation'}});
    if(path.endsWith('/disk-preparation'))return route.fulfill({json:{current:false,drives:[],volumes:[],blockers:[],health_issues:[],saved_intent:{volumes:[],wipe_existing_logical_drives:false}}});
    throw Error(`Unexpected request: ${path}`);
  });
  await page.route('**/diagnosis-fixture',r=>r.fulfill({contentType:'text/html',body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/diskPreparationHarness.tsx');</script></body></html>`}));
  await page.goto('/diagnosis-fixture');
  expect(reads).toBe(0);
  await page.getByRole('button',{name:'Diagnose this server'}).click();
  await expect(page.getByText('6 of 6 report healthy')).toBeVisible();
  await page.getByRole('button',{name:'Review recovery steps'}).click();
  await expect(page.getByText('Manual vendor tool required.')).toBeVisible();
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:950});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    await page.screenshot({path:`test-results/storage-diagnosis-${width}.png`,fullPage:true});
  }
  await page.getByRole('button',{name:'Verify recovery'}).click();
  await expect(page.getByRole('alert')).toContainText('iLO unreachable');
  await expect(page.getByText('6 of 6 report healthy')).toBeHidden();
  expect(reads).toBe(2);
  await page.getByText('Advanced maintenance diagnostics',{exact:true}).click();
  await page.getByRole('button',{name:'Read SSA diagnostics with Ansible'}).click();
  await expect(page.getByText('Read-only SSA diagnostics completed.',{exact:true})).toBeVisible({timeout:10000});
  await page.getByText('Detailed storage configuration',{exact:true}).click();
  await expect(page.getByText('Cache Status: Obsolete Data',{exact:true})).toBeVisible();
});
