import { expect, test } from "@playwright/test";

test("browse mounted media, inspect package, retain selection and explain validation", async ({page}) => {
  let selected: any = null;
  let reads = 0;
  let posts = 0;
  let reject = true;
  await page.route("**/api/**", route => {
    const request = route.request();
    expect(new URL(request.url()).pathname).toBe("/api/v1/rack-plans/fixture-kit/firmware-package");
    if (request.method()==="POST") {
      posts++;
      expect(request.postDataJSON()).toEqual({path:"SPP/fixture.iso"});
      if(reject) return route.fulfill({status:422,json:{detail:"ISO is incomplete. Wait for the copy to finish."}});
      selected = {path:"SPP/fixture.iso",file_name:"fixture.iso",size_bytes:4096,modified_ns:"123",volume_label:"SPP_FIXTURE",release_hint:null,generation_hints:[],manifest_files:["/PACKAGES/BP000001.XML;1"],status:"ISO readable; compatibility unverified",validation_note:"No installation is enabled."};
      return route.fulfill({json:selected});
    }
    reads++;
    const folder = new URL(request.url()).searchParams.get("folder") || "";
    return route.fulfill({json:{root:"/workspace/artifacts/Media",host_root:"C:\\LabBuilder\\artifacts\\Media",folder,folders:folder?[]:[{name:"SPP",path:"SPP"}],files:folder?[{name:"fixture.iso",path:"SPP/fixture.iso",size_bytes:4096}]:[],warning:null,selected,selection_current:!!selected}});
  });
  await page.route("**/package-fixture",route=>route.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script type="module">
    import RefreshRuntime from '/@react-refresh'; RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$=()=>{}; window.$RefreshSig$=()=>(type)=>type; window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/firmwarePackageHarness.tsx');</script></body></html>`}));
  await page.goto("/package-fixture");
  await page.getByText("Media folder and Docker settings",{exact:true}).click();
  await expect(page.getByText("C:\\LabBuilder\\artifacts\\Media",{exact:true})).toBeVisible();
  await expect(page.getByRole("link",{name:"Get HPE SPP"})).toHaveAttribute("href",/support\.hpe\.com\/hpesc\/public\/docDisplay/);
  expect(posts).toBe(0);
  await page.getByRole("button",{name:"SPP",exact:true}).click();
  await page.getByLabel("ISO package").selectOption("SPP/fixture.iso");
  await page.getByRole("button",{name:"Inspect and select package"}).click();
  await expect(page.getByRole("alert")).toContainText("ISO is incomplete");
  reject=false;
  await page.getByRole("button",{name:"Inspect and select package"}).click();
  await expect(page.getByText("Server-specific comparison results are below.",{exact:true})).toBeVisible();
  for(const width of [1440,390]) {
    await page.setViewportSize({width,height:1000});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:`test-results/firmware-package-${width}.png`,fullPage:true});
  }
  await page.reload();
  await expect(page.getByText("Selected package: fixture.iso",{exact:true})).toBeVisible();
  expect(posts).toBe(2);
  expect(reads).toBeGreaterThanOrEqual(3);
});

test("dragging an ISO uploads bytes, refreshes files and never selects it automatically", async ({page}) => {
  let uploaded=false;
  let uploads=0;
  await page.route("**/api/**", route=>{
    const request=route.request();
    const url=new URL(request.url());
    if(url.pathname.endsWith("/media-upload")) {
      expect(request.method()).toBe("POST");
      expect(url.searchParams.get("name")).toBe("dropped.iso");
      expect(url.searchParams.get("size")).toBe("7");
      expect(request.postData()).toBe("fixture");
      uploaded=true;uploads++;
      return route.fulfill({status:201,json:{name:"dropped.iso",path:"dropped.iso",size_bytes:7}});
    }
    expect(request.method()).toBe("GET");
    return route.fulfill({json:{root:"/media",host_root:"C:\\Media",folder:"",folders:[],files:uploaded?[{name:"dropped.iso",path:"dropped.iso",size_bytes:7}]:[],warning:null,selected:null,selection_current:false}});
  });
  await page.route("**/package-fixture",route=>route.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script type="module">
    import RefreshRuntime from '/@react-refresh'; RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$=()=>{}; window.$RefreshSig$=()=>(type)=>type; window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/firmwarePackageHarness.tsx');</script></body></html>`}));
  await page.goto("/package-fixture");
  await expect(page.getByRole("button",{name:"Choose ISO file"})).toBeEnabled();
  const dataTransfer=await page.evaluateHandle(()=>{const data=new DataTransfer();data.items.add(new File(["fixture"],"dropped.iso",{type:"application/octet-stream"}));return data;});
  await page.locator(".media-drop-zone").dispatchEvent("drop",{dataTransfer});
  await expect(page.getByText("dropped.iso uploaded. Select it below to inspect it.")).toBeVisible();
  await expect(page.getByLabel("ISO package")).toHaveValue("");
  expect(uploads).toBe(1);
  await page.getByLabel("Upload ISO file").setInputFiles({name:"wrong.exe",mimeType:"application/octet-stream",buffer:Buffer.from("fixture")});
  await expect(page.getByRole("alert")).toContainText("Choose an ISO file");
  expect(uploads).toBe(1);
  for(const width of [1440,390]) {
    await page.setViewportSize({width,height:1000});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:`test-results/media-drop-${width}.png`,fullPage:true});
  }
});
