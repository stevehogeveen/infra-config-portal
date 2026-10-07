import {expect,test} from "@playwright/test";

test("ESXi-only saves preserve network and iLO settings and do not invoke RAID",async({page})=>{
  const global={gateway:"192.0.2.1",dns_servers:["192.0.2.53"],ntp_servers:["192.0.2.123"],snmp_servers:["192.0.2.90"],subnet_prefix:27,mtu:1500};
  const address={subnet:"192.0.2.0/27",ilo:"192.0.2.10",ilo_initial:"198.51.100.17",esxi_management:"192.0.2.20",server_embedded_nic:"vmnic0"};
  const profile={id:"fixture",name:"Test kit",source:"saved",version:1,profile_topology:"custom",subnet_cidr:address.subnet,gateway:global.gateway,dns:global.dns_servers,ntp:global.ntp_servers,mtu:1500,vlan_id:"30",description:"Keep me",features:{enable_ntp:false,enable_snmp:true},devices:{ilo:address.ilo,esxi:address.esxi_management,switch_primary:"192.0.2.5"},address_plan:address,resolved_address_plan:address,global_settings:global};
  let saves=0;
  await page.route("**/api/**",route=>{
    const req=route.request(),path=new URL(req.url()).pathname;
    if(path==="/api/v1/rack-plans/fixture")return route.fulfill({json:{equipment:[{id:"s",device_id:"s",name:"Test server",kind:"server"}]}});
    if(req.method()==="PUT"&&path==="/api/v1/lab/profiles/fixture"){
      saves++;const body=req.postDataJSON();
      expect(body.global_settings).toEqual(global);expect(body.features).toEqual(profile.features);
      expect(body.address_plan).toEqual({...address,esxi_management:"192.0.2.21"});
      expect(body.devices).toEqual({...profile.devices,esxi:"192.0.2.21"});
      expect(body.subnet_cidr).toBe(address.subnet);expect(body.description).toBe("Keep me");
      return route.fulfill({json:{}});
    }
    expect(req.method()).toBe("GET");expect(path).toBe("/api/v1/workflows/actions");return route.fulfill({json:[]});
  });
  await page.route("**/esxi-only-fixture",r=>r.fulfill({contentType:"text/html",body:`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root" class="app-shell-workbench"></div><script type="module">import R from '/@react-refresh'; R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    window.esxiFixture={active_profile:${JSON.stringify(profile)}};await import('/tests/fixtures/esxiOnlyHarness.tsx');</script></body></html>`}));
  await page.goto("/esxi-only-fixture");
  await expect(page.getByRole("heading",{name:"ESXi host settings",exact:true})).toBeVisible();
  await expect(page.getByLabel("Initial iLO IP")).toHaveCount(0);
  await expect(page.getByRole("button",{name:/RAID/})).toHaveCount(0);
  await page.getByLabel("ESXi management IP",{exact:true}).fill("192.0.2.21");
  await page.getByRole("button",{name:"Save ESXi settings"}).click();
  await expect(page.getByText("ESXi settings saved. Other kit settings were preserved.")).toBeVisible();
  expect(saves).toBe(1);
});
