import { useEffect, useState, type KeyboardEvent } from "react";
import { Database, Home, Layers3, ListChecks, Plus, Server, Settings2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "./api";
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
};

function useSimpleData(): SimpleData {
  const [data, setData] = useState<SimpleData>({
    devices: [],
    providers: [],
    access: null,
    storage: null,
    vsan: null,
    profiles: null,
    health: null,
    loaded: false
  });

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [devices, providers, access, storage, vsan, profiles, health] = await Promise.all([
        api.deviceInventory().catch(() => [] as DeviceInventoryItem[]),
        api.providers().catch(() => [] as ProviderStatus[]),
        api.iloAccessSettings().catch(() => null),
        api.hpeStorageDiscovery().catch(() => null),
        api.hpeVsanReadiness().catch(() => null),
        api.labProfiles().catch(() => null),
        api.health().catch(() => null)
      ]);
      if (!cancelled) {
        setData({ devices, providers, access, storage, vsan, profiles, health, loaded: true });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return data;
}

const PROVIDERS_BY_TYPE: Record<string, string[]> = {
  ilo: ["ilo-redfish"],
  esxi_host: ["esxi-readonly"],
  cisco_switch: ["cisco-console", "cisco-ansible"],
  netapp: ["netapp-ontap"]
};

function deviceWord(device: DeviceInventoryItem, providers: ProviderStatus[]): "Ready" | "Problem" | "Not checked" {
  const providerIds = PROVIDERS_BY_TYPE[device.device_type] ?? [];
  const provider = providers.find((item) => providerIds.includes(item.id));
  if (!provider || !provider.is_current || provider.status === "not_checked" || provider.freshness === "not_checked") {
    return "Not checked";
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
  return "/overview";
}

type RackWord = "Ready" | "Problem" | "Partial" | "Not checked";
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

function combinedServerWord(
  ilo: DeviceInventoryItem | undefined,
  esxi: DeviceInventoryItem | undefined,
  providers: ProviderStatus[]
): RackWord {
  const words = [ilo, esxi]
    .filter((device): device is DeviceInventoryItem => Boolean(device))
    .map((device) => deviceWord(device, providers));
  if (!words.length || words.every((word) => word === "Not checked")) return "Not checked";
  if (words.some((word) => word === "Problem")) return "Problem";
  if (words.every((word) => word === "Ready")) return "Ready";
  return "Partial";
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

function RackElevationGraphic({
  cisco,
  serverDevice,
  netapp,
  extras,
  serverWord,
  providers,
  bays,
  selectedId,
  onSelect
}: {
  cisco?: DeviceInventoryItem;
  serverDevice?: DeviceInventoryItem;
  netapp?: DeviceInventoryItem;
  extras: DeviceInventoryItem[];
  serverWord: RackWord;
  providers: ProviderStatus[];
  bays: RackBay[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const switchWord = cisco ? deviceWord(cisco, providers) : "Not checked";
  const netappWord = netapp ? deviceWord(netapp, providers) : "Not checked";
  const keySelect = (event: KeyboardEvent<SVGGElement>, id: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(id);
    }
  };

  return (
    <svg className="rack-light-svg" viewBox="0 0 620 560" role="img" aria-label="Interactive rack elevation">
      <defs>
        <linearGradient id="rackFrame" x1="0" x2="1"><stop offset="0" stopColor="#dce7eb" /><stop offset=".5" stopColor="#f8fbfc" /><stop offset="1" stopColor="#c8d6dc" /></linearGradient>
        <linearGradient id="deviceFace" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#fff" /><stop offset="1" stopColor="#e8f0f3" /></linearGradient>
        <pattern id="rackVent" width="8" height="8" patternUnits="userSpaceOnUse"><circle cx="4" cy="4" r="1.1" fill="#91a5ad" opacity=".45" /></pattern>
        <filter id="rackShadow" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="7" stdDeviation="8" floodColor="#102932" floodOpacity=".14" /></filter>
      </defs>
      <ellipse cx="320" cy="526" rx="190" ry="18" fill="#b7c7cd" opacity=".22" />
      <rect x="85" y="22" width="470" height="500" rx="20" fill="url(#rackFrame)" stroke="#bccbd1" />
      <rect x="104" y="38" width="432" height="464" rx="10" fill="#dbe5e9" stroke="#aebfc6" />
      <rect x="125" y="45" width="390" height="450" rx="6" fill="url(#rackVent)" />
      {[8, 7, 6, 5, 4, 3, 2, 1].map((unit, index) => <text key={unit} x="109" y={82 + index * 52} className="rack-u-label">{String(unit).padStart(2, "0")}</text>)}

      {cisco && <g className={`rack-unit is-${rackWordClass(switchWord)} ${selectedId === cisco.id ? "is-selected" : ""}`} role="button" tabIndex={0} aria-label={`Open ${cisco.display_name}`} onClick={() => onSelect(cisco.id)} onKeyDown={(event) => keySelect(event, cisco.id)}>
        <rect x="143" y="61" width="354" height="58" rx="7" fill="url(#deviceFace)" filter="url(#rackShadow)" />
        <circle cx="157" cy="77" r="5" className="rack-status-dot" /><text x="170" y="80" className="rack-face-title">{cisco.display_name}</text><text x="471" y="80" textAnchor="end" className="rack-face-meta">U8 · 1U</text>
        {Array.from({ length: 24 }).map((_, index) => <rect key={index} x={168 + (index % 12) * 25} y={89 + Math.floor(index / 12) * 12} width="18" height="8" rx="1.5" className={`rack-port ${index < 6 ? "is-live" : ""}`} />)}
      </g>}

      {serverDevice && <g className={`rack-unit is-${rackWordClass(serverWord)} ${selectedId === serverDevice.id ? "is-selected" : ""}`} role="button" tabIndex={0} aria-label={`Open ${serverDevice.display_name}`} onClick={() => onSelect(serverDevice.id)} onKeyDown={(event) => keySelect(event, serverDevice.id)}>
        <rect x="143" y="132" width="354" height="112" rx="7" fill="url(#deviceFace)" filter="url(#rackShadow)" />
        <circle cx="157" cy="150" r="5" className="rack-status-dot" /><text x="170" y="154" className="rack-face-title">{serverDevice.display_name}</text><text x="471" y="154" textAnchor="end" className="rack-face-meta">U5–6 · 2U</text>
        {bays.length ? bays.map((bay, index) => <g key={bay.id}><rect x={158 + (index % 8) * 40} y={169 + Math.floor(index / 8) * 32} width="32" height="25" rx="3" className={`rack-drive is-${bay.state}`} /><text x={174 + (index % 8) * 40} y={185 + Math.floor(index / 8) * 32} textAnchor="middle" className="rack-drive-label">{bay.label}</text></g>) : <><rect x="158" y="169" width="320" height="55" rx="4" fill="url(#rackVent)" /><text x="318" y="201" textAnchor="middle" className="rack-empty-label">READ HARDWARE TO SHOW DRIVE BAYS</text></>}
      </g>}

      {netapp && <g className={`rack-unit is-${rackWordClass(netappWord)} ${selectedId === netapp.id ? "is-selected" : ""}`} role="button" tabIndex={0} aria-label={`Open ${netapp.display_name}`} onClick={() => onSelect(netapp.id)} onKeyDown={(event) => keySelect(event, netapp.id)}>
        <rect x="143" y="257" width="354" height="103" rx="7" fill="url(#deviceFace)" filter="url(#rackShadow)" />
        <circle cx="157" cy="276" r="5" className="rack-status-dot" /><text x="170" y="280" className="rack-face-title">{netapp.display_name}</text><text x="471" y="280" textAnchor="end" className="rack-face-meta">U3–4 · 2U</text>
        {Array.from({ length: 24 }).map((_, index) => <rect key={index} x={158 + (index % 12) * 27} y={296 + Math.floor(index / 12) * 25} width="21" height="19" rx="2" className="rack-shelf-bay" />)}
      </g>}

      {extras.slice(0, 2).map((device, index) => {
        const word = deviceWord(device, providers);
        return <g key={device.id} className={`rack-unit is-${rackWordClass(word)} ${selectedId === device.id ? "is-selected" : ""}`} role="button" tabIndex={0} aria-label={`Open ${device.display_name}`} onClick={() => onSelect(device.id)} onKeyDown={(event) => keySelect(event, device.id)}>
          <rect x="143" y={374 + index * 58} width="354" height="47" rx="7" fill="url(#deviceFace)" filter="url(#rackShadow)" /><circle cx="157" cy={392 + index * 58} r="5" className="rack-status-dot" /><text x="170" y={396 + index * 58} className="rack-face-title">{device.display_name}</text><text x="471" y={396 + index * 58} textAnchor="end" className="rack-face-meta">U{2 - index} · 1U</text>
        </g>;
      })}
    </svg>
  );
}

function RackInspector({ selected, isServer, word, bays, access, storage }: {
  selected?: DeviceInventoryItem;
  isServer: boolean;
  word: RackWord;
  bays: RackBay[];
  access: IloAccessSettings | null;
  storage: HpeStorageDiscovery | null;
}) {
  if (!selected) {
    return <aside className="rack-inspector"><p>No devices are in this kit yet.</p><Link className="rack-action is-primary" to="/lab-profiles#new">Create or change kit</Link></aside>;
  }
  const controllerName = recordText(storage?.controllers?.[0], "model", "name", "id") ?? "Not read yet";
  const freeBays = bays.filter((bay) => bay.state === "free").length;
  const primaryRoute = isServer ? "/server" : devicePage(selected);
  const statusDetail = word === "Ready"
    ? "Current cached evidence confirms access."
    : word === "Problem"
      ? "The latest cached check did not succeed."
      : word === "Partial"
        ? "Only part of this system has current evidence."
        : "No current check proves access yet.";

  return (
    <aside className="rack-inspector" aria-live="polite">
      <div className={`rack-inspector-status is-${rackWordClass(word)}`}><span />{word}</div>
      <h2>{selected.display_name}</h2>
      <p className="rack-inspector-kind">{isServer ? "Server · iLO + ESXi · local storage" : selected.device_type.replace(/_/g, " ")}</p>
      <p className="rack-evidence-note">{statusDetail}</p>
      {isServer && bays.length > 0 && <div className="rack-bay-legend"><span className="is-boot">Boot volume</span><span className="is-data">Data volume</span><span className="is-free">Free / ready</span><span className="is-unknown">Unclassified</span></div>}
      <dl className="rack-facts">
        <div><dt>Address</dt><dd>{isServer ? access?.host ?? selected.host ?? "Not set" : selected.host ?? (selected.dhcp_enabled ? "DHCP" : "Not set")}</dd></div>
        {isServer && <div><dt>Controller</dt><dd>{controllerName}</dd></div>}
        {isServer && <div><dt>Drive bays</dt><dd>{bays.length ? `${bays.length} read · ${freeBays} free` : "Inventory not read"}</dd></div>}
        <div><dt>Evidence</dt><dd>{isServer ? access?.last_probe_time ? new Date(access.last_probe_time).toLocaleString() : "Not checked" : new Date(selected.updated_at).toLocaleDateString()}</dd></div>
      </dl>
      <div className="rack-actions">
        <Link className="rack-action is-primary" to={primaryRoute}>{isServer ? "Open iLO & server" : `Open ${selected.display_name}`}</Link>
        {isServer && <Link className="rack-action" to="/storage">Local storage &amp; RAID</Link>}
        {isServer && <Link className="rack-action" to="/virtualization">ESXi configuration</Link>}
      </div>
    </aside>
  );
}

export function SimpleLabPage() {
  const { devices, providers, access, storage, vsan, profiles, health, loaded } = useSimpleData();
  const cisco = devices.find((device) => device.device_type === "cisco_switch");
  const ilo = devices.find((device) => device.device_type === "ilo");
  const esxi = devices.find((device) => device.device_type === "esxi_host");
  const netapp = devices.find((device) => device.device_type === "netapp");
  const serverDevice = ilo ?? esxi;
  const reserved = new Set([cisco?.id, ilo?.id, esxi?.id, netapp?.id].filter((id): id is string => Boolean(id)));
  const extras = devices.filter((device) => !reserved.has(device.id));
  const visibleIds = [serverDevice?.id, cisco?.id, netapp?.id, ...extras.map((device) => device.id)].filter((id): id is string => Boolean(id));
  const visibleKey = visibleIds.join("|");
  const [selectedId, setSelectedId] = useState("");
  useEffect(() => {
    if (visibleIds.length && !visibleIds.includes(selectedId)) setSelectedId(visibleIds[0]);
  }, [selectedId, visibleKey]);
  const serverWord = combinedServerWord(ilo, esxi, providers);
  const bays = rackBays(vsan);
  const selected = devices.find((device) => device.id === selectedId) ?? serverDevice;
  const isServer = Boolean(serverDevice && selected?.id === serverDevice.id);
  const selectedWord: RackWord = isServer ? serverWord : selected ? deviceWord(selected, providers) : "Not checked";
  const profile = profiles?.active_profile;
  const mode = health?.operator_runtime_mode ?? health?.provider_mode ?? "unknown";

  return (
    <main className="rack-light-page" aria-label="Rack elevation">
      <p className="rack-direction"><span /> Rack workspace · cached evidence only</p>
      <div className="rack-light-app">
        <aside className="rack-rail">
          <div className="rack-brand"><span>L</span><div><strong>Lab Builder</strong><small>{profile?.name ?? "Current kit"}</small></div></div>
          <nav aria-label="Rack workspace navigation">
            <p>Console</p>
            <Link to="/overview"><Home size={17} /> Overview</Link>
            <Link className="is-active" to="/simple" aria-current="page"><Layers3 size={17} /> Rack view</Link>
            <p>Build</p>
            <Link to="/simple-steps"><ListChecks size={17} /> Runbook</Link>
            <Link to="/storage"><Database size={17} /> Storage &amp; vSAN</Link>
            <p>Manage</p>
            <Link to="/setup/defaults"><Settings2 size={17} /> Lab defaults</Link>
            <Link to="/lab-profiles#new"><Plus size={17} /> Create or change kit</Link>
          </nav>
          <dl className="rack-rail-facts">
            <div><dt>Subnet</dt><dd>{profile?.subnet_cidr ?? "Not set"}</dd></div>
            <div><dt>Rack</dt><dd>R1 · {Math.min(8, devices.length + 4)}U used</dd></div>
            <div><dt>Bays free</dt><dd>{bays.length ? `${bays.filter((bay) => bay.state === "free").length}/${bays.length}` : "Not read"}</dd></div>
            <div><dt>Mode</dt><dd>{mode}</dd></div>
          </dl>
        </aside>
        <section className="rack-workspace">
          <header className="rack-workspace-head"><div><h1>Rack elevation</h1><p>The lab as it is—select any unit to inspect it.</p></div><span className={`rack-runtime-badge ${mode.includes("readwrite") ? "is-write" : ""}`}>{mode.includes("readwrite") ? "Live lab · guarded writes" : "Live lab · read-only checks"}</span></header>
          {!loaded
            ? <div className="rack-loading"><Server size={24} /> Reading cached lab state…</div>
            : <div className="rack-stage"><div className="rack-canvas"><RackElevationGraphic cisco={cisco} serverDevice={serverDevice} netapp={netapp} extras={extras} serverWord={serverWord} providers={providers} bays={bays} selectedId={selected?.id ?? ""} onSelect={setSelectedId} /></div><div className="rack-detail"><RackInspector selected={selected} isServer={isServer} word={selectedWord} bays={bays} access={access} storage={storage} /><p className="rack-help">Select a rack unit to see only its current evidence and the next useful workspace. Green is shown only when a current provider check proves access.</p></div></div>}
        </section>
      </div>
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
          Example simplified view. Tiles example at <Link to="/simple">Your lab</Link>; the full map
          stays at <Link to="/overview">Overview</Link>.
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
