import {test,expect} from "@playwright/test";

test("erase progress distinguishes staging, unknown progress and hardware evidence",async({page})=>{
  let status="staged", driveStatus="unverified";
  await page.route("**/api/v1/**",route=>{
    expect(route.request().method()).toBe("GET");
    expect(new URL(route.request().url()).pathname).toMatch(/raid-rebuild\/status$/);
    return route.fulfill({json:{status,operation:"sanitize",active:true,boot_blockers:[],
      message:"Fixture result",sanitization:{checked_at:new Date().toISOString(),drives:[
        {identity:"fixture",bay:"1",model:"Fixture disk",media:"HDD",status:driveStatus,erase_pattern:"OnePass"}
      ]}}});
  });
  await page.route("**/progress-fixture",r=>r.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
    import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/eraseProgressHarness.tsx');
  </script></body></html>`}));
  await page.goto("/progress-fixture");
  await expect(page.getByRole("heading",{name:"Wipe staged - start server next"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Start server and begin erasure"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Check every disk's erase result"})).toHaveCount(0);
  status="waiting";
  await page.reload();
  await expect(page.getByRole("heading",{name:"Waiting for the controller to confirm erasure"})).toBeVisible();
  driveStatus="erasing";
  await page.reload();
  await expect(page.getByRole("heading",{name:"Controller reports disk erasure in progress"})).toBeVisible();
  status="verified";driveStatus="completed";
  await page.reload();
  await expect(page.getByRole("heading",{name:"Disk erasure verified"})).toBeVisible();
});

test("drive progress shows actual percentages, unknown readings and a prominent rejection",async({page})=>{
  let stale=false, readFailure=false;
  const statuses=['erasing','erasing','queued','completed','failed','unverified'];
  const data=()=>({status:'needs_attention',operation:'sanitize',active:true,message:'Fixture rejection',boot_blockers:[],
    sanitization:{power:'On',checked_at:new Date(Date.now()-(stale?180000:0)).toISOString(),controller_errors:['SmartStorageMessages.2.0.1.PropertyValueEnumNotInList'],drives:statuses.map((status,i)=>({
      identity:`disk-${i}`,bay:`1I:1:${i+1}`,model:'Fixture HDD',media:'HDD',capacity_bytes:300e9,erase_pattern:'OnePass',status,percent:i===0?33:i===3?100:null
    }))}});
  await page.route('**/api/v1/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/status'))return route.fulfill({json:data()});
    expect(path).toMatch(/\/verify$/);
    readFailure=true;
    return route.fulfill({status:503,json:{detail:'Fixture iLO unavailable'}});
  });
  await page.route('**/progress-fixture',r=>r.fulfill({contentType:'text/html',body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
    import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/eraseProgressHarness.tsx');
  </script></body></html>`}));
  await page.goto('/progress-fixture');
  const progress=page.getByRole('region',{name:'Disk wipe progress'});
  await expect(progress.getByText('1 of 6 disks verified')).toBeVisible();
  await expect(progress.getByRole('alert')).toContainText('Controller rejected an erase setting');
  await expect(progress.getByRole('alert')).toContainText('Some disks still report active work');
  await expect(progress.getByRole('progressbar',{name:'Verified disks',exact:true})).toHaveAttribute('value','1');
  await expect(progress.getByRole('progressbar',{name:'Erase progress bay 1I:1:1',exact:true})).toHaveAttribute('value','33');
  await expect(progress.getByRole('progressbar',{name:'Erase progress bay 1I:1:2',exact:true})).not.toHaveAttribute('value');
  await expect(progress.getByText('Percentage not reported by controller.')).toBeVisible();
  await expect(progress.getByRole('progressbar',{name:'Erase progress bay 1I:1:6',exact:true})).toHaveCount(0);
  await expect(progress.getByText('Power at last check: On')).toBeVisible();
  for(const width of [1440,768,390,320]){
    await page.setViewportSize({width,height:1000});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
    await page.screenshot({path:`test-results/drive-progress-${width}.png`,fullPage:true});
  }
  stale=true;
  await page.reload();
  await expect(progress.getByText(/Reading is 3 min old/)).toBeVisible();
  await expect(progress.getByText('Last reported: erasing')).toHaveCount(2);
  await expect(progress.getByRole('progressbar',{name:'Erase progress bay 1I:1:2',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:"Check every disk's erase result"}).click();
  await expect(progress.getByText(/Live update unavailable/)).toBeVisible();
  expect(readFailure).toBe(true);
});

test("staged wipe lists every planned disk without inventing activity",async({page})=>{
  await page.route('**/api/v1/**',route=>{
    expect(new URL(route.request().url()).pathname).toMatch(/\/status$/);
    return route.fulfill({json:{status:'staged',operation:'sanitize',active:true,message:'Staged only',boot_blockers:[],sanitization:null,
      erase_scope:[1,2].map(i=>({identity:`disk-${i}`,bay:String(i),model:'Fixture disk',media:'HDD',capacity_bytes:300e9,erase_pattern:'OnePass'}))}});
  });
  await page.route('**/progress-fixture',r=>r.fulfill({contentType:'text/html',body:`<html><body><div id="root"></div><script type="module">
    import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/eraseProgressHarness.tsx');
  </script></body></html>`}));
  await page.goto('/progress-fixture');
  const progress=page.getByRole('region',{name:'Disk wipe progress'});
  await expect(progress.getByText('0 of 2 disks verified')).toBeVisible();
  await expect(progress.getByText('Awaiting power-on',{exact:true})).toHaveCount(2);
  await expect(progress.getByText('Power at last check: Not read')).toBeVisible();
  await expect(progress.getByRole('progressbar')).toHaveCount(1);
  await expect(progress.getByText('Waiting for your power-on confirmation. Erasure has not been verified.')).toBeVisible();
});

test("partial erase keeps polling but rejection with no active disks stops automatic checks",async({page})=>{
  let checks=0;
  const bootStartedAt=new Date().toISOString();
  await page.clock.install();
  const result=()=>({status:'needs_attention',operation:'sanitize',active:true,message:'Fixture controller error',
    boot_started_at:bootStartedAt,sanitization:{checked_at:new Date().toISOString(),controller_errors:['Fixture.Error'],drives:[
      {identity:'disk',bay:'1',model:'Fixture disk',media:'HDD',status:checks<2?'erasing':'unverified',erase_pattern:'OnePass'}
    ]}});
  await page.route('**/api/v1/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/status'))return route.fulfill({json:result()});
    expect(path).toMatch(/\/verify$/);
    checks++;
    return route.fulfill({json:{status:'needs_attention',verified:false,message:'Fixture controller error'}});
  });
  await page.route('**/progress-fixture',r=>r.fulfill({contentType:'text/html',body:`<html><body><div id="root"></div><script type="module">
    import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/eraseProgressHarness.tsx');
  </script></body></html>`}));
  await page.goto('/progress-fixture');
  await expect(page.getByText('Automatic disk checks are running while this page is open.')).toBeVisible();
  await page.clock.runFor(1200);
  await expect.poll(()=>checks).toBe(1);
  await expect(page.getByRole('button',{name:"Check every disk's erase result"})).toHaveCount(0);
  await expect(page.getByText('Automatic disk checks are running while this page is open.')).toBeVisible();
  await page.clock.runFor(16000);
  await expect.poll(()=>checks).toBe(2);
  await expect(page.getByRole('button',{name:"Check every disk's erase result"})).toBeEnabled();
  await page.clock.runFor(30000);
  expect(checks).toBe(2);
});

test("confirmed rejection offers preparation without sending another command",async({page})=>{
  await page.route('**/api/v1/**',route=>{
    expect(route.request().method()).toBe('GET');
    expect(new URL(route.request().url()).pathname).toMatch(/\/status$/);
    return route.fulfill({json:{status:'failed',operation:'sanitize',active:false,
      message:'Rejected method',erase_recovery:{rejected_method:'OnePass',message:'OnePass was rejected. Choose a different method.'},
      sanitization:{checked_at:new Date().toISOString(),drives:[]}}});
  });
  await page.route('**/progress-fixture',r=>r.fulfill({contentType:'text/html',body:`<html><body><div id="root"></div><script type="module">
    import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    await import('/tests/fixtures/eraseProgressHarness.tsx');
  </script></body></html>`}));
  await page.goto('/progress-fixture');
  await expect(page.getByText('Choose a different erase method',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Set up another wipe attempt'}).click();
  await expect(page.locator('body')).toHaveAttribute('data-retry-opened','true');
  await expect(page.getByRole('button',{name:'Start server and begin erasure'})).toHaveCount(0);
});
