import {test,expect} from "@playwright/test";

test("review disk health and save only a confirmed plan, never execute deletion",async({page})=>{
  let plans=0,probes=0;
  const drives=[1,2,3].map(i=>({id:`drive-${i}`,location:`1I:1:${i}`,model:"Fixture drive",capacity_bytes:300e9,health:i===3?"Critical":"OK",firmware:"HPD1",eligible:i!==3}));
  await page.route("**/api/**",route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith("/probe")){probes++;return route.fulfill({json:{status:"ok"}});}
    if(path.endsWith("/disk-preparation")){
      if(route.request().method()==="POST"){
        plans++;expect(route.request().postDataJSON()).toMatchObject({boot_drive_ids:["drive-1","drive-2"],remove_existing_volumes:true,data_loss_reviewed:true});
        return route.fulfill({json:{status:"Plan saved",message:"No disks changed."}});
      }
      return route.fulfill({json:{name:"Test server",model:"HPE DL360 Gen10",host:"192.0.2.10",current:true,checked_at:new Date().toISOString(),inventory_token:"a".repeat(64),controllers:[{id:"c",model:"Smart Array",health:"Warning",firmware:"1.66"}],drives,volumes:[{id:"v1",name:"Old RAID1",raid:"RAID1",capacity_bytes:300e9}],blockers:[],health_issues:["1I:1:3: Critical"],saved_intent:{volumes:[],wipe_existing_logical_drives:false}}});
    }
    expect(path).toBe("/api/v1/rack-plans/fixture");
    return route.fulfill({json:{equipment:[{id:"s",device_id:"s",kind:"server",name:"Test server"}]}});
  });
  await page.route("**/disk-fixture",r=>r.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh'; R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/diskPreparationHarness.tsx');</script></body></html>`}));
  await page.goto("/disk-fixture");
  await expect(page.getByText("Hardware needs attention (1)")).toBeVisible();
  expect(probes).toBe(0);
  await expect(page.getByLabel("Role for drive 1I:1:3",{exact:true})).toBeDisabled();
  await page.getByLabel("Role for drive 1I:1:1",{exact:true}).selectOption("boot");
  await page.getByLabel("Role for drive 1I:1:2",{exact:true}).selectOption("boot");
  await expect(page.getByRole("button",{name:"Save proposed layout"})).toBeDisabled();
  await page.getByText(/Existing configuration \(1 volume\)/).click();
  await page.getByLabel("Replace the existing RAID volumes").check();
  await page.getByLabel(/I have reviewed the backups/).check();
  await page.getByRole("button",{name:"Save proposed layout"}).click();
  await expect(page.getByText("No disks changed.",{exact:true})).toBeVisible();
  expect(plans).toBe(1);expect(probes).toBe(0);
  for(const width of [1440,390]){await page.setViewportSize({width,height:950});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);await page.screenshot({path:`test-results/disk-preparation-${width}.png`,fullPage:true});}
});

test("unavailable inventory has no editable drive assignments or automatic probe",async({page})=>{
  let inventoryReads=0;
  await page.route("**/api/**",route=>{
    const url=new URL(route.request().url());
    expect(route.request().method()).toBe("GET");
    if(url.pathname.endsWith("/disk-preparation")){
      inventoryReads++;
      expect(url.searchParams.get("device_id")).toBe("s");
      return route.fulfill({json:{current:false,blockers:["Refresh drive inventory before planning storage."],drives:[],saved_intent:{volumes:[],wipe_existing_logical_drives:false}}});
    }
    return route.fulfill({json:{equipment:[{id:"s",device_id:"s",kind:"server",name:"Test server"}]}});
  });
  await page.route("**/disk-fixture*",r=>r.fulfill({contentType:"text/html",body:`<html><body><div id="root"></div><script type="module">import R from '/@react-refresh'; R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/diskPreparationHarness.tsx');</script></body></html>`}));
  await page.goto("/disk-fixture");
  await expect(page.getByText("Refresh drive inventory before planning storage.")).toBeVisible();
  await expect(page.getByRole("button",{name:"Save proposed layout"})).toHaveCount(0);
  await expect(page.getByText("ESXi installation and advanced server settings",{exact:true})).toHaveCount(0);
  expect(inventoryReads).toBe(1);
});
