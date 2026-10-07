import {test,expect} from '@playwright/test';

test('shutdown requires a separate confirmation and never forces automatically',async({page})=>{
  let writes=0,reads=0;
  await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/shutdown-preview')){
      const force=route.request().postDataJSON().force;
      return route.fulfill({json:{preview_id:'a'.repeat(36),name:'Fixture server',force,confirmation:force?'FORCE POWER OFF Fixture server':'SHUT DOWN Fixture server',blockers:force?['Allow at least two minutes for shutdown.']:[],apply_enabled:!force,payload:{ResetType:force?'ForceOff':'PushPowerButton'}}});
    }
    if(path.endsWith('/shutdown')){writes++;expect(route.request().postDataJSON()).toMatchObject({confirmation:'SHUT DOWN Fixture server',downtime_confirmed:true,data_loss_confirmed:true});return route.fulfill({json:{message:'Shutdown requested. Read the power state.'}});}
    if(path.endsWith('/power-state')){reads++;return route.fulfill({json:{power:reads===1?'On':'Off',pending_changes:false}});}
    throw Error('Unexpected request '+path);
  });
  await page.route('**/shutdown-fixture',r=>r.fulfill({contentType:'text/html',body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/shutdownHarness.tsx');</script></body></html>`}));
  await page.goto('/shutdown-fixture');
  await page.getByRole('button',{name:'Shut down server...',exact:true}).click();
  const send=page.getByRole('button',{name:'Send shutdown request'});
  await expect(send).toBeDisabled();
  await page.getByRole('checkbox').check();
  await page.getByLabel('Shutdown confirmation phrase').fill('SHUT DOWN Fixture server');
  for(const width of [1440,768,390,320]){
    await page.setViewportSize({width,height:950});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    const input=await page.getByLabel('Shutdown confirmation phrase').boundingBox();
    const button=await send.boundingBox();
    expect(button!.y).toBeGreaterThanOrEqual(input!.y+input!.height+12);
    await page.screenshot({path:`test-results/shutdown-${width}.png`,fullPage:true});
  }
  await send.click();
  await expect(page.getByText(/^Shutdown requested. Waiting for iLO to confirm power is off./)).toBeVisible();
  await expect(send).toHaveCount(0);
  expect(writes).toBe(1);
  await expect(page.getByRole('status',{name:'Observed server power'})).toContainText('Server power: On');
  // While it still reads On, a forced power-off can be reviewed, but never sent without its own confirmation.
  await page.getByText('Server still running?',{exact:true}).click();
  await page.getByRole('button',{name:'Review forced power-off'}).click();
  await expect(page.getByRole('button',{name:'Confirm forced power-off',exact:true})).toBeDisabled();
  await expect(page.getByText('Allow at least two minutes for shutdown.')).toBeVisible();
  // Monitoring keeps reading the power by itself and reports Off once the iLO does.
  await expect(page.getByRole('status',{name:'Observed server power'})).toContainText('Server power: Off',{timeout:20000});
  expect(reads).toBeGreaterThanOrEqual(2);
  expect(writes).toBe(1);
});
