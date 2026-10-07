import {test,expect} from "@playwright/test";

for(const unsupported of [false,true]) test(unsupported?"unsupported Gen11 still explains erase choices":"method selection requests a new review without writing hardware",async({page})=>{
  const methods:string[]=[];
  const catalog={models:[unsupported?"ProLiant DL380 Gen11":"ProLiant DL360 Gen10 Plus"],controllers:["Fixture controller"],current:true,
    options:[
      {id:"auto",label:"Choose by drive type",selectable:!unsupported,status:unsupported?"Unavailable":"Review required",speed:"Duration varies.",protection:"Device sanitize.",reason:unsupported?"Execution adapter not implemented.":"Support approval required."},
      {id:"OnePass",label:"Single-pass overwrite",selectable:!unsupported,status:unsupported?"Unavailable":"Review required",speed:"Can take hours.",protection:"Not a purge.",reason:unsupported?"Execution adapter not implemented.":"Support approval required."},
      {id:"crypto",label:"Cryptographic erase",selectable:false,status:"Not implemented",speed:"Potentially fast.",protection:"Requires encryption coverage.",reason:"Encryption prerequisites unverified."},
    ],reset:{label:"Reset RAID for reuse",speed:"Fast",protection:"NOT secure erasure.",reason:"No arrays remain."}};
  await page.route("**/api/v1/**",route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith("/erase-options"))return route.fulfill({json:catalog});
    if(!path.endsWith("/preview"))throw Error("Unexpected write or API request: "+path);
    const method=route.request().postDataJSON().erase_pattern;
    methods.push(method);
    if(unsupported)return route.fulfill({status:409,json:{detail:"Gen11/RDE is not supported by this executor."}});
    return route.fulfill({json:{preview_id:"a".repeat(36),name:"Fixture",host:"192.0.2.10",controller:"Fixture controller",
      operation:"sanitize",erase_pattern:method,erase_options:catalog,power:"Off",arrays_present:false,drives:[],authorization_expires_at:new Date(Date.now()+86400000).toISOString(),
      blockers:["Method approval required."],warnings:[],volumes:[],empty_bays:[],apply_enabled:false,
      confirmation:"ERASE ALL 0 DISKS Fixture",method:"PATCH",path:"/settings",payload:{}}});
  });
  await page.route("**/options-fixture",r=>r.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/diskSanitizationHarness.tsx');</script></body></html>`}));
  await page.goto("/options-fixture");
  await page.getByRole("button",{name:"Review all disks for erasure"}).click();
  const dialog=page.getByRole("dialog");
  await expect(dialog.getByRole("radio",{name:/Cryptographic erase/})).toBeDisabled();
  const onePass=dialog.getByRole("radio",{name:/Single-pass overwrite/});
  if(unsupported){
    await expect(onePass).toBeDisabled();
    await expect(dialog.getByText(/Gen11\/RDE is not supported/)).toBeVisible();
  }else{
    await onePass.click();
    expect(methods).toEqual(["auto"]);
    await expect(onePass).toBeChecked();
    await dialog.getByRole("button",{name:"Next",exact:true}).click();
    await expect.poll(()=>methods).toEqual(["auto","OnePass"]);
    await dialog.getByRole("button",{name:"Retry checks",exact:true}).click();
    await expect.poll(()=>methods).toEqual(["auto","OnePass","OnePass"]);
    await dialog.getByRole("button",{name:"Back",exact:true}).click();
    await expect(onePass).toBeChecked();
  }
  for(const width of [1440,390,320]){
    await page.setViewportSize({width,height:950});
    expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    await page.screenshot({path:`test-results/erase-options-${unsupported}-${width}.png`});
  }
});
