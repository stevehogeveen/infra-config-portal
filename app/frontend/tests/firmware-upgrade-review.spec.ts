import {test,expect} from "@playwright/test";

test("hardware alerts can be acknowledged without unlocking automatic upgrades",async({page})=>{
  let acknowledged=false;
  const writes:string[]=[];
  const packageFile="P95170_001_gen10spp-2026.05.00.00-SPP2026050000.2026_0527.9.iso";
  const issue={id:"a".repeat(64),title:"Drive at 1I:1:4",group:"Drive",health:"Critical",location:"1I:1:4",details:["The controller cannot communicate with this drive."],next_step:"Identify the bay in iLO Storage and HPE SSA before making changes.",facts:{Location:"1I:1:4",Model:"Not identified",CapacityBytes:0},reasons:["CommunicationFailure"]};
  const health=()=>({current:true,checked_at:new Date().toISOString(),review_token:"b".repeat(64),unacknowledged:acknowledged?0:1,issues:[{...issue,acknowledged_at:acknowledged?new Date().toISOString():null}],message:"Acknowledgement records review only. Alerts remain unresolved.",refresh_required:null,
    diagnostic_log:{complete:false,message:"Historical sample; not a confirmed current cause.",entries:[{Id:"1",Message:"Fixture cache event",Repaired:true,HpeRecommendedAction:"Inspect the cache module in SSA",Created:"2026-01-01T12:00:00Z"}]}});
  const updates=[{component:"iLO",installed:"1.37",target:"3.19",status:"Update available",reason:"Matched; prerequisites unverified",files:["ilo.fwpkg"]}];
  await page.route("**/api/**",route=>{
    const request=route.request(),url=new URL(request.url());
    expect(url.searchParams.get("device_id")).toBe("fixture-server");
    if(request.method()!=="GET")writes.push(url.pathname);
    if(url.pathname.endsWith("access-settings"))return route.fulfill({json:{host:"192.0.2.10",username_configured:true,password_configured:true}});
    if(url.pathname.endsWith("firmware-assessment"))return route.fulfill({json:{status:"Updates available",reason:"Firmware comparison only",rows:updates,health_review:health()}});
    if(url.pathname.endsWith("health-acknowledgements")){
      expect(request.postDataJSON()).toEqual({review_token:"b".repeat(64),issue_id:issue.id});acknowledged=true;
      return route.fulfill({json:health()});
    }
    expect(url.pathname).toBe("/api/v1/rack-plans/fixture-kit/firmware-upgrade-review");
    if(request.method()==="POST"){
      expect(request.postDataJSON()).toEqual({review_token:"c".repeat(64)});
      return route.fulfill({json:{status:"Review saved",message:"Review saved. No firmware installation approved or started.",apply_enabled:false}});
    }
    return route.fulfill({json:{review_token:"c".repeat(64),server:"Fixture server",host:"192.0.2.10",model:"HPE DL360 Gen10",package_file:packageFile,updates,unassessed:0,health_review:health(),blockers:["Hardware alerts remain unresolved.","Automatic SPP installation is not connected. Use attended HPE SUM."],can_save_review:acknowledged,apply_enabled:false,execution_method:"Attended HPE SUM",vendor_url:"https://support.hpe.com/"}});
  });
  await page.route("**/firmware-fixture",route=>route.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/firmwareReadHarness.tsx');</script></body></html>`}));
  await page.goto("/firmware-fixture");
  await page.locator(".firmware-saved-readings > summary").click();
  await expect(page.getByText("The controller cannot communicate with this drive.")).toBeVisible();
  await page.getByText("Server diagnostic log (IML): 1 entries collected",{exact:true}).click();
  await expect(page.getByText("Marked repaired (historical)",{exact:true})).toBeVisible();
  await expect(page.getByText("Fixture cache event",{exact:true})).toBeVisible();
  await expect(page.getByText(/Inspect the cache module in SSA/)).toBeVisible();
  expect(writes).toHaveLength(0);
  await page.getByRole("button",{name:"Review upgrades",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"Review firmware upgrades"});
  await expect(dialog.getByRole("button",{name:"Save upgrade review"})).toBeDisabled();
  await expect(dialog.getByRole("button",{name:"Install automatically"})).toBeDisabled();
  await dialog.getByRole("button",{name:"Close upgrade review"}).click();
  await page.getByRole("button",{name:"Acknowledge Drive at 1I:1:4"}).click();
  await expect(page.getByText(/Acknowledged, still unresolved/)).toBeVisible();
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:950});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    expect(await page.locator('.hardware-health-issue dl > div').evaluateAll(facts=>facts.every(fact=>{
      const label=fact.querySelector('dt')!.getBoundingClientRect();
      const value=fact.querySelector('dd')!.getBoundingClientRect();
      return value.top>=label.bottom && value.right<=fact.getBoundingClientRect().right+1;
    }))).toBe(true);
    await page.screenshot({path:`test-results/firmware-health-${width}.png`,fullPage:true});
  }
  await page.getByRole("button",{name:"Review upgrades",exact:true}).click();
  await expect(dialog.getByRole("button",{name:"Save upgrade review"})).toBeEnabled();
  await expect(dialog.getByRole("button",{name:"Install automatically"})).toBeDisabled();
  await expect(dialog.getByRole("link",{name:"Open this server's iLO"})).toHaveAttribute("href","https://192.0.2.10/");
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:950});
    expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    await page.screenshot({path:`test-results/firmware-upgrade-${width}.png`,fullPage:true});
  }
  await dialog.getByRole("button",{name:"Save upgrade review"}).click();
  await expect(dialog.getByText("Review saved. No firmware installation approved or started.")).toBeVisible();
  expect(writes).toEqual(["/api/v1/rack-plans/fixture-kit/health-acknowledgements","/api/v1/rack-plans/fixture-kit/firmware-upgrade-review"]);
});
