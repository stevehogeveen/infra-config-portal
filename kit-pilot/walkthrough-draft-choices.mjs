import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch(); const page=await browser.newPage();
const url=process.argv[2] || 'http://127.0.0.1:7791';
try {
  await page.addInitScript(()=>{if(!sessionStorage.getItem('kit-pilot:briefing:fixture')) sessionStorage.setItem('kit-pilot:briefing:fixture',JSON.stringify({step:'summary'}));});
  await page.goto(url+'/briefing');
  await page.getByRole('button',{name:'Change options',exact:true}).click();
  const first=page.getByRole('button',{name:/^(Replace them with the plan|Update firmware this run)$/}).first(); await first.waitFor();
  const replace=page.getByRole('button',{name:'Replace them with the plan',exact:true}); if(await replace.isVisible()) await replace.click();
  await page.getByRole('button',{name:'Skip firmware this run',exact:true}).click();
  await page.getByRole('button',{name:'Skip the proof this run',exact:true}).waitFor();
  await page.reload(); await first.waitFor(); if(await replace.isVisible()) {assert.equal(await replace.getAttribute('aria-pressed'),'true'); await replace.click();}
  const skip=page.getByRole('button',{name:'Skip firmware this run',exact:true}); await skip.waitFor(); assert.equal(await skip.getAttribute('aria-pressed'),'true');
  await skip.click(); await page.getByRole('button',{name:'Skip the proof this run',exact:true}).click();
  await page.getByRole('button',{name:'Go to the flight board',exact:true}).waitFor();
  console.log('PASS: non-secret option choices survive refresh and return to summary');
} finally {await browser.close();}
