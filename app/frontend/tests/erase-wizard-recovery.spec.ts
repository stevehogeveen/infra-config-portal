import {test,expect,type Page} from "@playwright/test";

const review=(expires=new Date(Date.now()+300000).toISOString())=>({
  preview_id:"a".repeat(36),operation:"sanitize",name:"Fixture server",host:"192.0.2.20",controller:"Fixture controller",
  power:"Off",arrays_present:false,authorization_expires_at:new Date(Date.now()+86400000).toISOString(),
  drives:[{bay:"1",identity:"disk-one",model:"Fixture HDD",media:"HDD",capacity_bytes:300e9,erase_pattern:"OnePass",blockers:[]}],
  blockers:[],warnings:[],volumes:[],empty_bays:[],apply_enabled:true,expires_at:expires,
  confirmation:"ERASE ALL 1 DISKS Fixture server",method:"PATCH",path:"/settings",payload:{}
});
async function fixture(page:Page){
  await page.route("**/wizard-fixture",r=>r.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh'; R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/diskSanitizationHarness.tsx');</script></body></html>`}));
  await page.goto("/wizard-fixture");
}
test("slow read can be cancelled and its late result cannot overwrite a new review",async({page})=>{
  let reads=0,release:(()=>Promise<void>)|undefined;
  await page.route("**/api/v1/**",async route=>{
    expect(new URL(route.request().url()).pathname).toMatch(/\/preview$/);
    reads++;
    if(reads===1){await new Promise<void>(resolve=>{release=async()=>{await route.fulfill({json:{...review(),name:"Old response"}});resolve();};});return;}
    await route.fulfill({json:review()});
  });
  await fixture(page);
  await page.getByRole("button",{name:"Review all disks for erasure"}).click();
  const dialog=page.getByRole("dialog");
  await expect(dialog.getByText(/Reading this server's disks/)).toBeVisible();
  await expect(dialog.getByRole("button",{name:"Cancel",exact:true})).toBeEnabled();
  await dialog.getByRole("button",{name:"Cancel",exact:true}).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole("button",{name:"Review all disks for erasure"}).click();
  await expect(dialog.getByText("Fixture server",{exact:true})).toBeVisible();
  await release!();
  await expect(dialog.getByText("Old response",{exact:true})).toHaveCount(0);
  await dialog.getByRole("button",{name:"Next",exact:true}).click();
  await expect(dialog.getByRole("heading",{name:"Step 2 of 4: Prepare the server"})).toBeVisible();
});

test("failed review offers retry and expiry refresh prevents stale confirmation",async({page})=>{
  let reads=0;
  await page.route("**/api/v1/**",route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith("/erase-options"))return route.fulfill({json:{models:[],controllers:[],current:false,options:[]}});
    expect(path).toMatch(/\/preview$/);
    reads++;
    if(reads===1)return route.fulfill({status:503,json:{detail:"Fixture hardware temporarily unavailable"}});
    return route.fulfill({json:review(reads===2?new Date(Date.now()-1000).toISOString():undefined)});
  });
  await fixture(page);
  await page.getByRole("button",{name:"Review all disks for erasure"}).click();
  const dialog=page.getByRole("dialog");
  await expect(dialog.getByRole("alert")).toContainText("temporarily unavailable");
  await dialog.getByRole("button",{name:"Retry check",exact:true}).click();
  await expect(dialog.getByText(/The hardware check expired/)).toBeVisible();
  await expect(dialog.getByRole("button",{name:"Next",exact:true})).toHaveCount(0);
  await dialog.getByRole("button",{name:"Refresh check",exact:true}).click();
  await dialog.getByRole("button",{name:"Next",exact:true}).click();
  await dialog.getByRole("button",{name:"Next",exact:true}).click();
  await expect(dialog.getByRole("heading",{name:"Step 3 of 4: Confirm drive wipe"})).toBeFocused();
  await expect(dialog.getByRole("button",{name:"Confirm wipe request"})).toBeDisabled();
  await dialog.getByRole("button",{name:"Back",exact:true}).click();
  await expect(dialog.getByRole("heading",{name:"Step 2 of 4: Prepare the server"})).toBeFocused();
  expect(reads).toBe(3);
});
