import {test,expect,type Page} from "@playwright/test";

// Connect is connection only; disks and RAID share one page with a picture of each server's bays.
const html=(entry:string)=>`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;await import('/tests/fixtures/${entry}');</script></body></html>`;
const planJson={revision:1,rack_units:12,equipment:["s","other"].map((id,index)=>({id,device_id:id,name:index?"Second server":"Test server",kind:"server",model:"HPE DL360",position:index+1,height:1,mount:"rack",ports:0,bay_count:10,occupied_bays:[]}))};
async function openSteps(page:Page,path:"/disks-fixture"|"/raid-fixture"){
  await page.route(/\/(disks|raid)-fixture$/,r=>r.fulfill({contentType:"text/html",body:html("storageStepsHarness.tsx")}));
  await page.goto(path);
}

test("connect has no drives tab and points to firmware next",async({page})=>{
  await page.route("**/api/**",route=>{
    const url=new URL(route.request().url());
    if(url.pathname.endsWith("access-settings"))return route.fulfill({json:{host:"192.0.2.10",username:"fixture",username_configured:true,password_configured:true,verify_tls:true}});
    return route.fulfill({status:404,json:{}});
  });
  await page.route("**/connection-storage-fixture",r=>r.fulfill({contentType:"text/html",body:html("connectionStorageHarness.tsx")}));
  await page.goto("/connection-storage-fixture");
  await expect(page.getByText("Password saved securely")).toBeVisible();
  await expect(page.getByRole("tab")).toHaveCount(0);
  await expect(page.getByRole("region",{name:"Drives and RAID"})).toHaveCount(0);
  await expect(page.getByRole("link",{name:"Preview the next step: firmware"})).toHaveAttribute("href",/\/setup\/check-firmware\?device=s/);
});

test("disks & raid: a running erase shows on the server card and opens its progress",async({page})=>{
  await page.route("**/api/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==="/api/v1/rack-plans/fixture")return route.fulfill({json:{...planJson,equipment:planJson.equipment.slice(0,1)}});
    if(path.endsWith('/status'))return route.fulfill({json:{status:'waiting',active:true,operation:'sanitize',
      boot_started_at:new Date().toISOString(),message:'Waiting',sanitization:{checked_at:new Date().toISOString(),drives:[]}}});
    if(path.endsWith('/verify'))return route.fulfill({json:{status:'unverified',verified:false,message:'Reading'}});
    expect(path).toMatch(/\/disk-preparation$/);
    return route.fulfill({json:{current:false,drives:[],controllers:[],volumes:[],blockers:[],health_issues:[],saved_intent:{volumes:[]}}});
  });
  await openSteps(page,"/disks-fixture");
  const card=page.getByRole("article",{name:"Test server"});
  await expect(card).toContainText("Disks are being erased");
  await card.getByRole("button",{name:"See progress"}).click();
  // It reopens the wipe installer where it left off, watching and sending nothing new.
  const box=page.getByRole("dialog",{name:"Wipe disks on Test server"});
  await expect(box.getByRole("heading",{name:"Erasing the disks…"})).toBeVisible();
  await expect(box.getByRole("button",{name:"Close (keeps going)"})).toBeVisible();
});

test("disks & raid: each server shows its bays and one decision: ready, erased, old RAID, or built",async({page})=>{
  const drive=(i:number,extra:any={})=>({id:`d${i}`,location:`1I:1:${i}`,model:"Fixture",capacity_bytes:300e9,media:"HDD",health:"OK",label:"OK",eligible:true,presence:"identified",...extra});
  const plan=[{bootable:true,raid_level:"RAID1",drive_bays:["1I:1:1","1I:1:2"],spare_bays:[]},{bootable:false,raid_level:"RAID5",drive_bays:["1I:1:3","1I:1:4","1I:1:5"],spare_bays:["1I:1:6"]}];
  const names=["Test server","Second server","Third server","Fourth server"];
  await page.route("**/api/**",route=>{
    const url=new URL(route.request().url()),device=url.searchParams.get("device_id");
    if(url.pathname==="/api/v1/rack-plans/fixture")return route.fulfill({json:{...planJson,equipment:["s","other","third","fourth"].map((id,i)=>({...planJson.equipment[0],id,device_id:id,name:names[i],position:i+1}))}});
    if(url.pathname.endsWith("/status"))return route.fulfill({json:{status:"not_started",active:false,message:"No operation"}});
    const base={name:device,current:true,checked_at:new Date().toISOString(),controllers:[{id:"c",model:"Smart Array P408i-a",health:"OK",firmware:"1.66"}],blockers:[],health_issues:[],boot_mirror_matches:false,saved_intent:{volumes:plan,wipe_existing_logical_drives:false}};
    const six=[1,2,3,4,5,6];
    if(device==="s")return route.fulfill({json:{...base,drives:six.map(i=>drive(i)),volumes:[]}});
    if(device==="other")return route.fulfill({json:{...base,drives:six.map(i=>drive(i,i<3?{health:"Warning",label:"Erased",explanation:"EraseCompleted",eligible:false}:{})),volumes:[]}});
    if(device==="third")return route.fulfill({json:{...base,drives:six.map(i=>drive(i)),volumes:[{id:"v",name:"Logical drive 1",raid:"RAID0",capacity_bytes:1.2e12,bays:["1I:1:1","1I:1:2","1I:1:3","1I:1:4"]}]}});
    // A read too old to plan from: the page still draws it, marked as the last read.
    expect(url.pathname).toBe("/api/v1/rack-plans/fixture/disk-preparation");
    return route.fulfill({json:{...base,current:false,drives:[],volumes:[],last_read:{checked_at:new Date(Date.now()-3600e3).toISOString(),drives:six.map(i=>drive(i)),
      volumes:[{id:"a",name:"Logical drive 1",raid:"RAID1",capacity_bytes:300e9,bays:["1I:1:1","1I:1:2"]},{id:"b",name:"Logical drive 2",raid:"RAID5",capacity_bytes:600e9,bays:["1I:1:3","1I:1:4","1I:1:5"]}]}}});
  });
  await openSteps(page,"/disks-fixture");
  await expect(page.getByRole("heading",{name:"Disks & RAID"})).toBeVisible();
  const card=(name:string)=>page.getByRole("article",{name});
  await expect(card("Test server")).toContainText("Ready to build RAID");
  await expect(card("Test server").getByRole("button",{name:"Build RAID"})).toBeVisible();
  await expect(card("Test server").getByRole("listitem",{name:"Bay 1: Ready, planned Boot disks"})).toBeVisible();
  await expect(card("Test server").getByRole("listitem",{name:"Bay 6: Ready, planned Spare"})).toBeVisible();
  await expect(card("Test server")).toContainText("can't look inside a disk that isn't in RAID");
  await expect(card("Second server")).toContainText("2 disks were securely erased");
  await expect(card("Second server").getByRole("button",{name:"Start re-enable guide"})).toBeVisible();
  await expect(card("Second server").getByRole("listitem",{name:"Bay 1: Erased, planned Boot disks"})).toBeVisible();
  await expect(card("Third server")).toContainText("already have RAID on them");
  await expect(card("Third server").getByRole("button",{name:"Wipe disks"})).toBeVisible();
  await expect(card("Third server").getByRole("listitem",{name:"Bay 4: In RAID (RAID0), planned VM storage"})).toBeVisible();
  await expect(card("Third server")).toContainText("Treat it as holding data");
  await expect(card("Fourth server")).toContainText("RAID is built as planned");
  await expect(card("Fourth server").getByRole("button",{name:"View disks"})).toBeVisible();
  await expect(card("Fourth server")).toContainText("last read");
  await expect(page.getByText("1 of 4 servers have RAID built")).toBeVisible();
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:950});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  }
});

test("disks & raid: the RAID plan editor shows the current setup, paints bays with jobs and saves only the plan",async({page})=>{
  let saved:any=null;const sent:string[]=[];
  const bays=["1I:1:1","1I:1:2","2I:1:5","2I:1:6","2I:1:7","2I:1:8"];
  const drives=bays.map((location,i)=>({id:`drive-${i}`,location,model:"Fixture SAS drive",media:"HDD",capacity_bytes:i<2?300e9:1.2e12,health:"OK",label:"OK",eligible:true}));
  await page.route("**/api/**",route=>{
    const req=route.request(),url=new URL(req.url());
    if(req.method()!=="GET")sent.push(url.pathname.replace(/^.*\/(providers\/ilo-redfish|rack-plans\/fixture)\//,""));
    if(url.pathname==="/api/v1/rack-plans/fixture")return route.fulfill({json:{...planJson,equipment:planJson.equipment.slice(0,1)}});
    if(url.pathname.endsWith('/raid-rebuild/status'))return route.fulfill({json:{status:'not_started',active:false,message:'No operation'}});
    if(url.pathname.endsWith("/probe"))return route.fulfill({json:{status:"ok",warnings:[],blockers:[]}});
    expect(url.pathname).toBe("/api/v1/rack-plans/fixture/disk-preparation");
    if(req.method()==="POST"){saved=req.postDataJSON();return route.fulfill({json:{message:"No disks changed. Plan saved."}});}
    const bayOf=(id:string)=>drives.find(d=>d.id===id)!.location;
    const intent=saved?[{bootable:true,raid_level:"RAID1",drive_bays:saved.boot_drive_ids.map(bayOf),spare_bays:saved.spare_for==="boot"?saved.spare_drive_ids.map(bayOf):[]},
      ...(saved.data_drive_ids.length?[{bootable:false,raid_level:saved.data_raid,drive_bays:saved.data_drive_ids.map(bayOf),spare_bays:saved.spare_for==="data"?saved.spare_drive_ids.map(bayOf):[]}]:[])]:[];
    return route.fulfill({json:{name:"Test server",current:true,checked_at:new Date().toISOString(),inventory_token:"a".repeat(64),drives,controllers:[{id:"c",model:"Smart Array",health:"OK",firmware:"1.66"}],
      volumes:[{id:"v",name:"Logical drive 1",raid:"RAID0",capacity_bytes:600e9,bays:["1I:1:1","1I:1:2"]}],blockers:[],health_issues:[],saved_intent:{volumes:intent,wipe_existing_logical_drives:false}}});
  });
  await openSteps(page,"/raid-fixture");
  const card=page.getByRole("article",{name:"Test server"});
  await card.getByRole("button",{name:"Plan RAID"}).click();
  const editor=page.getByRole("dialog",{name:"RAID plan on Test server"});
  // The current setup is shown first: what is on the disks and what plan is saved.
  await expect(editor.getByRole("region",{name:"Current setup"})).toContainText("RAID 0 on bay 1, 2");
  await expect(editor.getByRole("region",{name:"Current setup"})).toContainText("No plan saved yet.");
  await expect(editor.getByRole("button",{name:"No changes"})).toBeDisabled();
  await editor.getByRole("button",{name:"Use recommended"}).click();
  await expect(editor.getByRole("button",{name:/^Bay 1: 300 GB HDD, Boot disks/})).toBeVisible();
  await expect(editor.getByRole("button",{name:/^Bay 8: 1.2 TB HDD, Spare/})).toBeVisible();
  await expect(editor).toContainText("3 disks · about 2.4 TB usable");
  // Repaint: take the spare off bay 8 and make it a datastore disk, then choose RAID 6.
  await editor.getByRole("radio",{name:/VM storage/}).click();
  await editor.getByRole("button",{name:/^Bay 8:/}).click();
  await expect(editor.getByRole("button",{name:/^Bay 8: 1.2 TB HDD, VM storage/})).toBeVisible();
  await editor.getByLabel("Datastore RAID level").selectOption("RAID6");
  await expect(editor).toContainText("4 disks · about 2.4 TB usable");
  // A broken plan explains itself and can't be saved.
  await editor.getByRole("radio",{name:/Boot disks/}).click();
  await editor.getByRole("button",{name:/^Bay 1:/}).click();
  await expect(editor.getByRole("alert")).toContainText("Pick exactly 2 disks for the boot mirror (1 picked).");
  await expect(editor.getByRole("button",{name:"Save plan"})).toBeDisabled();
  await editor.getByRole("button",{name:/^Bay 1:/}).click();
  await expect(editor).toContainText("The disks have RAID on them now. Saving marks it to be replaced");
  await expect(editor.getByRole("textbox")).toHaveCount(0);
  await editor.getByRole("button",{name:"Save plan"}).click();
  await expect(editor).toHaveCount(0);
  expect(saved).toMatchObject({boot_drive_ids:["drive-0","drive-1"],data_drive_ids:["drive-2","drive-3","drive-4","drive-5"],spare_drive_ids:[],data_raid:"RAID6",remove_existing_volumes:true,data_loss_reviewed:true});
  // Reading the disks is the only other request; nothing else is sent.
  expect(sent.filter(path=>path!=="probe")).toEqual(["disk-preparation"]);
  await card.getByRole("button",{name:"Change the RAID plan"}).click();
  await expect(page.getByRole("dialog",{name:"RAID plan on Test server"}).getByRole("region",{name:"Current setup"})).toContainText("VM storage RAID 6 bay 5, 6, 7, 8");
});

test("disks & raid: Read disks is a read-only check that redraws the bays", async ({ page }) => {
  let probed = false; const sent: string[] = [];
  await page.route("**/api/**", route => {
    const url = new URL(route.request().url());
    if (route.request().method() !== "GET") sent.push(url.pathname);
    if (url.pathname === "/api/v1/rack-plans/fixture") return route.fulfill({ json: { ...planJson, equipment: planJson.equipment.slice(0, 1) } });
    if (url.pathname.endsWith("/status")) return route.fulfill({ json: { status: "not_started", active: false, message: "No operation" } });
    if (url.pathname.endsWith("/probe")) { probed = true; return route.fulfill({ json: { status: "ok", warnings: [], blockers: [] } }); }
    expect(url.pathname).toBe("/api/v1/rack-plans/fixture/disk-preparation");
    return route.fulfill({ json: { name: "Test server", current: probed, checked_at: new Date().toISOString(), controllers: [], blockers: [], health_issues: [], volumes: [],
      saved_intent: { volumes: [], wipe_existing_logical_drives: false }, drives: probed ? [1, 4].map(i => ({ id: `d${i}`, location: `1I:1:${i}`, model: "Fixture", capacity_bytes: 300e9, health: "OK", eligible: true })) : [] } });
  });
  await openSteps(page, "/disks-fixture");
  const card = page.getByRole("article", { name: "Test server" });
  await expect(card).toContainText("Disks not read yet");
  await card.getByRole("button", { name: "Read disks" }).first().click();
  await expect(card.getByRole("listitem", { name: "Bay 4: Ready, not in plan" })).toBeVisible();
  // The iLO lists only occupied bays; the slots between them are drawn empty, nothing beyond.
  await expect(card.getByRole("listitem", { name: "Bay 2: Empty, not in plan" })).toBeVisible();
  await expect(card.getByRole("list", { name: "Drive bays" }).getByRole("listitem")).toHaveCount(4);
  await expect(card).toContainText("No RAID plan yet");
  expect(sent.map(path => path.replace(/^.*\/providers\//, ""))).toEqual(["ilo-redfish/probe"]);
});

test("disks & raid: erased disks open a hands-on guide that ends with a read-only check", async ({ page }) => {
  let reenabled = false; const sent: string[] = [];
  const drive = (i: number, erased: boolean) => ({ id: `d${i}`, location: `1I:1:${i}`, model: "Fixture", capacity_bytes: 300e9,
    ...(erased ? { health: "Warning", label: "Erased", explanation: "EraseCompleted", eligible: false } : { health: "OK", label: "OK", eligible: true }) });
  await page.route("**/api/**", route => {
    const url = new URL(route.request().url());
    if (route.request().method() !== "GET") sent.push(url.pathname);
    if (url.pathname === "/api/v1/rack-plans/fixture") return route.fulfill({ json: { ...planJson, equipment: planJson.equipment.slice(0, 1) } });
    if (url.pathname.endsWith("/status")) return route.fulfill({ json: { status: "not_started", active: false, message: "No operation" } });
    if (url.pathname.endsWith("access-settings")) return route.fulfill({ json: { host: "192.0.2.10", username_configured: true, password_configured: true } });
    if (url.pathname.endsWith("/probe")) { reenabled = true; return route.fulfill({ json: { status: "ok", warnings: [], blockers: [] } }); }
    expect(url.pathname).toBe("/api/v1/rack-plans/fixture/disk-preparation");
    return route.fulfill({ json: { name: "Test server", current: true, checked_at: new Date().toISOString(), controllers: [], blockers: [], health_issues: [], volumes: [],
      saved_intent: { volumes: [], wipe_existing_logical_drives: false }, drives: [1, 2].map(i => drive(i, !reenabled)) } });
  });
  await openSteps(page, "/disks-fixture");
  await page.getByRole("button", { name: "Start re-enable guide" }).click();
  const guide = page.getByRole("dialog", { name: "Re-enable erased disks on Test server" });
  await expect(guide.getByRole("link", { name: "Open the iLO web page" })).toHaveAttribute("href", "https://192.0.2.10");
  await guide.getByRole("button", { name: "Next" }).click();
  await expect(guide).toContainText("press F10");
  await guide.getByRole("button", { name: "Next" }).click();
  await expect(guide.getByRole("button", { name: "Next" })).toBeDisabled();
  for (const bay of ["1I:1:1", "1I:1:2"]) await guide.getByText(`Bay ${bay}`).click();
  await guide.getByRole("button", { name: "Next" }).click();
  await expect(guide.getByRole("heading", { name: "All disks are back in service" })).toBeVisible();
  await guide.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("article", { name: "Test server" })).toContainText("No RAID plan yet");
  expect(sent.filter(path => !path.endsWith("/probe"))).toEqual([]);
});

for (const power of ["Off", "On"] as const) test(`raid: Build RAID is one click in a centred installer (server ${power}); it watches by itself until the volumes read back`, async ({ page }) => {
  await page.clock.install();
  let raid: any = { status: "not_started", active: false, message: "No operation" }; let verifies = 0; let scope = "read_only"; let powered = power;
  const posts: string[] = [];
  const drives = ["1I:1:1", "1I:1:2", "2I:1:5", "2I:1:6", "2I:1:7", "2I:1:8"].map((location, i) => ({ id: `/redfish/v1/Systems/1/SmartStorage/ArrayControllers/0/DiskDrives/${i}/`, location,
    model: "Fixture", capacity_bytes: 300e9, health: "OK", label: "OK", eligible: true }));
  await page.route("**/api/**", route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname;
    if (req.method() === "POST") posts.push(path.replace(/^.*\/(raid-rebuild|runtime\/write-scope|providers\/ilo-redfish)\/?/, ""));
    if (path === "/api/v1/rack-plans/fixture") return route.fulfill({ json: { ...planJson, equipment: planJson.equipment.slice(0, 1) } });
    if (path.endsWith("/runtime/write-scope")) return route.fulfill({ json: { scope, active_operations: [], blockers: [] } });
    if (path.endsWith("/runtime/write-scope/preview")) return route.fulfill({ json: { review_token: "s", current_scope: scope, target_scope: req.postDataJSON().target_scope, expires_at: new Date(Date.now() + 6e5).toISOString(), blockers: [], confirmation_phrase: req.postDataJSON().target_scope === "storage_only" ? "ONLY BUILD RAID" : "" } });
    if (path.endsWith("/runtime/write-scope/apply")) { scope = req.postDataJSON().confirmation_phrase === "ONLY BUILD RAID" ? "storage_only" : "read_only"; return route.fulfill({ json: { scope, active_operations: [], blockers: [] } }); }
    if (path.endsWith("/probe")) return route.fulfill({ json: { status: "ok", warnings: [], blockers: [] } });
    if (path.endsWith("/raid-rebuild/status")) return route.fulfill({ json: raid });
    if (path.endsWith("/raid-rebuild/power-state")) return route.fulfill({ json: { power: powered, pending_changes: false } });
    if (path.endsWith("/raid-rebuild/shutdown-preview")) return route.fulfill({ json: { preview_id: "sd1", name: "Test server", force: false, confirmation: "SHUT DOWN Test server", blockers: [], apply_enabled: true, payload: { ResetType: "PushPowerButton" } } });
    if (path.endsWith("/raid-rebuild/shutdown")) { powered = "Off"; return route.fulfill({ json: { message: "requested" } }); }
    if (path.endsWith("/raid-rebuild/preview")) {
      const blockers = [...(scope === "storage_only" ? [] : ["This hardware action is outside the enabled live-operation scope."]), ...(powered === "Off" ? [] : ["Shut down the server cleanly first. This operation requires the server power state to be Off; iLO stays on."])];
      return route.fulfill({ json: { preview_id: "p1", operation: "create", name: "Test server", host: "192.0.2.10", controller: "P408i-a", method: "PUT", path: "/x", payload: {}, volumes: [], empty_bays: [], warnings: [], blockers, apply_enabled: !blockers.length, confirmation: "CREATE RAID ON TEST SERVER", expires_at: new Date(Date.now() + 6e5).toISOString() } });
    }
    if (path.endsWith("/raid-rebuild/apply")) { raid = { status: "staged", active: true, operation: "create", message: "Staged" }; return route.fulfill({ json: { status: "staged", message: "Staged", verified: false } }); }
    if (path.endsWith("/raid-rebuild/boot-preview")) return route.fulfill({ json: { preview_id: "b1", name: "Test server", operation: "create", confirmation: "START TEST SERVER", pending_payload: {}, path: "/x", method: "POST", payload: {}, blockers: [], apply_enabled: true, expires_at: new Date(Date.now() + 6e5).toISOString() } });
    if (path.endsWith("/raid-rebuild/boot")) { raid = { status: "waiting", active: true, operation: "create", message: "Power-on requested", boot_started_at: new Date().toISOString() }; return route.fulfill({ json: { status: "waiting", message: "ok" } }); }
    if (path.endsWith("/raid-rebuild/verify")) { verifies++; if (verifies >= 2) raid = { status: "verified", active: false, operation: "create", message: "Verified" }; return route.fulfill({ json: { status: verifies >= 2 ? "verified" : "waiting", message: "", verified: verifies >= 2 } }); }
    expect(path).toBe("/api/v1/rack-plans/fixture/disk-preparation");
    return route.fulfill({ json: { name: "Test server", current: true, checked_at: new Date().toISOString(), inventory_token: "a".repeat(64), drives, controllers: [{ id: "/redfish/v1/Systems/1/SmartStorage/ArrayControllers/0/", model: "P408i-a", health: "OK", firmware: "1.66" }],
      volumes: [], blockers: [], health_issues: [], saved_intent: { wipe_existing_logical_drives: false, volumes: [
        { bootable: true, raid_level: "RAID1", drive_bays: ["1I:1:1", "1I:1:2"], spare_bays: [] },
        { bootable: false, raid_level: "RAID5", drive_bays: ["2I:1:5", "2I:1:6", "2I:1:7"], spare_bays: ["2I:1:8"] }] } } });
  });
  await openSteps(page, "/raid-fixture");
  await page.getByRole("button", { name: "Build RAID" }).click();
  const box = page.getByRole("dialog", { name: "Build RAID on Test server" });
  await expect(box.getByRole("heading", { name: "Ready to build" })).toBeVisible();
  await expect(box).toContainText("Boot disks (RAID 1, ESXi)");
  await expect(box).toContainText("Spare: 2I:1:8");
  await expect(box).not.toContainText("Can't build yet");
  await expect(box.getByRole("textbox")).toHaveCount(0);
  await box.getByRole("button", { name: "Build RAID" }).click();
  // Power-off polling and the automatic checks run on timers; advance until the volumes read back.
  await expect.poll(async () => { await page.clock.runFor(16000); return box.getByRole("heading", { name: "Complete" }).isVisible(); }, { timeout: 30000 }).toBe(true);
  await box.getByRole("button", { name: "Done" }).click();
  await expect(box).toHaveCount(0);
  const expected = ["probe", "preview", "preview", "apply", ...(power === "On" ? ["shutdown-preview", "shutdown"] : []), "preview", "apply", "boot-preview", "boot"];
  expect(posts.slice(0, expected.length)).toEqual(expected);
  expect(posts.filter(p => p === "apply").length).toBe(3);
});

for (const withRaid of [false, true]) test(`wipe: one tick and one button wipe every disk${withRaid ? ", deleting the old RAID first" : ""}; it watches until each disk confirms`, async ({ page }) => {
  test.setTimeout(120000);
  await page.clock.install();
  const bays = ["1I:1:1", "1I:1:2", "2I:1:5", "2I:1:6"];
  const drives = bays.map((location, i) => ({ id: `/redfish/v1/Systems/1/SmartStorage/ArrayControllers/0/DiskDrives/${i}/`, location, model: "EG000300JWEBF", capacity_bytes: 300e9, media: "HDD", health: "OK", label: "OK", eligible: true }));
  const eraseDrives = bays.map((bay, i) => ({ bay, identity: `id-${i}`, model: "EG000300JWEBF", firmware: "HPD9", capacity_bytes: 300e9, media: "HDD", erase_pattern: "SanitizeRestrictedOverwrite" }));
  let raid: any = { status: "not_started", active: false, message: "No operation" }; let scope = "read_only"; let powered = "On";
  let hasRaid = withRaid, authorized = false, verifies = 0; const posts: string[] = []; let authorization: any = null, saved: any = null, eraseApply: any = null;
  await page.route("**/api/**", route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname;
    if (req.method() === "POST") posts.push(path.replace(/^.*\/runtime\/write-scope\/?/, "scope-").replace(/^.*\/(raid-rebuild|providers\/ilo-redfish|rack-plans\/fixture)\/?/, "") + (path.endsWith("/raid-rebuild/preview") ? `:${req.postDataJSON().operation}` : ""));
    if (path === "/api/v1/rack-plans/fixture") return route.fulfill({ json: { ...planJson, equipment: planJson.equipment.slice(0, 1) } });
    if (path.endsWith("/runtime/write-scope")) return route.fulfill({ json: { scope, active_operations: [], blockers: [] } });
    if (path.endsWith("/runtime/write-scope/preview")) return route.fulfill({ json: { review_token: "s", current_scope: scope, target_scope: req.postDataJSON().target_scope, expires_at: new Date(Date.now() + 6e5).toISOString(), blockers: [], confirmation_phrase: req.postDataJSON().target_scope === "storage_only" ? "ONLY BUILD RAID" : "" } });
    if (path.endsWith("/runtime/write-scope/apply")) { scope = req.postDataJSON().confirmation_phrase === "ONLY BUILD RAID" ? "storage_only" : "read_only"; return route.fulfill({ json: { scope, active_operations: [], blockers: [] } }); }
    if (path.endsWith("/probe")) return route.fulfill({ json: { status: "ok", warnings: [], blockers: [] } });
    if (path.endsWith("/raid-rebuild/status")) return route.fulfill({ json: raid });
    if (path.endsWith("/raid-rebuild/power-state")) return route.fulfill({ json: { power: powered, pending_changes: false } });
    if (path.endsWith("/raid-rebuild/shutdown-preview")) return route.fulfill({ json: { preview_id: "sd1", name: "Test server", force: false, confirmation: "SHUT DOWN Test server", blockers: [], apply_enabled: true, payload: { ResetType: "PushPowerButton" } } });
    if (path.endsWith("/raid-rebuild/shutdown")) { powered = "Off"; return route.fulfill({ json: { message: "requested" } }); }
    if (path.endsWith("/raid-rebuild/preview")) {
      const operation = req.postDataJSON().operation;
      const common = scope === "storage_only" ? [] : ["This hardware action is outside the enabled live-operation scope."];
      if (operation === "clear") {
        const blockers = [...common, ...(powered === "Off" ? [] : ["Shut down the server cleanly first."]), ...(saved?.remove_existing_volumes ? [] : ["Review and save removal of the existing logical volumes first."])];
        return route.fulfill({ json: { preview_id: "c1", operation, name: "Test server", host: "192.0.2.10", controller: "P408i-a", method: "PUT", path: "/x", payload: {}, volumes: [], empty_bays: [], warnings: [], blockers, apply_enabled: !blockers.length, confirmation: "CLEAR RAID Test server", expires_at: new Date(Date.now() + 6e5).toISOString() } });
      }
      const blockers = [...common, ...(powered === "Off" ? [] : ["Shut down the server before staging physical-disk erasure."]),
        ...(hasRaid ? ["Delete the existing RAID arrays and verify the empty controller first."] : []),
        ...(authorized ? [] : ["Physical-disk erasure is not enabled for this server. Complete Erase authorization below."])];
      return route.fulfill({ json: { preview_id: authorized ? "e2" : "e1", operation, name: "Test server", host: "192.0.2.10", controller: "Smart Array P408i-a SR Gen10", capability_context: { controller_firmware: "1.66" }, method: "PATCH", path: "/x", payload: {}, volumes: [], empty_bays: [], warnings: [], drives: eraseDrives, blockers, apply_enabled: !blockers.length, confirmation: "ERASE ALL 4 DISKS Test server", expires_at: new Date(Date.now() + 6e5).toISOString() } });
    }
    if (path.endsWith("/sanitize-authorization")) { authorization = req.postDataJSON(); authorized = true; return route.fulfill({ json: { message: "saved", expires_at: new Date(Date.now() + 864e5).toISOString() } }); }
    if (path.endsWith("/raid-rebuild/apply")) {
      const body = req.postDataJSON(); const operation = body.preview_id.startsWith("c") ? "clear" : "sanitize";
      if (operation === "sanitize") eraseApply = body;
      raid = { status: "staged", active: true, operation, message: "Staged" }; return route.fulfill({ json: { status: "pending", message: "Staged", verified: false } });
    }
    if (path.endsWith("/raid-rebuild/boot-preview")) return route.fulfill({ json: { preview_id: "b1", name: "Test server", operation: raid.operation, confirmation: "START TEST SERVER", pending_payload: {}, path: "/x", method: "POST", payload: {}, blockers: [], apply_enabled: true, expires_at: new Date(Date.now() + 6e5).toISOString() } });
    if (path.endsWith("/raid-rebuild/boot")) { powered = "On"; raid = { ...raid, status: "waiting", boot_started_at: new Date().toISOString() }; return route.fulfill({ json: { status: "waiting", message: "ok" } }); }
    if (path.endsWith("/raid-rebuild/verify")) {
      if (raid.operation === "clear") { hasRaid = false; raid = { status: "verified", active: false, operation: "clear", message: "Cleared" }; return route.fulfill({ json: { status: "verified", verified: true, message: "cleared" } }); }
      verifies++;
      const done = verifies >= 2;
      raid = { ...raid, status: done ? "verified" : "waiting", active: !done, sanitization: { checked_at: new Date().toISOString(), message: "", drives: eraseDrives.map(d => ({ ...d, status: done ? "verified" : "unverified", percent: done ? 100 : 40 })) } };
      return route.fulfill({ json: { status: done ? "verified" : "waiting", verified: done, message: "" } });
    }
    if (path.endsWith("/disk-preparation") && req.method() === "POST") { saved = req.postDataJSON(); return route.fulfill({ json: { message: "No disks changed. Plan saved." } }); }
    expect(path).toBe("/api/v1/rack-plans/fixture/disk-preparation");
    return route.fulfill({ json: { name: "Test server", current: true, checked_at: new Date().toISOString(), inventory_token: "a".repeat(64), drives, controllers: [{ id: "c", model: "P408i-a", health: "OK", firmware: "1.66" }],
      volumes: hasRaid ? [{ id: "v1", name: "Logical drive 1", raid: "RAID1", capacity_bytes: 300e9, bays: bays.slice(0, 2) }] : [], blockers: [], health_issues: [],
      saved_intent: { wipe_existing_logical_drives: false, volumes: [{ bootable: true, raid_level: "RAID1", drive_bays: bays.slice(0, 2), spare_bays: [] }, { bootable: false, raid_level: "RAID1", drive_bays: bays.slice(2), spare_bays: [] }] } } });
  });
  await openSteps(page, "/disks-fixture");
  const card = page.getByRole("article", { name: "Test server" });
  await card.getByRole("button", { name: "Wipe disks" }).click();
  const box = page.getByRole("dialog", { name: "Wipe disks on Test server" });
  await expect(box.getByRole("heading", { name: "Ready to wipe" })).toBeVisible();
  await expect(box).toContainText("Everything on these 4 disks is destroyed for good");
  if (withRaid) await expect(box).toContainText("The RAID on them (RAID 1, 300 GB) is deleted first.");
  await expect(box.getByRole("textbox")).toHaveCount(0);
  const wipe = box.getByRole("button", { name: "Wipe 4 disks" });
  await expect(wipe).toBeDisabled();
  await box.getByRole("checkbox").check();
  await wipe.click();
  await expect.poll(async () => { await page.clock.runFor(10000); return box.getByRole("heading", { name: "Complete" }).isVisible(); }, { timeout: 100000 }).toBe(true);
  expect(authorization.confirmation).toBe("AUTHORIZE ERASURE Test server");
  expect(Object.keys(authorization.sources).sort()).toEqual(["id-0", "id-1", "id-2", "id-3"]);
  expect(authorization.sources["id-2"]).toContain("SanitizeRestrictedOverwrite");
  expect(eraseApply).toMatchObject({ preview_id: "e2", confirmation: "ERASE ALL 4 DISKS Test server", physical_erase_confirmed: true });
  if (withRaid) expect(saved).toMatchObject({ remove_existing_volumes: true, data_loss_reviewed: true, boot_drive_ids: [drives[0].id, drives[1].id], data_drive_ids: [drives[2].id, drives[3].id], data_raid: "RAID1" });
  // Every state-changing request, in order: each sent once, nothing retried.
  const changes = posts.filter(p => /^(shutdown|apply|boot|sanitize-authorization|disk-preparation)$/.test(p));
  expect(changes).toEqual([...(withRaid ? ["disk-preparation", "shutdown", "apply", "boot"] : []), "shutdown", "sanitize-authorization", "apply", "boot"]);
  await box.getByRole("button", { name: "Done" }).click();
  await expect(box).toHaveCount(0);
  expect(scope).toBe("read_only");
});
