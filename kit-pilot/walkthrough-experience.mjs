// Run a copy from app/frontend so Playwright resolves there. Simulated kit only.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
const url = process.argv[2] || 'http://127.0.0.1:7790';
const browser = await chromium.launch();
const page = await browser.newPage({viewport:{width:1200,height:860}});
const errors = []; page.on('pageerror', e => errors.push(e.message));
const chip = async name => { console.log('answer:',name); await page.getByRole('button',{name,exact:true}).click({timeout:25000}); };
const fill = async values => { console.log('fill:',Object.keys(values).join(','));
  for (const [id,value] of Object.entries(values)) {
    const el = page.locator('#f-'+id); await el.waitFor({timeout:25000});
    if (await el.evaluate(e=>e.tagName) === 'SELECT') await el.selectOption(value); else await el.fill(value);
  }
  await page.locator('#ask button').click();
};
const text = async value => { await page.locator('#ask[data-ready="1"]').waitFor({timeout:25000}); await page.locator('#text').fill(value); await page.locator('#ask button').click(); };
const summary = () => page.getByRole('button',{name:'Go to the flight board',exact:true}).waitFor({timeout:25000});
try {
  await page.goto(url+'/briefing');
  await page.waitForTimeout(2400);
  const change = page.getByRole('button',{name:'Change it',exact:true}); if(await change.isVisible()) await change.click();
  await chip('A server and a switch');
  await fill({server_name:'Practice server',server_model:'HPE DL360 Gen10',switch_name:'Practice switch',switch_ports:'24'});
  await chip('Change it'); await text('192.0.2.0/27');
  await fill({name:'Practice kit (simulated)',gateway:'192.0.2.1',dns:'192.0.2.53',domain:'lab.test'});
  await page.waitForTimeout(2500);
  const sign = page.getByRole('button',{name:'Change the sign-in first',exact:true}); if(await sign.isVisible()) await sign.click();
  await page.getByRole('button',{name:/^(I have the address|Use 192.0.2.10)$/}).click();
  await fill({host:'192.0.2.10',username:'Administrator',password:'Practice-Tag-1'});
  await chip("Yes, it's plugged in");
  await page.getByRole('button',{name:/COM5/}).click();
  await fill({hostname:'lab-sw01',domain:'lab.test',vlan:'1',mode:'dhcp',username:'admin',password:'Practice-Sw-1'});
  await fill({hostname:'esx01',addressing:'dhcp',datastore_name:'VMdata',root_password:'Practice-Root-1',iso:'esxi-8.iso'});
  // Leave an unsaved non-secret answer and a password, then refresh the same tab.
  await page.locator('#f-vm_name').waitFor({timeout:25000});
  await page.locator('#f-vm_name').fill('draft-windows');
  await page.locator('#f-password').fill('Never-Store-This');
  const stored = await page.evaluate(()=>JSON.stringify(sessionStorage));
  assert(!stored.includes('Never-Store-This') && !stored.includes('Practice-Root-1') && !stored.includes('Practice-Tag-1'));
  await page.reload(); await page.locator('#f-vm_name').waitFor({timeout:25000});
  assert.equal(await page.locator('#f-vm_name').inputValue(),'draft-windows');
  assert.equal(await page.locator('#f-password').inputValue(),'');
  await fill({image:'win2022.ova',vm_name:'windows01',username:'Administrator',password:'Practice-Win-1'});
  await page.getByRole('button',{name:/^(Replace them with the plan|Update firmware this run)$/}).first().waitFor({timeout:25000});
  const initialReplace = page.getByRole('button',{name:'Replace them with the plan',exact:true}); if(await initialReplace.isVisible()) await initialReplace.click();
  await chip('Update firmware this run'); await chip('Skip the proof this run'); await summary();
  for (const label of ['network','server sign-in','switch','ESXi','Windows','options']) assert(await page.getByRole('button',{name:'Change '+label,exact:true}).isVisible());
  // Every edit returns directly to summary, without re-running unrelated questions.
  await chip('Change network'); await text('192.0.2.0/27'); await fill({name:'Edited practice kit',gateway:'192.0.2.1',dns:'192.0.2.53',domain:'lab.test'}); await summary();
  await chip('Change server sign-in'); await page.getByRole('button',{name:'Use 192.0.2.10',exact:true}).click(); await fill({host:'192.0.2.10',username:'Administrator',password:''}); await summary();
  await chip('Change switch'); await chip('Not yet'); await fill({hostname:'lab-sw02',domain:'lab.test',vlan:'1',mode:'dhcp',username:'admin',password:''}); await summary();
  await chip('Change ESXi'); await fill({hostname:'esx02',addressing:'dhcp',datastore_name:'VMdata',root_password:'',iso:'esxi-8.iso'}); await summary();
  await chip('Change Windows'); await fill({image:'win2022.ova',vm_name:'windows02',username:'Administrator',password:''}); await summary();
  await chip('Change options');
  const replace = page.getByRole('button',{name:'Replace them with the plan',exact:true});
  await page.getByRole('button',{name:/^(Replace them with the plan|Update firmware this run)$/}).first().waitFor({timeout:25000}); if(await replace.isVisible()) await replace.click();
  await chip('Update firmware this run'); await chip('Skip the proof this run'); await summary();
  await page.reload(); await summary();
  assert((await page.locator('#log').innerText()).includes('windows02'));
  await page.screenshot({path:process.argv[3]+'/briefing-summary.png'});
  await chip('Go to the flight board');
  await page.waitForURL(url+'/');
  // A completed demo shows Open report, so use the same Check action to start a fresh review.
  await page.request.post(url+'/do',{data:{action:'check'}}); await page.reload(); await chip('Build'); await page.locator('#approve').waitFor({timeout:15000});
  assert((await page.locator('#unknowns').innerText()).includes('switch address arrives from DHCP'));
  assert((await page.locator('#unknowns').innerText()).includes('restart proof is skipped by choice'));
  await page.screenshot({path:process.argv[3]+'/approval-unknowns.png',fullPage:true});
  await page.locator('#understood').check(); await chip('Approve and build');
  await page.getByRole('button',{name:'Open report',exact:true}).waitFor({timeout:90000});
  assert((await page.locator('#say').innerText()).includes('Windows proof was skipped'));
  assert((await page.locator('#board').innerText()).includes('skipped by choice'));
  assert((await page.locator('#timeline').innerText()).includes('started'));
  assert((await page.locator('#freshness').innerText()).includes('last progress'));
  const report = await (await page.request.get(url+'/report')).text();
  assert(report.includes('Flight log') && report.includes('skipped by choice'));
  assert(!report.includes('Prove it works \u00b7 already done'));
  await page.screenshot({path:process.argv[3]+'/flight-finished.png'});
  assert.deepEqual(errors,[]);
  console.log('PASS: briefing, all six summary edits, refresh recovery, no stored passwords, approval unknowns, scoped completion and report timeline');
} catch (err) { console.log("BROWSER ERRORS", errors); console.log(await page.locator("body").innerText()); throw err; } finally { await browser.close(); }
