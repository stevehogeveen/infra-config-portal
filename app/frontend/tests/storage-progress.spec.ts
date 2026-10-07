import {test,expect} from "@playwright/test";

const cases = [
  {operation:"clear",status:"staged",title:"Ready to start the server",tone:"ready",current:1},
  {operation:"sanitize",status:"waiting",title:"Waiting for verified results",tone:"running",current:2},
  {operation:"clear",status:"uncertain",title:"Request outcome is unknown",tone:"attention",current:0},
  {operation:"create",status:"failed",title:"Storage operation rejected",tone:"attention",current:0},
  {operation:"clear",status:"verified",title:"RAID arrays removed",tone:"complete",current:3,next:"Prepare disk erasure"},
  {operation:"sanitize",status:"verified",title:"Disk erasure verified",tone:"complete",current:3,next:"Plan new RAID"},
  {operation:"create",status:"verified",title:"New RAID layout verified",tone:"complete",current:3,next:"Continue to ESXi setup"},
];

for (const example of cases) test(`${example.operation}: ${example.status} has clear progress and next action`,async({page})=>{
  await page.route("**/api/**",route=>{
    expect(route.request().method()).toBe("GET");
    expect(new URL(route.request().url()).pathname).toMatch(/raid-rebuild\/status$/);
    return route.fulfill({json:{...example,active:example.status!=="verified",message:"Controller evidence retained for this operation.",
      submitted_at:"2026-09-24T13:00:00Z",verified_at:example.status==="verified"?"2026-09-24T13:10:00Z":null,
      boot_started_at:example.status==="verified"?"2026-09-24T13:01:00Z":null,
      boot_blockers:[],
      sanitization:example.operation==="sanitize"?{checked_at:"2026-09-24T13:10:00Z",message:"Per-drive evidence",
        drives:[{identity:"fixture",bay:"1I:1:1",model:"Example SSD",media:"SSD",capacity_bytes:480e9,erase_pattern:"SanitizeRestrictedBlockErase",status:example.status==="verified"?"completed":"erasing",percent:example.status==="verified"?100:42}]}:null,
    }});
  });
  await page.route("**/storage-progress-fixture",route=>route.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/storageProgressHarness.tsx');</script></body></html>`}));
  await page.goto("/storage-progress-fixture");
  const panel=page.getByRole("region",{name:"RAID operation progress"});
  await expect(panel.getByRole("heading",{name:example.title,exact:true})).toBeVisible();
  await expect(panel).toHaveClass(new RegExp("is-"+example.tone));
  const stages=panel.getByRole("list",{name:"Operation stages"});
  await expect(stages.locator(".is-done")).toHaveCount(example.current);
  await expect(stages.locator('[aria-current="step"]')).toHaveCount(example.current===3?0:1);
  if(example.next){
    await expect(panel.getByText(/Recorded result, not a live health check/)).toBeVisible();
    await panel.getByRole("button",{name:example.next}).click();
    await expect(page.getByRole("status")).toHaveText("Next selected: "+example.operation);
    await expect(panel.locator(".storage-monitor-note")).toHaveCount(0);
  }
  for(const width of [1440,768,390,320]){
    await page.setViewportSize({width,height:1050});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    expect(await panel.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    if(width===1440||width===390)await page.screenshot({path:`test-results/storage-${example.operation}-${example.status}-${width}.png`,fullPage:true});
  }
});
