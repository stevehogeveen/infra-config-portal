import { expect, test, type Page } from "@playwright/test";

// Prepare ESXi: 1 installer media, 2 host settings, 3 install. Documentation addresses only.
const global = { gateway: "192.0.2.1", dns_servers: ["192.0.2.53", "192.0.2.54"], ntp_servers: [], subnet_prefix: 24, mtu: 1500, domain_name: "lab.example" };
const address = { subnet: "192.0.2.0/24", ilo: "192.0.2.10", esxi_management: null as string | null, server_embedded_nic: null };
const profile = { id: "fixture", name: "Test kit", source: "saved", version: 1, profile_topology: "custom", subnet_cidr: address.subnet, gateway: global.gateway,
  dns: global.dns_servers, ntp: [], mtu: 1500, vlan_id: "10", description: "", features: { enable_ntp: false, deployment_mode: "single_server_local_storage", storage_location: "server_local" },
  devices: { ilo: address.ilo }, address_plan: address, resolved_address_plan: address, global_settings: global };
const iso = { path: "VMware-ESXi-8.0.3-24859861-HPE-803.0.0.12.2.0.9-oct2025.iso", name: "VMware-ESXi-8.0.3-24859861-HPE-803.0.0.12.2.0.9-oct2025.iso", size_bytes: 698e6, version: "8.0.3 build 24859861", hpe_image: true };
const volume = { name: "ESXi boot", bays: ["1I:1:1", "1I:1:2"], capacity_bytes: 300e9, disk_id: "naa.600508b1001c0000", read_at: null };
const dataVolume = { name: "VM data", raid: "RAID5", bays: ["2I:1:5", "2I:1:6", "2I:1:7", "2I:1:8"], capacity_bytes: 3.6e12, disk_id: "naa.600508b1001cdata", read_at: null };
const checks = [
  { name: "ESXi answered the root sign-in", ok: true, expected: "VMware ESXi", found: "VMware ESXi 8.0.3" },
  { name: "Host name", ok: true, expected: "esxi01.lab.example", found: "esxi01.lab.example" },
  { name: "Management address", ok: true, expected: "192.0.2.20/255.255.255.0 static", found: "192.0.2.20/255.255.255.0 static" },
  { name: "Management VLAN", ok: true, expected: "untagged (0)", found: "0" },
  { name: "Installed on the boot mirror", ok: true, expected: volume.disk_id, found: "ESXi partitions found" },
];

function kit(saved: any) {
  return { profile_id: "fixture", profile_version: 1, saved_profile: true, subnet: "192.0.2.0/24", gateway: "192.0.2.1", dns: global.dns_servers, ntp_enabled: false, ntp: [],
    domain_name: "lab.example", esxi_management: saved?.management_ip ?? null, single_server_local: true };
}

async function open(page: Page) {
  await page.route("**/esxi-step-fixture", r => r.fulfill({ contentType: "text/html", body: `<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(t)=>t;window.__vite_plugin_react_preamble_installed__=true;
    window.esxiFixture={active_profile:${JSON.stringify(profile)}};await import('/tests/fixtures/esxiStepHarness.tsx');</script></body></html>` }));
  await page.goto("/esxi-step-fixture");
}

function mockApi(page: Page, state: { selected: any; saved: any; built: any; install: any; checks: number; scope: string; sent: string[]; profilePut: any; settingsPut: any; typed?: string; refuseBoot?: boolean }) {
  return page.route("**/api/**", async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname, method = req.method();
    if (method !== "GET") state.sent.push(`${method} ${path.replace("/api/v1/rack-plans/fixture/", "").replace("/api/v1/", "")}`);
    if (path === "/api/v1/rack-plans/fixture") return route.fulfill({ json: { revision: 1, rack_units: 4, equipment: [{ id: "s", device_id: "srv", name: "HPE DL360 3", kind: "server", model: "HPE DL360 Gen10", position: 1, height: 1, mount: "rack", ports: 0, bay_count: 10, occupied_bays: [] }] } });
    if (path.endsWith("/esxi/media")) {
      if (method === "POST") state.selected = { ...iso, selected_at: new Date().toISOString(), present: true };
      return route.fulfill({ json: { root_ready: true, folder: "", isos: [iso], selected: state.selected } });
    }
    if (path.endsWith("/esxi/network-ports")) return route.fulfill({ json: { available: true, suggested: "02:00:00:00:00:02", message: null, ports: [
      { mac: "02:00:00:00:00:01", adapter: "HPE Ethernet 1Gb 4-port 331i Adapter", location: "Embedded LOM", port: 1, link: false, speed_mbps: null, vmnic: null },
      { mac: "02:00:00:00:00:02", adapter: "HPE Ethernet 1Gb 4-port 331i Adapter", location: "Embedded LOM", port: 2, link: true, speed_mbps: 1000, vmnic: null },
      { mac: "02:00:00:00:01:01", adapter: "Broadcom NetXtreme-E Quad 25Gb SFP28 PCIe Ethernet", location: "NIC.Slot.3.1", port: 1, link: false, speed_mbps: null, vmnic: null }] } });
    if (path.endsWith("/esxi/settings")) {
      if (method === "PUT") { state.settingsPut = req.postDataJSON(); state.saved = { ...state.settingsPut, saved_at: new Date().toISOString() }; }
      const saved = state.saved;
      return route.fulfill({ json: { hostname: saved?.hostname ?? null, addressing: saved?.addressing ?? "static", management_ip: saved?.management_ip ?? null, vlan_id: saved?.vlan_id ?? 0,
        management_nic: saved?.management_nic ?? "vmnic0", datastore_name: saved?.datastore_name ?? "VMdata", password_set: !!saved, signin_ready: !!saved,
        saved_at: saved?.saved_at ?? null, kit: kit(saved), boot_volume: volume, data_volume: dataVolume } });
    }
    if (path === "/api/v1/lab/profiles/fixture" && method === "PUT") { state.profilePut = req.postDataJSON(); return route.fulfill({ json: {} }); }
    if (path.endsWith("/esxi/installer")) {
      if (method === "POST") state.built = { iso_name: "esxi-installer-0123456789abcdef.iso", iso_sha256: "a".repeat(64), size_bytes: 699e6, built_at: new Date().toISOString(), install_disk_id: volume.disk_id, hostname: "esxi01.lab.example", management_ip: "192.0.2.20" };
      const missing = [...(state.selected ? [] : ["Choose the ESXi installer ISO."]), ...(state.saved ? [] : ["Save the ESXi host settings and root password."])];
      return route.fulfill({ json: missing.length ? { status: "blocked", blockers: missing, built: null } : state.built ? { status: "ready", blockers: [], built: state.built } : { status: "not_built", blockers: [], built: null } });
    }
    if (path.endsWith("/esxi/install/resume")) {
      state.install = { ...state.install, state: "verified", active: false, verified_at: new Date().toISOString(), ejected: true, management_ip: "192.0.2.20",
        phases: { ...state.install.phases, datastore: "ok" }, datastore: { name: "VMdata", disk: dataVolume.disk_id },
        verification: { passed: true, address: "192.0.2.20", checked_at: new Date().toISOString(), checks }, message: "ESXi is installed and verified at 192.0.2.20." };
      return route.fulfill({ json: state.install });
    }
    if (path.endsWith("/esxi/install/check")) {
      state.checks++;
      const typed = req.postDataJSON()?.address as string | undefined;
      if (typed) state.typed = typed;
      const ip = state.install.addressing === "dhcp" ? state.typed : "192.0.2.20";
      if (!ip) state.install = { ...state.install, last_check: { answering: false, address: null, detail: "Waiting for the server to report its DHCP address. If the server's screen shows one, enter it.", checked_at: new Date().toISOString() } };
      else if (state.checks >= 2 || typed) state.install = { ...state.install, state: "verified", active: false, verified_at: new Date().toISOString(), ejected: true, management_ip: ip,
        phases: { ...state.install.phases, eject: "ok", datastore: "ok" }, datastore: { name: "VMdata", disk: dataVolume.disk_id },
        verification: { passed: true, address: ip, checked_at: new Date().toISOString(), checks }, message: `ESXi is installed and verified at ${ip}.` };
      else state.install = { ...state.install, last_check: { answering: false, detail: "Nothing answers on port 443 yet.", checked_at: new Date().toISOString() } };
      return route.fulfill({ json: state.install });
    }
    if (path.endsWith("/esxi/install")) {
      if (method === "POST") state.install = { state: "installing", active: true, phases: { media: "ok", boot: "ok", power: "ok" }, started_at: new Date().toISOString(),
        addressing: state.saved?.addressing ?? "static", management_ip: state.saved?.addressing === "dhcp" ? null : "192.0.2.20", hostname: "esxi01.lab.example",
        iso_name: "esxi-installer-0123456789abcdef.iso", message: "The installer is running on the server." };
      if (method === "POST" && state.refuseBoot) state.install = { ...state.install, state: "needs_attention", phase: "boot", can_check_installed: true, phases: { media: "ok", boot: "failed" },
        message: "The iLO refused the one-time boot from the installer (HTTP 400: iLO.2.14.UnableToModifyDuringSystemPOST). Nothing was applied; Check the server again sends it once more." };
      return route.fulfill({ json: state.install });
    }
    if (path.endsWith("/runtime/write-scope")) return route.fulfill({ json: { scope: state.scope, active_operations: [], blockers: [] } });
    if (path.endsWith("/runtime/write-scope/preview")) { const target = req.postDataJSON().target_scope; return route.fulfill({ json: { review_token: "t", current_scope: state.scope, target_scope: target, expires_at: new Date(Date.now() + 6e5).toISOString(), blockers: [], confirmation_phrase: target === "esxi_install_only" ? "ONLY INSTALL ESXI" : "" } }); }
    if (path.endsWith("/runtime/write-scope/apply")) { state.scope = req.postDataJSON().confirmation_phrase === "ONLY INSTALL ESXI" ? "esxi_install_only" : "read_only"; return route.fulfill({ json: { scope: state.scope, active_operations: [], blockers: [] } }); }
    return route.fulfill({ status: 404, json: { detail: "unexpected " + path } });
  });
}

const fresh = () => ({ selected: null as any, saved: null as any, built: null as any, install: { state: "not_started", active: false, phases: {}, message: "" } as any, checks: 0, scope: "read_only", sent: [] as string[], profilePut: null as any, settingsPut: null as any });

test("Prepare ESXi: pick the ISO, save host settings (plan only), then Install becomes available", async ({ page }) => {
  const state = fresh();
  await mockApi(page, state);
  await open(page);
  await expect(page.getByRole("heading", { name: "Prepare ESXi", exact: true })).toBeVisible();
  const card = page.getByRole("article", { name: "HPE DL360 3" });
  const install = card.getByRole("button", { name: "Install ESXi" });
  await expect(install).toBeDisabled();
  await expect(card.getByRole("list", { name: "Still to do" })).toContainText("Choose the ESXi installer ISO.");
  await expect(card).toContainText("Installs to ESXi boot (RAID 1, 300 GB, bays 1 & 2)");

  // 1: the ISO tile, with its version and HPE badge; picking it is a plan-only save.
  const media = card.getByRole("radiogroup", { name: "ESXi installer ISO" });
  await media.getByRole("radio", { name: /ESXi 8\.0\.3 build 24859861/ }).click();
  await expect(media.getByRole("radio", { name: /ESXi 8\.0\.3/ })).toHaveAttribute("aria-checked", "true");
  await expect(card.getByRole("region", { name: "Installer media" })).toContainText("Using VMware-ESXi-8.0.3");

  // 2: host settings. Mismatched passwords are caught before anything is saved.
  const settings = card.getByRole("region", { name: "Host settings" });
  await settings.getByLabel("ESXi host name").fill("esxi01");
  await expect(settings).toContainText(".lab.example");
  await settings.getByLabel("ESXi management IP").fill("192.0.2.20");
  // The port with a cable is chosen for you; an unplugged one is called out.
  const builtIn = settings.getByRole("radiogroup", { name: /Ports on Built-in/ });
  await expect(builtIn.getByRole("radio", { name: /port 2, cable connected/ })).toHaveAttribute("aria-checked", "true");
  await expect(builtIn.getByRole("radio", { name: /port 2/ })).toContainText("Cable · 1 Gb");
  await builtIn.getByRole("radio", { name: /port 1, no cable/ }).click();
  await expect(settings.getByRole("alert")).toContainText("Built-in port 1 has no cable");
  await builtIn.getByRole("radio", { name: /port 2, cable connected/ }).click();
  await expect(settings.getByRole("radiogroup", { name: /Ports on Slot 3/ })).toBeVisible();
  await settings.getByLabel("ESXi root password", { exact: true }).fill("Lab-Pass-2026");
  await settings.getByLabel("Confirm ESXi root password").fill("Lab-Pass-2027");
  await settings.getByRole("button", { name: "Save host settings" }).click();
  await expect(settings.getByRole("alert")).toContainText("The two passwords don't match.");
  expect(state.settingsPut).toBeNull();
  await settings.getByLabel("Confirm ESXi root password").fill("Lab-Pass-2026");
  await settings.getByRole("button", { name: "Save host settings" }).click();
  await expect.poll(() => state.settingsPut).not.toBeNull();
  expect(state.settingsPut).toEqual({ hostname: "esxi01.lab.example", addressing: "static", management_ip: "192.0.2.20", vlan_id: 0, management_nic: "02:00:00:00:00:02", datastore_name: "VMdata", root_password: "Lab-Pass-2026" });
  // The kit learns the same address, and every other kit setting rides along unchanged.
  expect(state.profilePut.address_plan.esxi_management).toBe("192.0.2.20");
  expect(state.profilePut.global_settings).toEqual(global);
  await expect(card.getByRole("region", { name: "Host settings" })).toContainText("esxi01.lab.example · 192.0.2.20 · untagged");
  await expect(card.getByRole("region", { name: "Host settings" }).locator(".ex-saved")).toContainText("Saved");
  await expect(card).toContainText("Then formats VM data (RAID 5, 3.6 TB) as datastore VMdata, after ESXi is verified.");
  await expect(card.getByRole("region", { name: "Host settings" }).getByLabel("ESXi root password", { exact: true })).toHaveCount(0);
  await expect(install).toBeEnabled();
  // Nothing so far went near the server: only plan saves.
  expect(state.sent).toEqual(["POST esxi/media", "PUT lab/profiles/fixture", "PUT esxi/settings"]);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 950 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  }
});

test("Install ESXi: one tick and one button, then signs in, verifies and creates the datastore; Done locks read-only", async ({ page }) => {
  test.setTimeout(90000);
  await page.clock.install();
  const state = fresh();
  state.selected = { ...iso, selected_at: new Date().toISOString(), present: true };
  state.saved = { hostname: "esxi01.lab.example", addressing: "static", management_ip: "192.0.2.20", vlan_id: 0, management_nic: "vmnic0", datastore_name: "VMdata", saved_at: new Date().toISOString() };
  await mockApi(page, state);
  await open(page);
  await page.getByRole("article", { name: "HPE DL360 3" }).getByRole("button", { name: "Install ESXi" }).click();
  const box = page.getByRole("dialog", { name: "Install ESXi on HPE DL360 3" });
  await expect(box.getByRole("heading", { name: "Ready to install" })).toBeVisible();
  expect(state.sent).toContain("POST esxi/installer");
  await expect(box).toContainText("esxi-installer-0123456789abcdef.iso");
  await expect(box).toContainText("ESXi replaces everything on ESXi boot");
  await expect(box).toContainText("VM data (RAID 5, 3.6 TB) is formatted as datastore VMdata, but only if it is still empty");
  await expect(box.getByRole("textbox")).toHaveCount(0);
  const go = box.getByRole("button", { name: "Install ESXi" });
  await expect(go).toBeDisabled();
  await box.getByRole("checkbox").check();
  await go.click();
  await expect(box.getByRole("heading", { name: "Installing ESXi…" })).toBeVisible();
  expect(state.scope).toBe("esxi_install_only");
  expect(state.sent.filter(item => item === "POST esxi/install")).toHaveLength(1);
  await expect.poll(async () => { await page.clock.runFor(30000); return box.getByRole("heading", { name: "Complete", exact: true }).isVisible(); }, { timeout: 60000 }).toBe(true);
  await expect(box).toContainText("ESXi is installed and verified at 192.0.2.20.");
  await expect(box).toContainText("Host name: esxi01.lab.example");
  await expect(box).toContainText("Installed on the boot mirror: ESXi partitions found");
  await expect(box).toContainText("Datastore VMdata is ready for your VMs.");
  await expect(box.getByRole("link", { name: /Open the ESXi host client/ })).toHaveAttribute("href", "https://192.0.2.20/ui/");
  await box.getByRole("button", { name: "Done" }).click();
  await expect(box).toHaveCount(0);
  expect(state.scope).toBe("read_only");
  expect(state.sent.filter(item => item === "POST esxi/install")).toHaveLength(1);
});

test("DHCP: no fixed IP is saved, and the address can be typed from the server screen while the install is watched", async ({ page }) => {
  test.setTimeout(90000);
  await page.clock.install();
  const state = fresh();
  state.selected = { ...iso, selected_at: new Date().toISOString(), present: true };
  await mockApi(page, state);
  await open(page);
  const card = page.getByRole("article", { name: "HPE DL360 3" });
  const settings = card.getByRole("region", { name: "Host settings" });
  await settings.getByLabel("ESXi host name").fill("esxi01");
  await settings.getByRole("radiogroup", { name: "Management addressing" }).getByRole("radio", { name: "DHCP" }).click();
  await expect(settings.getByLabel("ESXi management IP")).toHaveCount(0);
  await expect(settings).toContainText("ESXi takes its address from your DHCP server");
  await settings.getByLabel("ESXi root password", { exact: true }).fill("Lab-Pass-2026");
  await settings.getByLabel("Confirm ESXi root password").fill("Lab-Pass-2026");
  await settings.getByRole("button", { name: "Save host settings" }).click();
  await expect.poll(() => state.settingsPut).not.toBeNull();
  expect(state.settingsPut).toMatchObject({ addressing: "dhcp", management_ip: null });
  expect(state.profilePut).toBeNull();
  await expect(settings).toContainText("esxi01.lab.example · DHCP · untagged");

  await card.getByRole("button", { name: "Install ESXi" }).click();
  const box = page.getByRole("dialog", { name: "Install ESXi on HPE DL360 3" });
  await expect(box).toContainText("From DHCP");
  await box.getByRole("checkbox").check();
  await box.getByRole("button", { name: "Install ESXi" }).click();
  await expect(box.getByRole("heading", { name: "Installing ESXi…" })).toBeVisible();
  await page.clock.runFor(21000);
  await expect(box).toContainText("Waiting for the server to report its DHCP address");
  await box.getByLabel("ESXi address from the server screen").fill("192.0.2.77");
  await box.getByRole("button", { name: "Use this address" }).click();
  await expect(box.getByRole("heading", { name: "Complete", exact: true })).toBeVisible();
  await expect(box).toContainText("ESXi is installed and verified at 192.0.2.77.");
});

test("A refused boot: the host that installed itself is checked by signing in, not by restarting it", async ({ page }) => {
  const state = { ...fresh(), refuseBoot: true };
  state.selected = { ...iso, selected_at: new Date().toISOString(), present: true };
  state.saved = { hostname: "esxi01.lab.example", addressing: "dhcp", management_ip: null, vlan_id: 0, management_nic: "vmnic0", datastore_name: "VMdata", saved_at: new Date().toISOString() };
  await mockApi(page, state);
  await open(page);
  await page.getByRole("article", { name: "HPE DL360 3" }).getByRole("button", { name: "Install ESXi" }).click();
  const box = page.getByRole("dialog", { name: "Install ESXi on HPE DL360 3" });
  await box.getByRole("checkbox").check();
  await box.getByRole("button", { name: "Install ESXi" }).click();
  await expect(box.getByRole("heading", { name: "The install needs attention" })).toBeVisible();
  await expect(box).toContainText("UnableToModifyDuringSystemPOST");
  await expect(box.getByRole("button", { name: "Retry the boot and restart" })).toBeVisible();
  const adopt = box.getByRole("form", { name: "Check an installed host" });
  await expect(adopt).toContainText("Did ESXi install anyway?");
  await adopt.getByLabel("ESXi address from the server screen").fill("192.0.2.77");
  await adopt.getByRole("button", { name: "Check the installed host" }).click();
  await expect(box.getByRole("heading", { name: "Complete", exact: true })).toBeVisible();
  await expect(box).toContainText("ESXi is installed and verified at 192.0.2.77.");
  expect(state.sent).not.toContain("POST esxi/install/resume");
});

test("A datastore step finished by Check the server again moves straight to Complete", async ({ page }) => {
  const state = fresh();
  state.selected = { ...iso, selected_at: new Date().toISOString(), present: true };
  state.saved = { hostname: "esxi01.lab.example", addressing: "static", management_ip: "192.0.2.20", vlan_id: 0, management_nic: "vmnic0", datastore_name: "VMdata", saved_at: new Date().toISOString() };
  state.built = { iso_name: "esxi-installer-0123456789abcdef.iso", iso_sha256: "a".repeat(64), size_bytes: 699e6, built_at: new Date().toISOString(), install_disk_id: volume.disk_id, hostname: "esxi01.lab.example", management_ip: "192.0.2.20" };
  state.install = { state: "needs_attention", active: true, phase: "datastore", started_at: new Date().toISOString(), addressing: "static", management_ip: "192.0.2.20",
    hostname: "esxi01.lab.example", iso_name: "esxi-installer-0123456789abcdef.iso", datastore_name: "VMdata",
    phases: { media: "ok", boot: "ok", power: "ok", eject: "ok", datastore: "uncertain" },
    verification: { passed: true, address: "192.0.2.20", checked_at: new Date().toISOString(), checks },
    message: "The server did not confirm the 'datastore' step (GovcError: please specify a host). Nothing was retried." };
  await mockApi(page, state);
  await open(page);
  await page.getByRole("article", { name: "HPE DL360 3" }).getByRole("button", { name: "See progress" }).click();
  const box = page.getByRole("dialog", { name: "Install ESXi on HPE DL360 3" });
  await expect(box.getByRole("heading", { name: "The install needs attention" })).toBeVisible();
  await expect(box).toContainText("please specify a host");
  await box.getByRole("button", { name: "Check the server again" }).click();
  await expect(box.getByRole("heading", { name: "Complete", exact: true })).toBeVisible();
  await expect(box).toContainText("Datastore VMdata is ready for your VMs.");
});
