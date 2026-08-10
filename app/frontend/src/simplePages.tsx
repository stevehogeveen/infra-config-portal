import { useCallback, useEffect, useState, type KeyboardEvent } from "react";
import { Layers3, ListChecks, Pencil, Plus, Server, Settings2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "./api";
import { DeviceInventoryForm } from "./components/DeviceInventoryForm";
import { RackDeviceConfigurator, RackIloConfigurator } from "./operatorPages";
import type {
  DeviceInventoryItem,
  HpeStorageDiscovery,
  HpeVsanReadiness,
  IloAccessSettings,
  LabProfileList,
  ProviderStatus
} from "./types";

// The rack workspace and ordered runbook use only cheap, already-cached data.
// They do not probe hardware or expose apply operations.

type SimpleData = {
  devices: DeviceInventoryItem[];
  providers: ProviderStatus[];
  access: IloAccessSettings | null;
  storage: HpeStorageDiscovery | null;
  vsan: HpeVsanReadiness | null;
  profiles: LabProfileList | null;
  health: Awaited<ReturnType<typeof api.health>> | null;
  loaded: boolean;
  loadError: string | null;
};

async function readSimpleData(): Promise<SimpleData> {
  const [healthResult, devicesResult] = await Promise.allSettled([
    api.health(),
    api.deviceInventory()
  ]);
  if (healthResult.status === "rejected" || devicesResult.status === "rejected") {
    return {
      devices: [],
      providers: [],
      access: null,
      storage: null,
      vsan: null,
      profiles: null,
      health: healthResult.status === "fulfilled" ? healthResult.value : null,
      loaded: true,
      loadError: "Lab Builder cannot reach its local backend. Rack data has not been loaded."
    };
  }
  const [providers, access, storage, vsan, profiles] = await Promise.all([
    api.providers().catch(() => [] as ProviderStatus[]),
    api.iloAccessSettings().catch(() => null),
    api.hpeStorageDiscovery().catch(() => null),
    api.hpeVsanReadiness().catch(() => null),
    api.labProfiles().catch(() => null)
  ]);
  return { devices: devicesResult.value, providers, access, storage, vsan, profiles, health: healthResult.value, loaded: true, loadError: null };
}

function useSimpleData(): SimpleData & { reload: () => Promise<void> } {
  const [data, setData] = useState<SimpleData>({
    devices: [],
    providers: [],
    access: null,
    storage: null,
    vsan: null,
    profiles: null,
    health: null,
    loaded: false,
    loadError: null
  });

  const reload = useCallback(async () => {
    setData((current) => ({ ...current, loaded: false, loadError: null }));
    setData(await readSimpleData());
  }, []);

  useEffect(() => {
    let cancelled = false;
    void readSimpleData().then((next) => {
      if (!cancelled) setData(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return { ...data, reload };
}

const PROVIDERS_BY_TYPE: Record<string, string[]> = {
  ilo: ["ilo-redfish"],
  esxi_host: ["esxi-readonly"],
  cisco_switch: ["cisco-console", "cisco-ansible"],
  netapp: ["netapp-ontap"],
  vcenter: ["vcenter"]
};

function deviceWord(device: DeviceInventoryItem, providers: ProviderStatus[], access?: IloAccessSettings | null): "Ready" | "Problem" | "Not checked" {
  const providerIds = PROVIDERS_BY_TYPE[device.device_type] ?? [];
  const provider = providers.find((item) => providerIds.includes(item.id));
  if (!provider || !provider.is_current || provider.status === "not_checked" || provider.freshness === "not_checked") {
    return "Not checked";
  }
  if (device.device_type === "ilo") {
    const deviceHost = device.host?.trim().toLowerCase();
    const accessHost = access?.host?.trim().toLowerCase();
    if (
      !deviceHost ||
      !accessHost ||
      deviceHost !== accessHost ||
      access?.last_probe_is_current !== true ||
      access.last_probe_target_matches_access_host !== true ||
      access.last_probe_target_fingerprint_present !== true
    ) {
      return "Not checked";
    }
  }
  if (provider.status === "ready" || provider.status === "ok") {
    return "Ready";
  }
  return "Problem";
}

function devicePage(device: DeviceInventoryItem): string {
  if (device.device_type === "ilo") return "/server";
  if (device.device_type === "esxi_host") return "/virtualization";
  if (device.device_type === "cisco_switch") return "/network";
  if (device.device_type === "netapp") return "/storage";
  if (device.device_type === "vcenter") return "/virtualization";
  if (device.device_type === "server") return "/server";
  return "/overview";
}

function rackConfigAvailable(device: DeviceInventoryItem): boolean {
  return ["cisco_switch", "esxi_host", "netapp", "vcenter", "server"].includes(device.device_type);
}

function rackConfigLabel(device: DeviceInventoryItem): string {
  if (device.device_type === "cisco_switch") return "Cisco switch";
  if (device.device_type === "esxi_host") return "ESXi host";
  if (device.device_type === "netapp") return "NetApp";
  if (device.device_type === "vcenter") return "vCenter";
  if (device.device_type === "server") return "server";
  return device.device_type.replace(/_/g, " ");
}

type RackWord = "Ready" | "Problem" | "Not checked";
type RackBayState = "boot" | "data" | "free" | "unknown";
type RackBay = { id: string; label: string; state: RackBayState };

function recordText(record: Record<string, unknown> | undefined, ...keys: string[]): string | null {
  if (!record) return null;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number") return String(value);
  }
  return null;
}

function rackWordClass(word: RackWord): string {
  return word.toLowerCase().replace(" ", "-");
}

function rackBays(vsan: HpeVsanReadiness | null): RackBay[] {
  if (!vsan?.storage_inventory_available) return [];
  return vsan.drives.slice(0, 16).map((drive, index) => {
    const label = recordText(drive, "bay_id", "bay", "slot", "location") ?? String(index + 1);
    const volume = recordText(drive, "volume_name", "logical_drive", "usage")?.toLowerCase() ?? "";
    const readiness = recordText(drive, "vsan_status", "status", "readiness")?.toLowerCase() ?? "";
    const state: RackBayState = volume.includes("boot") || volume.includes("esxi") || volume.includes("os")
      ? "boot"
      : volume
        ? "data"
        : readiness.includes("passthrough") || readiness.includes("ready")
          ? "free"
          : "unknown";
    return { id: `${label}-${index}`, label, state };
  });
}

function rackUnitHeight(device: DeviceInventoryItem): number {
  if (device.device_type === "ilo" || device.device_type === "netapp") return 88;
  if (device.device_type === "cisco_switch") return 68;
  return 60;
}

function RackElevationGraphic({ devices, providers, access, bays, selectedId, onSelect }: {
  devices: DeviceInventoryItem[];
  providers: ProviderStatus[];
  access: IloAccessSettings | null;
  bays: RackBay[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const keySelect = (event: KeyboardEvent<SVGGElement>, id: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(id);
    }
  };

  let rackCursor = 62;
  const rows = devices.map((device, index) => {
    const height = rackUnitHeight(device);
    const row = { device, height, index, y: rackCursor };
    rackCursor += height + 12;
    return row;
  });
  const rackHeight = Math.max(560, rackCursor + 44);
  const rackBodyHeight = rackHeight - 60;

  return (
    <svg className="rack-light-svg" viewBox={`0 0 620 ${rackHeight}`} role="img" aria-label="Interactive rack elevation">
      <defs>
        <linearGradient id="rackFrame" x1="0" x2="1"><stop offset="0" stopColor="#dce7eb" /><stop offset=".5" stopColor="#f8fbfc" /><stop offset="1" stopColor="#c8d6dc" /></linearGradient>
        <linearGradient id="deviceFace" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#fff" /><stop offset="1" stopColor="#e8f0f3" /></linearGradient>
        <pattern id="rackVent" width="8" height="8" patternUnits="userSpaceOnUse"><circle cx="4" cy="4" r="1.1" fill="#91a5ad" opacity=".45" /></pattern>
        <filter id="rackShadow" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="7" stdDeviation="8" floodColor="#102932" floodOpacity=".14" /></filter>
      </defs>
      <ellipse cx="320" cy={rackHeight - 20} rx="190" ry="18" fill="#b7c7cd" opacity=".22" />
      <rect x="85" y="22" width="470" height={rackBodyHeight} rx="20" fill="url(#rackFrame)" stroke="#bccbd1" />
      <rect x="104" y="38" width="432" height={rackBodyHeight - 36} rx="10" fill="#dbe5e9" stroke="#aebfc6" />
      <rect x="125" y="45" width="390" height={rackBodyHeight - 50} rx="6" fill="url(#rackVent)" />

      {rows.map(({ device, height, index, y }) => {
        const word = deviceWord(device, providers, access);
        const isCisco = device.device_type === "cisco_switch";
        const isIlo = device.device_type === "ilo";
        const isActiveIloTarget = isIlo && Boolean(
          device.host?.trim().toLowerCase() &&
          device.host.trim().toLowerCase() === access?.host?.trim().toLowerCase()
        );
        const isNetapp = device.device_type === "netapp";
        const isEsxi = device.device_type === "esxi_host";
        return <g key={device.id} className={`rack-unit is-${rackWordClass(word)} ${selectedId === device.id ? "is-selected" : ""}`} role="button" tabIndex={0} aria-label={`Open ${device.display_name}`} onClick={() => onSelect(device.id)} onKeyDown={(event) => keySelect(event, device.id)}>
          <text x="109" y={y + 22} className="rack-u-label">{String(devices.length - index).padStart(2, "0")}</text>
          <rect x="143" y={y} width="354" height={height} rx="7" fill="url(#deviceFace)" filter="url(#rackShadow)" />
          <circle cx="157" cy={y + 18} r="5" className="rack-status-dot" />
          <text x="170" y={y + 22} className="rack-face-title">{device.display_name}</text>
          <text x="478" y={y + 22} textAnchor="end" className="rack-face-meta">{device.device_type.replace(/_/g, " ")}</text>
          {isCisco && Array.from({ length: 24 }).map((_, port) => <rect key={port} x={168 + (port % 12) * 25} y={y + 34 + Math.floor(port / 12) * 12} width="18" height="8" rx="1.5" className="rack-port" />)}
          {isIlo && <>
            <rect x="158" y={y + 32} width="72" height="38" rx="5" className="rack-management-module" />
            <text x="194" y={y + 55} textAnchor="middle" className="rack-module-label">iLO MGMT</text>
            {isActiveIloTarget && bays.length ? bays.slice(0, 8).map((bay, bayIndex) => <g key={bay.id}><rect x={242 + bayIndex * 29} y={y + 34} width="23" height="32" rx="3" className={`rack-drive is-${bay.state}`} /><text x={253.5 + bayIndex * 29} y={y + 53} textAnchor="middle" className="rack-drive-label">{bay.label}</text></g>) : <><rect x="242" y={y + 34} width="230" height="32" rx="4" fill="url(#rackVent)" /><text x="357" y={y + 54} textAnchor="middle" className="rack-empty-label">{isActiveIloTarget ? "LOCAL STORAGE NOT READ" : "FIRST CONTACT REQUIRED"}</text></>}
          </>}
          {isNetapp && Array.from({ length: 24 }).map((_, bay) => <rect key={bay} x={158 + (bay % 12) * 27} y={y + 34 + Math.floor(bay / 12) * 22} width="21" height="16" rx="2" className="rack-shelf-bay" />)}
          {isEsxi && <><rect x="158" y={y + 32} width="190" height="15" rx="3" fill="url(#rackVent)" /><rect x="362" y={y + 33} width="22" height="12" rx="2" className="rack-port" /><rect x="390" y={y + 33} width="22" height="12" rx="2" className="rack-port" /><rect x="418" y={y + 33} width="22" height="12" rx="2" className="rack-port" /><circle cx="466" cy={y + 39} r="4" className="rack-host-led" /></>}
          {!isCisco && !isIlo && !isNetapp && !isEsxi && <rect x="158" y={y + 32} width="314" height={Math.max(15, height - 44)} rx="4" fill="url(#rackVent)" />}
        </g>;
      })}
    </svg>
  );
}

function RackInspector({ selected, word, bays, access, storage, onEdit, onAdd, onConfigure }: {
  selected?: DeviceInventoryItem;
  word: RackWord;
  bays: RackBay[];
  access: IloAccessSettings | null;
  storage: HpeStorageDiscovery | null;
  onEdit: () => void;
  onAdd: () => void;
  onConfigure: () => void;
}) {
  if (!selected) {
    return <aside className="rack-inspector rack-inspector-empty"><div className="rack-empty-icon"><Plus size={22} /></div><h2>Build your rack</h2><p>No devices are in this kit yet. Add the first piece of equipment without contacting it.</p><button className="rack-action is-primary" onClick={onAdd} type="button">Add first device</button></aside>;
  }
  const isIlo = selected.device_type === "ilo";
  const isEsxi = selected.device_type === "esxi_host";
  const isActiveIloTarget = isIlo && Boolean(
    selected.host?.trim().toLowerCase() &&
    selected.host.trim().toLowerCase() === access?.host?.trim().toLowerCase()
  );
  const iloCredentialsReady = isActiveIloTarget && Boolean(access?.username_configured && access.password_configured);
  const iloFirstContactComplete = isIlo && word === "Ready";
  const controllerName = isActiveIloTarget ? recordText(storage?.controllers?.[0], "model", "name", "id") ?? "Not read yet" : "First contact required";
  const freeBays = bays.filter((bay) => bay.state === "free").length;
  const primaryRoute = devicePage(selected);
  const typeLabel = isIlo ? "iLO" : selected.device_type.replace(/_/g, " ");
  const canConfigureBesideRack = rackConfigAvailable(selected);
  const statusDetail = word === "Ready"
    ? "Current cached evidence confirms access."
    : word === "Problem"
      ? "The latest cached check did not succeed."
      : "No current check proves access yet.";

  return (
    <aside className="rack-inspector" aria-live="polite">
      <div className={`rack-inspector-status is-${rackWordClass(word)}`}><span />{word}</div>
      <h2>{selected.display_name}</h2>
      <p className="rack-inspector-kind">{typeLabel} · {selected.dhcp_enabled ? "DHCP" : "static address"}</p>
      <p className="rack-evidence-note">{statusDetail}</p>
      {isIlo && <div className={`rack-first-contact ${iloFirstContactComplete ? "is-complete" : ""}`}>
        <span>{iloFirstContactComplete ? "First contact complete" : iloCredentialsReady ? "Step 3 of 3" : "Step 2 of 3"}</span>
        <strong>{iloFirstContactComplete ? "This iLO is proven reachable" : iloCredentialsReady ? "Verify this exact iLO address" : "Add the iLO username and password"}</strong>
        <small>{iloFirstContactComplete ? "You can now configure iLO and read local storage." : "The map stays unconfirmed until an explicit read-only check succeeds."}</small>
      </div>}
      {isIlo && bays.length > 0 && <div className="rack-bay-legend"><span className="is-boot">Boot volume</span><span className="is-data">Data volume</span><span className="is-free">Free / ready</span><span className="is-unknown">Unclassified</span></div>}
      <dl className="rack-facts">
        <div><dt>{selected.dhcp_enabled ? "Observed address" : "Address"}</dt><dd>{selected.host ?? (selected.dhcp_enabled ? "Not observed" : "Not set")}</dd></div>
        {isIlo && <div><dt>Credentials</dt><dd>{iloCredentialsReady ? "Saved locally" : "Still required"}</dd></div>}
        {isIlo && <div><dt>Controller</dt><dd>{controllerName}</dd></div>}
        {isIlo && <div><dt>Local storage</dt><dd>{isActiveIloTarget && bays.length ? `${bays.length} bays · ${freeBays} free` : isActiveIloTarget ? "Inventory not read" : "First contact required"}</dd></div>}
        <div><dt>Inventory updated</dt><dd>{new Date(selected.updated_at).toLocaleString()}</dd></div>
        <div><dt>Notes</dt><dd>{selected.notes || "None"}</dd></div>
      </dl>
      <div className="rack-actions">
        {isIlo && isActiveIloTarget
          ? <button className="rack-action is-primary" onClick={onConfigure} type="button">Configure iLO beside rack</button>
          : isIlo && !isActiveIloTarget
          ? <button className="rack-action is-primary" onClick={onEdit} type="button">Continue: set up this iLO</button>
          : canConfigureBesideRack
          ? <button className="rack-action is-primary" onClick={onConfigure} type="button">{`Configure ${rackConfigLabel(selected)} beside rack`}</button>
          : <Link className="rack-action is-primary" to={primaryRoute}>{`Configure ${typeLabel}`}</Link>}
        {isIlo && <Link className="rack-action" to="/storage">Local storage &amp; RAID</Link>}
        {isEsxi && <Link className="rack-action" to="/virtualization">ESXi installation &amp; config</Link>}
        <button className="rack-action" onClick={onEdit} type="button"><Pencil size={14} /> Edit rack details</button>
        <button className="rack-add-another" onClick={onAdd} type="button"><Plus size={14} /> Add another device</button>
      </div>
    </aside>
  );
}

export function SimpleLabPage() {
  const { devices, providers, access, storage, vsan, profiles, health, loaded, loadError, reload } = useSimpleData();
  const visibleIds = devices.map((device) => device.id);
  const visibleKey = visibleIds.join("|");
  const [selectedId, setSelectedId] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editingDevice, setEditingDevice] = useState<DeviceInventoryItem | null>(null);
  const [configuringId, setConfiguringId] = useState("");
  useEffect(() => {
    if (visibleIds.length && !visibleIds.includes(selectedId)) setSelectedId(visibleIds[0]);
    if (!visibleIds.length && selectedId) setSelectedId("");
  }, [selectedId, visibleKey]);
  const bays = rackBays(vsan);
  const selected = devices.find((device) => device.id === selectedId) ?? devices[0];
  const selectedWord: RackWord = selected ? deviceWord(selected, providers, access) : "Not checked";
  const editingIloIsActiveTarget = Boolean(
    editingDevice?.device_type === "ilo" &&
    editingDevice.host?.trim().toLowerCase() &&
    editingDevice.host.trim().toLowerCase() === access?.host?.trim().toLowerCase()
  );
  const profile = profiles?.active_profile;
  const mode = health?.provider_mode ?? health?.operator_runtime_mode ?? "unknown";

  return (
    <main className="rack-light-page" aria-label="Rack elevation">
      <p className="rack-direction"><span /> Rack workspace · cached evidence only</p>
      <div className="rack-light-app">
        <aside className="rack-rail">
          <div className="rack-brand"><span>L</span><div><strong>Lab Builder</strong><small>{profile?.name ?? "Current kit"}</small></div></div>
          <nav aria-label="Rack workspace navigation">
            <p>Console</p>
            <Link className="is-active" to="/simple" aria-current="page"><Layers3 size={17} /> Rack home</Link>
            <Link to="/simple-steps"><ListChecks size={17} /> Runbook</Link>
            <p>Manage</p>
            <Link to="/setup/defaults"><Settings2 size={17} /> Lab defaults</Link>
            <Link to="/lab-profiles#new"><Plus size={17} /> Create or change kit</Link>
          </nav>
          <dl className="rack-rail-facts">
            <div><dt>Subnet</dt><dd>{loadError ? "Unavailable" : profile?.subnet_cidr ?? "Not set"}</dd></div>
            <div><dt>Rack</dt><dd>{loadError ? "Unavailable" : `R1 · ${devices.length} devices`}</dd></div>
            <div><dt>Bays free</dt><dd>{loadError ? "Unavailable" : bays.length ? `${bays.filter((bay) => bay.state === "free").length}/${bays.length}` : "Not read"}</dd></div>
            <div><dt>Mode</dt><dd>{loadError ? "Disconnected" : mode}</dd></div>
          </dl>
        </aside>
        <section className="rack-workspace">
          <header className="rack-workspace-head"><div><h1>Rack elevation</h1><p>Add equipment, select it, then configure it.</p></div><div className="rack-workspace-head-actions"><span className={`rack-runtime-badge ${loadError ? "is-disconnected" : mode.includes("readwrite") ? "is-write" : ""}`}>{loadError ? "Backend disconnected" : mode.includes("readwrite") ? "Live lab · guarded writes" : "Live lab · read-only checks"}</span><button className="rack-head-add" disabled={Boolean(loadError)} onClick={() => setAddOpen(true)} type="button"><Plus size={15} /> Add equipment</button></div></header>
          {!loaded
            ? <div className="rack-loading"><Server size={24} /> Reading cached lab state…</div>
            : loadError
              ? <div className="rack-disconnected" role="alert"><Server size={30} /><h2>Backend disconnected</h2><p>{loadError}</p><button onClick={() => void reload()} type="button">Reconnect</button><small>Adding or changing equipment is paused so a connection failure cannot look like an empty rack or a successful save.</small></div>
              : <div className={`rack-stage ${configuringId ? "is-configuring" : ""}`}><div className="rack-canvas"><RackElevationGraphic devices={devices} providers={providers} access={access} bays={bays} selectedId={selected?.id ?? ""} onSelect={(id) => { setSelectedId(id); setConfiguringId(""); }} /></div><div className="rack-detail">{configuringId && selected?.id === configuringId && selected.device_type === "ilo" ? <RackIloConfigurator activeProfile={profile ?? null} onClose={() => setConfiguringId("")} onReload={reload} /> : configuringId && selected?.id === configuringId && rackConfigAvailable(selected) ? <RackDeviceConfigurator activeProfile={profile ?? null} device={selected} health={health} onClose={() => setConfiguringId("")} onReload={reload} /> : <><RackInspector selected={selected} word={selectedWord} bays={bays} access={access} storage={storage} onEdit={() => selected && setEditingDevice(selected)} onAdd={() => setAddOpen(true)} onConfigure={() => selected && setConfiguringId(selected.id)} /><p className="rack-help">Select a device, then configure its essential settings beside the rack. Green is shown only when a current provider check proves access.</p></>}</div></div>}
        </section>
      </div>
      {addOpen && <DeviceInventoryForm defaultDeviceType="ilo" iloOnboarding onClose={() => setAddOpen(false)} onReload={reload} onSaved={(device) => setSelectedId(device.id)} submitLabel="Add to rack" />}
      {editingDevice && <DeviceInventoryForm device={editingDevice} iloOnboarding initialIloAccessHost={access?.host} initialIloUsername={editingIloIsActiveTarget ? access?.username : null} iloCredentialsConfigured={editingIloIsActiveTarget && Boolean(access?.username_configured && access.password_configured)} onClose={() => setEditingDevice(null)} onReload={reload} onSaved={(device) => setSelectedId(device.id)} submitLabel="Save rack details" />}
    </main>
  );
}

type StepState = "done" | "next" | "waiting";

export function SimpleStepsPage() {
  const { providers, access, storage, loaded } = useSimpleData();

  const iloReady = access?.last_probe_status === "ok" && access?.last_probe_is_current === true;
  const inventoryRead = Boolean(storage?.storage_inventory_available);
  const esxiProvider = providers.find((item) => item.id === "esxi-readonly");
  const esxiReady = esxiProvider?.status === "ready" || esxiProvider?.status === "ok";

  const steps: Array<{ title: string; detail: string; done: boolean; to: string }> = [
    {
      title: "Reach the iLO",
      detail: iloReady ? "Proven reachable with current evidence." : "Save access and run the iLO check.",
      done: Boolean(iloReady),
      to: "/server"
    },
    {
      title: "Read the hardware",
      detail: inventoryRead ? "Drive inventory is loaded from the server." : "Run the iLO inventory read.",
      done: inventoryRead,
      to: "/storage"
    },
    {
      title: "Decide the storage layout",
      detail: "Review the drive plan (and vSAN readiness once available).",
      done: false,
      to: "/storage"
    },
    {
      title: "Reach ESXi",
      detail: esxiReady ? "ESXi answers with current evidence." : "Validate the ESXi target.",
      done: Boolean(esxiReady),
      to: "/virtualization"
    },
    {
      title: "Deploy the VM",
      detail: "Run the guarded VM deploy once everything above is green.",
      done: false,
      to: "/virtualization"
    }
  ];
  const nextIndex = steps.findIndex((step) => !step.done);

  return (
    <main className="simple-page" aria-label="Runbook view (example)">
      <header className="simple-head">
        <h1>Build the lab, in order</h1>
        <p className="simple-sub">
          Return to <Link to="/simple">Rack home</Link>. Each step opens the controls for the device it needs.
        </p>
      </header>
      {!loaded && <p className="simple-loading">Loading…</p>}
      <ol className="simple-steps">
        {steps.map((step, index) => {
          const state: StepState = step.done ? "done" : index === nextIndex ? "next" : "waiting";
          return (
            <li className={`simple-step is-${state}`} key={step.title}>
              <span className="simple-step-number">{index + 1}</span>
              <div className="simple-step-body">
                <strong>{step.title}</strong>
                <span>{step.detail}</span>
              </div>
              <Link className="simple-step-go" to={step.to}>
                {state === "done" ? "Review" : "Go"} →
              </Link>
            </li>
          );
        })}
      </ol>
    </main>
  );
}
