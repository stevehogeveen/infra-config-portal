// Walks the briefing like a person would, against the simulated kit, and photographs it.
// Run from app/frontend (for playwright): node ../../kit-pilot/walkthrough.mjs <kit pilot url> <out dir>
import { chromium } from "playwright";
const [url, out] = [process.argv[2], process.argv[3]];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 860 } });
page.on("pageerror", e => console.log("pageerror:", e.message));
const ready = () => page.locator('#ask[data-ready="1"]').waitFor({ timeout: 20000 });
const chip = async name => { const b = page.getByRole("button", { name, exact: false }).first(); await b.waitFor({ timeout: 20000 }); await page.waitForTimeout(300); await b.click(); };
const fill = async (pairs) => { await ready(); for (const [id, value] of pairs) { const el = page.locator("#f-" + id); await el.waitFor({ timeout: 20000 }); if (await el.evaluate(e => e.tagName) === "SELECT") await el.selectOption(value); else await el.fill(value); } await page.locator("#ask button").click(); };
const type = async text => { await ready(); await page.locator("#text").fill(text); await page.locator("#ask button").click(); };
let shot = 0; const snap = async name => { await page.waitForTimeout(900); await page.screenshot({ path: `${out}/brief-${++shot}-${name}.png` }); };

await page.goto(url + "/briefing");
await chip("A server and a switch"); await snap("start");
await fill([["server_name", "HPE DL360 1"], ["server_model", "HPE DL360 Gen10"], ["switch_name", "Cisco switch 1"], ["switch_ports", "24"]]);
await chip("Change it");  // network: the practice kit has one; change it to exercise the questions
await type("192.0.2.0/27");
await fill([["name", "Lab kit A"], ["gateway", "192.0.2.1"], ["dns", "192.0.2.53"], ["domain", "lab.test"]]);
await fill([["host", "192.0.2.10"], ["username", "Administrator"], ["password", "Practice-Tag-1"]]); await snap("ilo");
await chip("Yes, it's plugged in");
await chip("COM5"); await snap("switch-read");
await fill([["hostname", "lab-sw01"], ["domain", "lab.test"], ["vlan", "100"], ["mode", "dhcp"], ["username", "admin"], ["password", "Practice-Sw-1"]]);
await fill([["hostname", "esx01"], ["addressing", "dhcp"], ["datastore_name", "VMdata"], ["root_password", "Practice-Root-1"], ["iso", "esxi-8.iso"]]);
await fill([["image", "win2022.ova"], ["vm_name", "windows01"], ["username", "Administrator"], ["password", "Practice-Win-1"]]);
await page.getByRole("button", { name: "Go to the flight board" }).waitFor({ timeout: 20000 }); await snap("summary");
const log = await page.locator("#log").innerText();
console.log(log.includes("That's the briefing") ? "briefing reached the summary" : "briefing did NOT reach the summary");
console.log(log.split("\n").filter(l => /didn't save|Couldn't|isn't|need/.test(l)).join("\n") || "no complaints along the way");
await browser.close();
